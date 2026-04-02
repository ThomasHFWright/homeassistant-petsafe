"""Authentication helpers for PetSafe Extended."""

from __future__ import annotations

from base64 import urlsafe_b64decode
import hashlib
import json
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_TOKEN


def _decode_jwt_payload(token: str | None) -> dict[str, Any] | None:
    """Return decoded JWT payload data without verifying the signature."""
    if not token:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)

    try:
        decoded = urlsafe_b64decode(f"{payload}{padding}")
        data = json.loads(decoded)
    except ValueError, TypeError, json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def build_account_unique_id(email: str, id_token: str | None) -> str:
    """Build a stable config-entry unique ID for a PetSafe account."""
    claims = _decode_jwt_payload(id_token)
    subject = claims.get("sub") if claims else None
    if isinstance(subject, str) and subject:
        return f"account_{subject}"

    normalized_email = email.strip().lower()
    email_hash = hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()
    return f"email_{email_hash}"


def get_entry_unique_id(entry: ConfigEntry) -> str | None:
    """Build a stable unique ID from stored config-entry auth data."""
    email = entry.data.get(CONF_EMAIL)
    if not isinstance(email, str) or not email:
        return None

    token = entry.data.get(CONF_TOKEN)
    id_token = token if isinstance(token, str) else None
    return build_account_unique_id(email, id_token)
