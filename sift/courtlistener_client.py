"""CourtListener API client."""

from __future__ import annotations

import asyncio
import re

import httpx
from typing import Any

from sift import __version__

_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:million|billion)?",
    re.IGNORECASE,
)

BASE_URL = "https://www.courtlistener.com/api/rest/v4"


class CourtListenerClient:
    """Async client for the CourtListener API.

    Auth: Token-based (free account required).
    Rate limit: 5,000 requests per hour.
    """

    def __init__(self, api_token: str | None = None, timeout: float = 30.0):
        headers: dict[str, str] = {"User-Agent": f"sift/{__version__}"}
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
        nature_of_suit: str | None = None,
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
        nature_of_suit : Nature of suit code for filtering (e.g. '422' for bankruptcy)
        """
        params: dict[str, Any] = {"q": query, "type": type, "page": page}
        if court:
            params["court"] = court
        if filed_after:
            params["filed_after"] = filed_after
        if filed_before:
            params["filed_before"] = filed_before
        if nature_of_suit:
            params["nature_of_suit"] = nature_of_suit

        resp = await self._client.get("/search/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_opinion(self, opinion_id: int) -> dict[str, Any]:
        """Get a court opinion by ID, including text if available."""
        resp = await self._client.get(f"/opinions/{opinion_id}/")
        resp.raise_for_status()
        data = resp.json()
        return {
            "id": data.get("id"),
            "type": data.get("type", ""),
            "author_str": data.get("author_str", ""),
            "plain_text": data.get("plain_text", ""),
            "download_url": data.get("download_url", ""),
            "date_filed": data.get("date_filed", ""),
            "cluster": data.get("cluster", ""),
        }

    async def get_person(self, person_id: int) -> dict[str, Any]:
        """Get judge or attorney details by person ID."""
        resp = await self._client.get(f"/people/{person_id}/")
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

    async def get_docket_entries(
        self, docket_id: int, page: int = 1,
    ) -> dict[str, Any]:
        """Get docket entries for a case."""
        resp = await self._client.get(
            "/docket-entries/",
            params={"docket": docket_id, "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "docket_id": docket_id,
            "count": data.get("count", len(results)),
            "next": data.get("next"),
            "entries": [
                {
                    "entry_number": e.get("entry_number"),
                    "date_filed": e.get("date_filed"),
                    "description": e.get("description", ""),
                    "recap_documents": [
                        {
                            "id": d.get("id"),
                            "description": d.get("description", ""),
                            "document_type": d.get("document_type", ""),
                            "page_count": d.get("page_count"),
                        }
                        for d in e.get("recap_documents", [])
                    ],
                }
                for e in results
            ],
        }

    async def get_recap_document(self, doc_id: int) -> dict[str, Any]:
        """Get a RECAP document by ID, including plain text if available."""
        resp = await self._client.get(f"/recap-documents/{doc_id}/")
        resp.raise_for_status()
        data = resp.json()
        return {
            "doc_id": doc_id,
            "description": data.get("description", ""),
            "document_type": data.get("document_type", ""),
            "plain_text": data.get("plain_text", ""),
            "page_count": data.get("page_count"),
            "filepath_local": data.get("filepath_local", ""),
        }

    async def get_parties(self, docket_id: int) -> dict[str, Any]:
        """Get parties (plaintiffs, defendants, etc.) for a docket."""
        resp = await self._client.get(
            "/parties/", params={"docket": docket_id},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return {
            "docket_id": docket_id,
            "parties": [
                {
                    "name": p.get("name", ""),
                    "party_type": (
                        p.get("party_types", [{}])[0].get("name", "")
                        if p.get("party_types") else ""
                    ),
                    "attorneys": [
                        a.get("attorney", {}).get("name", "")
                        for a in p.get("attorneys", [])
                    ],
                    "date_terminated": p.get("date_terminated"),
                }
                for p in results
            ],
        }

    async def get_docket_detail(self, docket_id: int) -> dict[str, Any]:
        """Get enriched docket details: case info, parties, related cases."""
        docket, parties, related = await asyncio.gather(
            self.get_docket(docket_id),
            self.get_parties(docket_id),
            self._client.get(
                "/dockets/", params={"related_docket": docket_id},
            ),
            return_exceptions=True,
        )
        result: dict[str, Any] = {"docket_id": docket_id}
        if not isinstance(docket, Exception):
            result.update({
                "case_name": docket.get("case_name", ""),
                "nature_of_suit": docket.get("nature_of_suit", ""),
                "cause": docket.get("cause", ""),
                "jury_demand": docket.get("jury_demand", ""),
                "jurisdiction_type": docket.get("jurisdiction_type", ""),
                "date_filed": docket.get("date_filed"),
                "date_terminated": docket.get("date_terminated"),
                "court": docket.get("court", ""),
            })
        if not isinstance(parties, Exception):
            result["parties"] = parties.get("parties", [])
        else:
            result["parties"] = []
        if not isinstance(related, Exception):
            rel_data = related.json() if hasattr(related, "json") else {}
            result["related_cases"] = [
                {
                    "id": r.get("id"),
                    "case_name": r.get("case_name", ""),
                    "date_filed": r.get("date_filed"),
                }
                for r in rel_data.get("results", [])
            ]
        else:
            result["related_cases"] = []
        return result

    async def get_complaint_text(self, docket_id: int) -> dict[str, Any]:
        """Get the complaint/petition text for a case (entry #1).

        Fetches docket entries, finds entry #1, retrieves its RECAP
        document text, and parses for amounts in dispute.
        """
        entries = await self.get_docket_entries(docket_id)
        complaint_entry = None
        for e in entries.get("entries", []):
            if e.get("entry_number") == 1:
                complaint_entry = e
                break
        if not complaint_entry:
            return {
                "docket_id": docket_id,
                "complaint_text": None,
                "amount_in_dispute": None,
                "note": "No entry #1 found in docket",
            }
        # Get RECAP document text
        docs = complaint_entry.get("recap_documents", [])
        if not docs:
            return {
                "docket_id": docket_id,
                "complaint_text": None,
                "amount_in_dispute": None,
                "filing_date": complaint_entry.get("date_filed"),
                "description": complaint_entry.get("description", ""),
                "note": "No RECAP document available for complaint",
            }
        doc = await self.get_recap_document(docs[0]["id"])
        text = doc.get("plain_text", "")
        # Parse for amount in dispute
        amount = None
        if text:
            amount = _extract_amount(text)
        return {
            "docket_id": docket_id,
            "complaint_text": text or None,
            "amount_in_dispute": amount,
            "filing_date": complaint_entry.get("date_filed"),
            "description": complaint_entry.get("description", ""),
            "page_count": doc.get("page_count"),
        }


def _extract_amount(text: str) -> str | None:
    """Extract the largest dollar amount near dispute-related keywords."""
    keywords = [
        "damages", "amount in controversy", "seeks", "judgment",
        "not less than", "excess of", "exceeding",
    ]
    best = None
    best_val = 0
    for match in _AMOUNT_RE.finditer(text):
        # Check if a keyword is within 200 chars of the match
        start = max(0, match.start() - 200)
        context = text[start:match.end() + 50].lower()
        if any(kw in context for kw in keywords):
            raw = match.group(1).replace(",", "")
            try:
                val = float(raw)
                suffix = match.group(0).lower()
                if "billion" in suffix:
                    val *= 1_000_000_000
                elif "million" in suffix:
                    val *= 1_000_000
                if val > best_val:
                    best_val = val
                    best = match.group(0).strip()
            except ValueError:
                continue
    return best
