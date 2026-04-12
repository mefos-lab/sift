"""Wikidata API client."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

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
                "User-Agent": "sift/0.4.0",
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

    async def get_family(self, entity_id: str) -> dict[str, Any]:
        """Get family relationships for a person."""
        query = f"""
SELECT ?relative ?relativeLabel ?relationship ?start ?end
WHERE {{
  {{
    wd:{entity_id} wdt:P26 ?relative . BIND("spouse" AS ?relationship)
    OPTIONAL {{
      wd:{entity_id} p:P26 ?stmt . ?stmt ps:P26 ?relative .
      OPTIONAL {{ ?stmt pq:P580 ?start }}
      OPTIONAL {{ ?stmt pq:P582 ?end }}
    }}
  }} UNION {{
    wd:{entity_id} wdt:P40 ?relative . BIND("child" AS ?relationship)
  }} UNION {{
    wd:{entity_id} wdt:P22 ?relative . BIND("father" AS ?relationship)
  }} UNION {{
    wd:{entity_id} wdt:P25 ?relative . BIND("mother" AS ?relationship)
  }} UNION {{
    wd:{entity_id} wdt:P3373 ?relative . BIND("sibling" AS ?relationship)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
        data = await self.sparql(query)
        family: dict[str, list] = {
            "spouse": [], "children": [], "parents": [], "siblings": [],
        }
        for r in data.get("results", []):
            rel_type = r.get("relationship", "")
            entry = {
                "id": _extract_qid(r.get("relative", "")),
                "name": r.get("relativeLabel", ""),
                "start": _parse_date(r.get("start")),
                "end": _parse_date(r.get("end")),
            }
            if rel_type == "spouse":
                family["spouse"].append(entry)
            elif rel_type == "child":
                family["children"].append(entry)
            elif rel_type in ("father", "mother"):
                family["parents"].append(entry)
            elif rel_type == "sibling":
                family["siblings"].append(entry)
        return {"entity_id": entity_id, **family}

    async def get_education_career(self, entity_id: str) -> dict[str, Any]:
        """Get education, employment, and board memberships."""
        query = f"""
SELECT ?item ?itemLabel ?type ?start ?end ?degreeLabel ?positionLabel
WHERE {{
  {{
    wd:{entity_id} p:P69 ?stmt . ?stmt ps:P69 ?item . BIND("education" AS ?type)
    OPTIONAL {{ ?stmt pq:P580 ?start }}
    OPTIONAL {{ ?stmt pq:P582 ?end }}
    OPTIONAL {{ ?stmt pq:P512 ?degree }}
  }} UNION {{
    wd:{entity_id} p:P108 ?stmt . ?stmt ps:P108 ?item . BIND("employer" AS ?type)
    OPTIONAL {{ ?stmt pq:P580 ?start }}
    OPTIONAL {{ ?stmt pq:P582 ?end }}
    OPTIONAL {{ ?stmt pq:P39 ?position }}
  }} UNION {{
    wd:{entity_id} wdt:P3320 ?item . BIND("board" AS ?type)
  }} UNION {{
    wd:{entity_id} wdt:P1037 ?item . BIND("management" AS ?type)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
        data = await self.sparql(query)
        result: dict[str, list] = {
            "education": [], "employers": [],
            "board_memberships": [], "management_roles": [],
        }
        for r in data.get("results", []):
            entry_type = r.get("type", "")
            entry = {
                "id": _extract_qid(r.get("item", "")),
                "name": r.get("itemLabel", ""),
                "start": _parse_date(r.get("start")),
                "end": _parse_date(r.get("end")),
            }
            if entry_type == "education":
                entry["degree"] = r.get("degreeLabel", "")
                result["education"].append(entry)
            elif entry_type == "employer":
                entry["position"] = r.get("positionLabel", "")
                result["employers"].append(entry)
            elif entry_type == "board":
                result["board_memberships"].append(entry)
            elif entry_type == "management":
                result["management_roles"].append(entry)
        return result

    async def get_citizenship(self, entity_id: str) -> dict[str, Any]:
        """Get country of citizenship with dates."""
        query = f"""
SELECT ?country ?countryLabel ?start ?end
WHERE {{
  wd:{entity_id} p:P27 ?stmt .
  ?stmt ps:P27 ?country .
  OPTIONAL {{ ?stmt pq:P580 ?start }}
  OPTIONAL {{ ?stmt pq:P582 ?end }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
        data = await self.sparql(query)
        return {
            "entity_id": entity_id,
            "citizenships": [
                {
                    "country": r.get("countryLabel", ""),
                    "country_id": _extract_qid(r.get("country", "")),
                    "start": _parse_date(r.get("start")),
                    "end": _parse_date(r.get("end")),
                }
                for r in data.get("results", [])
            ],
        }

    async def get_deep_enrichment(self, entity_id: str) -> dict[str, Any]:
        """Composite: family + education/career + citizenship + PEP info."""
        family, career, citizenship, pep = await asyncio.gather(
            self.get_family(entity_id),
            self.get_education_career(entity_id),
            self.get_citizenship(entity_id),
            self.get_pep_info(entity_id),
            return_exceptions=True,
        )
        result: dict[str, Any] = {"entity_id": entity_id}
        if not isinstance(family, Exception):
            result["family"] = family
        if not isinstance(career, Exception):
            result["career"] = career
        if not isinstance(citizenship, Exception):
            result["citizenship"] = citizenship
        if not isinstance(pep, Exception):
            result["political_positions"] = pep
        return result

    async def cross_reference_dates(
        self, person_id: str, company_ids: list[str],
    ) -> dict[str, Any]:
        """Cross-reference political appointment dates with company inception dates."""
        # Get person's political positions
        pep = await self.get_pep_info(person_id)
        appointments = []
        for r in pep.get("results", []):
            start = _parse_date(r.get("start"))
            if start:
                appointments.append({
                    "position": r.get("positionLabel", ""),
                    "start": start,
                })
        # Get company inception dates
        companies = []
        if company_ids:
            ids = " ".join(f"wd:{qid}" for qid in company_ids)
            query = f"""
SELECT ?company ?companyLabel ?inception
WHERE {{
  VALUES ?company {{ {ids} }}
  OPTIONAL {{ ?company wdt:P571 ?inception }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""
            data = await self.sparql(query)
            for r in data.get("results", []):
                companies.append({
                    "id": _extract_qid(r.get("company", "")),
                    "name": r.get("companyLabel", ""),
                    "inception": _parse_date(r.get("inception")),
                })
        # Find temporal overlaps (±6 months)
        overlaps = []
        for appt in appointments:
            appt_date = appt["start"]
            try:
                appt_dt = datetime.fromisoformat(appt_date)
            except (ValueError, TypeError):
                continue
            for comp in companies:
                inc = comp.get("inception")
                if not inc:
                    continue
                try:
                    inc_dt = datetime.fromisoformat(inc)
                except (ValueError, TypeError):
                    continue
                diff = abs((appt_dt - inc_dt).days)
                if diff <= 183:  # ~6 months
                    overlaps.append({
                        "appointment": appt["position"],
                        "appointment_date": appt_date,
                        "company": comp["name"],
                        "company_id": comp["id"],
                        "inception_date": inc,
                        "days_apart": diff,
                    })
        return {
            "person_id": person_id,
            "appointments": appointments,
            "companies": companies,
            "temporal_overlaps": overlaps,
        }


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


def _extract_qid(uri: str) -> str:
    """Extract Q-ID from a Wikidata URI."""
    if "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


def _parse_date(value: str | None) -> str | None:
    """Parse a Wikidata date value into ISO format."""
    if not value:
        return None
    # Strip leading + and timezone suffix
    value = value.lstrip("+").split("T")[0]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    if re.match(r"^\d{4}$", value):
        return value
    return value


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
