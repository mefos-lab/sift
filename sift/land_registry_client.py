"""UK HM Land Registry API client."""

from __future__ import annotations

import httpx
from typing import Any

# Price Paid linked data endpoint (free, no auth)
PPD_BASE = "https://landregistry.data.gov.uk"


class LandRegistryClient:
    """Async client for the UK HM Land Registry.

    Uses the Price Paid Data linked data API (free, no auth required).
    Provides property transaction data including buyer names, prices,
    property types, and addresses — useful for tracing real estate
    purchases by persons or companies under investigation.
    """

    def __init__(self, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "sift/0.4.0", "Accept": "application/json"},
        )

    async def close(self):
        await self._client.aclose()

    async def search_price_paid(
        self,
        query: str,
        limit: int = 20,
        min_price: int | None = None,
        max_price: int | None = None,
        property_type: str | None = None,
    ) -> dict[str, Any]:
        """Search Price Paid Data via SPARQL for property transactions.

        Searches by street, town, postcode, or area name. Returns
        transaction records with buyer name (where available), price,
        date, and property details.
        """
        filters = []
        if min_price is not None:
            filters.append(f"FILTER(?amount >= {min_price})")
        if max_price is not None:
            filters.append(f"FILTER(?amount <= {max_price})")
        if property_type:
            type_map = {
                "detached": "lrcommon:detached",
                "semi-detached": "lrcommon:semi-detached",
                "terraced": "lrcommon:terraced",
                "flat": "lrcommon:flat-maisonette",
            }
            lrtype = type_map.get(property_type.lower())
            if lrtype:
                filters.append(f"FILTER(?type = {lrtype})")

        filter_block = "\n    ".join(filters)
        # Escape the query for SPARQL — search across address fields
        safe_q = query.replace("'", "\\'").upper()

        sparql = f"""
PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

SELECT ?transaction ?amount ?date ?propertyAddress ?paon ?saon ?street ?town ?county ?postcode ?type ?newBuild
WHERE {{
    ?transaction lrppi:pricePaid ?amount ;
                 lrppi:transactionDate ?date ;
                 lrppi:propertyAddress ?addr ;
                 lrppi:propertyType ?type .
    ?addr lrcommon:paon ?paon .
    OPTIONAL {{ ?addr lrcommon:saon ?saon }}
    ?addr lrcommon:street ?street ;
          lrcommon:town ?town .
    OPTIONAL {{ ?addr lrcommon:county ?county }}
    ?addr lrcommon:postcode ?postcode .
    OPTIONAL {{ ?transaction lrppi:newBuild ?newBuild }}
    FILTER(
        CONTAINS(UCASE(?street), '{safe_q}') ||
        CONTAINS(UCASE(?town), '{safe_q}') ||
        CONTAINS(UCASE(?postcode), '{safe_q}') ||
        CONTAINS(UCASE(?paon), '{safe_q}')
    )
    {filter_block}
}}
ORDER BY DESC(?date)
LIMIT {limit}
"""
        resp = await self._client.get(
            f"{PPD_BASE}/app/root/qonsole/query",
            params={"query": sparql, "output": "json"},
        )
        resp.raise_for_status()
        raw = resp.json()
        bindings = raw.get("results", {}).get("bindings", [])
        return {
            "total": len(bindings),
            "results": [_normalize_transaction(b) for b in bindings],
        }

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Get details of a specific transaction by its URI/ID."""
        # Transaction IDs are URIs like http://landregistry.data.gov.uk/data/ppi/transaction/...
        url = transaction_id if transaction_id.startswith("http") else (
            f"{PPD_BASE}/data/ppi/transaction/{transaction_id}"
        )
        resp = await self._client.get(
            url, headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    async def search_postcode(
        self, postcode: str, limit: int = 50,
    ) -> dict[str, Any]:
        """Get all transactions for a specific postcode."""
        safe_pc = postcode.replace("'", "\\'").upper().strip()
        sparql = f"""
PREFIX lrppi: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

SELECT ?transaction ?amount ?date ?paon ?saon ?street ?town ?postcode ?type
WHERE {{
    ?transaction lrppi:pricePaid ?amount ;
                 lrppi:transactionDate ?date ;
                 lrppi:propertyAddress ?addr ;
                 lrppi:propertyType ?type .
    ?addr lrcommon:paon ?paon .
    OPTIONAL {{ ?addr lrcommon:saon ?saon }}
    ?addr lrcommon:street ?street ;
          lrcommon:town ?town ;
          lrcommon:postcode ?postcode .
    FILTER(?postcode = '{safe_pc}')
}}
ORDER BY DESC(?date)
LIMIT {limit}
"""
        resp = await self._client.get(
            f"{PPD_BASE}/app/root/qonsole/query",
            params={"query": sparql, "output": "json"},
        )
        resp.raise_for_status()
        raw = resp.json()
        bindings = raw.get("results", {}).get("bindings", [])
        return {
            "total": len(bindings),
            "results": [_normalize_transaction(b) for b in bindings],
        }


def _normalize_transaction(binding: dict) -> dict[str, Any]:
    """Flatten a SPARQL binding into a plain dict."""
    def _val(key: str) -> str:
        return binding.get(key, {}).get("value", "")

    def _type_label(uri: str) -> str:
        """Convert type URI to readable label."""
        labels = {
            "detached": "Detached",
            "semi-detached": "Semi-detached",
            "terraced": "Terraced",
            "flat-maisonette": "Flat/Maisonette",
        }
        for key, label in labels.items():
            if key in uri.lower():
                return label
        return uri.rsplit("/", 1)[-1] if "/" in uri else uri

    return {
        "transaction_id": _val("transaction"),
        "price": int(float(_val("amount"))) if _val("amount") else None,
        "date": _val("date"),
        "property_address": {
            "paon": _val("paon"),
            "saon": _val("saon"),
            "street": _val("street"),
            "town": _val("town"),
            "county": _val("county"),
            "postcode": _val("postcode"),
        },
        "property_type": _type_label(_val("type")),
        "new_build": _val("newBuild").lower() == "true" if _val("newBuild") else None,
    }
