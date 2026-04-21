"""GLEIF LEI Registry API client."""

from __future__ import annotations

import httpx
from typing import Any

from sift import __version__

BASE_URL = "https://api.gleif.org/api/v1"


class GLEIFClient:
    """Async client for the GLEIF LEI Registry API.

    No authentication required. Returns normalized dicts from JSON:API responses.
    """

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"User-Agent": f"sift/{__version__}"},
        )

    async def close(self):
        await self._client.aclose()

    async def search(
        self,
        query: str,
        page_size: int = 10,
        jurisdiction: str | None = None,
        entity_status: str | None = None,
        legal_form: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Full-text search for LEI records by company name.

        Optional filters narrow results by jurisdiction (e.g. 'US-DE', 'GB'),
        entity status ('ACTIVE', 'INACTIVE'), legal form ID, or category.
        """
        params: dict[str, Any] = {
            "filter[fulltext]": query,
            "page[size]": page_size,
        }
        if jurisdiction:
            params["filter[entity.jurisdiction]"] = jurisdiction
        if entity_status:
            params["filter[entity.status]"] = entity_status
        if legal_form:
            params["filter[entity.legalForm.id]"] = legal_form
        if category:
            params["filter[entity.category]"] = category
        resp = await self._client.get("/lei-records", params=params)
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": raw.get("meta", {}).get("pagination", {}).get("total", 0),
            "results": [_normalize_record(r) for r in raw.get("data", [])],
        }

    async def get_lei(self, lei: str) -> dict[str, Any]:
        """Get a full LEI record by LEI code."""
        resp = await self._client.get(f"/lei-records/{lei}")
        resp.raise_for_status()
        raw = resp.json()
        return _normalize_record(raw.get("data", {}))

    async def get_ownership(self, lei: str) -> dict[str, Any]:
        """Get parent and child entities for an LEI."""
        result: dict[str, Any] = {
            "lei": lei,
            "direct_parent": None,
            "ultimate_parent": None,
            "children": [],
        }

        # Direct parent — the entity IS_DIRECTLY_CONSOLIDATED_BY its parent
        # The relationship endNode is the parent
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/direct-parent-relationship"
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    rel = data[0] if isinstance(data, list) else data
                    end_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("endNode", {})
                    )
                    parent_lei = end_node.get("id")
                    if parent_lei and parent_lei != lei:
                        result["direct_parent"] = parent_lei
        except httpx.HTTPError:
            pass

        # Ultimate parent
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/ultimate-parent-relationship"
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    rel = data[0] if isinstance(data, list) else data
                    end_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("endNode", {})
                    )
                    parent_lei = end_node.get("id")
                    if parent_lei and parent_lei != lei:
                        result["ultimate_parent"] = parent_lei
        except httpx.HTTPError:
            pass

        # Children — each child IS_DIRECTLY_CONSOLIDATED_BY this entity
        # The child LEI is in startNode.id
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/direct-child-relationships",
                params={"page[size]": 50},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for rel in data:
                    start_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("startNode", {})
                    )
                    child_lei = start_node.get("id")
                    if child_lei and child_lei != lei:
                        result["children"].append(child_lei)
        except httpx.HTTPError:
            pass

        return result

    async def get_all_relationships(self, lei: str) -> dict[str, Any]:
        """Get full ownership tree: parents + direct children + all descendants."""
        result: dict[str, Any] = {
            "lei": lei,
            "direct_parent": None,
            "ultimate_parent": None,
            "direct_children": [],
            "all_children": [],
        }

        # Direct parent
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/direct-parent-relationship"
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    rel = data[0] if isinstance(data, list) else data
                    end_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("endNode", {})
                    )
                    parent_lei = end_node.get("id")
                    if parent_lei and parent_lei != lei:
                        result["direct_parent"] = parent_lei
        except httpx.HTTPError:
            pass

        # Ultimate parent
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/ultimate-parent-relationship"
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    rel = data[0] if isinstance(data, list) else data
                    end_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("endNode", {})
                    )
                    parent_lei = end_node.get("id")
                    if parent_lei and parent_lei != lei:
                        result["ultimate_parent"] = parent_lei
        except httpx.HTTPError:
            pass

        # Direct children
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/direct-child-relationships",
                params={"page[size]": 50},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for rel in data:
                    start_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("startNode", {})
                    )
                    child_lei = start_node.get("id")
                    if child_lei and child_lei != lei:
                        result["direct_children"].append(child_lei)
        except httpx.HTTPError:
            pass

        # All descendants (ultimate children)
        try:
            resp = await self._client.get(
                f"/lei-records/{lei}/ultimate-child-relationships",
                params={"page[size]": 100},
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for rel in data:
                    start_node = (
                        rel.get("attributes", {})
                        .get("relationship", {})
                        .get("startNode", {})
                    )
                    child_lei = start_node.get("id")
                    if child_lei and child_lei != lei:
                        result["all_children"].append(child_lei)
        except httpx.HTTPError:
            pass

        return result


def _normalize_record(record: dict) -> dict[str, Any]:
    """Flatten a JSON:API LEI record into a plain dict."""
    attrs = record.get("attributes", {})
    entity = attrs.get("entity", {})
    legal_address = entity.get("legalAddress", {})
    reg = attrs.get("registration", {})
    return {
        "lei": record.get("id", attrs.get("lei", "")),
        "legal_name": entity.get("legalName", {}).get("name", ""),
        "status": entity.get("status", ""),
        "jurisdiction": entity.get("jurisdiction", ""),
        "legal_form": entity.get("legalForm", {}).get("id", ""),
        "category": entity.get("category", ""),
        "country": legal_address.get("country", ""),
        "city": legal_address.get("city", ""),
        "address": ", ".join(legal_address.get("addressLines", [])),
        "registration_status": reg.get("status", ""),
        "initial_registration": reg.get("initialRegistrationDate", ""),
        "last_update": reg.get("lastUpdateDate", ""),
        "managing_lou": reg.get("managingLou", ""),
    }
