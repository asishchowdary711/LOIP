"""Shared async HTTP client base for all integration stubs."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2


class IntegrationError(Exception):
    """Raised when an external API call fails after retries."""

    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service}: {message}")


class ConsentRequiredError(Exception):
    """Raised when a required consent record is missing."""

    def __init__(self, service: str, purpose: str):
        self.service = service
        self.purpose = purpose
        super().__init__(f"{service} requires consent for purpose={purpose}")


class BaseClient:
    """Async HTTP client with retry, timeout, and mock-mode support.

    Set environment variable <SERVICE>_MOCK=1 to return mock responses
    instead of hitting real APIs. Useful for development and testing.
    """

    service_name: str = "base"
    env_prefix: str = "BASE"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.api_url = api_url or os.getenv(f"{self.env_prefix}_API_URL", "")
        self.api_key = api_key or os.getenv(f"{self.env_prefix}_API_KEY", "")
        self.timeout = timeout
        self.retries = retries
        self._mock = os.getenv(f"{self.env_prefix}_MOCK", "0") == "1"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._default_headers(),
            )
        return self._client

    def _default_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        url = f"{self.api_url.rstrip('/')}/{path.lstrip('/')}" if path else self.api_url

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = await client.request(
                    method, url, json=json_body, params=params,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    "%s: timeout on attempt %d/%d", self.service_name, attempt, self.retries,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504):
                    last_error = e
                    logger.warning(
                        "%s: HTTP %d on attempt %d/%d",
                        self.service_name, e.response.status_code, attempt, self.retries,
                    )
                else:
                    raise IntegrationError(
                        self.service_name,
                        f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                        e.response.status_code,
                    ) from e

        raise IntegrationError(
            self.service_name,
            f"Failed after {self.retries} attempts: {last_error}",
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
