"""Tests for API clients.

Uses httpx mock transport to avoid hitting real APIs in tests.
"""

import json
import pytest
import httpx
from sift.client import ICIJClient, INVESTIGATIONS, ENTITY_TYPES
from sift.opensanctions_client import OpenSanctionsClient
from sift.aleph_client import AlephClient
from sift.land_registry_client import LandRegistryClient
from sift.wikidata_client import WikidataClient


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
        # Prefer longest (most specific) match
        best_match = None
        best_len = -1
        for pattern, response_data in self.routes.items():
            if pattern in path and len(pattern) > best_len:
                best_match = response_data
                best_len = len(pattern)
        if best_match is not None:
            return httpx.Response(
                status_code=best_match.get("status", 200),
                json=best_match.get("json", {}),
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


# =============================================================================
# OCCRP Aleph Client tests
# =============================================================================

class TestAlephClient:
    @pytest.fixture
    def mock_routes(self):
        # Order matters: more specific paths first (MockTransport uses 'in')
        return {
            "/entities/abc123/similar": {
                "json": {
                    "total": 1,
                    "results": [
                        {
                            "id": "def456",
                            "schema": "Company",
                            "properties": {"name": ["Test Corporation"]},
                            "countries": ["bz"],
                        },
                    ],
                },
            },
            "/entities/abc123": {
                "json": {
                    "id": "abc123",
                    "schema": "Company",
                    "properties": {
                        "name": ["Test Corp"],
                        "jurisdiction": ["pa"],
                        "registrationNumber": ["12345"],
                    },
                    "countries": ["pa"],
                    "collection_id": 42,
                },
            },
            "/entities": {
                "json": {
                    "total": 2,
                    "results": [
                        {
                            "id": "abc123",
                            "schema": "Company",
                            "properties": {"name": ["Test Corp"]},
                            "countries": ["pa"],
                            "collection_id": 42,
                        },
                    ],
                },
            },
            "/collections": {
                "json": {
                    "total": 1,
                    "results": [
                        {
                            "id": 42,
                            "label": "Panama Papers",
                            "category": "leak",
                            "countries": ["pa"],
                            "count": 100000,
                            "summary": "Panama Papers source documents",
                        },
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = AlephClient()
        c._client = httpx.AsyncClient(
            base_url="https://aleph.occrp.org/api/2",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_search_entities(self, client):
        result = await client.search_entities("test")
        assert result["total"] == 2
        assert result["results"][0]["name"] == "Test Corp"
        assert result["results"][0]["countries"] == ["pa"]

    @pytest.mark.asyncio
    async def test_search_entities_with_filters(self, client):
        result = await client.search_entities(
            "test", schema="Company", countries=["pa"], limit=5,
        )
        assert "results" in result

    @pytest.mark.asyncio
    async def test_get_entity(self, client):
        result = await client.get_entity("abc123")
        assert result["id"] == "abc123"
        assert result["name"] == "Test Corp"
        assert result["registration_number"] == "12345"

    @pytest.mark.asyncio
    async def test_get_entity_similar(self, client):
        result = await client.get_entity_similar("abc123")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "Test Corporation"

    @pytest.mark.asyncio
    async def test_search_collections(self, client):
        result = await client.search_collections("panama")
        assert result["total"] == 1
        assert result["results"][0]["label"] == "Panama Papers"

    @pytest.mark.asyncio
    async def test_auth_header_set(self):
        transport = MockTransport({"/entities": {"json": {"total": 0, "results": []}}})
        c = AlephClient(api_key="test-key")
        c._client._transport = transport
        await c.search_entities("test")
        req = transport.requests[0]
        assert req.headers["Authorization"] == "ApiKey test-key"
        await c.close()

    @pytest.mark.asyncio
    async def test_no_auth_without_key(self):
        transport = MockTransport({"/entities": {"json": {"total": 0, "results": []}}})
        c = AlephClient()
        c._client = httpx.AsyncClient(
            base_url="https://aleph.occrp.org/api/2",
            transport=transport,
        )
        await c.search_entities("test")
        req = transport.requests[0]
        assert "Authorization" not in req.headers
        await c.close()


# =============================================================================
# UK Land Registry Client tests
# =============================================================================

class TestLandRegistryClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/app/root/qonsole/query": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "transaction": {"value": "http://example.com/tx/1"},
                                "amount": {"value": "500000"},
                                "date": {"value": "2024-06-15"},
                                "paon": {"value": "10"},
                                "street": {"value": "DOWNING STREET"},
                                "town": {"value": "LONDON"},
                                "postcode": {"value": "SW1A 2AA"},
                                "type": {"value": "http://example.com/terraced"},
                            },
                        ],
                    },
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = LandRegistryClient()
        c._client = httpx.AsyncClient(transport=transport)
        return c

    @pytest.mark.asyncio
    async def test_search_price_paid(self, client):
        result = await client.search_price_paid("DOWNING STREET")
        assert result["total"] == 1
        assert result["results"][0]["price"] == 500000
        assert result["results"][0]["property_address"]["street"] == "DOWNING STREET"

    @pytest.mark.asyncio
    async def test_search_with_price_filters(self, client):
        result = await client.search_price_paid(
            "LONDON", min_price=100000, max_price=1000000,
        )
        assert "results" in result

    @pytest.mark.asyncio
    async def test_search_with_property_type(self, client):
        result = await client.search_price_paid(
            "LONDON", property_type="terraced",
        )
        assert "results" in result

    @pytest.mark.asyncio
    async def test_search_postcode(self, client):
        result = await client.search_postcode("SW1A 2AA")
        assert result["total"] == 1
        assert result["results"][0]["property_address"]["postcode"] == "SW1A 2AA"

    @pytest.mark.asyncio
    async def test_normalize_transaction_types(self, client):
        result = await client.search_price_paid("test")
        assert result["results"][0]["property_type"] == "Terraced"

    @pytest.mark.asyncio
    async def test_normalize_empty_optional_fields(self):
        """Missing optional fields should normalize to empty strings."""
        from sift.land_registry_client import _normalize_transaction
        binding = {
            "transaction": {"value": "http://example.com/tx/1"},
            "amount": {"value": "100000"},
            "date": {"value": "2024-01-01"},
            "paon": {"value": "1"},
            "street": {"value": "TEST ST"},
            "town": {"value": "TESTTOWN"},
            "postcode": {"value": "AB1 2CD"},
            "type": {"value": "detached"},
        }
        result = _normalize_transaction(binding)
        assert result["property_address"]["saon"] == ""
        assert result["property_address"]["county"] == ""
        assert result["new_build"] is None


# =============================================================================
# Wikidata Client tests
# =============================================================================

class TestWikidataClient:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/w/api.php": {
                "json": {
                    "search": [
                        {
                            "id": "Q937",
                            "label": "Albert Einstein",
                            "description": "German-born theoretical physicist",
                            "concepturi": "http://www.wikidata.org/entity/Q937",
                        },
                    ],
                    # wbgetentities response — same route, different action
                    "entities": {
                        "Q937": {
                            "id": "Q937",
                            "labels": {"en": {"value": "Albert Einstein"}},
                            "descriptions": {"en": {"value": "German-born theoretical physicist"}},
                            "aliases": {"en": [{"value": "Einstein"}]},
                            "claims": {
                                "P27": [{
                                    "mainsnak": {
                                        "datavalue": {
                                            "type": "wikibase-entityid",
                                            "value": {"id": "Q183"},
                                        },
                                    },
                                }],
                                "P569": [{
                                    "mainsnak": {
                                        "datavalue": {
                                            "type": "time",
                                            "value": {"time": "+1879-03-14T00:00:00Z"},
                                        },
                                    },
                                }],
                            },
                        },
                    },
                    # wbgetclaims response
                    "claims": {
                        "P27": [{
                            "mainsnak": {
                                "datavalue": {
                                    "type": "wikibase-entityid",
                                    "value": {"id": "Q183"},
                                },
                            },
                        }],
                    },
                },
            },
            "/sparql": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "position": {"value": "http://www.wikidata.org/entity/Q123"},
                                "positionLabel": {"value": "President"},
                                "start": {"value": "2020-01-01"},
                            },
                        ],
                    },
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = WikidataClient()
        c._client = httpx.AsyncClient(transport=transport)
        return c

    @pytest.mark.asyncio
    async def test_search(self, client):
        result = await client.search("Einstein")
        assert result["total"] == 1
        assert result["results"][0]["id"] == "Q937"
        assert result["results"][0]["label"] == "Albert Einstein"

    @pytest.mark.asyncio
    async def test_search_with_limit(self, client):
        result = await client.search("Einstein", limit=5)
        assert "results" in result

    @pytest.mark.asyncio
    async def test_get_entity(self, client):
        result = await client.get_entity("Q937")
        assert result["id"] == "Q937"
        assert result["label"] == "Albert Einstein"
        assert "country_of_citizenship" in result
        assert result["country_of_citizenship"] == ["Q183"]

    @pytest.mark.asyncio
    async def test_get_entity_date_property(self, client):
        result = await client.get_entity("Q937")
        assert "date_of_birth" in result
        assert "+1879-03-14T00:00:00Z" in result["date_of_birth"]

    @pytest.mark.asyncio
    async def test_get_entity_aliases(self, client):
        result = await client.get_entity("Q937")
        assert "Einstein" in result["aliases"]

    @pytest.mark.asyncio
    async def test_get_claims(self, client):
        result = await client.get_claims("Q937", property_id="P27")
        assert "P27" in result

    @pytest.mark.asyncio
    async def test_sparql(self, client):
        result = await client.sparql("SELECT ?x WHERE { ?x ?y ?z } LIMIT 1")
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_pep_info(self, client):
        result = await client.get_pep_info("Q937")
        assert result["total"] == 1
        assert result["results"][0]["positionLabel"] == "President"

    @pytest.mark.asyncio
    async def test_no_auth_required(self):
        """Wikidata requires no authentication."""
        transport = MockTransport({
            "/w/api.php": {"json": {"search": []}},
        })
        c = WikidataClient()
        c._client = httpx.AsyncClient(transport=transport)
        await c.search("test")
        req = transport.requests[0]
        assert "Authorization" not in req.headers
        await c.close()


# =============================================================================
# Aleph Client — new tools tests
# =============================================================================

class TestAlephExpand:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/entities/abc123/expand": {
                "json": {
                    "total": 2,
                    "results": [
                        {
                            "id": "rel001",
                            "schema": "Ownership",
                            "properties": {
                                "name": ["Ownership of Test Corp"],
                                "owner": [{"id": "person001", "caption": "John Owner"}],
                                "asset": [{"id": "abc123", "caption": "Test Corp"}],
                            },
                            "countries": [],
                        },
                        {
                            "id": "rel002",
                            "schema": "Directorship",
                            "properties": {
                                "name": ["Director of Test Corp"],
                                "director": [{"id": "person002", "caption": "Jane Director"}],
                                "organization": [{"id": "abc123", "caption": "Test Corp"}],
                            },
                            "countries": [],
                        },
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = AlephClient()
        c._client = httpx.AsyncClient(
            base_url="https://aleph.occrp.org/api/2",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_expand_entity(self, client):
        result = await client.expand_entity("abc123")
        assert result["total"] == 2
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_expand_entity_with_limit(self, client):
        result = await client.expand_entity("abc123", limit=1)
        assert "results" in result


class TestAlephDocuments:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/entities": {
                "json": {
                    "total": 1,
                    "results": [
                        {
                            "id": "doc001",
                            "schema": "Document",
                            "properties": {
                                "name": ["Leaked Contract.pdf"],
                                "fileName": ["contract.pdf"],
                            },
                            "countries": ["pa"],
                            "collection_id": 42,
                        },
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = AlephClient()
        c._client = httpx.AsyncClient(
            base_url="https://aleph.occrp.org/api/2",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_search_collection_documents(self, client):
        result = await client.search_collection_documents(42, query="contract")
        assert result["total"] == 1
        assert result["results"][0]["name"] == "Leaked Contract.pdf"

    @pytest.mark.asyncio
    async def test_search_collection_documents_no_query(self, client):
        result = await client.search_collection_documents(42)
        assert "results" in result


class TestAlephRelationships:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/entities/abc123/expand": {
                "json": {
                    "total": 3,
                    "results": [
                        {
                            "id": "rel001",
                            "schema": "Ownership",
                            "properties": {"name": ["Ownership"]},
                            "countries": [],
                        },
                        {
                            "id": "rel002",
                            "schema": "Directorship",
                            "properties": {"name": ["Directorship"]},
                            "countries": [],
                        },
                        {
                            "id": "rel003",
                            "schema": "Payment",
                            "properties": {"name": ["Payment"]},
                            "countries": [],
                        },
                    ],
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = AlephClient()
        c._client = httpx.AsyncClient(
            base_url="https://aleph.occrp.org/api/2",
            transport=transport,
        )
        return c

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self, client):
        result = await client.get_entity_relationships("abc123")
        assert result["entity_id"] == "abc123"
        assert len(result["relationships"]) == 3

    @pytest.mark.asyncio
    async def test_get_entity_relationships_filtered(self, client):
        result = await client.get_entity_relationships(
            "abc123", schemata=["Ownership", "Directorship"],
        )
        assert result["entity_id"] == "abc123"
        assert len(result["relationships"]) == 2
        schemas = {r["schema"] for r in result["relationships"]}
        assert schemas == {"Ownership", "Directorship"}


# =============================================================================
# Land Registry — new tools tests
# =============================================================================

class TestLandRegistryAddressHistory:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/app/root/qonsole/query": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "transaction": {"value": "http://example.com/tx/1"},
                                "amount": {"value": "250000"},
                                "date": {"value": "2010-03-15"},
                                "paon": {"value": "10"},
                                "street": {"value": "DOWNING STREET"},
                                "town": {"value": "LONDON"},
                                "postcode": {"value": "SW1A 2AA"},
                                "type": {"value": "terraced"},
                            },
                            {
                                "transaction": {"value": "http://example.com/tx/2"},
                                "amount": {"value": "500000"},
                                "date": {"value": "2020-06-01"},
                                "paon": {"value": "10"},
                                "street": {"value": "DOWNING STREET"},
                                "town": {"value": "LONDON"},
                                "postcode": {"value": "SW1A 2AA"},
                                "type": {"value": "terraced"},
                            },
                        ],
                    },
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = LandRegistryClient()
        c._client = httpx.AsyncClient(transport=transport)
        return c

    @pytest.mark.asyncio
    async def test_search_address_history(self, client):
        result = await client.search_address_history(
            paon="10", street="DOWNING STREET", town="LONDON",
        )
        assert result["total"] == 2
        # Should be ordered by date ascending (oldest first)
        assert result["results"][0]["date"] <= result["results"][1]["date"]

    @pytest.mark.asyncio
    async def test_search_address_history_with_postcode(self, client):
        result = await client.search_address_history(
            paon="10", street="DOWNING STREET", town="LONDON",
            postcode="SW1A 2AA",
        )
        assert "results" in result


class TestLandRegistryAreaStats:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/app/root/qonsole/query": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "year": {"value": "2023"},
                                "avg_price": {"value": "450000.0"},
                                "min_price": {"value": "200000"},
                                "max_price": {"value": "900000"},
                                "count": {"value": "150"},
                            },
                            {
                                "year": {"value": "2024"},
                                "avg_price": {"value": "475000.0"},
                                "min_price": {"value": "210000"},
                                "max_price": {"value": "950000"},
                                "count": {"value": "130"},
                            },
                        ],
                    },
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = LandRegistryClient()
        c._client = httpx.AsyncClient(transport=transport)
        return c

    @pytest.mark.asyncio
    async def test_get_area_stats(self, client):
        result = await client.get_area_stats("LONDON")
        assert result["town"] == "LONDON"
        assert len(result["stats"]) == 2
        assert result["stats"][0]["year"] == "2023"
        assert result["stats"][0]["avg_price"] == 450000.0

    @pytest.mark.asyncio
    async def test_get_area_stats_with_year_range(self, client):
        result = await client.get_area_stats(
            "LONDON", year_from=2023, year_to=2024,
        )
        assert "stats" in result


class TestLandRegistryHighValue:
    @pytest.fixture
    def mock_routes(self):
        return {
            "/app/root/qonsole/query": {
                "json": {
                    "results": {
                        "bindings": [
                            {
                                "transaction": {"value": "http://example.com/tx/hv1"},
                                "amount": {"value": "5000000"},
                                "date": {"value": "2024-01-15"},
                                "paon": {"value": "1"},
                                "street": {"value": "PARK LANE"},
                                "town": {"value": "LONDON"},
                                "postcode": {"value": "W1K 1AA"},
                                "type": {"value": "detached"},
                            },
                        ],
                    },
                },
            },
        }

    @pytest.fixture
    def client(self, mock_routes):
        transport = MockTransport(mock_routes)
        c = LandRegistryClient()
        c._client = httpx.AsyncClient(transport=transport)
        return c

    @pytest.mark.asyncio
    async def test_search_high_value(self, client):
        result = await client.search_high_value("LONDON")
        assert result["total"] == 1
        assert result["results"][0]["price"] == 5000000

    @pytest.mark.asyncio
    async def test_search_high_value_custom_threshold(self, client):
        result = await client.search_high_value("LONDON", min_price=2000000)
        assert "results" in result
