"""
Employee AD (Darwin) integration client.

Proxies requests to the Emcure Darwin AD integrator service at:
  https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1

OpenAPI endpoints:
  - GET  /getemployees          — Get all employees
  - POST /validatecredentials   — Validate employee AD credentials (multipart/form-data)
  - POST /getselectedemployees  — Fetch employee details by IDs (multipart/form-data)
  - GET  /getHierarchyData      — Get hierarchy data

Uses httpx for async HTTP calls. No business logic — only Darwin API interaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


class EmployeeADError(Exception):
    """Base class for Employee AD adapter errors."""

    def __init__(self, detail: str = "Employee AD service error") -> None:
        super().__init__(detail)
        self.detail = detail


class EmployeeADAuthError(EmployeeADError):
    """Darwin rejected the request with an HTTP 401/403 status."""

    def __init__(self, detail: str = "Employee AD authentication failed") -> None:
        super().__init__(detail)


class EmployeeADUnavailableError(EmployeeADError):
    """Darwin service could not be reached."""

    def __init__(self, detail: str = "Employee AD service unavailable") -> None:
        super().__init__(detail)


@dataclass(frozen=True)
class EmployeeValidationResult:
    """Parsed result of a Darwin credential validation call."""

    is_success: bool
    is_valid_user: bool
    raw_response: dict = field(default_factory=dict)


class EmployeeADClient:
    """Client for the Darwin / Active Directory Employee services."""

    def __init__(self) -> None:
        # Ensure no trailing slash for clean URL joining
        self._base_url = settings.EMPLOYEE_AD_BASE_URL.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_configured(self) -> bool:
        """True when the base URL is set."""
        return bool(self._base_url)

    def _handle_http_error(self, exc: httpx.HTTPStatusError, context: str) -> None:
        """Raise appropriate exception based on HTTP status code."""
        detail = f"{context}: {exc.response.status_code} - {exc.response.text[:200]}"
        logger.error(detail)
        if exc.response.status_code in (401, 403):
            raise EmployeeADAuthError(detail) from exc
        raise EmployeeADError(detail) from exc

    async def health_check(self) -> dict:
        """
        Check if the Darwin AD service is reachable by hitting the base URL.

        Returns:
            Dict with status and response details.
        """
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                response = await client.get(
                    self._base_url,
                    headers={"accept": "application/json"},
                )
                return {
                    "status": "reachable",
                    "status_code": response.status_code,
                    "url": self._base_url,
                }
        except httpx.RequestError as exc:
            logger.error("Employee AD service unreachable: %s", exc)
            return {
                "status": "unreachable",
                "error": str(exc),
                "url": self._base_url,
            }

    async def validate_credentials(
        self, employee_id: str, password: str
    ) -> EmployeeValidationResult:
        """
        POST multipart/form-data to /validatecredentials.

        Raises:
            EmployeeADAuthError: Darwin responded with 401/403.
            EmployeeADError: Darwin responded with other HTTP error.
            EmployeeADUnavailableError: Darwin was unreachable.
        """
        url = f"{self._base_url}/validatecredentials"
        logger.info("Calling Darwin validatecredentials for employee: %s", employee_id)

        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                response = await client.post(
                    url,
                    files={
                        "EmployeeId": (None, employee_id),
                        "Password": (None, password),
                    },
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "Darwin validatecredentials response for %s: success=%s",
                    employee_id,
                    data.get("IsSuccess"),
                )
                return EmployeeValidationResult(
                    is_success=bool(data.get("IsSuccess")),
                    is_valid_user=bool(data.get("IsValidUser")),
                    raw_response=data,
                )
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "Darwin validatecredentials error")
            raise  # unreachable but satisfies type checker
        except httpx.RequestError as exc:
            logger.error("Darwin API connection error: %s", exc)
            raise EmployeeADUnavailableError(str(exc)) from exc

    async def get_selected_employees(self, employee_ids: list[str]) -> dict:
        """
        POST multipart/form-data to /getselectedemployees.

        Returns:
            Raw JSON response dict from Darwin.

        Raises:
            EmployeeADAuthError: Darwin responded with 401/403.
            EmployeeADError: Darwin responded with other HTTP error.
            EmployeeADUnavailableError: Darwin was unreachable.
        """
        url = f"{self._base_url}/getselectedemployees"
        ids_payload = ",".join(employee_ids)
        logger.info("Calling Darwin getselectedemployees for IDs: %s", ids_payload)

        try:
            async with httpx.AsyncClient(verify=False, timeout=120) as client:
                response = await client.post(
                    url,
                    files={"EmployeeIDs": (None, ids_payload)},
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "Darwin getselectedemployees error")
            raise
        except httpx.RequestError as exc:
            logger.error("Darwin API connection error: %s", exc)
            raise EmployeeADUnavailableError(str(exc)) from exc

    async def get_employees(self) -> dict:
        """
        GET /getemployees — Fetch all employees.

        Returns:
            Raw JSON response dict from Darwin.

        Raises:
            EmployeeADAuthError: Darwin responded with 401/403.
            EmployeeADError: Darwin responded with other HTTP error.
            EmployeeADUnavailableError: Darwin was unreachable.
        """
        url = f"{self._base_url}/getemployees"
        logger.info("Calling Darwin getemployees")

        try:
            async with httpx.AsyncClient(verify=False, timeout=120) as client:
                response = await client.get(
                    url,
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "Darwin getemployees error")
            raise
        except httpx.RequestError as exc:
            logger.error("Darwin API connection error: %s", exc)
            raise EmployeeADUnavailableError(str(exc)) from exc

    async def get_hierarchy_data(self) -> dict:
        """
        GET /getHierarchyData — Fetch hierarchy data.

        Returns:
            Raw JSON response dict from Darwin.

        Raises:
            EmployeeADAuthError: Darwin responded with 401/403.
            EmployeeADError: Darwin responded with other HTTP error.
            EmployeeADUnavailableError: Darwin was unreachable.
        """
        url = f"{self._base_url}/getHierarchyData"
        logger.info("Calling Darwin getHierarchyData")

        try:
            async with httpx.AsyncClient(verify=False, timeout=120) as client:
                response = await client.get(
                    url,
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc, "Darwin getHierarchyData error")
            raise
        except httpx.RequestError as exc:
            logger.error("Darwin API connection error: %s", exc)
            raise EmployeeADUnavailableError(str(exc)) from exc
