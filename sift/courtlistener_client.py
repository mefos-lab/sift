"""CourtListener API client."""

from __future__ import annotations

import httpx
from typing import Any

BASE_URL = "https://www.courtlistener.com/api/rest/v4"


class CourtListenerClient:
    """Async client for the CourtListener API.

    Auth: Token-based (free account required).
    Rate limit: 5,000 requests per hour.
    """

    def __init__(self, api_token: str | None = None, timeout: float = 30.0):
        headers: dict[str, str] = {"User-Agent": "sift/0.4.0"}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers=headers,
        )

    async def close(self):
        await self._client.aclose()

    async def search(
        self,
        query: str,
        type: str = "r",
        court: str | None = None,
        filed_after: str | None = None,
        filed_before: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search court opinions (type='o') or docket entries (type='r').

        Parameters
        ----------
        query : Search terms
        type : 'o' for opinions, 'r' for RECAP dockets
        court : Court ID filter (optional)
        filed_after : ISO date (optional)
        filed_before : ISO date (optional)
        """
        params: dict[str, Any] = {"q": query, "type": type, "page": page}
        if court:
            params["court"] = court
        if filed_after:
            params["filed_after"] = filed_after
        if filed_before:
            params["filed_before"] = filed_before

        resp = await self._client.get("/search/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_docket(self, docket_id: int) -> dict[str, Any]:
        """Get full docket details."""
        resp = await self._client.get(f"/dockets/{docket_id}/")
        resp.raise_for_status()
        return resp.json()

    async def search_people(self, query: str) -> dict[str, Any]:
        """Search for judges and attorneys."""
        resp = await self._client.get("/people/", params={"q": query})
        resp.raise_for_status()
        return resp.json()
