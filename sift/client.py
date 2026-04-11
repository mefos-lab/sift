"""ICIJ Offshore Leaks API client."""

from __future__ import annotations

import httpx
from typing import Any

BASE_URL = "https://offshoreleaks.icij.org/api/v1"

INVESTIGATIONS = [
    "bahamas-leaks",
    "offshore-leaks",
    "panama-papers",
    "pandora-papers",
    "paradise-papers",
]

ENTITY_TYPES = ["Address", "Entity", "Intermediary", "Node", "Officer", "Other"]


class ICIJClient:
    """Async client for the ICIJ Offshore Leaks API."""

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"User-Agent": "sift/0.4.0"},
        )

    async def close(self):
        await self._client.aclose()

    async def reconcile(
        self,
        query: str,
        entity_type: str | None = None,
        investigation: str | None = None,
        properties: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Match a name against the offshore leaks database."""
        path = "/reconcile"
        if investigation and investigation in INVESTIGATIONS:
            path = f"/reconcile/{investigation}"

        payload: dict[str, Any] = {"query": query}
        if entity_type and entity_type in ENTITY_TYPES:
            payload["type"] = entity_type
        if properties:
            payload["properties"] = properties

        resp = await self._client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def batch_reconcile(
        self,
        queries: dict[str, dict],
        investigation: str | None = None,
    ) -> dict[str, Any]:
        """Batch reconcile multiple names (max 25 per request)."""
        path = "/reconcile"
        if investigation and investigation in INVESTIGATIONS:
            path = f"/reconcile/{investigation}"

        payload: dict[str, Any] = {"queries": queries}

        resp = await self._client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_node(self, node_id: int) -> dict[str, Any]:
        """Fetch full details on a specific node by ID.

        Tries the REST API first; falls back to extend API with
        common properties if REST returns an error.
        """
        try:
            resp = await self._client.get(f"/rest/nodes/{node_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            # REST endpoint may be unavailable — fall back to extend
            props = ["country_codes", "name", "note", "sourceID"]
            extended = await self.extend([node_id], props)
            row = extended.get("rows", {}).get(str(node_id), {})
            return {
                "id": node_id,
                "source": "extend_fallback",
                "url": f"https://offshoreleaks.icij.org/nodes/{node_id}",
                **row,
            }

    async def extend(
        self,
        ids: list[int],
        properties: list[str],
    ) -> dict[str, Any]:
        """Get additional property data for known entities."""
        import json as json_mod
        import urllib.parse

        extend_param = json_mod.dumps({
            "ids": ids,
            "properties": [{"id": p} for p in properties],
        })
        resp = await self._client.get(
            "/reconcile",
            params={"extend": extend_param},
        )
        resp.raise_for_status()
        return resp.json()

    async def suggest_entity(self, prefix: str) -> dict[str, Any]:
        """Autocomplete entity names."""
        resp = await self._client.get(
            "/reconcile/suggest/entity",
            params={"prefix": prefix},
        )
        resp.raise_for_status()
        return resp.json()

    async def suggest_property(self, prefix: str) -> dict[str, Any]:
        """Autocomplete property names."""
        resp = await self._client.get(
            "/reconcile/suggest/property",
            params={"prefix": prefix},
        )
        resp.raise_for_status()
        return resp.json()

    async def suggest_type(self, prefix: str) -> dict[str, Any]:
        """Autocomplete type names."""
        resp = await self._client.get(
            "/reconcile/suggest/type",
            params={"prefix": prefix},
        )
        resp.raise_for_status()
        return resp.json()

    async def service_manifest(self) -> dict[str, Any]:
        """Get the service manifest describing capabilities."""
        resp = await self._client.get("/reconcile")
        resp.raise_for_status()
        return resp.json()
