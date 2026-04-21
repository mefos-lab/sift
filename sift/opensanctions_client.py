"""OpenSanctions API client."""

from __future__ import annotations

import httpx
from typing import Any

from sift import __version__

BASE_URL = "https://api.opensanctions.org"


class OpenSanctionsClient:
    """Async client for the OpenSanctions API."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        headers = {"User-Agent": f"sift/{__version__}"}
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers=headers,
        )

    async def close(self):
        await self._client.aclose()

    # --- Search ---

    async def search(
        self,
        query: str,
        dataset: str = "default",
        schema: str | None = None,
        countries: list[str] | None = None,
        topics: list[str] | None = None,
        datasets: list[str] | None = None,
        limit: int = 10,
        offset: int = 0,
        fuzzy: bool = True,
        changed_since: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Full-text search with faceted filtering."""
        params: dict[str, Any] = {
            "q": query,
            "limit": limit,
            "offset": offset,
            "fuzzy": str(fuzzy).lower(),
        }
        if schema:
            params["schema"] = schema
        if countries:
            params["countries"] = countries
        if topics:
            params["topics"] = topics
        if datasets:
            params["datasets"] = datasets
        if changed_since:
            params["changed_since"] = changed_since
        if sort:
            params["sort"] = sort

        resp = await self._client.get(f"/search/{dataset}", params=params)
        resp.raise_for_status()
        return resp.json()

    # --- Match ---

    async def match(
        self,
        queries: dict[str, dict],
        dataset: str = "default",
        threshold: float = 0.7,
        limit: int = 5,
        algorithm: str | None = None,
        topics: list[str] | None = None,
        changed_since: str | None = None,
    ) -> dict[str, Any]:
        """Structured entity matching against sanctions/PEP lists.

        queries format:
        {
            "q1": {"schema": "Person", "properties": {"name": ["John Doe"]}},
            "q2": {"schema": "Company", "properties": {"name": ["Acme Corp"]}}
        }
        """
        params: dict[str, Any] = {
            "threshold": threshold,
            "limit": limit,
        }
        if algorithm:
            params["algorithm"] = algorithm
        if topics:
            params["topics"] = topics
        if changed_since:
            params["changed_since"] = changed_since

        payload = {"queries": queries}
        resp = await self._client.post(
            f"/match/{dataset}",
            params=params,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    # --- Entity ---

    async def get_entity(
        self,
        entity_id: str,
        nested: bool = True,
    ) -> dict[str, Any]:
        """Get full entity details including related entities."""
        resp = await self._client.get(
            f"/entities/{entity_id}",
            params={"nested": str(nested).lower()},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_adjacent(
        self,
        entity_id: str,
        property_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get entities related to a given entity.

        If property_name is provided, filters to that relationship type
        (e.g., 'ownershipOwner', 'directorshipDirector').
        """
        path = f"/entities/{entity_id}/adjacent"
        if property_name:
            path = f"{path}/{property_name}"

        resp = await self._client.get(
            path,
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        return resp.json()

    # --- Statements (provenance) ---

    async def get_statements(
        self,
        entity_id: str | None = None,
        dataset: str | None = None,
        prop: str | None = None,
        schema: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get granular statement-level data with source provenance."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if entity_id:
            params["entity_id"] = entity_id
        if dataset:
            params["dataset"] = dataset
        if prop:
            params["prop"] = prop
        if schema:
            params["schema"] = schema

        resp = await self._client.get("/statements", params=params)
        resp.raise_for_status()
        return resp.json()

    # --- Catalog & metadata ---

    async def get_catalog(self) -> dict[str, Any]:
        """Get the full data catalog with all indexed datasets."""
        resp = await self._client.get("/catalog")
        resp.raise_for_status()
        return resp.json()

    async def get_algorithms(self) -> dict[str, Any]:
        """List available matching/scoring algorithms."""
        resp = await self._client.get("/algorithms")
        resp.raise_for_status()
        return resp.json()
