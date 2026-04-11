"""Bearer token generation and Argon2id hashing/verification utilities."""

from __future__ import annotations

import base64
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from argon2.low_level import ARGON2_VERSION as _ARGON2_VERSION
from argon2.low_level import Type, hash_secret_raw

from mealplan.shared.errors import ValidationError

TOKEN_PREFIX = "mpu_v1_"
TOKEN_RANDOM_BYTES = 32
ARGON2ID_ALGORITHM = "argon2id"
ARGON2ID_SALT_LENGTH_BYTES = 16
ARGON2_VERSION = int(_ARGON2_VERSION)


@dataclass(frozen=True, slots=True)
class Argon2idParameters:
    """Argon2id hashing parameters."""

    memory_cost_kib: int = 65536
    time_cost: int = 3
    parallelism: int = 1
    hash_len: int = 32


@dataclass(frozen=True, slots=True)
class TokenVerificationResult:
    """Verification status and whether verifier hardening is recommended."""

    is_valid: bool
    needs_rehash: bool


DEFAULT_ARGON2ID_PARAMETERS = Argon2idParameters()


def generate_bearer_token() -> str:
    """Generate a high-entropy bearer token with canonical prefix."""
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_RANDOM_BYTES)}"


def hash_bearer_token(
    *,
    token: str,
    parameters: Argon2idParameters = DEFAULT_ARGON2ID_PARAMETERS,
) -> dict[str, object]:
    """Build a persisted verifier payload for one plaintext bearer token."""
    _validate_token_format(token=token)

    salt = secrets.token_bytes(ARGON2ID_SALT_LENGTH_BYTES)
    token_hash = _hash_token_with_salt(token=token, salt=salt, parameters=parameters)

    return {
        "algorithm": ARGON2ID_ALGORITHM,
        "version": ARGON2_VERSION,
        "params": {
            "memory_cost_kib": parameters.memory_cost_kib,
            "time_cost": parameters.time_cost,
            "parallelism": parameters.parallelism,
            "hash_len": parameters.hash_len,
        },
        "salt": _encode_base64(value=salt),
        "hash": _encode_base64(value=token_hash),
    }


def verify_bearer_token(
    *,
    token: str,
    verifier: Mapping[str, object],
    current_parameters: Argon2idParameters = DEFAULT_ARGON2ID_PARAMETERS,
) -> TokenVerificationResult:
    """Verify token against persisted verifier metadata in constant time."""
    if not token.startswith(TOKEN_PREFIX):
        return TokenVerificationResult(is_valid=False, needs_rehash=False)

    parsed_verifier = _parse_verifier(verifier=verifier)
    candidate_hash = _hash_token_with_salt(
        token=token,
        salt=parsed_verifier.salt,
        parameters=parsed_verifier.parameters,
    )
    is_valid = hmac.compare_digest(candidate_hash, parsed_verifier.hash_value)
    if not is_valid:
        return TokenVerificationResult(is_valid=False, needs_rehash=False)

    needs_rehash = (
        parsed_verifier.version != ARGON2_VERSION
        or _parameters_weaker_than_current(
            stored=parsed_verifier.parameters,
            current=current_parameters,
        )
    )
    return TokenVerificationResult(is_valid=True, needs_rehash=needs_rehash)


@dataclass(frozen=True, slots=True)
class _ParsedVerifier:
    version: int
    parameters: Argon2idParameters
    salt: bytes
    hash_value: bytes


def _parse_verifier(*, verifier: Mapping[str, object]) -> _ParsedVerifier:
    algorithm = verifier.get("algorithm")
    if algorithm != ARGON2ID_ALGORITHM:
        raise ValidationError("token_verifier.algorithm: expected argon2id")

    version = verifier.get("version")
    if not isinstance(version, int):
        raise ValidationError("token_verifier.version: expected int")

    params_payload = verifier.get("params")
    if not isinstance(params_payload, Mapping):
        raise ValidationError("token_verifier.params: expected object")

    parameters = _parse_parameters(params_payload=params_payload)

    salt_value = _decode_base64(
        raw_value=verifier.get("salt"),
        field_name="token_verifier.salt",
    )
    hash_value = _decode_base64(
        raw_value=verifier.get("hash"),
        field_name="token_verifier.hash",
    )
    expected_hash_len = parameters.hash_len
    if len(hash_value) != expected_hash_len:
        raise ValidationError(
            "token_verifier.hash: expected byte length "
            f"{expected_hash_len} but got {len(hash_value)}"
        )

    return _ParsedVerifier(
        version=version,
        parameters=parameters,
        salt=salt_value,
        hash_value=hash_value,
    )


def _parse_parameters(*, params_payload: Mapping[str, object]) -> Argon2idParameters:
    memory_cost_kib = _require_positive_int(
        raw_value=params_payload.get("memory_cost_kib"),
        field_name="token_verifier.params.memory_cost_kib",
    )
    time_cost = _require_positive_int(
        raw_value=params_payload.get("time_cost"),
        field_name="token_verifier.params.time_cost",
    )
    parallelism = _require_positive_int(
        raw_value=params_payload.get("parallelism"),
        field_name="token_verifier.params.parallelism",
    )
    hash_len = _require_positive_int(
        raw_value=params_payload.get("hash_len"),
        field_name="token_verifier.params.hash_len",
    )

    return Argon2idParameters(
        memory_cost_kib=memory_cost_kib,
        time_cost=time_cost,
        parallelism=parallelism,
        hash_len=hash_len,
    )


def _require_positive_int(*, raw_value: object, field_name: str) -> int:
    if not isinstance(raw_value, int):
        raise ValidationError(f"{field_name}: expected int")
    if raw_value <= 0:
        raise ValidationError(f"{field_name}: expected positive int")
    return raw_value


def _hash_token_with_salt(*, token: str, salt: bytes, parameters: Argon2idParameters) -> bytes:
    return hash_secret_raw(
        secret=token.encode("utf-8"),
        salt=salt,
        time_cost=parameters.time_cost,
        memory_cost=parameters.memory_cost_kib,
        parallelism=parameters.parallelism,
        hash_len=parameters.hash_len,
        type=Type.ID,
        version=ARGON2_VERSION,
    )


def _parameters_weaker_than_current(
    *,
    stored: Argon2idParameters,
    current: Argon2idParameters,
) -> bool:
    return (
        stored.memory_cost_kib < current.memory_cost_kib
        or stored.time_cost < current.time_cost
        or stored.parallelism < current.parallelism
        or stored.hash_len < current.hash_len
    )


def _encode_base64(*, value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_base64(*, raw_value: object, field_name: str) -> bytes:
    if not isinstance(raw_value, str):
        raise ValidationError(f"{field_name}: expected base64 string")

    try:
        return base64.b64decode(raw_value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise ValidationError(f"{field_name}: invalid base64 value") from error


def _validate_token_format(*, token: str) -> None:
    if not token.startswith(TOKEN_PREFIX):
        raise ValidationError(f"token: expected prefix {TOKEN_PREFIX}")
    token_value = token[len(TOKEN_PREFIX) :]
    if not token_value:
        raise ValidationError("token: missing token value")
