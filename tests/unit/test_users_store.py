"""Unit tests for file-backed users persistence."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

import pytest

from mealplan.infrastructure import (
    DEFAULT_USERS_STORE_PATH,
    USERS_STORE_PATH_ENV,
    JsonUsersStore,
    resolve_users_store_path,
)
from mealplan.shared.errors import ConfigError, ValidationError


def _store_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "users.json"


def test_upsert_persists_deterministic_schema_and_sorted_users(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonUsersStore(storage_path)

    store.upsert_user(
        email="zoe@example.com",
        name="Zoe",
        token_verifier={"algorithm": "argon2id", "hash": "hash-z"},
    )
    store.upsert_user(
        email="amy@example.com",
        name="Amy",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )

    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert [user["email"] for user in persisted["users"]] == [
        "amy@example.com",
        "zoe@example.com",
    ]
    assert persisted["users"][0]["token_verifier"] == {
        "algorithm": "argon2id",
        "hash": "hash-a",
    }


def test_list_users_creates_missing_store_with_defaults(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonUsersStore(storage_path)

    users = store.list_users()

    assert users == []
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert persisted == {"schema_version": 1, "users": []}


def test_get_by_email_returns_match_or_none(tmp_path: Path) -> None:
    store = JsonUsersStore(_store_path(tmp_path))
    store.upsert_user(
        email="alice@example.com",
        name="Alice",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )

    found = store.get_by_email(email="alice@example.com")
    missing = store.get_by_email(email="bob@example.com")

    assert found is not None
    assert found.email == "alice@example.com"
    assert missing is None


def test_create_user_returns_none_for_duplicate_email(tmp_path: Path) -> None:
    store = JsonUsersStore(_store_path(tmp_path))
    created = store.create_user(
        email="alice@example.com",
        name="Alice",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )
    duplicate = store.create_user(
        email="alice@example.com",
        name="Alice Two",
        token_verifier={"algorithm": "argon2id", "hash": "hash-b"},
    )

    assert created is not None
    assert duplicate is None
    users = store.list_users()
    assert len(users) == 1
    assert users[0].name == "Alice"


def test_rejects_plaintext_token_persistence(tmp_path: Path) -> None:
    store = JsonUsersStore(_store_path(tmp_path))

    with pytest.raises(
        ValidationError,
        match="token: plaintext bearer token persistence is forbidden",
    ):
        store.upsert_user(
            email="alice@example.com",
            name="Alice",
            token_verifier={"token": "plaintext-secret"},
        )


def test_warns_when_weaker_than_0600_permissions_detected(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonUsersStore(storage_path)
    store.list_users()
    storage_path.chmod(0o644)

    caplog.set_level(logging.WARNING, logger="mealplan.security")
    store.list_users()

    assert "weaker-than-0600 permissions detected" in caplog.text


def test_write_targets_0600_mode(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonUsersStore(storage_path)

    store.upsert_user(
        email="alice@example.com",
        name="Alice",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )

    mode = stat.S_IMODE(storage_path.stat().st_mode)
    assert mode == 0o600


def test_upsert_user_uses_atomic_replace_and_fsync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_path = _store_path(tmp_path)
    store = JsonUsersStore(storage_path)
    replace_calls: list[tuple[Path, Path]] = []
    fsync_calls: list[int] = []
    original_replace = os.replace

    def _tracked_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    def _tracked_fsync(fd: int) -> None:
        fsync_calls.append(fd)

    monkeypatch.setattr("mealplan.infrastructure.users_store.os.replace", _tracked_replace)
    monkeypatch.setattr("mealplan.infrastructure.users_store.os.fsync", _tracked_fsync)

    store.upsert_user(
        email="alice@example.com",
        name="Alice",
        token_verifier={"algorithm": "argon2id", "hash": "hash-a"},
    )

    assert replace_calls
    assert replace_calls[0][1] == storage_path
    assert fsync_calls
    assert list(storage_path.parent.glob(f".{storage_path.name}.*.tmp")) == []


def test_resolve_users_store_path_uses_env_override() -> None:
    resolved = resolve_users_store_path(env={USERS_STORE_PATH_ENV: "~/custom-users.json"})

    assert resolved == Path("~/custom-users.json").expanduser()


def test_resolve_users_store_path_defaults_when_env_missing() -> None:
    assert resolve_users_store_path(env={}) == DEFAULT_USERS_STORE_PATH


def test_invalid_store_shape_raises_config_error(tmp_path: Path) -> None:
    storage_path = _store_path(tmp_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_text('{"schema_version": 1, "users": {}}\n', encoding="utf-8")
    store = JsonUsersStore(storage_path)

    with pytest.raises(ConfigError, match="users.store: users must be an array"):
        store.list_users()
