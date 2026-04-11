"""File-backed JSON storage for persisted user identity and token verifier metadata."""

from __future__ import annotations

import json
import logging
import os
import stat
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from typing import Any

from mealplan.shared.errors import ConfigError, ValidationError

USERS_STORE_PATH_ENV = "MEALPLAN_USERS_STORE_PATH"
USERS_STORE_SCHEMA_VERSION = 1
DEFAULT_USERS_STORE_PATH = Path.home() / ".mealplan" / "users.json"

_SECURITY_LOGGER = logging.getLogger("mealplan.security")


@dataclass(frozen=True, slots=True)
class PersistedUser:
    """Persisted user identity and token verifier metadata."""

    email: str
    name: str
    token_verifier: dict[str, Any]

    def as_dict(self) -> dict[str, object]:
        return {
            "email": self.email,
            "name": self.name,
            "token_verifier": dict(self.token_verifier),
        }


class JsonUsersStore:
    """Persist users in users.json with deterministic schema and ordering."""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path

    def list_users(self) -> list[PersistedUser]:
        """Return all persisted users sorted by email."""
        payload = self._load_store()
        users_payload = payload.get("users", [])
        if not isinstance(users_payload, list):
            raise ConfigError("users.store: users must be an array")

        users: list[PersistedUser] = []
        for index, raw_user in enumerate(users_payload):
            users.append(_parse_persisted_user(raw_user=raw_user, index=index))
        return sorted(users, key=lambda user: user.email)

    def get_by_email(self, *, email: str) -> PersistedUser | None:
        """Return one persisted user by exact email or None."""
        for user in self.list_users():
            if user.email == email:
                return user
        return None

    def upsert_user(
        self,
        *,
        email: str,
        name: str,
        token_verifier: Mapping[str, object],
    ) -> PersistedUser:
        """Create or replace one user by email."""
        normalized_email = email.strip()
        if not normalized_email:
            raise ValidationError("email: value is required")
        if not name.strip():
            raise ValidationError("name: value is required")
        if _contains_plaintext_token(raw_value=token_verifier):
            raise ValidationError("token: plaintext bearer token persistence is forbidden")

        persisted = PersistedUser(
            email=normalized_email,
            name=name,
            token_verifier=dict(token_verifier),
        )

        with self._exclusive_lock():
            existing = {user.email: user for user in self._list_users_for_update()}
            existing[normalized_email] = persisted
            self._write_users(users_by_email=existing)
        return persisted

    def create_user(
        self,
        *,
        email: str,
        name: str,
        token_verifier: Mapping[str, object],
    ) -> PersistedUser | None:
        """Create one user by email, returning None if email already exists."""
        normalized_email = email.strip()
        if not normalized_email:
            raise ValidationError("email: value is required")
        if not name.strip():
            raise ValidationError("name: value is required")
        if _contains_plaintext_token(raw_value=token_verifier):
            raise ValidationError("token: plaintext bearer token persistence is forbidden")

        persisted = PersistedUser(
            email=normalized_email,
            name=name,
            token_verifier=dict(token_verifier),
        )
        with self._exclusive_lock():
            existing = {user.email: user for user in self._list_users_for_update()}
            if normalized_email in existing:
                return None
            existing[normalized_email] = persisted
            self._write_users(users_by_email=existing)
        return persisted

    def _load_store(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            default_payload = {
                "schema_version": USERS_STORE_SCHEMA_VERSION,
                "users": [],
            }
            self._write_store(default_payload)
            return default_payload

        self._warn_if_permissions_weaker_than_target()

        try:
            parsed = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"users.store: unable to read storage file: {error}") from error

        if not isinstance(parsed, dict):
            raise ConfigError("users.store: storage root must be a JSON object")

        schema_version = parsed.get("schema_version")
        if schema_version != USERS_STORE_SCHEMA_VERSION:
            raise ConfigError(
                "users.store: unsupported schema_version "
                f"{schema_version!r}; expected {USERS_STORE_SCHEMA_VERSION}"
            )

        users_value = parsed.get("users")
        if users_value is None:
            raise ConfigError("users.store: missing users")
        if not isinstance(users_value, list):
            raise ConfigError("users.store: users must be an array")

        return {"schema_version": schema_version, "users": users_value}

    def _write_store(self, payload: Mapping[str, object]) -> None:
        with self._exclusive_lock():
            self._write_store_locked(payload)

    def _list_users_for_update(self) -> list[PersistedUser]:
        if not self._storage_path.exists():
            return []
        payload = self._load_store()
        users_payload = payload.get("users", [])
        if not isinstance(users_payload, list):
            raise ConfigError("users.store: users must be an array")
        return [
            _parse_persisted_user(raw_user=user, index=index)
            for index, user in enumerate(users_payload)
        ]

    def _write_users(self, *, users_by_email: Mapping[str, PersistedUser]) -> None:
        ordered_users = [users_by_email[key] for key in sorted(users_by_email)]
        payload = {
            "schema_version": USERS_STORE_SCHEMA_VERSION,
            "users": [user.as_dict() for user in ordered_users],
        }
        self._write_store_locked(payload)

    def _write_store_locked(self, payload: Mapping[str, object]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._storage_path.parent / f".{self._storage_path.name}.{os.getpid()}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as temp_file:
                temp_file.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self._storage_path)
            self._fsync_parent_directory()
        except OSError as error:
            raise ConfigError(f"users.store: unable to write storage file: {error}") from error
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

        self._warn_if_permissions_weaker_than_target()
        try:
            os.chmod(self._storage_path, 0o600)
        except OSError:
            _SECURITY_LOGGER.warning(
                "users.store: unable to set file mode 0600 for %s",
                self._storage_path,
            )

    def _fsync_parent_directory(self) -> None:
        try:
            directory_fd = os.open(self._storage_path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)

    @contextmanager
    def _exclusive_lock(self) -> Any:
        lock_path = self._storage_path.parent / f".{self._storage_path.name}.lock"
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                flock(lock_file.fileno(), LOCK_EX)
            except OSError as error:
                raise ConfigError(f"users.store: unable to lock storage file: {error}") from error
            try:
                yield
            finally:
                with suppress(OSError):
                    flock(lock_file.fileno(), LOCK_UN)

    def _warn_if_permissions_weaker_than_target(self) -> None:
        try:
            mode = stat.S_IMODE(self._storage_path.stat().st_mode)
        except OSError:
            return

        if mode & 0o077:
            _SECURITY_LOGGER.warning(
                "users.store: weaker-than-0600 permissions detected for %s (mode=%04o)",
                self._storage_path,
                mode,
            )


def resolve_users_store_path(*, env: Mapping[str, str] | None = None) -> Path:
    """Resolve users store path from canonical env var with default fallback."""
    env_values = os.environ if env is None else env
    configured = env_values.get(USERS_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_USERS_STORE_PATH


def _parse_persisted_user(*, raw_user: object, index: int) -> PersistedUser:
    if not isinstance(raw_user, dict):
        raise ConfigError(f"users.store: users[{index}] must be an object")

    email = raw_user.get("email")
    if not isinstance(email, str) or not email:
        raise ConfigError(f"users.store: users[{index}].email must be a non-empty string")

    name = raw_user.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"users.store: users[{index}].name must be a non-empty string")

    token_verifier = raw_user.get("token_verifier")
    if not isinstance(token_verifier, dict):
        raise ConfigError(f"users.store: users[{index}].token_verifier must be an object")

    return PersistedUser(email=email, name=name, token_verifier=dict(token_verifier))


def _contains_plaintext_token(*, raw_value: object) -> bool:
    if isinstance(raw_value, dict):
        for key, value in raw_value.items():
            if isinstance(key, str) and key.strip().lower() == "token":
                return True
            if _contains_plaintext_token(raw_value=value):
                return True
    elif isinstance(raw_value, list):
        return any(_contains_plaintext_token(raw_value=value) for value in raw_value)
    return False
