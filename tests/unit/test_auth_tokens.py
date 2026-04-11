"""Unit tests for bearer token utility helpers."""

from __future__ import annotations

import hmac

import pytest

from mealplan.infrastructure.auth_tokens import (
    ARGON2_VERSION,
    ARGON2ID_ALGORITHM,
    ARGON2ID_SALT_LENGTH_BYTES,
    DEFAULT_ARGON2ID_PARAMETERS,
    TOKEN_PREFIX,
    Argon2idParameters,
    generate_bearer_token,
    hash_bearer_token,
    verify_bearer_token,
)
from mealplan.shared.errors import ValidationError


def test_generate_bearer_token_uses_canonical_prefix() -> None:
    generated = generate_bearer_token()

    assert generated.startswith(TOKEN_PREFIX)
    assert len(generated) > len(TOKEN_PREFIX)


def test_hash_bearer_token_persists_metadata_and_hash_payload() -> None:
    token = generate_bearer_token()

    verifier = hash_bearer_token(token=token)

    assert verifier["algorithm"] == ARGON2ID_ALGORITHM
    assert verifier["version"] == ARGON2_VERSION
    assert verifier["params"] == {
        "memory_cost_kib": DEFAULT_ARGON2ID_PARAMETERS.memory_cost_kib,
        "time_cost": DEFAULT_ARGON2ID_PARAMETERS.time_cost,
        "parallelism": DEFAULT_ARGON2ID_PARAMETERS.parallelism,
        "hash_len": DEFAULT_ARGON2ID_PARAMETERS.hash_len,
    }
    assert isinstance(verifier["salt"], str)
    assert isinstance(verifier["hash"], str)


def test_hash_bearer_token_rejects_non_canonical_format() -> None:
    with pytest.raises(ValidationError, match=f"token: expected prefix {TOKEN_PREFIX}"):
        hash_bearer_token(token="not-prefixed")


def test_verify_bearer_token_returns_valid_without_rehash_when_defaults_used() -> None:
    token = generate_bearer_token()
    verifier = hash_bearer_token(token=token)

    result = verify_bearer_token(token=token, verifier=verifier)

    assert result.is_valid is True
    assert result.needs_rehash is False


def test_verify_bearer_token_returns_invalid_for_wrong_token() -> None:
    token = generate_bearer_token()
    verifier = hash_bearer_token(token=token)

    result = verify_bearer_token(token=f"{TOKEN_PREFIX}wrong", verifier=verifier)

    assert result.is_valid is False
    assert result.needs_rehash is False


def test_verify_bearer_token_recommends_rehash_for_weaker_params() -> None:
    weak_parameters = Argon2idParameters(
        memory_cost_kib=4096,
        time_cost=2,
        parallelism=1,
        hash_len=16,
    )
    token = generate_bearer_token()
    verifier = hash_bearer_token(token=token, parameters=weak_parameters)

    result = verify_bearer_token(token=token, verifier=verifier)

    assert result.is_valid is True
    assert result.needs_rehash is True


def test_verify_bearer_token_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    token = generate_bearer_token()
    verifier = hash_bearer_token(token=token)
    compare_called = False

    original_compare_digest = hmac.compare_digest

    def _tracking_compare_digest(left: bytes, right: bytes) -> bool:
        nonlocal compare_called
        compare_called = True
        return original_compare_digest(left, right)

    monkeypatch.setattr(
        "mealplan.infrastructure.auth_tokens.hmac.compare_digest",
        _tracking_compare_digest,
    )

    result = verify_bearer_token(token=token, verifier=verifier)

    assert result.is_valid is True
    assert compare_called is True


def test_verify_bearer_token_rejects_invalid_verifier_payload() -> None:
    token = generate_bearer_token()
    verifier = hash_bearer_token(token=token)
    verifier["hash"] = "not-base64***"

    with pytest.raises(ValidationError, match="token_verifier.hash: invalid base64 value"):
        verify_bearer_token(token=token, verifier=verifier)


def test_hash_bearer_token_uses_random_salt() -> None:
    token = generate_bearer_token()

    first = hash_bearer_token(token=token)
    second = hash_bearer_token(token=token)

    assert first["salt"] != second["salt"]
    assert first["hash"] != second["hash"]
    assert len(first["salt"]) >= ARGON2ID_SALT_LENGTH_BYTES
