"""Canonical user-email normalization and filesystem-safe path helpers."""

from __future__ import annotations

import re
from pathlib import Path

from mealplan.shared.errors import ValidationError

_UNSAFE_FILENAME_CHARACTER_PATTERN = re.compile(r"[^a-zA-Z0-9.]")


def canonicalize_user_email(email: str) -> str:
    """Return canonical user identity representation (trim, then lowercase)."""
    canonical = email.strip().lower()
    if not canonical:
        raise ValidationError("email: expected non-empty value")
    return canonical


def user_email_to_filename_prefix(email: str) -> str:
    """Map a canonicalized email to a filesystem-safe deterministic filename prefix."""
    canonical_email = canonicalize_user_email(email)
    return _UNSAFE_FILENAME_CHARACTER_PATTERN.sub("_", canonical_email)


def resolve_user_partitioned_path(
    *,
    storage_directory: Path,
    email: str,
    suffix_filename: str,
) -> Path:
    """Resolve a user-partitioned file path that is guaranteed to remain in storage_directory."""
    if not suffix_filename:
        raise ValidationError("filename: expected non-empty value")
    if Path(suffix_filename).name != suffix_filename:
        raise ValidationError("filename: expected basename without path separators")

    user_prefix = user_email_to_filename_prefix(email)
    filename = f"{user_prefix}-{suffix_filename}"
    root_directory = storage_directory.expanduser().resolve()
    resolved_path = (root_directory / filename).resolve()
    try:
        resolved_path.relative_to(root_directory)
    except ValueError as error:
        raise ValidationError("storage_path: expected path within storage directory") from error
    return resolved_path
