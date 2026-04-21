"""Tests for GLEIF, SEC EDGAR, UK Companies House, CourtListener, and Wikidata clients.

Uses httpx mock transport to avoid hitting real APIs in tests.
"""

import json
import pytest
import httpx
from sift.gleif_client import GLEIFClient
from sift.sec_client import SECEdgarClient, _pad_cik
from sift.companies_house_client import CompaniesHouseClient
from sift.courtlistener_client import CourtListenerClient, _extract_amount
from sift.wikidata_client import WikidataClient


# =============================================================================
# Mock transport (shared)
# =============================================================================

class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[str, dict]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        path = request.url.path
        # Check query params too for routes that need them
        for pattern, response_data in self.routes.items():
            if pattern in path or pattern in url:
                if "html" in response_data:
                    return httpx.Response(
                        status_code=response_data.get("status", 200),
                        text=response_data["html"],
                        headers={"content-type": "text/html"},
                    )
                return httpx.Response(
                    status_code=response_data.get("status", 200),
                    json=response_data.get("json", {}),
                )
        return httpx.Response(status_code=404, json={"error": "not found"})


# =============================================================================
# GLEIF Client tests
# =============================================================================

class TestGLEIFClient:
    LEI_RECORD = {
        "id": "549300TEST00LEI001",
        "attributes": {
            "lei": "549300TEST00LEI001",
            "entity": {
                "legalName": {"name": "Test Corp"},
                "status": "ACTIVE",
                "jurisdiction": "US-DE",
                "legalForm": {"id": "8888"},
                "category": "GENERAL",
                "legalAddress": {
                    "country": "US",
                    "city": "Wilmington",
                    "addressLines": ["100 Test St"],
                },
            },
            "registration": {
                "status": "ISSUED",
                "initialRegistrationDate": "2020-01-01",
                "lastUpdateDate": "2024-06-01",
                "managingLou": "EVK05KS7XY1DEII3R011",
            },
        },
    }

    @pytest.fixture
    def mock_routes(self):
        return {
            # Specific routes first (checked via substring match)
            "/direct-parent": {"json": {"data": []}},
            "/ultimate-parent": {"json": {"data": []}},
            "/direct-child": {"json": {"data": []}},
            "/549300TEST00LEI001": {
                "json": {"data": self.LEI_RECORD},
            },
            "/lei-records": {
                "json": {
                    "meta": {"pagination": {"total": 1}},
                    "data": [self.LEI_RECORD],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = GLEIFClient()
        c._client = httpx.AsyncClient(
            base_url="https://api.gleif.org/api/v1",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_search_returns_normalized(self, client):
        result = await client.search("Test Corp")
        assert result["total"] == 1
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["lei"] == "549300TEST00LEI001"
        assert r["legal_name"] == "Test Corp"
        assert r["country"] == "US"
        assert r["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_lei(self, client):
        result = await client.get_lei("549300TEST00LEI001")
        assert result["lei"] == "549300TEST00LEI001"
        assert result["legal_name"] == "Test Corp"

    @pytest.mark.asyncio
    async def test_get_ownership(self, client):
        result = await client.get_ownership("549300TEST00LEI001")
        assert result["lei"] == "549300TEST00LEI001"
        assert result["direct_parent"] is None
        assert result["children"] == []


# =============================================================================
# SEC EDGAR Client tests
# =============================================================================

class TestSECEdgarClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search-index": {
                "json": {
                    "hits": {
                        "total": {"value": 1},
                        "hits": [
                            {
                                "_source": {
                                    "file_type": "10-K",
                                    "entity_name": "APPLE INC",
                                    "file_date": "2024-11-01",
                                    "period_of_report": "2024-09-28",
                                    "file_num": "001-36743",
                                    "entity_id": "320193",
                                    "display_names": ["APPLE INC"],
                                }
                            }
                        ],
                    }
                }
            },
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "entityType": "operating",
                    "sic": "3571",
                    "sicDescription": "Electronic Computers",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0928",
                    "addresses": {"mailing": {}, "business": {}},
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-24-000001"],
                            "form": ["10-K"],
                            "filingDate": ["2024-11-01"],
                            "primaryDocument": ["aapl-20240928.htm"],
                            "primaryDocDescription": ["10-K"],
                        },
                        "files": [],
                    },
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST",
            transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov",
            transport=transport,
        )
        return c

    def test_pad_cik(self):
        assert _pad_cik(320193) == "0000320193"
        assert _pad_cik("320193") == "0000320193"
        assert _pad_cik("0000320193") == "0000320193"

    @pytest.mark.asyncio
    async def test_search(self, client):
        result = await client.search("Apple")
        assert result["total"] == 1
        assert result["results"][0]["entity_name"] == "APPLE INC"
        assert result["results"][0]["filing_type"] == "10-K"

    @pytest.mark.asyncio
    async def test_get_company(self, client):
        result = await client.get_company(320193)
        assert result["name"] == "Apple Inc."
        assert result["tickers"] == ["AAPL"]
        assert len(result["recent_filings"]) == 1

    @pytest.mark.asyncio
    async def test_get_filings(self, client):
        result = await client.get_filings(320193, form_type="10-K")
        assert result["count"] == 1
        assert result["filings"][0]["form"] == "10-K"


class TestSECCompanyFacts:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/api/xbrl/companyfacts/": {
                "json": {
                    "entityName": "Apple Inc.",
                    "cik": 320193,
                    "facts": {
                        "us-gaap": {
                            "Assets": {
                                "units": {
                                    "USD": [
                                        {"val": 352583000000, "end": "2023-09-30", "form": "10-K", "filed": "2023-11-03"},
                                        {"val": 338516000000, "end": "2022-09-24", "form": "10-K", "filed": "2022-10-28"},
                                    ]
                                }
                            },
                            "Revenues": {
                                "units": {
                                    "USD": [
                                        {"val": 383285000000, "end": "2023-09-30", "form": "10-K", "filed": "2023-11-03"},
                                    ]
                                }
                            },
                            "NetIncomeLoss": {
                                "units": {
                                    "USD": [
                                        {"val": 96995000000, "end": "2023-09-30", "form": "10-K", "filed": "2023-11-03"},
                                    ]
                                }
                            },
                        }
                    },
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_company_facts(self, client):
        result = await client.get_company_facts(320193)
        assert result["name"] == "Apple Inc."
        assert "total_assets" in result["metrics"]
        assert result["metrics"]["total_assets"][0]["value"] == 352583000000
        assert "revenue" in result["metrics"]
        assert "net_income" in result["metrics"]


class TestExhibit21Parser:
    def test_parse_parenthetical_jurisdiction(self):
        from sift.sec_client import _parse_exhibit_21
        html = """
        <p>Apple Operations International (Ireland)</p>
        <p>Apple Sales International (Ireland)</p>
        <p>Beats Electronics LLC (Delaware)</p>
        """
        result = _parse_exhibit_21(html)
        assert len(result) == 3
        assert result[0]["name"] == "Apple Operations International"
        assert result[0]["jurisdiction"] == "Ireland"
        assert result[2]["jurisdiction"] == "Delaware"

    def test_parse_space_separated(self):
        from sift.sec_client import _parse_exhibit_21
        text = """Apple Operations International         Ireland
Beats Electronics LLC                  Delaware
Apple Japan LLC                        Japan"""
        result = _parse_exhibit_21(text)
        assert len(result) == 3
        assert result[1]["name"] == "Beats Electronics LLC"

    def test_parse_empty(self):
        from sift.sec_client import _parse_exhibit_21
        result = _parse_exhibit_21("")
        assert result == []


# =============================================================================
# UK Companies House Client tests
# =============================================================================

class TestCompaniesHouseClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search/companies": {
                "json": {
                    "total_results": 1,
                    "items": [
                        {
                            "company_number": "00000001",
                            "title": "TEST COMPANY LTD",
                            "company_status": "active",
                            "address_snippet": "London",
                        }
                    ],
                }
            },
            "/search/officers": {
                "json": {
                    "total_results": 1,
                    "items": [
                        {
                            "title": "John Smith",
                            "links": {"self": "/officers/abc123/appointments"},
                        }
                    ],
                }
            },
            "/company/00000001/officers": {
                "json": {
                    "items": [
                        {"name": "SMITH, John", "officer_role": "director"},
                    ],
                }
            },
            "/company/00000001/persons-with-significant-control": {
                "json": {
                    "items": [
                        {
                            "name": "Mr John Smith",
                            "natures_of_control": [
                                "ownership-of-shares-75-to-100-percent"
                            ],
                        }
                    ],
                }
            },
            "/company/00000001": {
                "json": {
                    "company_number": "00000001",
                    "company_name": "TEST COMPANY LTD",
                    "company_status": "active",
                    "type": "ltd",
                    "date_of_creation": "2020-01-01",
                    "registered_office_address": {"locality": "London"},
                }
            },
            "/officers/abc123/appointments": {
                "json": {
                    "items": [
                        {
                            "appointed_to": {"company_number": "00000001"},
                            "name": "SMITH, John",
                            "officer_role": "director",
                        }
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CompaniesHouseClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.company-information.service.gov.uk",
            transport=transport,
            auth=("test-key", ""),
        )
        return c

    @pytest.mark.asyncio
    async def test_search_company(self, client):
        result = await client.search_company("Test")
        assert result["total_results"] == 1
        assert result["items"][0]["company_number"] == "00000001"

    @pytest.mark.asyncio
    async def test_search_officer(self, client):
        result = await client.search_officer("Smith")
        assert result["total_results"] == 1

    @pytest.mark.asyncio
    async def test_get_company(self, client):
        result = await client.get_company("00000001")
        assert result["company_name"] == "TEST COMPANY LTD"

    @pytest.mark.asyncio
    async def test_get_officers(self, client):
        result = await client.get_officers("00000001")
        assert result["items"][0]["name"] == "SMITH, John"

    @pytest.mark.asyncio
    async def test_get_pscs(self, client):
        result = await client.get_pscs("00000001")
        assert "ownership" in result["items"][0]["natures_of_control"][0]

    @pytest.mark.asyncio
    async def test_get_officer_appointments(self, client):
        result = await client.get_officer_appointments("abc123")
        assert result["items"][0]["appointed_to"]["company_number"] == "00000001"


# =============================================================================
# CourtListener Client tests
# =============================================================================

class TestCourtListenerClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search/": {
                "json": {
                    "count": 1,
                    "results": [
                        {
                            "docket_id": 12345,
                            "caseName": "United States v. Test",
                            "court": "Supreme Court",
                            "dateFiled": "2024-01-15",
                        }
                    ],
                }
            },
            "/dockets/12345": {
                "json": {
                    "id": 12345,
                    "case_name": "United States v. Test",
                    "court": "scotus",
                    "date_filed": "2024-01-15",
                    "docket_number": "23-1234",
                }
            },
            "/people/": {
                "json": {
                    "count": 1,
                    "results": [
                        {"id": 1, "name_full": "John G. Roberts Jr."},
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CourtListenerClient(api_token="test-token")
        c._client = httpx.AsyncClient(
            base_url="https://www.courtlistener.com/api/rest/v4",
            transport=transport,
            headers={"Authorization": "Token test-token"},
        )
        return c

    @pytest.mark.asyncio
    async def test_search_dockets(self, client):
        result = await client.search("test case", type="r")
        assert result["count"] == 1
        assert result["results"][0]["caseName"] == "United States v. Test"

    @pytest.mark.asyncio
    async def test_get_docket(self, client):
        result = await client.get_docket(12345)
        assert result["id"] == 12345
        assert result["case_name"] == "United States v. Test"

    @pytest.mark.asyncio
    async def test_search_people(self, client):
        result = await client.search_people("Roberts")
        assert result["count"] == 1


# =============================================================================
# SEC EDGAR — Related Party, 13D, Risk Factors tests
# =============================================================================

class TestSECRelatedParty:
    FILING_INDEX_HTML = """
    <table>
    <tr><td>10-K</td><td>aapl-20240928.htm</td></tr>
    <tr><td>EX-21</td><td>aapl-20240928_ex21.htm</td></tr>
    </table>
    """

    TEN_K_HTML = """
    <html><body>
    <h2>Item 12. Security Ownership</h2>
    <p>Some security ownership info.</p>
    <h2>Item 13. Certain Relationships and Related Transactions</h2>
    <p>During fiscal year 2024, the Company entered into a consulting
    agreement with Acme Partners, a firm controlled by Board Member
    Jane Doe, for $2,500,000 in advisory services.</p>
    <table><tr><td>Acme Partners</td><td>$2,500,000</td><td>Consulting</td></tr></table>
    <h2>Item 14. Principal Accountant Fees</h2>
    <p>Audit fees.</p>
    </body></html>
    """

    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "entityType": "operating",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "sicDescription": "Electronic Computers",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0928",
                    "addresses": {"mailing": {}, "business": {}},
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-24-000001"],
                            "form": ["10-K"],
                            "filingDate": ["2024-11-01"],
                            "primaryDocument": ["aapl-20240928.htm"],
                            "primaryDocDescription": ["10-K"],
                        },
                        "files": [],
                    },
                }
            },
            "-index.htm": {"html": self.FILING_INDEX_HTML},
            "aapl-20240928.htm": {"html": self.TEN_K_HTML},
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_related_party_transactions(self, client):
        result = await client.get_related_party_transactions(320193)
        assert result["name"] == "Apple Inc."
        assert "Acme Partners" in result["section_text"]
        assert result["filing_date"] == "2024-11-01"

    @pytest.mark.asyncio
    async def test_get_risk_factors(self, client):
        # Our mock 10-K doesn't have Item 1A, so should return empty
        result = await client.get_risk_factors(320193)
        assert result["name"] == "Apple Inc."
        assert result["matching_paragraphs"] == []


class TestSECSchedule13D:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "entityType": "operating",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "sicDescription": "Electronic Computers",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0928",
                    "addresses": {"mailing": {}, "business": {}},
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-24-000099"],
                            "form": ["SC 13D"],
                            "filingDate": ["2024-06-15"],
                            "primaryDocument": ["sc13d.htm"],
                            "primaryDocDescription": ["SC 13D"],
                        },
                        "files": [],
                    },
                }
            },
            "sc13d.htm": {
                "html": """
                <html><body>
                <p>Item 2. Identity and Background</p>
                <p>Warren Buffett, Omaha, NE</p>
                <p>Item 3. Source and Amount of Funds</p>
                <p>Personal funds</p>
                <p>Item 4. Purpose of Transaction</p>
                <p>Long-term investment. No intent to acquire control.</p>
                <p>Item 5. Interest in Securities</p>
                <p>Percent of Class: 5.2%</p>
                </body></html>
                """,
            },
            "-index.htm": {
                "html": "<table><tr><td>SC 13D</td><td>sc13d.htm</td></tr></table>",
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_schedule_13d(self, client):
        result = await client.get_schedule_13d(320193)
        assert len(result["filings"]) == 1
        f = result["filings"][0]
        assert f["form"] == "SC 13D"
        assert f["filing_date"] == "2024-06-15"
        assert "5.2" in (f.get("percent_of_class") or "")


class TestSECRiskFactors:
    TEN_K_WITH_RISKS = """
    <html><body>
    <h2>Item 1. Business</h2>
    <p>We sell things.</p>
    <h2>Item 1A. Risk Factors</h2>
    <p>We are subject to various legal proceedings and regulatory investigations
    that could result in material losses.</p>
    <p>The SEC has opened an investigation into our accounting practices.</p>
    <p>Our stock price may fluctuate.</p>
    <p>Competition in our industry is intense.</p>
    <h2>Item 1B. Unresolved Staff Comments</h2>
    </body></html>
    """

    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "entityType": "operating",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "sicDescription": "Electronic Computers",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0928",
                    "addresses": {"mailing": {}, "business": {}},
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-24-000001"],
                            "form": ["10-K"],
                            "filingDate": ["2024-11-01"],
                            "primaryDocument": ["aapl-20240928.htm"],
                            "primaryDocDescription": ["10-K"],
                        },
                        "files": [],
                    },
                }
            },
            "-index.htm": {
                "html": "<table><tr><td>10-K</td><td>aapl-20240928.htm</td></tr></table>",
            },
            "aapl-20240928.htm": {"html": self.TEN_K_WITH_RISKS},
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_risk_factors_with_keywords(self, client):
        result = await client.get_risk_factors(320193)
        assert result["name"] == "Apple Inc."
        # Should match paragraphs with "legal proceeding", "investigation", "SEC"
        assert len(result["matching_paragraphs"]) >= 2
        keywords_found = set()
        for p in result["matching_paragraphs"]:
            keywords_found.update(p["keywords_found"])
        assert "SEC" in keywords_found or "investigation" in keywords_found

    @pytest.mark.asyncio
    async def test_risk_factors_custom_keywords(self, client):
        result = await client.get_risk_factors(320193, keywords=["stock price"])
        assert len(result["matching_paragraphs"]) == 1
        assert "stock price" in result["matching_paragraphs"][0]["keywords_found"]


# =============================================================================
# Companies House enrichment tests
# =============================================================================

class TestCompaniesHouseEnriched:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/company/00000001/filing-history": {
                "json": {
                    "total_count": 5,
                    "items": [
                        {"date": "2024-06-01", "category": "accounts",
                         "type": "AA", "description": "Full accounts"},
                        {"date": "2024-03-01", "category": "confirmation-statement",
                         "type": "CS01", "description": "Confirmation statement"},
                        {"date": "2023-06-01", "category": "accounts",
                         "type": "AA", "description": "Full accounts"},
                        {"date": "2023-03-01", "category": "confirmation-statement",
                         "type": "CS01", "description": "Confirmation statement"},
                        {"date": "2021-01-15", "category": "address",
                         "type": "AD01", "description": "Change of registered office"},
                    ],
                }
            },
            "/company/00000001/charges": {
                "json": {
                    "total_count": 1,
                    "items": [
                        {
                            "charge_number": 1,
                            "status": "outstanding",
                            "classification": {"description": "Floating charge"},
                            "persons_entitled": [{"name": "HSBC Bank"}],
                            "created_on": "2022-01-15",
                            "delivered_on": "2022-01-20",
                            "satisfied_on": None,
                            "particulars": {"description": "All assets"},
                        }
                    ],
                }
            },
            "/company/00000001": {
                "json": {
                    "company_number": "00000001",
                    "company_name": "TEST COMPANY LTD",
                    "company_status": "active",
                    "type": "ltd",
                    "date_of_creation": "2020-01-01",
                    "registered_office_address": {"locality": "London"},
                    "accounts": {
                        "last_accounts": {
                            "type": "full",
                            "period_start_on": "2023-07-01",
                            "period_end_on": "2024-06-30",
                        },
                        "next_due": "2025-03-30",
                        "overdue": False,
                        "accounting_reference_date": {"month": "06", "day": "30"},
                    },
                }
            },
            "/company/00000001/officers": {
                "json": {"items": [{"name": "SMITH, John", "officer_role": "director"}]}
            },
            "/company/00000001/persons-with-significant-control": {
                "json": {"items": []}
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CompaniesHouseClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.company-information.service.gov.uk",
            transport=transport,
            auth=("test-key", ""),
        )
        return c

    @pytest.mark.asyncio
    async def test_get_filing_history(self, client):
        result = await client.get_filing_history("00000001")
        assert result["total_count"] == 5
        assert len(result["items"]) == 5
        # Should detect address change
        gaps = result["filing_gaps"]
        address_changes = [g for g in gaps if g["type"] == "address_change"]
        assert len(address_changes) == 1

    @pytest.mark.asyncio
    async def test_get_filing_history_with_category(self, client):
        result = await client.get_filing_history("00000001", category="accounts")
        assert result["company_number"] == "00000001"

    @pytest.mark.asyncio
    async def test_get_accounts(self, client):
        result = await client.get_accounts("00000001")
        assert result["overdue"] is False
        assert result["accounts_type"] == "full"
        assert result["next_due"] == "2025-03-30"

    @pytest.mark.asyncio
    async def test_get_charges(self, client):
        result = await client.get_charges("00000001")
        assert result["total_count"] == 1
        c = result["charges"][0]
        assert c["status"] == "outstanding"
        assert "HSBC" in c["persons_entitled"][0]
        assert c["particulars"] == "All assets"

    @pytest.mark.asyncio
    async def test_get_confirmation_statements(self, client):
        result = await client.get_confirmation_statements("00000001")
        assert result["total_count"] == 5  # Returns all filing history items
        # No large gaps in our test data
        assert isinstance(result["gaps"], list)


# =============================================================================
# CourtListener enrichment tests
# =============================================================================

class TestCourtListenerEnriched:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/docket-entries/": {
                "json": {
                    "count": 2,
                    "results": [
                        {
                            "entry_number": 1,
                            "date_filed": "2024-01-15",
                            "description": "COMPLAINT for damages",
                            "recap_documents": [
                                {
                                    "id": 999,
                                    "description": "Complaint",
                                    "document_type": "complaint",
                                    "page_count": 45,
                                }
                            ],
                        },
                        {
                            "entry_number": 2,
                            "date_filed": "2024-02-01",
                            "description": "ANSWER to Complaint",
                            "recap_documents": [],
                        },
                    ],
                }
            },
            "/recap-documents/999": {
                "json": {
                    "id": 999,
                    "description": "Complaint",
                    "document_type": "complaint",
                    "plain_text": "Plaintiff seeks damages in excess of $75,000. "
                                  "The amount in controversy exceeds $5,000,000.",
                    "page_count": 45,
                    "filepath_local": "/path/to/doc.pdf",
                }
            },
            "/parties/": {
                "json": {
                    "count": 2,
                    "results": [
                        {
                            "name": "John Smith",
                            "party_types": [{"name": "Plaintiff"}],
                            "attorneys": [
                                {"attorney": {"name": "Jane Doe, Esq."}},
                            ],
                            "date_terminated": None,
                        },
                        {
                            "name": "Acme Corporation",
                            "party_types": [{"name": "Defendant"}],
                            "attorneys": [],
                            "date_terminated": None,
                        },
                    ],
                }
            },
            "/dockets/12345": {
                "json": {
                    "id": 12345,
                    "case_name": "Smith v. Acme Corp",
                    "nature_of_suit": "440 Civil Rights: Other",
                    "cause": "42 U.S.C. § 1983",
                    "jury_demand": "Plaintiff",
                    "jurisdiction_type": "Federal question",
                    "date_filed": "2024-01-15",
                    "date_terminated": None,
                    "court": "cacd",
                }
            },
            "/dockets/?related_docket=12345": {
                "json": {"count": 0, "results": []},
            },
            "/search/": {
                "json": {"count": 0, "results": []},
            },
            "/people/": {
                "json": {"count": 0, "results": []},
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CourtListenerClient(api_token="test-token")
        c._client = httpx.AsyncClient(
            base_url="https://www.courtlistener.com/api/rest/v4",
            transport=transport,
            headers={"Authorization": "Token test-token"},
        )
        return c

    @pytest.mark.asyncio
    async def test_get_docket_entries(self, client):
        result = await client.get_docket_entries(12345)
        assert result["count"] == 2
        assert result["entries"][0]["entry_number"] == 1
        assert len(result["entries"][0]["recap_documents"]) == 1

    @pytest.mark.asyncio
    async def test_get_recap_document(self, client):
        result = await client.get_recap_document(999)
        assert "Plaintiff seeks damages" in result["plain_text"]
        assert result["page_count"] == 45

    @pytest.mark.asyncio
    async def test_get_parties(self, client):
        result = await client.get_parties(12345)
        assert len(result["parties"]) == 2
        plaintiff = result["parties"][0]
        assert plaintiff["name"] == "John Smith"
        assert plaintiff["party_type"] == "Plaintiff"
        assert "Jane Doe" in plaintiff["attorneys"][0]

    @pytest.mark.asyncio
    async def test_get_docket_detail(self, client):
        result = await client.get_docket_detail(12345)
        assert result["case_name"] == "Smith v. Acme Corp"
        assert result["nature_of_suit"] == "440 Civil Rights: Other"
        assert result["cause"] == "42 U.S.C. § 1983"
        assert len(result["parties"]) == 2

    @pytest.mark.asyncio
    async def test_get_complaint_text(self, client):
        result = await client.get_complaint_text(12345)
        assert result["complaint_text"] is not None
        assert "Plaintiff seeks damages" in result["complaint_text"]
        assert result["amount_in_dispute"] is not None
        assert "5,000,000" in result["amount_in_dispute"]

    def test_extract_amount(self):
        text = "Plaintiff seeks damages in excess of $75,000."
        assert _extract_amount(text) == "$75,000"

    def test_extract_amount_millions(self):
        text = "The amount in controversy exceeds $5 million in damages."
        result = _extract_amount(text)
        assert result is not None
        assert "5" in result

    def test_extract_amount_none(self):
        text = "The defendant denies all allegations."
        assert _extract_amount(text) is None


# =============================================================================
# Wikidata enrichment tests
# =============================================================================

class TestWikidataEnriched:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/sparql": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "relative": {"value": "http://www.wikidata.org/entity/Q514717"},
                                "relativeLabel": {"value": "Sindika Dokolo"},
                                "relationship": {"value": "spouse"},
                                "start": {"value": "2002-01-01T00:00:00Z"},
                                "end": {"value": "2020-10-29T00:00:00Z"},
                            },
                            {
                                "relative": {"value": "http://www.wikidata.org/entity/Q57313"},
                                "relativeLabel": {"value": "José Eduardo dos Santos"},
                                "relationship": {"value": "father"},
                            },
                        ]
                    }
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = WikidataClient()
        c._client = httpx.AsyncClient(
            timeout=30.0,
            transport=transport,
            headers={"User-Agent": "test", "Accept": "application/json"},
        )
        return c

    @pytest.mark.asyncio
    async def test_get_family(self, client):
        result = await client.get_family("Q456034")
        assert result["entity_id"] == "Q456034"
        # Should have parsed the SPARQL results into family structure
        all_relatives = (
            result.get("spouse", []) + result.get("parents", [])
            + result.get("children", []) + result.get("siblings", [])
        )
        names = [r["name"] for r in all_relatives]
        assert "Sindika Dokolo" in names or "José Eduardo dos Santos" in names

    @pytest.mark.asyncio
    async def test_get_citizenship(self, client):
        result = await client.get_citizenship("Q456034")
        assert result["entity_id"] == "Q456034"
        assert isinstance(result["citizenships"], list)

    @pytest.mark.asyncio
    async def test_get_education_career(self, client):
        result = await client.get_education_career("Q456034")
        assert isinstance(result.get("education", []), list)
        assert isinstance(result.get("employers", []), list)
        assert isinstance(result.get("board_memberships", []), list)


class TestWikidataDateXref:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/sparql": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "position": {"value": "http://www.wikidata.org/entity/Q484876"},
                                "positionLabel": {"value": "CEO"},
                                "start": {"value": "2016-05-01T00:00:00Z"},
                            },
                            {
                                "inception": {"value": "2016-07-15T00:00:00Z"},
                                "companyLabel": {"value": "Test Offshore Corp"},
                                "company": {"value": "http://www.wikidata.org/entity/Q999"},
                            },
                        ]
                    }
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = WikidataClient()
        c._client = httpx.AsyncClient(
            timeout=30.0,
            transport=transport,
            headers={"User-Agent": "test", "Accept": "application/json"},
        )
        return c

    @pytest.mark.asyncio
    async def test_cross_reference_dates(self, client):
        result = await client.cross_reference_dates("Q456034", ["Q999"])
        assert result["person_id"] == "Q456034"
        assert isinstance(result.get("temporal_overlaps", []), list)


# =============================================================================
# Companies House — new tools tests
# =============================================================================

class TestCompaniesHouseDisqualified:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search/disqualified-officers": {
                "json": {
                    "total_results": 1,
                    "items": [
                        {
                            "title": "John Fraudster",
                            "address_snippet": "London",
                            "links": {
                                "self": "/disqualified-officers/natural/abc999",
                            },
                        }
                    ],
                }
            },
            "/disqualified-officers/natural/abc999": {
                "json": {
                    "name": "John Fraudster",
                    "disqualifications": [
                        {
                            "disqualified_from": "2020-01-01",
                            "disqualified_until": "2035-01-01",
                            "reason": {
                                "description_identifier": "fraud-or-breach-of-duty",
                                "act": "Company Directors Disqualification Act 1986",
                                "section": "6",
                            },
                            "case_identifier": "CASE-001",
                            "company_names": ["SCAM LTD"],
                        }
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CompaniesHouseClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.company-information.service.gov.uk",
            transport=transport,
            auth=("test-key", ""),
        )
        return c

    @pytest.mark.asyncio
    async def test_search_disqualified(self, client):
        result = await client.search_disqualified("Fraudster")
        assert result["total_results"] == 1
        assert result["items"][0]["title"] == "John Fraudster"

    @pytest.mark.asyncio
    async def test_get_disqualified_officer(self, client):
        result = await client.get_disqualified_officer("abc999")
        assert result["name"] == "John Fraudster"
        assert len(result["disqualifications"]) == 1
        assert result["disqualifications"][0]["disqualified_from"] == "2020-01-01"


class TestCompaniesHouseInsolvency:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/company/00000001/insolvency": {
                "json": {
                    "cases": [
                        {
                            "type": "compulsory-liquidation",
                            "dates": [
                                {"type": "wound-up-on", "date": "2023-06-15"},
                            ],
                            "practitioners": [
                                {
                                    "name": "Mr IP Smith",
                                    "role": "liquidator",
                                    "appointed_on": "2023-06-15",
                                }
                            ],
                        }
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CompaniesHouseClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.company-information.service.gov.uk",
            transport=transport,
            auth=("test-key", ""),
        )
        return c

    @pytest.mark.asyncio
    async def test_get_insolvency(self, client):
        result = await client.get_insolvency("00000001")
        assert len(result["cases"]) == 1
        assert result["cases"][0]["type"] == "compulsory-liquidation"
        assert result["cases"][0]["practitioners"][0]["name"] == "Mr IP Smith"


class TestCompaniesHouseDissolved:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/dissolved-search/companies": {
                "json": {
                    "total_results": 1,
                    "items": [
                        {
                            "company_number": "99999999",
                            "company_name": "DEFUNCT SHELL LTD",
                            "company_status": "dissolved",
                            "date_of_cessation": "2022-03-01",
                            "date_of_creation": "2015-01-01",
                        }
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CompaniesHouseClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.company-information.service.gov.uk",
            transport=transport,
            auth=("test-key", ""),
        )
        return c

    @pytest.mark.asyncio
    async def test_search_dissolved(self, client):
        result = await client.search_dissolved("Defunct Shell")
        assert result["total_results"] == 1
        assert result["items"][0]["company_name"] == "DEFUNCT SHELL LTD"
        assert result["items"][0]["company_status"] == "dissolved"


# =============================================================================
# GLEIF — enhanced search + relationships tests
# =============================================================================

class TestGLEIFEnhancedSearch:
    LEI_RECORD = TestGLEIFClient.LEI_RECORD

    @pytest.fixture
    def mock_routes(self):
        return {
            "/lei-records": {
                "json": {
                    "meta": {"pagination": {"total": 1}},
                    "data": [self.LEI_RECORD],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = GLEIFClient()
        c._client = httpx.AsyncClient(
            base_url="https://api.gleif.org/api/v1",
            transport=transport,
        )
        c._transport = transport
        return c, transport

    @pytest.mark.asyncio
    async def test_search_with_jurisdiction_filter(self, client):
        c, transport = client
        result = await c.search("Test", jurisdiction="US-DE")
        assert result["total"] == 1
        req = transport.requests[0]
        assert "filter%5Bentity.jurisdiction%5D" in str(req.url) or "filter[entity.jurisdiction]" in str(req.url)

    @pytest.mark.asyncio
    async def test_search_with_status_filter(self, client):
        c, transport = client
        result = await c.search("Test", entity_status="ACTIVE")
        assert result["total"] == 1
        req = transport.requests[0]
        assert "ACTIVE" in str(req.url)

    @pytest.mark.asyncio
    async def test_search_with_multiple_filters(self, client):
        c, transport = client
        result = await c.search(
            "Test", jurisdiction="GB", entity_status="ACTIVE",
            legal_form="8888", category="GENERAL",
        )
        assert result["total"] == 1


class TestGLEIFRelationships:
    LEI_RECORD = TestGLEIFClient.LEI_RECORD

    @pytest.fixture
    def mock_routes(self):
        return {
            "/direct-parent": {
                "json": {
                    "data": [{
                        "attributes": {
                            "relationship": {
                                "endNode": {"id": "PARENT_LEI_001"},
                            },
                        },
                    }],
                },
            },
            "/ultimate-parent": {
                "json": {
                    "data": [{
                        "attributes": {
                            "relationship": {
                                "endNode": {"id": "ULTIMATE_LEI_001"},
                            },
                        },
                    }],
                },
            },
            "/direct-child": {
                "json": {
                    "data": [
                        {
                            "attributes": {
                                "relationship": {
                                    "startNode": {"id": "CHILD_LEI_001"},
                                },
                            },
                        },
                        {
                            "attributes": {
                                "relationship": {
                                    "startNode": {"id": "CHILD_LEI_002"},
                                },
                            },
                        },
                    ],
                },
            },
            "/ultimate-child": {
                "json": {
                    "data": [
                        {
                            "attributes": {
                                "relationship": {
                                    "startNode": {"id": "CHILD_LEI_001"},
                                },
                            },
                        },
                        {
                            "attributes": {
                                "relationship": {
                                    "startNode": {"id": "CHILD_LEI_002"},
                                },
                            },
                        },
                        {
                            "attributes": {
                                "relationship": {
                                    "startNode": {"id": "GRANDCHILD_LEI_001"},
                                },
                            },
                        },
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = GLEIFClient()
        c._client = httpx.AsyncClient(
            base_url="https://api.gleif.org/api/v1",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_all_relationships(self, client):
        result = await client.get_all_relationships("549300TEST00LEI001")
        assert result["lei"] == "549300TEST00LEI001"
        assert result["direct_parent"] == "PARENT_LEI_001"
        assert result["ultimate_parent"] == "ULTIMATE_LEI_001"
        assert len(result["direct_children"]) == 2
        assert len(result["all_children"]) == 3
        assert "GRANDCHILD_LEI_001" in result["all_children"]


# =============================================================================
# CourtListener — new tools tests
# =============================================================================

class TestCourtListenerOpinion:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/opinions/99999": {
                "json": {
                    "id": 99999,
                    "type": "010combined",
                    "author_str": "Roberts, C.J.",
                    "plain_text": "This is the opinion text for the case.",
                    "download_url": "/path/to/opinion.pdf",
                    "date_filed": "2024-06-15",
                    "cluster": "https://www.courtlistener.com/api/rest/v4/clusters/12345/",
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CourtListenerClient(api_token="test-token")
        c._client = httpx.AsyncClient(
            base_url="https://www.courtlistener.com/api/rest/v4",
            transport=transport,
            headers={"Authorization": "Token test-token"},
        )
        return c

    @pytest.mark.asyncio
    async def test_get_opinion(self, client):
        result = await client.get_opinion(99999)
        assert result["id"] == 99999
        assert result["author_str"] == "Roberts, C.J."
        assert "opinion text" in result["plain_text"]


class TestCourtListenerPerson:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/people/42": {
                "json": {
                    "id": 42,
                    "name_full": "John G. Roberts Jr.",
                    "date_dob": "1955-01-27",
                    "positions": [
                        {
                            "court": {"short_name": "SCOTUS"},
                            "position_type": "Chief Justice",
                            "date_start": "2005-09-29",
                        },
                    ],
                },
            },
            "/people/": {
                "json": {
                    "count": 1,
                    "results": [
                        {"id": 42, "name_full": "John G. Roberts Jr."},
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CourtListenerClient(api_token="test-token")
        c._client = httpx.AsyncClient(
            base_url="https://www.courtlistener.com/api/rest/v4",
            transport=transport,
            headers={"Authorization": "Token test-token"},
        )
        return c

    @pytest.mark.asyncio
    async def test_get_person(self, client):
        result = await client.get_person(42)
        assert result["id"] == 42
        assert result["name_full"] == "John G. Roberts Jr."
        assert len(result["positions"]) == 1

    @pytest.mark.asyncio
    async def test_search_people_exposed(self, client):
        result = await client.search_people("Roberts")
        assert result["count"] == 1


class TestCourtListenerBankruptcy:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search/": {
                "json": {
                    "count": 1,
                    "results": [
                        {
                            "docket_id": 55555,
                            "caseName": "In re: Test Corp",
                            "court": "bankr. S.D.N.Y.",
                            "dateFiled": "2024-03-01",
                            "nature_of_suit": "Bankruptcy",
                        }
                    ],
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = CourtListenerClient(api_token="test-token")
        c._client = httpx.AsyncClient(
            base_url="https://www.courtlistener.com/api/rest/v4",
            transport=transport,
            headers={"Authorization": "Token test-token"},
        )
        return c

    @pytest.mark.asyncio
    async def test_search_with_nature_of_suit(self, client):
        result = await client.search("Test Corp", nature_of_suit="422")
        assert result["count"] == 1
        assert result["results"][0]["caseName"] == "In re: Test Corp"


# =============================================================================
# SEC EDGAR — new tools tests
# =============================================================================

class TestSECProxyStatement:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0930",
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-24-000099"],
                            "form": ["DEF 14A"],
                            "filingDate": ["2024-01-15"],
                            "primaryDocument": ["proxy2024.htm"],
                            "primaryDocDescription": ["DEF 14A"],
                        }
                    },
                    "addresses": {"mailing": {}, "business": {}},
                }
            },
            "/Archives/": {
                "html": """
                <html><body>
                <h2>Compensation Discussion and Analysis</h2>
                <table>
                <tr><th>Name</th><th>Title</th><th>Salary</th><th>Bonus</th><th>Total</th></tr>
                <tr><td>Tim Cook</td><td>CEO</td><td>$3,000,000</td><td>$0</td><td>$63,209,365</td></tr>
                <tr><td>Luca Maestri</td><td>CFO</td><td>$1,000,000</td><td>$0</td><td>$26,987,466</td></tr>
                </table>
                <h2>Director Nominees</h2>
                <p>The following directors are nominated:</p>
                <p><strong>James Bell</strong>, Independent Director</p>
                <p><strong>Al Gore</strong>, Independent Director</p>
                </body></html>
                """,
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_proxy_statement(self, client):
        result = await client.get_proxy_statement(320193)
        assert result["name"] == "Apple Inc."
        assert result["filing_date"] == "2024-01-15"
        assert isinstance(result.get("executives"), list)
        assert isinstance(result.get("board_members"), list)


class TestSEC8KEvents:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0930",
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0000320193-24-000050",
                                "0000320193-24-000051",
                            ],
                            "form": ["8-K", "8-K"],
                            "filingDate": ["2024-06-01", "2024-03-15"],
                            "primaryDocument": ["event1.htm", "event2.htm"],
                            "primaryDocDescription": ["8-K", "8-K"],
                        }
                    },
                    "addresses": {"mailing": {}, "business": {}},
                }
            },
            "/Archives/": {
                "html": """
                <html><body>
                <h3>Item 2.01 Completion of Acquisition</h3>
                <p>On June 1, 2024, the Company completed its acquisition of
                AI Startup Inc. for approximately $2 billion in cash.</p>
                <h3>Item 5.02 Departure of Directors or Certain Officers</h3>
                <p>On June 1, 2024, John Doe resigned as SVP of Engineering.</p>
                </body></html>
                """,
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_8k_events(self, client):
        result = await client.get_8k_events(320193, limit=2)
        assert result["name"] == "Apple Inc."
        assert isinstance(result["events"], list)
        assert len(result["events"]) <= 2


class TestSECAmendments:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/submissions/": {
                "json": {
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "tickers": ["AAPL"],
                    "exchanges": ["Nasdaq"],
                    "sic": "3571",
                    "stateOfIncorporation": "CA",
                    "fiscalYearEnd": "0930",
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0000320193-24-000001",
                                "0000320193-24-000002",
                                "0000320193-24-000003",
                            ],
                            "form": ["10-K", "10-K/A", "10-Q/A"],
                            "filingDate": [
                                "2024-11-01", "2024-12-15", "2025-01-10",
                            ],
                            "primaryDocument": ["10k.htm", "10ka.htm", "10qa.htm"],
                            "primaryDocDescription": [
                                "10-K", "10-K/A", "10-Q/A",
                            ],
                        }
                    },
                    "addresses": {"mailing": {}, "business": {}},
                }
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = SECEdgarClient(user_agent="test-agent test@test.com")
        c._efts = httpx.AsyncClient(
            base_url="https://efts.sec.gov/LATEST", transport=transport,
        )
        c._data = httpx.AsyncClient(
            base_url="https://data.sec.gov", transport=transport,
        )
        c._www = httpx.AsyncClient(
            base_url="https://www.sec.gov", transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_amendments(self, client):
        result = await client.get_amendments(320193)
        assert result["name"] == "Apple Inc."
        assert result["count"] == 2
        assert all(
            a["form"] in ("10-K/A", "10-Q/A")
            for a in result["amendments"]
        )
