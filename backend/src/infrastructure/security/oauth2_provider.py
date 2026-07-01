"""
OAuth2/OIDC provider integration (Azure AD).

This module re-exports the Azure SSO client for convenience.
The actual implementation lives in src/infrastructure/external/azure_sso/.
"""

from src.infrastructure.external.azure_sso import (
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
