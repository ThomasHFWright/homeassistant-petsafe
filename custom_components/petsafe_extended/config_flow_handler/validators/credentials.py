"""
Credential validators.

Validation functions for user credentials and authentication.

When this file grows, consider splitting into:
- credentials.py: Basic credential validation
- oauth.py: OAuth-specific validation
- api_auth.py: API authentication methods
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.petsafe_extended.api import PetSafeExtendedApiClient
from homeassistant.helpers.aiohttp_client import async_create_clientsession

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def validate_credentials(hass: HomeAssistant, username: str, password: str) -> None:
    """
    Validate user credentials by testing API connection.

    Args:
        hass: Home Assistant instance.
        username: The username to validate.
        password: The password to validate.

    Raises:
        PetSafeExtendedApiClientAuthenticationError: If credentials are invalid.
        PetSafeExtendedApiClientCommunicationError: If communication fails.
        PetSafeExtendedApiClientError: For other API errors.

    """
    client = PetSafeExtendedApiClient(
        username=username,
        password=password,
        session=async_create_clientsession(hass),
    )
    await client.async_get_data()  # May raise authentication/communication errors


__all__ = [
    "validate_credentials",
]
