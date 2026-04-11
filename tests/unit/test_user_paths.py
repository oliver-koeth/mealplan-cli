"""Unit tests for canonical user email and user-partitioned path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from mealplan.infrastructure.user_paths import (
    canonicalize_user_email,
    resolve_user_partitioned_path,
    user_email_to_filename_prefix,
)
from mealplan.shared.errors import ValidationError


def test_canonicalize_user_email_trims_and_lowercases() -> None:
    assert canonicalize_user_email("  Koeth@ACM.ORG  ") == "koeth@acm.org"


def test_canonicalize_user_email_rejects_empty_values() -> None:
    with pytest.raises(ValidationError, match="email: expected non-empty value"):
        canonicalize_user_email("   ")


def test_user_email_to_filename_prefix_replaces_non_alnum_and_dot_characters() -> None:
    assert user_email_to_filename_prefix("koeth@acm.org") == "koeth_acm.org"
    assert user_email_to_filename_prefix("  A+B@Example-Org.com  ") == "a_b_example_org.com"


def test_resolve_user_partitioned_path_returns_file_inside_storage_directory(
    tmp_path: Path,
) -> None:
    resolved = resolve_user_partitioned_path(
        storage_directory=tmp_path,
        email="koeth@acm.org",
        suffix_filename="calendar.json",
    )

    assert resolved == tmp_path.resolve() / "koeth_acm.org-calendar.json"
    assert resolved.parent == tmp_path.resolve()


@pytest.mark.parametrize("suffix_filename", ["../calendar.json", "nested/calendar.json", ""])
def test_resolve_user_partitioned_path_rejects_invalid_suffix_filename(
    tmp_path: Path,
    suffix_filename: str,
) -> None:
    with pytest.raises(ValidationError, match="filename:"):
        resolve_user_partitioned_path(
            storage_directory=tmp_path,
            email="koeth@acm.org",
            suffix_filename=suffix_filename,
        )
