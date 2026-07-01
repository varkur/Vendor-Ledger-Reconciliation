"""Azure AD / Microsoft SSO integration adapter."""

from src.infrastructure.external.azure_sso.azure_client import (
    AzureAuthError,
    AzureSsoClient,
    AzureSsoError,
    AzureTokenMissingError,
    AzureUnavailableError,
)

__all__ = [
    "AzureAuthError",
    "AzureSsoClient",
    "AzureSsoError",
    "AzureTokenMissingError",
    "AzureUnavailableError",
]
