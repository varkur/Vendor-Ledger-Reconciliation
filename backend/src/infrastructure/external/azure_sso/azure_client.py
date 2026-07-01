"""
Azure AD / Microsoft SSO integration client.

Handles:
- Building the OAuth2 authorization URL (login.microsoftonline.com/.../authorize)
- Exchanging an authorization code for tokens at the /token endpoint
- Fetching user profile from Microsoft Graph (/v1.0/me)

Uses httpx for async HTTP calls. No business logic — only Microsoft API interaction.
"""

from __future__ import annotations

import logging
import urllib.parse

from src.config.settings import settings

logger = logging.getLogger(__name__)


class AzureSsoError(Exception):
    """Base class for Azure SSO adapter errors."""


class AzureTokenMissingError(AzureSsoError):
    """Token endpoint responded without an access_token."""


class AzureAuthError(AzureSsoError):
    """Microsoft returned an HTTP error status during the auth flow."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AzureUnavailableError(AzureSsoError):
    """Microsoft identity service could not be reached."""


class AzureSsoClient:
    """Client for Azure AD / Microsoft OAuth2 SSO."""

    def __init__(self) -> None:
        self._client_id = settings.AZURE_CLIENT_ID
        self._client_secret = settings.AZURE_CLIENT_SECRET
        self._tenant_id = settings.AZURE_TENANT_ID
        self._redirect_uri = settings.AZURE_REDIRECT_URI or "http://localhost:3000/auth/microsoft/callback"

    @property
    def is_configured(self) -> bool:
        """True when client_id and tenant_id are present."""
        return bool(self._client_id and self._tenant_id)

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri

    def build_authorization_url(self) -> tuple[str, str]:
        """
        Build the Azure AD OAuth2 authorization URL.

        Returns:
            Tuple of (auth_url, redirect_uri)
        """
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "prompt": "select_account",
        }
        base_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/authorize"
        auth_url = base_url + "?" + urllib.parse.urlencode(params)
        return auth_url, self._redirect_uri

    async def exchange_code_for_profile(self, code: str) -> dict:
        """
        Exchange an authorization code for tokens and return the Microsoft Graph profile.

        Flow:
        1. POST to Azure /token endpoint with the authorization code
        2. Extract access_token from the response
        3. GET Microsoft Graph /v1.0/me with the access token
        4. Return the user profile dict

        Raises:
            AzureTokenMissingError: Token response lacked an access_token.
            AzureAuthError: Microsoft returned an HTTP error status.
            AzureUnavailableError: Microsoft was unreachable.
        """
        import httpx

        token_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as http_client:
                # Step 1: Exchange code for tokens
                token_resp = await http_client.post(token_url, data=token_data)
                token_resp.raise_for_status()
                token_json = token_resp.json()

                ms_access_token = token_json.get("access_token")
                if not ms_access_token:
                    raise AzureTokenMissingError()

                # Step 2: Fetch user profile from Microsoft Graph
                graph_resp = await http_client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {ms_access_token}"},
                )
                graph_resp.raise_for_status()
                return graph_resp.json()

        except AzureTokenMissingError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = f"Microsoft authentication failed: {exc.response.text}"
            logger.error(detail)
            raise AzureAuthError(detail) from exc
        except httpx.RequestError as exc:
            logger.error(f"Microsoft unreachable: {exc}")
            raise AzureUnavailableError() from exc
