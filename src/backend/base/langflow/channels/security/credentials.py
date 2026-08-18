"""Encryption helpers for channel provider credentials."""

from __future__ import annotations

import json
from collections.abc import Mapping

from langflow.services.auth import utils as auth_utils


class ChannelCredentialError(ValueError):
    """Raised when stored channel credentials cannot be decoded safely."""


def encrypt_credentials(credentials: Mapping[str, str]) -> str:
    normalized: dict[str, str] = {}
    for key, value in credentials.items():
        if not isinstance(key, str) or not key.strip():
            msg = "Channel credential keys must be non-empty strings"
            raise ChannelCredentialError(msg)
        if not isinstance(value, str):
            msg = f"Channel credential '{key}' must be a string"
            raise ChannelCredentialError(msg)
        normalized[key.strip()] = value

    serialized = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    return auth_utils.encrypt_api_key(serialized)


def decrypt_credentials(encrypted_value: str) -> dict[str, str]:
    try:
        serialized = auth_utils.decrypt_api_key(encrypted_value)
        decoded = json.loads(serialized)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ChannelCredentialError("Stored channel credentials could not be decrypted") from exc

    if not isinstance(decoded, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in decoded.items()
    ):
        raise ChannelCredentialError("Stored channel credentials have an invalid shape")
    return decoded


def list_credential_keys(encrypted_value: str) -> list[str]:
    return sorted(decrypt_credentials(encrypted_value))
