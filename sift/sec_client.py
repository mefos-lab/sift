"""SEC EDGAR API client."""

from __future__ import annotations

import asyncio
import re
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
        self._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", timeout=timeout,
            headers={**headers, "Accept": "text/html, */*"},
        )
        self._lock: asyncio.Lock | None = None

    async def close(self):
        await self._efts.aclose()
        await self._data.aclose()
        await self._www.aclose()

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
        start: int = 0,
    ) -> dict[str, Any]:
        """Full-text search across SEC filings."""
        await self._rate_limit()
        params: dict[str, Any] = {
            "q": query,
            "from": start,
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
        for i in range(min(filing_count, 100)):
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

    async def get_company_facts(self, cik: str | int) -> dict[str, Any]:
        """Get structured XBRL financial data for a company.

        Returns key financial metrics (revenue, assets, liabilities, net
        income, equity) from the Company Facts API with values from the
        most recent annual (10-K) and quarterly (10-Q) filings.
        """
        await self._rate_limit()
        padded = _pad_cik(cik)
        resp = await self._data.get(
            f"/api/xbrl/companyfacts/CIK{padded}.json",
        )
        resp.raise_for_status()
        raw = resp.json()

        # Extract key metrics from us-gaap taxonomy
        us_gaap = raw.get("facts", {}).get("us-gaap", {})

        # Tags we care about — maps XBRL tag to human label
        target_tags = {
            "Revenues": "revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
            "SalesRevenueNet": "revenue",
            "Assets": "total_assets",
            "Liabilities": "total_liabilities",
            "StockholdersEquity": "stockholders_equity",
            "NetIncomeLoss": "net_income",
            "CashAndCashEquivalentsAtCarryingValue": "cash",
            "LongTermDebt": "long_term_debt",
            "NumberOfSubsidiaries": "subsidiary_count",
        }

        metrics: dict[str, list[dict]] = {}
        for xbrl_tag, label in target_tags.items():
            fact = us_gaap.get(xbrl_tag)
            if not fact:
                continue
            units = fact.get("units", {})
            # Most financial facts are in USD
            values = units.get("USD", units.get("pure", []))
            if not values:
                continue
            # Get the most recent annual (10-K) and quarterly (10-Q) values
            annual = [
                v for v in values
                if v.get("form") == "10-K" and v.get("val") is not None
            ]
            quarterly = [
                v for v in values
                if v.get("form") == "10-Q" and v.get("val") is not None
            ]
            # Sort by end date descending
            annual.sort(key=lambda v: v.get("end", ""), reverse=True)
            quarterly.sort(key=lambda v: v.get("end", ""), reverse=True)

            entries = []
            for v in annual[:3]:  # Last 3 annual periods
                entries.append({
                    "period": v.get("end", ""),
                    "value": v["val"],
                    "form": "10-K",
                    "filed": v.get("filed", ""),
                })
            for v in quarterly[:1]:  # Most recent quarter
                entries.append({
                    "period": v.get("end", ""),
                    "value": v["val"],
                    "form": "10-Q",
                    "filed": v.get("filed", ""),
                })

            if label not in metrics or len(entries) > len(metrics[label]):
                metrics[label] = entries

        return {
            "cik": padded,
            "name": raw.get("entityName", ""),
            "metrics": metrics,
        }

    async def get_filing_documents(
        self,
        cik: str | int,
        accession_number: str,
    ) -> dict[str, Any]:
        """List all documents within a specific filing.

        Use this to find Exhibit 21 (subsidiary list), Schedule 13D/G,
        and other exhibits by their description.
        """
        await self._rate_limit()
        cik_num = str(int(str(cik).lstrip("0") or "0"))
        acc_clean = accession_number.replace("-", "")
        # Filing index is on www.sec.gov as HTML
        resp = await self._www.get(
            f"/Archives/edgar/data/{cik_num}/{acc_clean}/{accession_number}-index.htm",
        )
        resp.raise_for_status()
        # Parse document links from the index page
        documents = []
        links = re.findall(
            r'<a\s+href="(/Archives/edgar/data/[^"]+)">([^<]+)</a>',
            resp.text, re.I,
        )
        for href, name in links:
            if name.endswith((".json", ".xsd")):
                continue
            documents.append({
                "name": name,
                "href": href,
            })
        # Also find exhibit descriptions from the table
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.I | re.S)
        doc_types = {}
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)
            if len(cells) >= 2:
                doc_type = re.sub(r"<[^>]+>", "", cells[0]).strip()
                doc_name = re.sub(r"<[^>]+>", "", cells[1]).strip()
                if doc_name:
                    doc_types[doc_name] = doc_type
        for doc in documents:
            doc["type"] = doc_types.get(doc["name"], "")
        return {
            "cik": cik_num,
            "accession_number": accession_number,
            "documents": documents,
            "filing_url": f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/",
        }

    async def get_subsidiary_list(self, cik: str | int) -> dict[str, Any]:
        """Extract Exhibit 21 (subsidiary list) from the most recent 10-K.

        Finds the latest 10-K filing, locates Exhibit 21, fetches its
        content, and parses subsidiary names and jurisdictions.
        """
        # Try recent filings first, fall back to search if no 10-K in recent
        filings = await self.get_filings(cik, form_type="10-K")
        if not filings.get("filings"):
            # Search for 10-K filings via full-text search
            padded = _pad_cik(cik)
            search = await self.search(
                query=f"cik:{padded}", forms="10-K", count=1,
            )
            if search.get("results"):
                r = search["results"][0]
                filings = {
                    "name": r.get("entity_name", ""),
                    "filings": [{
                        "accession_number": r.get("accession_number", ""),
                        "form": "10-K",
                        "filing_date": r.get("file_date", ""),
                        "primary_document": "",
                        "primary_doc_description": "",
                    }],
                }
        if not filings.get("filings"):
            return {"cik": str(cik), "name": filings.get("name", ""), "subsidiaries": [], "error": "No 10-K filings found"}

        latest = filings["filings"][0]
        accession = latest["accession_number"]

        docs = await self.get_filing_documents(cik, accession)

        # Find Exhibit 21 by filename or type
        ex21_doc = None
        for doc in docs.get("documents", []):
            name_lower = doc["name"].lower()
            doc_type = doc.get("type", "").lower()
            if ("ex21" in name_lower or "exhibit21" in name_lower
                    or "ex-21" in name_lower or "ex-21" in doc_type):
                ex21_doc = doc
                break

        if not ex21_doc:
            return {
                "cik": str(cik),
                "name": filings.get("name", ""),
                "subsidiaries": [],
                "filing_date": latest.get("filing_date", ""),
                "note": "No Exhibit 21 found in latest 10-K",
            }

        # Fetch the exhibit content via its href or constructed URL
        await self._rate_limit()
        if ex21_doc.get("href"):
            resp = await self._www.get(ex21_doc["href"])
        else:
            cik_num = str(int(str(cik).lstrip("0") or "0"))
            acc_clean = accession.replace("-", "")
            resp = await self._www.get(
                f"/Archives/edgar/data/{cik_num}/{acc_clean}/{ex21_doc['name']}",
            )
        resp.raise_for_status()
        content = resp.text

        # Parse subsidiaries from Exhibit 21 content
        subsidiaries = _parse_exhibit_21(content)

        return {
            "cik": str(cik),
            "name": filings.get("name", ""),
            "filing_date": latest.get("filing_date", ""),
            "accession_number": accession,
            "subsidiaries": subsidiaries,
            "count": len(subsidiaries),
        }


    async def _fetch_10k_primary(self, cik: str | int) -> dict[str, Any]:
        """Fetch the primary document HTML of the latest 10-K filing."""
        filings = await self.get_filings(cik, form_type="10-K")
        if not filings.get("filings"):
            return {"name": filings.get("name", ""), "html": "", "filing_date": ""}
        latest = filings["filings"][0]
        accession = latest["accession_number"]
        primary = latest.get("primary_document", "")
        if not primary:
            return {"name": filings.get("name", ""), "html": "", "filing_date": latest.get("filing_date", "")}
        await self._rate_limit()
        cik_num = str(int(str(cik).lstrip("0") or "0"))
        acc_clean = accession.replace("-", "")
        resp = await self._www.get(
            f"/Archives/edgar/data/{cik_num}/{acc_clean}/{primary}",
        )
        resp.raise_for_status()
        return {
            "name": filings.get("name", ""),
            "html": resp.text,
            "filing_date": latest.get("filing_date", ""),
            "accession_number": accession,
        }

    async def get_related_party_transactions(
        self, cik: str | int,
    ) -> dict[str, Any]:
        """Extract Item 13 (Related Party Transactions) from the latest 10-K."""
        doc = await self._fetch_10k_primary(cik)
        section = _extract_10k_section(
            doc["html"],
            r"Item\s*13",
            r"Item\s*14",
        )
        transactions = _parse_related_party_tables(section)
        return {
            "cik": str(cik),
            "name": doc["name"],
            "filing_date": doc.get("filing_date", ""),
            "section_text": _strip_tags(section),
            "transactions": transactions,
        }

    async def get_schedule_13d(self, cik: str | int) -> dict[str, Any]:
        """Get Schedule 13D/G filings showing beneficial ownership."""
        company = await self.get_company(cik)
        forms_13d = ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"]
        filings_found = [
            f for f in company.get("recent_filings", [])
            if f["form"] in forms_13d
        ]
        results = []
        for filing in filings_found[:5]:  # Cap at 5 most recent
            accession = filing["accession_number"]
            primary = filing.get("primary_document", "")
            if not primary:
                continue
            try:
                await self._rate_limit()
                cik_num = str(int(str(cik).lstrip("0") or "0"))
                acc_clean = accession.replace("-", "")
                resp = await self._www.get(
                    f"/Archives/edgar/data/{cik_num}/{acc_clean}/{primary}",
                )
                resp.raise_for_status()
                parsed = _parse_schedule_13d(resp.text)
                parsed["form"] = filing["form"]
                parsed["filing_date"] = filing.get("filing_date", "")
                parsed["accession_number"] = accession
                results.append(parsed)
            except Exception:
                results.append({
                    "form": filing["form"],
                    "filing_date": filing.get("filing_date", ""),
                    "error": "Failed to fetch/parse",
                })
        return {
            "cik": str(cik),
            "name": company.get("name", ""),
            "filings": results,
        }

    async def get_risk_factors(
        self,
        cik: str | int,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extract Item 1A (Risk Factors) from latest 10-K, filtered by keywords."""
        if keywords is None:
            keywords = [
                "legal proceeding", "litigation", "regulatory action",
                "investigation", "enforcement", "SEC", "DOJ",
                "indictment", "settlement", "consent decree", "class action",
            ]
        doc = await self._fetch_10k_primary(cik)
        section = _extract_10k_section(
            doc["html"],
            r"Item\s*1A",
            r"Item\s*1B|Item\s*2\b",
        )
        text = _strip_tags(section)
        # Split into paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z])", text) if p.strip()]
        matching = []
        for para in paragraphs:
            found = [kw for kw in keywords if kw.lower() in para.lower()]
            if found:
                matching.append({"text": para, "keywords_found": found})
        return {
            "cik": str(cik),
            "name": doc["name"],
            "filing_date": doc.get("filing_date", ""),
            "total_paragraphs": len(paragraphs),
            "matching_paragraphs": matching,
        }

    async def get_proxy_statement(self, cik: str | int) -> dict[str, Any]:
        """Extract executive compensation and board members from latest DEF 14A."""
        company = await self.get_company(cik)
        proxy_filings = [
            f for f in company.get("recent_filings", [])
            if f["form"] == "DEF 14A"
        ]
        if not proxy_filings:
            return {
                "cik": str(cik),
                "name": company.get("name", ""),
                "filing_date": "",
                "executives": [],
                "board_members": [],
                "note": "No DEF 14A filing found",
            }
        latest = proxy_filings[0]
        accession = latest["accession_number"]
        primary = latest.get("primary_document", "")
        if not primary:
            return {
                "cik": str(cik),
                "name": company.get("name", ""),
                "filing_date": latest.get("filing_date", ""),
                "executives": [],
                "board_members": [],
                "note": "No primary document in DEF 14A",
            }
        await self._rate_limit()
        cik_num = str(int(str(cik).lstrip("0") or "0"))
        acc_clean = accession.replace("-", "")
        resp = await self._www.get(
            f"/Archives/edgar/data/{cik_num}/{acc_clean}/{primary}",
        )
        resp.raise_for_status()
        html = resp.text
        executives = _parse_proxy_compensation(html)
        board_members = _parse_proxy_board(html)
        return {
            "cik": str(cik),
            "name": company.get("name", ""),
            "filing_date": latest.get("filing_date", ""),
            "accession_number": accession,
            "executives": executives,
            "board_members": board_members,
        }

    async def get_8k_events(
        self, cik: str | int, limit: int = 5,
    ) -> dict[str, Any]:
        """Get recent 8-K filings with extracted Item descriptions."""
        company = await self.get_company(cik)
        filings_8k = [
            f for f in company.get("recent_filings", [])
            if f["form"] == "8-K"
        ][:limit]
        events = []
        for filing in filings_8k:
            accession = filing["accession_number"]
            primary = filing.get("primary_document", "")
            if not primary:
                events.append({
                    "filing_date": filing.get("filing_date", ""),
                    "accession_number": accession,
                    "items": [],
                })
                continue
            try:
                await self._rate_limit()
                cik_num = str(int(str(cik).lstrip("0") or "0"))
                acc_clean = accession.replace("-", "")
                resp = await self._www.get(
                    f"/Archives/edgar/data/{cik_num}/{acc_clean}/{primary}",
                )
                resp.raise_for_status()
                items = _parse_8k_items(resp.text)
                events.append({
                    "filing_date": filing.get("filing_date", ""),
                    "accession_number": accession,
                    "items": items,
                })
            except Exception:
                events.append({
                    "filing_date": filing.get("filing_date", ""),
                    "accession_number": accession,
                    "items": [],
                    "error": "Failed to fetch/parse",
                })
        return {
            "cik": str(cik),
            "name": company.get("name", ""),
            "events": events,
            "count": len(events),
        }

    async def get_amendments(self, cik: str | int) -> dict[str, Any]:
        """Get 10-K/A and 10-Q/A amendment filings.

        The existence and timing of amendments is itself a risk signal —
        companies that repeatedly amend filings may be correcting errors
        or responding to SEC inquiries.
        """
        company = await self.get_company(cik)
        amendment_forms = {"10-K/A", "10-Q/A"}
        amendments = [
            {
                "form": f["form"],
                "filing_date": f.get("filing_date", ""),
                "accession_number": f["accession_number"],
            }
            for f in company.get("recent_filings", [])
            if f["form"] in amendment_forms
        ]
        return {
            "cik": str(cik),
            "name": company.get("name", ""),
            "amendments": amendments,
            "count": len(amendments),
        }


def _parse_proxy_compensation(html: str) -> list[dict[str, str]]:
    """Extract executive names and titles from compensation tables in DEF 14A."""
    executives = []
    # Look for compensation table rows: <tr><td>Name</td><td>Title</td>...
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.DOTALL)
        if len(cells) >= 2:
            name = _strip_tags(cells[0]).strip()
            title = _strip_tags(cells[1]).strip()
            # Filter: names should be 3-60 chars, not header-like
            if (3 <= len(name) <= 60 and name[0].isupper()
                    and name.lower() not in ("name", "total", "all others")):
                executives.append({"name": name, "title": title})
    return executives


def _parse_proxy_board(html: str) -> list[str]:
    """Extract board member names from DEF 14A proxy statement."""
    members = []
    # Pattern: <strong>Name</strong> or <b>Name</b> followed by director-like text
    patterns = [
        re.compile(r"<(?:strong|b)[^>]*>([\w\s.,'()-]{3,50})</(?:strong|b)>\s*,?\s*(?:Independent|Director|Chairman|Lead)", re.I),
        re.compile(r"(?:Director|Nominee)[^<]*<[^>]*>([\w\s.,'()-]{3,50})<", re.I),
    ]
    for pattern in patterns:
        for match in pattern.finditer(html):
            name = _strip_tags(match.group(1)).strip()
            if name and name not in members and len(name) >= 3:
                members.append(name)
    return members


# Standard 8-K Item number to description mapping
_8K_ITEMS = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate or Increase an Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.05": "Amendments to the Registrant's Code of Ethics",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


def _parse_8k_items(html: str) -> list[dict[str, str]]:
    """Extract Item numbers and their content from an 8-K filing."""
    items = []
    # Match "Item X.XX" headers
    item_pattern = re.compile(
        r"Item\s+(\d+\.\d{2})\b[.\s]*([^\n<]{0,200})",
        re.I,
    )
    matches = list(item_pattern.finditer(html))
    for i, match in enumerate(matches):
        item_num = match.group(1)
        # Get text between this item and the next (or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else start + 2000
        section_html = html[start:end]
        summary = _strip_tags(section_html)[:500].strip()
        items.append({
            "item": item_num,
            "title": _8K_ITEMS.get(item_num, match.group(2).strip()),
            "summary": summary,
        })
    return items


def _strip_tags(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"</(p|tr|div|li|td|th|h\d)[^>]*>", "\n", html, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _extract_10k_section(html: str, start_pattern: str, end_pattern: str) -> str:
    """Extract a section of a 10-K filing between two Item headers."""
    # Look for the section start
    start_match = re.search(start_pattern, html, re.I)
    if not start_match:
        return ""
    rest = html[start_match.start():]
    # Look for the next section header
    end_match = re.search(end_pattern, rest[10:], re.I)
    if end_match:
        return rest[:end_match.start() + 10]
    return rest


def _parse_related_party_tables(section_html: str) -> list[dict[str, str]]:
    """Extract counterparty/amount/description from tables in the section."""
    transactions = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", section_html, re.I | re.S)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)
        if len(cells) >= 2:
            name = re.sub(r"<[^>]+>", "", cells[0]).strip()
            amount = re.sub(r"<[^>]+>", "", cells[1]).strip() if len(cells) > 1 else ""
            desc = re.sub(r"<[^>]+>", "", cells[2]).strip() if len(cells) > 2 else ""
            if name and name.lower() not in ("name", "counterparty", "party"):
                transactions.append({
                    "counterparty": name,
                    "amount": amount,
                    "description": desc,
                })
    return transactions


def _parse_schedule_13d(html: str) -> dict[str, str]:
    """Parse Schedule 13D/G for ownership details."""
    text = _strip_tags(html)
    result: dict[str, str] = {
        "reporting_person": "",
        "source_of_funds": "",
        "purpose": "",
        "percent_of_class": "",
    }
    # Item 2 — Identity
    m = re.search(r"Item\s*2[.\s]+(.*?)(?=Item\s*3|$)", text, re.I | re.S)
    if m:
        result["reporting_person"] = m.group(1).strip()[:500]
    # Item 3 — Source of Funds
    m = re.search(r"Item\s*3[.\s]+(.*?)(?=Item\s*4|$)", text, re.I | re.S)
    if m:
        result["source_of_funds"] = m.group(1).strip()[:500]
    # Item 4 — Purpose
    m = re.search(r"Item\s*4[.\s]+(.*?)(?=Item\s*5|$)", text, re.I | re.S)
    if m:
        result["purpose"] = m.group(1).strip()[:500]
    # Percent of class — look for percentage
    m = re.search(r"(?:percent\s+of\s+class|%\s*of\s*class)[:\s]*(\d+\.?\d*)%?", text, re.I)
    if not m:
        m = re.search(r"(\d+\.?\d*)\s*%", text)
    if m:
        result["percent_of_class"] = m.group(1) + "%"
    return result


def _parse_exhibit_21(html_content: str) -> list[dict[str, str]]:
    """Parse subsidiary names and jurisdictions from Exhibit 21 HTML/text.

    Exhibit 21 typically contains a table or list of subsidiaries with
    their name and jurisdiction of incorporation/organization.
    """
    subsidiaries: list[dict[str, str]] = []

    # Strategy 1: Parse HTML table rows directly (most reliable)
    if "<tr" in html_content.lower():
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_content, re.I | re.S)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.I | re.S)
            if len(cells) >= 2:
                # Strip HTML from cell contents
                name = re.sub(r"<[^>]+>", "", cells[0]).strip()
                name = re.sub(r"&nbsp;|&#160;", " ", name).strip()
                jur = re.sub(r"<[^>]+>", "", cells[-1]).strip()
                jur = re.sub(r"&nbsp;|&#160;", " ", jur).strip()
                # Skip header rows and empty rows
                if (name and jur and len(name) > 2
                        and "jurisdiction" not in name.lower()
                        and "name" != name.lower()
                        and not name.startswith("*")):
                    subsidiaries.append({"name": name, "jurisdiction": jur})
        if subsidiaries:
            return subsidiaries

    # Strategy 2: Plain text / fallback
    if "<" in html_content:
        text = re.sub(r"</(p|tr|div|li|td|th)[^>]*>", "\n", html_content, flags=re.I)
        text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"&#\d+;", " ", text)
    else:
        text = html_content

    subsidiaries = []

    # Common patterns in Exhibit 21:
    # "Subsidiary Name    Delaware" or "Subsidiary Name (Delaware)"
    # or table rows with name and jurisdiction columns

    # Pattern 1: "Name .... Jurisdiction" (dot/space separated)
    # Pattern 2: "Name (Jurisdiction)"
    # Pattern 3: Tab or multi-space separated

    # Try to find lines with jurisdiction keywords
    jurisdiction_keywords = {
        "delaware", "nevada", "california", "new york", "texas",
        "florida", "virginia", "maryland", "massachusetts",
        "british virgin islands", "bvi", "cayman islands",
        "bermuda", "hong kong", "singapore", "luxembourg",
        "ireland", "netherlands", "united kingdom", "england",
        "england and wales", "scotland", "jersey", "guernsey",
        "switzerland", "panama", "bahamas", "mauritius",
        "japan", "australia", "canada", "germany", "france",
        "brazil", "india", "china", "south korea", "israel",
        "spain", "italy", "portugal", "belgium", "sweden",
        "norway", "denmark", "finland", "austria", "mexico",
        "colombia", "chile", "argentina", "south africa",
        "nigeria", "kenya", "egypt", "uae", "dubai",
        "qatar", "saudi arabia", "hungary", "czech republic",
        "poland", "romania", "greece", "turkey", "thailand",
        "indonesia", "philippines", "vietnam", "malaysia",
        "new zealand", "cyprus", "malta", "isle of man",
        "seychelles", "marshall islands", "liberia",
    }

    # Split into candidate lines
    lines = re.split(r"[;\n\r]+", text)
    for line in lines:
        line = line.strip()
        if len(line) < 5 or len(line) > 300:
            continue

        # Try parenthetical jurisdiction: "Company Name (Delaware)"
        m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", line)
        if m:
            name, jur = m.group(1).strip(), m.group(2).strip()
            if jur.lower() in jurisdiction_keywords and len(name) > 2:
                subsidiaries.append({"name": name, "jurisdiction": jur})
                continue

        # Try multi-space/tab separated: "Company Name          Delaware"
        parts = re.split(r"\s{3,}|\t+|\.{3,}", line)
        if len(parts) >= 2:
            name = parts[0].strip()
            jur = parts[-1].strip()
            if jur.lower() in jurisdiction_keywords and len(name) > 2:
                subsidiaries.append({"name": name, "jurisdiction": jur})
                continue

    return subsidiaries
