"""OCCRP Aleph API client."""

from __future__ import annotations

import httpx
from typing import Any

from sift import __version__

BASE_URL = "https://aleph.occrp.org/api/2"


class AlephClient:
    """Async client for the OCCRP Aleph API.

    Auth: API key (optional but recommended for higher rate limits).
    Provides access to investigative documents, company records,
    court filings, and leaked datasets from dozens of countries.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        headers: dict[str, str] = {"User-Agent": f"sift/{__version__}"}
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers=headers,
        )

    async def close(self):
        await self._client.aclose()

    async def search_entities(
        self,
        query: str,
        schema: str | None = None,
        countries: list[str] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search across all Aleph datasets for entities."""
        params: dict[str, Any] = {
            "q": query,
            "limit": limit,
            "offset": offset,
        }
        if schema:
            params["filter:schemata"] = schema
        if countries:
            params["filter:countries"] = countries

        resp = await self._client.get("/entities", params=params)
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("total", 0),
            "results": [_normalize_entity(r) for r in raw.get("results", [])],
        }

    async def get_entity(self, entity_id: str) -> dict[str, Any]:
        """Get full entity details by Aleph entity ID."""
        resp = await self._client.get(f"/entities/{entity_id}")
        resp.raise_for_status()
        return _normalize_entity(resp.json())

    async def get_entity_similar(
        self, entity_id: str, limit: int = 10,
    ) -> dict[str, Any]:
        """Find entities similar to a given entity (cross-referencing)."""
        resp = await self._client.get(
            f"/entities/{entity_id}/similar",
            params={"limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("total", 0),
            "results": [_normalize_entity(r) for r in raw.get("results", [])],
        }

    async def expand_entity(
        self, entity_id: str, limit: int = 50,
    ) -> dict[str, Any]:
        """Expand an entity to discover connected entities and relationships."""
        resp = await self._client.get(
            f"/entities/{entity_id}/expand",
            params={"limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("total", 0),
            "results": [_normalize_entity(r) for r in raw.get("results", [])],
        }

    async def search_collection_documents(
        self,
        collection_id: int | str,
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search documents within a specific collection."""
        params: dict[str, Any] = {
            "filter:collection_id": collection_id,
            "filter:schemata": "Document",
            "limit": limit,
        }
        if query:
            params["q"] = query
        resp = await self._client.get("/entities", params=params)
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("total", 0),
            "results": [_normalize_entity(r) for r in raw.get("results", [])],
        }

    async def get_entity_relationships(
        self,
        entity_id: str,
        limit: int = 50,
        schemata: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get relationships for an entity, optionally filtered by schema type.

        Uses the expand endpoint and filters results by relationship schemata
        (e.g., Ownership, Directorship, Membership).
        """
        expanded = await self.expand_entity(entity_id, limit=limit)
        results = expanded.get("results", [])
        if schemata:
            schemata_set = set(schemata)
            results = [r for r in results if r.get("schema") in schemata_set]
        return {
            "entity_id": entity_id,
            "relationships": results,
        }

    async def search_collections(
        self, query: str, limit: int = 10,
    ) -> dict[str, Any]:
        """Search Aleph datasets/collections (investigations, source datasets)."""
        resp = await self._client.get(
            "/collections",
            params={"q": query, "limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("total", 0),
            "results": [
                {
                    "id": c.get("id"),
                    "label": c.get("label", ""),
                    "category": c.get("category", ""),
                    "countries": c.get("countries", []),
                    "count": c.get("count", 0),
                    "summary": c.get("summary", ""),
                }
                for c in raw.get("results", [])
            ],
        }


def _normalize_entity(entity: dict) -> dict[str, Any]:
    """Flatten an Aleph entity into a plain dict."""
    props = entity.get("properties", {})
    return {
        "id": entity.get("id", ""),
        "schema": entity.get("schema", ""),
        "name": _first(props.get("name", [])) or entity.get("name", ""),
        "countries": entity.get("countries", props.get("country", [])),
        "collection_id": entity.get("collection_id"),
        "datasets": [c.get("label", "") for c in entity.get("collection", {}).get("links", [])]
            if isinstance(entity.get("collection"), dict) else [],
        "addresses": props.get("address", []),
        "registration_number": _first(props.get("registrationNumber", [])),
        "incorporation_date": _first(props.get("incorporationDate", [])),
        "dissolution_date": _first(props.get("dissolutionDate", [])),
        "jurisdiction": _first(props.get("jurisdiction", [])),
        "notes": props.get("notes", []),
        "source_url": _first(props.get("sourceUrl", [])),
    }


def _first(lst: list) -> str | None:
    """Return first element or None."""
    return lst[0] if lst else None
