"""SEC EDGAR API client."""

from __future__ import annotations

import asyncio
import httpx
from typing import Any

EFTS_URL = "https://efts.sec.gov/LATEST"
DATA_URL = "https://data.sec.gov"


def _pad_cik(cik: str | int) -> str:
    """Zero-pad a CIK to 10 digits."""
    return str(cik).zfill(10)


class SECEdgarClient:
    """Async client for SEC EDGAR APIs.

    No API key required. Must provide a User-Agent with name and email
    per SEC fair access policy. Rate limit: 10 req/sec.
    """

    def __init__(
        self,
        user_agent: str = "sift contact@example.com",
        timeout: float = 30.0,
    ):
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
        self._efts = httpx.AsyncClient(
            base_url=EFTS_URL, timeout=timeout, headers=headers,
        )
        self._data = httpx.AsyncClient(
            base_url=DATA_URL, timeout=timeout, headers=headers,
        )
        self._lock: asyncio.Lock | None = None

    async def close(self):
        await self._efts.aclose()
        await self._data.aclose()

    async def _rate_limit(self):
        """Enforce ~10 req/sec rate limit."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            await asyncio.sleep(0.12)

    async def search(
        self,
        query: str,
        forms: str | None = None,
        date_range: str | None = None,
        count: int = 10,
    ) -> dict[str, Any]:
        """Full-text search across SEC filings."""
        await self._rate_limit()
        params: dict[str, Any] = {
            "q": query,
            "from": 0,
            "size": count,
        }
        if forms:
            params["forms"] = forms
        if date_range:
            params["dateRange"] = date_range

        resp = await self._efts.get("/search-index", params=params)
        resp.raise_for_status()
        raw = resp.json()
        hits = raw.get("hits", {})
        return {
            "total": hits.get("total", {}).get("value", 0),
            "results": [
                {
                    "filing_type": h.get("_source", {}).get("file_type", ""),
                    "form": h.get("_source", {}).get("form", ""),
                    "entity_name": (h.get("_source", {}).get("display_names") or [""])[0],
                    "file_date": h.get("_source", {}).get("file_date", ""),
                    "period_of_report": h.get("_source", {}).get("period_ending", ""),
                    "file_description": h.get("_source", {}).get("file_description", ""),
                    "file_num": (h.get("_source", {}).get("file_num") or [""])[0],
                    "cik": (h.get("_source", {}).get("ciks") or [""])[0],
                    "display_names": h.get("_source", {}).get("display_names", []),
                    "accession_number": h.get("_source", {}).get("adsh", ""),
                }
                for h in hits.get("hits", [])
            ],
        }

    async def get_company(self, cik: str | int) -> dict[str, Any]:
        """Get company profile and recent filings by CIK."""
        await self._rate_limit()
        padded = _pad_cik(cik)
        resp = await self._data.get(f"/submissions/CIK{padded}.json")
        resp.raise_for_status()
        raw = resp.json()
        recent = raw.get("filings", {}).get("recent", {})
        filing_count = len(recent.get("accessionNumber", []))
        filings = []
        for i in range(min(filing_count, 20)):
            filings.append({
                "accession_number": recent["accessionNumber"][i],
                "form": recent["form"][i],
                "filing_date": recent["filingDate"][i],
                "primary_document": recent.get("primaryDocument", [""])[i] if i < len(recent.get("primaryDocument", [])) else "",
                "primary_doc_description": recent.get("primaryDocDescription", [""])[i] if i < len(recent.get("primaryDocDescription", [])) else "",
            })
        return {
            "cik": raw.get("cik", padded),
            "name": raw.get("name", ""),
            "entity_type": raw.get("entityType", ""),
            "sic": raw.get("sic", ""),
            "sic_description": raw.get("sicDescription", ""),
            "tickers": raw.get("tickers", []),
            "exchanges": raw.get("exchanges", []),
            "state": raw.get("stateOfIncorporation", ""),
            "fiscal_year_end": raw.get("fiscalYearEnd", ""),
            "mailing_address": raw.get("addresses", {}).get("mailing", {}),
            "business_address": raw.get("addresses", {}).get("business", {}),
            "recent_filings": filings,
            "total_filings": filing_count,
        }

    async def get_filings(
        self,
        cik: str | int,
        form_type: str | None = None,
    ) -> dict[str, Any]:
        """Get filing list for a company, optionally filtered by form type."""
        company = await self.get_company(cik)
        filings = company.get("recent_filings", [])
        if form_type:
            filings = [f for f in filings if f["form"] == form_type]
        return {
            "cik": company["cik"],
            "name": company["name"],
            "form_filter": form_type,
            "filings": filings,
            "count": len(filings),
        }
