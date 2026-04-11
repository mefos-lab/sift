"""Wikidata API client."""

from __future__ import annotations

import httpx
from typing import Any

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


class WikidataClient:
    """Async client for the Wikidata API.

    No authentication required. Provides entity search, entity details,
    and SPARQL queries for structured data on people, companies, and
    organizations. Useful for entity enrichment (birth dates,
    nationalities, political roles) and PEP identification.
    """

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "sift/0.4.0 (investigative journalism tool)",
                "Accept": "application/json",
            },
        )

    async def close(self):
        await self._client.aclose()

    async def search(
        self, query: str, language: str = "en", limit: int = 10,
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """Search for Wikidata entities by name.

        Parameters
        ----------
        query : Search terms
        language : Language code (default: en)
        limit : Max results (default: 10)
        entity_type : 'item' or 'property' (default: item)
        """
        params: dict[str, Any] = {
            "action": "wbsearchentities",
            "search": query,
            "language": language,
            "limit": limit,
            "format": "json",
            "type": entity_type or "item",
        }
        resp = await self._client.get(WIKIDATA_API, params=params)
        resp.raise_for_status()
        raw = resp.json()
        return {
            "total": len(raw.get("search", [])),
            "results": [
                {
                    "id": r.get("id", ""),
                    "label": r.get("label", ""),
                    "description": r.get("description", ""),
                    "url": r.get("concepturi", ""),
                }
                for r in raw.get("search", [])
            ],
        }

    async def get_entity(
        self, entity_id: str, language: str = "en",
    ) -> dict[str, Any]:
        """Get full Wikidata entity with claims/properties."""
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "languages": language,
            "format": "json",
        }
        resp = await self._client.get(WIKIDATA_API, params=params)
        resp.raise_for_status()
        raw = resp.json()
        entity = raw.get("entities", {}).get(entity_id, {})
        return _normalize_entity(entity, language)

    async def get_claims(
        self, entity_id: str, property_id: str | None = None,
    ) -> dict[str, Any]:
        """Get claims (structured facts) for an entity.

        Optionally filter to a specific property (e.g., P27 for citizenship).
        """
        params: dict[str, Any] = {
            "action": "wbgetclaims",
            "entity": entity_id,
            "format": "json",
        }
        if property_id:
            params["property"] = property_id
        resp = await self._client.get(WIKIDATA_API, params=params)
        resp.raise_for_status()
        raw = resp.json()
        return raw.get("claims", {})

    async def sparql(self, query: str) -> dict[str, Any]:
        """Execute a SPARQL query against Wikidata."""
        resp = await self._client.get(
            SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
        )
        resp.raise_for_status()
        raw = resp.json()
        bindings = raw.get("results", {}).get("bindings", [])
        return {
            "total": len(bindings),
            "results": [
                {k: v.get("value", "") for k, v in b.items()}
                for b in bindings
            ],
        }

    async def get_pep_info(self, entity_id: str) -> dict[str, Any]:
        """Check if a Wikidata entity holds or held political positions.

        Queries P39 (position held) for government/political roles.
        Returns positions with start/end dates where available.
        """
        query = f"""
SELECT ?position ?positionLabel ?start ?end ?ofLabel
WHERE {{
  wd:{entity_id} p:P39 ?stmt .
  ?stmt ps:P39 ?position .
  OPTIONAL {{ ?stmt pq:P580 ?start }}
  OPTIONAL {{ ?stmt pq:P582 ?end }}
  OPTIONAL {{ ?stmt pq:P642 ?of . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
        return await self.sparql(query)


# Key Wikidata properties for investigative work
PROPERTIES = {
    "P27": "country of citizenship",
    "P39": "position held",
    "P108": "employer",
    "P463": "member of",
    "P569": "date of birth",
    "P570": "date of death",
    "P856": "official website",
    "P1566": "GeoNames ID",
    "P213": "ISNI",
    "P214": "VIAF ID",
    "P1830": "owner of",
    "P127": "owned by",
    "P1037": "director/manager",
    "P3320": "board member",
    "P749": "parent organization",
    "P355": "subsidiary",
    "P17": "country",
    "P159": "headquarters location",
    "P571": "inception",
    "P576": "dissolved",
    "P452": "industry",
    "P1454": "legal form",
}


def _normalize_entity(entity: dict, language: str = "en") -> dict[str, Any]:
    """Flatten a Wikidata entity into a plain dict with key properties."""
    labels = entity.get("labels", {})
    descriptions = entity.get("descriptions", {})
    claims = entity.get("claims", {})

    result: dict[str, Any] = {
        "id": entity.get("id", ""),
        "label": labels.get(language, {}).get("value", ""),
        "description": descriptions.get(language, {}).get("value", ""),
        "aliases": [
            a.get("value", "")
            for a in entity.get("aliases", {}).get(language, [])
        ],
    }

    # Extract key properties
    for pid, label in PROPERTIES.items():
        if pid in claims:
            values = []
            for claim in claims[pid]:
                mainsnak = claim.get("mainsnak", {})
                dv = mainsnak.get("datavalue", {})
                if dv.get("type") == "wikibase-entityid":
                    values.append(dv["value"].get("id", ""))
                elif dv.get("type") == "time":
                    values.append(dv["value"].get("time", ""))
                elif dv.get("type") == "string":
                    values.append(dv.get("value", ""))
                elif dv.get("type") == "monolingualtext":
                    values.append(dv["value"].get("text", ""))
            if values:
                result[label.replace(" ", "_").replace("/", "_")] = values

    return result
