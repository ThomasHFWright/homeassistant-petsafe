"""
API package for petsafe_extended.

Architecture:
    Three-layer data flow: Entities → Coordinator → API Client.
    Only the coordinator should call the API client. Entities must never
    import or call the API client directly.

Exception hierarchy:
    PetSafeExtendedApiClientError (base)
    ├── PetSafeExtendedApiClientCommunicationError (network/timeout)
    └── PetSafeExtendedApiClientAuthenticationError (401/403)

Coordinator exception mapping:
    ApiClientAuthenticationError → ConfigEntryAuthFailed (triggers reauth)
    ApiClientCommunicationError → UpdateFailed (auto-retry)
    ApiClientError             → UpdateFailed (auto-retry)
"""

from .client import (
    PetSafeExtendedApiClient,
    PetSafeExtendedApiClientAuthenticationError,
    PetSafeExtendedApiClientCommunicationError,
    PetSafeExtendedApiClientError,
)

__all__ = [
    "PetSafeExtendedApiClient",
    "PetSafeExtendedApiClientAuthenticationError",
    "PetSafeExtendedApiClientCommunicationError",
    "PetSafeExtendedApiClientError",
]
