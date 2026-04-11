"""UK Companies House API client."""

from __future__ import annotations

import httpx
from typing import Any

BASE_URL = "https://api.company-information.service.gov.uk"


class CompaniesHouseClient:
    """Async client for the UK Companies House API.

    Auth: HTTP Basic with api_key as username, empty password.
    Rate limit: 600 requests per 5-minute window.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        kwargs: dict[str, Any] = {
            "base_url": BASE_URL,
            "timeout": timeout,
            "headers": {"User-Agent": "sift/0.4.0"},
        }
        if api_key:
            kwargs["auth"] = (api_key, "")
        self._client = httpx.AsyncClient(**kwargs)
        self._has_key = api_key is not None

    async def close(self):
        await self._client.aclose()

    async def search_company(
        self, query: str, items_per_page: int = 10, start_index: int = 0,
    ) -> dict[str, Any]:
        """Search for UK companies by name."""
        resp = await self._client.get(
            "/search/companies",
            params={
                "q": query,
                "items_per_page": items_per_page,
                "start_index": start_index,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def search_officer(
        self, query: str, items_per_page: int = 10, start_index: int = 0,
    ) -> dict[str, Any]:
        """Search for company officers/directors by name."""
        resp = await self._client.get(
            "/search/officers",
            params={
                "q": query,
                "items_per_page": items_per_page,
                "start_index": start_index,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_company(self, company_number: str) -> dict[str, Any]:
        """Get full company profile."""
        resp = await self._client.get(f"/company/{company_number}")
        resp.raise_for_status()
        return resp.json()

    async def get_officers(
        self, company_number: str, items_per_page: int = 50,
    ) -> dict[str, Any]:
        """List directors and officers of a company."""
        resp = await self._client.get(
            f"/company/{company_number}/officers",
            params={"items_per_page": items_per_page},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_pscs(self, company_number: str) -> dict[str, Any]:
        """Get Persons with Significant Control (beneficial ownership)."""
        resp = await self._client.get(
            f"/company/{company_number}/persons-with-significant-control",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_officer_appointments(self, officer_id: str) -> dict[str, Any]:
        """Get all companies where a specific officer serves."""
        resp = await self._client.get(f"/officers/{officer_id}/appointments")
        resp.raise_for_status()
        return resp.json()
