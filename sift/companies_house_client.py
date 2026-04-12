"""UK Companies House API client."""

from __future__ import annotations

import httpx
from typing import Any

BASE_URL = "https://api.company-information.service.gov.uk"


class CompaniesHouseClient:
    """Async client for the UK Companies House API.

    Auth: HTTP Basic with api_key as username, empty password.
    Rate limit: 600 requests per 5-minute window.
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        kwargs: dict[str, Any] = {
            "base_url": BASE_URL,
            "timeout": timeout,
            "headers": {"User-Agent": "sift/0.4.0"},
        }
        if api_key:
            kwargs["auth"] = (api_key, "")
        self._client = httpx.AsyncClient(**kwargs)
        self._has_key = api_key is not None

    async def close(self):
        await self._client.aclose()

    async def search_company(
        self, query: str, items_per_page: int = 10, start_index: int = 0,
    ) -> dict[str, Any]:
        """Search for UK companies by name."""
        resp = await self._client.get(
            "/search/companies",
            params={
                "q": query,
                "items_per_page": items_per_page,
                "start_index": start_index,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def search_officer(
        self, query: str, items_per_page: int = 10, start_index: int = 0,
    ) -> dict[str, Any]:
        """Search for company officers/directors by name."""
        resp = await self._client.get(
            "/search/officers",
            params={
                "q": query,
                "items_per_page": items_per_page,
                "start_index": start_index,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_company(self, company_number: str) -> dict[str, Any]:
        """Get full company profile."""
        resp = await self._client.get(f"/company/{company_number}")
        resp.raise_for_status()
        return resp.json()

    async def get_officers(
        self, company_number: str, items_per_page: int = 50,
    ) -> dict[str, Any]:
        """List directors and officers of a company."""
        resp = await self._client.get(
            f"/company/{company_number}/officers",
            params={"items_per_page": items_per_page},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_pscs(self, company_number: str) -> dict[str, Any]:
        """Get Persons with Significant Control (beneficial ownership)."""
        resp = await self._client.get(
            f"/company/{company_number}/persons-with-significant-control",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_officer_appointments(self, officer_id: str) -> dict[str, Any]:
        """Get all companies where a specific officer serves."""
        resp = await self._client.get(f"/officers/{officer_id}/appointments")
        resp.raise_for_status()
        return resp.json()

    async def get_filing_history(
        self,
        company_number: str,
        category: str | None = None,
        items_per_page: int = 50,
    ) -> dict[str, Any]:
        """Get filing history for a company, optionally filtered by category.

        Categories: accounts, address, annual-return, capital,
        change-of-name, confirmation-statement, incorporation,
        liquidation, miscellaneous, mortgage, officers, resolution.
        """
        params: dict[str, Any] = {"items_per_page": items_per_page}
        if category:
            params["category"] = category
        resp = await self._client.get(
            f"/company/{company_number}/filing-history", params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        return {
            "company_number": company_number,
            "total_count": data.get("total_count", len(items)),
            "items": items,
            "filing_gaps": _analyze_filing_gaps(items),
        }

    async def get_accounts(self, company_number: str) -> dict[str, Any]:
        """Get accounts summary: profile metadata + accounts filing history."""
        import asyncio
        profile, history = await asyncio.gather(
            self.get_company(company_number),
            self.get_filing_history(company_number, category="accounts"),
            return_exceptions=True,
        )
        accts = {}
        if not isinstance(profile, Exception):
            raw = profile.get("accounts", {})
            accts = {
                "last_accounts": raw.get("last_accounts", {}),
                "next_due": raw.get("next_due"),
                "overdue": raw.get("overdue", False),
                "accounting_reference_date": raw.get(
                    "accounting_reference_date", {},
                ),
                "accounts_type": raw.get("last_accounts", {}).get("type"),
            }
        filings = []
        if not isinstance(history, Exception):
            filings = history.get("items", [])
        return {
            "company_number": company_number,
            **accts,
            "filing_history": filings,
        }

    async def get_charges(self, company_number: str) -> dict[str, Any]:
        """Get the charge register (secured lending) for a company."""
        resp = await self._client.get(
            f"/company/{company_number}/charges",
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        return {
            "company_number": company_number,
            "total_count": data.get("total_count", len(items)),
            "charges": [
                {
                    "charge_number": c.get("charge_number"),
                    "status": c.get("status"),
                    "classification": c.get("classification", {}).get(
                        "description",
                    ),
                    "persons_entitled": [
                        p.get("name", "") for p in c.get("persons_entitled", [])
                    ],
                    "created_on": c.get("created_on"),
                    "delivered_on": c.get("delivered_on"),
                    "satisfied_on": c.get("satisfied_on"),
                    "particulars": c.get("particulars", {}).get(
                        "description",
                    ),
                }
                for c in items
            ],
        }

    async def get_confirmation_statements(
        self, company_number: str,
    ) -> dict[str, Any]:
        """Get confirmation statement history and flag timeliness gaps."""
        history = await self.get_filing_history(
            company_number, category="confirmation-statement",
        )
        items = history.get("items", [])
        # Check for gaps > 14 months between consecutive statements
        gaps = []
        dates = sorted(
            [i["date"] for i in items if i.get("date")], reverse=True,
        )
        for i in range(len(dates) - 1):
            d1 = dates[i]
            d2 = dates[i + 1]
            # Simple month diff — dates are YYYY-MM-DD strings
            y1, m1 = int(d1[:4]), int(d1[5:7])
            y2, m2 = int(d2[:4]), int(d2[5:7])
            months = (y1 - y2) * 12 + (m1 - m2)
            if months > 14:
                gaps.append({
                    "from": d2,
                    "to": d1,
                    "months": months,
                })
        return {
            "company_number": company_number,
            "statements": items,
            "total_count": len(items),
            "gaps": gaps,
            "overdue": len(gaps) > 0,
        }


def _analyze_filing_gaps(items: list[dict]) -> list[dict]:
    """Identify gaps and anomalies in filing history."""
    gaps = []
    # Group annual filings (accounts + confirmation statements)
    annual_dates = sorted(
        [i["date"] for i in items if i.get("date") and i.get("category") in (
            "accounts", "confirmation-statement", "annual-return",
        )],
        reverse=True,
    )
    for i in range(len(annual_dates) - 1):
        d1 = annual_dates[i]
        d2 = annual_dates[i + 1]
        y1, m1 = int(d1[:4]), int(d1[5:7])
        y2, m2 = int(d2[:4]), int(d2[5:7])
        months = (y1 - y2) * 12 + (m1 - m2)
        if months > 15:  # More than 15 months between annual filings
            gaps.append({
                "type": "annual_filing_gap",
                "from": d2,
                "to": d1,
                "months": months,
            })
    # Flag address changes
    for item in items:
        if item.get("category") == "address":
            gaps.append({
                "type": "address_change",
                "date": item.get("date"),
                "description": item.get("description", ""),
            })
    return gaps
