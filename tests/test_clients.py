"""Tests for ICIJ and OpenSanctions API clients.

Uses httpx mock transport to avoid hitting real APIs in tests.
"""

import json
import pytest
import httpx
from sift.client import ICIJClient, INVESTIGATIONS, ENTITY_TYPES
from sift.opensanctions_client import OpenSanctionsClient


# =============================================================================
# Mock transport
# =============================================================================

class MockTransport(httpx.AsyncBaseTransport):
    """Returns canned responses based on URL path."""

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
# ICIJ Client tests
# =============================================================================

class TestICIJClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/reconcile": {
                "json": {
                    "result": [
                        {"id": "12345", "name": "TEST ENTITY", "score": 85.0,
                         "types": [{"id": "entity", "name": "Entity"}]},
                    ]
                }
            },
            "/rest/nodes/": {
                "status": 500,
                "json": {"code": 500, "message": "Server Error"},
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = ICIJClient()
        c._client = httpx.AsyncClient(
            base_url="https://offshoreleaks.icij.org/api/v1",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_reconcile_returns_results(self, client):
        result = await client.reconcile("test")
        assert "result" in result
        assert len(result["result"]) == 1
        assert result["result"][0]["name"] == "TEST ENTITY"

    @pytest.mark.asyncio
    async def test_reconcile_with_entity_type(self, client):
        result = await client.reconcile("test", entity_type="Officer")
        assert "result" in result

    @pytest.mark.asyncio
    async def test_reconcile_with_investigation(self, client):
        result = await client.reconcile("test", investigation="panama-papers")
        assert "result" in result

    @pytest.mark.asyncio
    async def test_reconcile_invalid_investigation_ignored(self, client):
        result = await client.reconcile("test", investigation="fake-papers")
        assert "result" in result

    @pytest.mark.asyncio
    async def test_batch_reconcile(self, client):
        result = await client.batch_reconcile(
            queries={"q0": {"query": "test1"}, "q1": {"query": "test2"}}
        )
        assert "result" in result

    @pytest.mark.asyncio
    async def test_get_node_falls_back_on_500(self, client):
        """REST endpoint returns 500 — should fall back to extend API."""
        # The extend fallback will also hit /reconcile route due to mock
        result = await client.get_node(12345)
        assert result["id"] == 12345
        assert result["source"] == "extend_fallback"

    @pytest.mark.asyncio
    async def test_suggest_entity(self, client):
        result = await client.suggest_entity("test")
        # Hits /reconcile route in mock
        assert isinstance(result, dict)

    def test_investigations_list(self):
        assert "panama-papers" in INVESTIGATIONS
        assert "paradise-papers" in INVESTIGATIONS
        assert len(INVESTIGATIONS) == 5

    def test_entity_types_list(self):
        assert "Entity" in ENTITY_TYPES
        assert "Officer" in ENTITY_TYPES
        assert len(ENTITY_TYPES) == 6


# =============================================================================
# OpenSanctions Client tests
# =============================================================================

class TestOpenSanctionsClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/search/": {
                "json": {
                    "total": {"value": 1},
                    "results": [
                        {"id": "os-123", "caption": "Test Person",
                         "schema": "Person", "topics": ["sanction"],
                         "datasets": ["us_ofac_sdn"]},
                    ],
                }
            },
            "/match/": {
                "json": {
                    "responses": {
                        "q0": {
                            "query": {"schema": "Person"},
                            "total": {"value": 1},
                            "results": [
                                {"id": "os-456", "caption": "Matched Person",
                                 "score": 0.92, "schema": "Person"},
                            ],
                        }
                    }
                }
            },
            "/entities/os-123/adjacent": {
                "json": {"total": 3, "results": [
                    {"id": "os-789", "caption": "Related Co", "schema": "Company"},
                ]},
            },
            "/entities/os-123": {
                "json": {
                    "id": "os-123", "caption": "Test Person",
                    "schema": "Person", "datasets": ["us_ofac_sdn"],
                    "properties": {"name": ["Test Person"], "topics": ["sanction"]},
                },
            },
            "/statements": {
                "json": {"total": 2, "results": [
                    {"entity_id": "os-123", "prop": "name",
                     "value": "Test Person", "dataset": "us_ofac_sdn"},
                ]},
            },
            "/catalog": {
                "json": {"datasets": [
                    {"name": "us_ofac_sdn", "title": "OFAC SDN",
                     "publisher": {"name": "US Treasury"}},
                ]},
            },
            "/algorithms": {
                "json": {"algorithms": [
                    {"name": "best", "description": "Best matching"},
                    {"name": "logic-v1", "description": "Logic V1"},
                ]},
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = OpenSanctionsClient(api_key="test-key")
        c._client = httpx.AsyncClient(
            base_url="https://api.opensanctions.org",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_search_basic(self, client):
        result = await client.search("test")
        assert result["results"][0]["caption"] == "Test Person"

    @pytest.mark.asyncio
    async def test_search_with_filters(self, client):
        result = await client.search(
            "test",
            schema="Person",
            countries=["US"],
            topics=["sanction"],
            limit=5,
            offset=10,
            fuzzy=False,
            changed_since="2026-01-01",
        )
        assert "results" in result

    @pytest.mark.asyncio
    async def test_match_single(self, client):
        queries = {"q0": {"schema": "Person", "properties": {"name": ["Test"]}}}
        result = await client.match(queries)
        assert "responses" in result
        assert result["responses"]["q0"]["results"][0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_match_with_algorithm(self, client):
        queries = {"q0": {"schema": "Person", "properties": {"name": ["Test"]}}}
        result = await client.match(queries, algorithm="logic-v1")
        assert "responses" in result

    @pytest.mark.asyncio
    async def test_match_with_changed_since(self, client):
        queries = {"q0": {"schema": "Person", "properties": {"name": ["Test"]}}}
        result = await client.match(queries, changed_since="2026-03-01")
        assert "responses" in result

    @pytest.mark.asyncio
    async def test_get_entity(self, client):
        result = await client.get_entity("os-123")
        assert result["caption"] == "Test Person"
        assert "properties" in result

    @pytest.mark.asyncio
    async def test_get_entity_nested(self, client):
        result = await client.get_entity("os-123", nested=True)
        assert result["id"] == "os-123"

    @pytest.mark.asyncio
    async def test_get_adjacent(self, client):
        result = await client.get_adjacent("os-123")
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_get_adjacent_with_property(self, client):
        result = await client.get_adjacent("os-123", property_name="ownershipOwner")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_statements(self, client):
        result = await client.get_statements(entity_id="os-123")
        assert result["results"][0]["dataset"] == "us_ofac_sdn"

    @pytest.mark.asyncio
    async def test_get_catalog(self, client):
        result = await client.get_catalog()
        assert result["datasets"][0]["name"] == "us_ofac_sdn"

    @pytest.mark.asyncio
    async def test_get_algorithms(self, client):
        result = await client.get_algorithms()
        assert len(result["algorithms"]) == 2

    @pytest.mark.asyncio
    async def test_auth_header_set(self):
        """Auth header must be present when API key is provided."""
        transport = MockTransport({"/search/": {"json": {"results": []}}})
        c = OpenSanctionsClient(api_key="test-key")
        # Replace transport but preserve the client's headers
        c._client._transport = transport
        await c.search("test")
        req = transport.requests[0]
        assert "Authorization" in req.headers
        assert req.headers["Authorization"] == "ApiKey test-key"
        await c.close()

    @pytest.mark.asyncio
    async def test_no_auth_header_without_key(self):
        transport = MockTransport({"/search/": {"json": {"results": []}}})
        c = OpenSanctionsClient(api_key=None)
        c._client = httpx.AsyncClient(
            base_url="https://api.opensanctions.org",
            transport=transport,
        )
        await c.search("test")
        req = transport.requests[0]
        assert "Authorization" not in req.headers
        await c.close()
