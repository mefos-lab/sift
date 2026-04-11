"""Tests for GLEIF, SEC EDGAR, UK Companies House, and CourtListener clients.

Uses httpx mock transport to avoid hitting real APIs in tests.
"""

import json
import pytest
import httpx
from sift.gleif_client import GLEIFClient
from sift.sec_client import SECEdgarClient, _pad_cik
from sift.companies_house_client import CompaniesHouseClient
from sift.courtlistener_client import CourtListenerClient


# =============================================================================
# Mock transport (shared)
# =============================================================================

class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[str, dict]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        for pattern, response_data in self.routes.items():
            if pattern in path:
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
