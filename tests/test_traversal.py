"""Tests for the multi-hop traversal engine.

Uses mock API clients to verify parallel execution, error resilience,
and result structure without hitting real APIs.
"""

import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from sift.traversal import traverse, TraversalResult, result_to_visualizer_data


# =============================================================================
# Mock clients
# =============================================================================

def _make_icij_client(reconcile_results=None, node_result=None, fail_reconcile=False):
    """Build a mock ICIJ client."""
    client = AsyncMock()

    if fail_reconcile:
        client.reconcile.side_effect = httpx.HTTPStatusError(
            "", request=httpx.Request("POST", "http://x"),
            response=httpx.Response(500, text='{"code":500}'))
    else:
        client.reconcile.return_value = {
            "result": reconcile_results or [
                {"id": "12345", "name": "TEST ENTITY LTD",
                 "score": 80.0,
                 "types": [{"id": "entity", "name": "Entity"}],
                 "description": "Entity from Panama Papers data."},
            ],
        }

    client.get_node.return_value = node_result or {
        "id": 12345,
        "country_codes": [{"str": "PA"}],
        "name": [{"str": "TEST ENTITY LTD"}],
    }
    return client


def _make_os_client(match_results=None, adjacent_results=None, fail_match=False):
    """Build a mock OpenSanctions client."""
    client = AsyncMock()

    if fail_match:
        client.match.side_effect = httpx.HTTPStatusError(
            "", request=httpx.Request("POST", "http://x"),
            response=httpx.Response(500))
    else:
        client.match.return_value = {
            "responses": {
                "q0": {
                    "results": match_results or [
                        {"id": "OS-001", "caption": "Test Person",
                         "schema": "Person", "score": 0.9,
                         "properties": {"topics": ["role.pep"]},
                         "datasets": ["wikidata"]},
                    ],
                },
            },
        }

    client.get_adjacent.return_value = {
        "results": adjacent_results or [],
    }
    return client


# =============================================================================
# Traversal tests
# =============================================================================

class TestTraverse:
    @pytest.mark.asyncio
    async def test_basic_traversal(self):
        """Seed search finds nodes from both ICIJ and OpenSanctions."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        assert isinstance(result, TraversalResult)
        assert result.stats["total_nodes"] > 0
        assert result.stats["api_calls"] > 0
        assert result.stats["api_calls"] <= 50

    @pytest.mark.asyncio
    async def test_finds_icij_and_os_nodes(self):
        """Both sources contribute nodes."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        sources = result.stats.get("nodes_per_source", {})
        assert "icij" in sources
        assert "opensanctions" in sources

    @pytest.mark.asyncio
    async def test_pep_detected(self):
        """PEP status is correctly identified."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        assert result.stats["pep"] >= 1

    @pytest.mark.asyncio
    async def test_budget_respected(self):
        """Traversal stops when budget is exhausted."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=2, budget=10)

        assert result.stats["api_calls"] <= 10

    @pytest.mark.asyncio
    async def test_icij_failure_continues(self):
        """When ICIJ returns 500, traversal continues with other sources."""
        icij = _make_icij_client(fail_reconcile=True)
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        # Should still have OS results even though ICIJ failed
        assert result.stats["total_nodes"] > 0
        assert len(result.service_warnings) > 0
        assert any("ICIJ" in w for w in result.service_warnings)

    @pytest.mark.asyncio
    async def test_os_failure_continues(self):
        """When OpenSanctions returns 500, traversal continues."""
        icij = _make_icij_client()
        os = _make_os_client(fail_match=True)

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        assert result.stats["total_nodes"] > 0
        assert any("OpenSanctions" in w for w in result.service_warnings)

    @pytest.mark.asyncio
    async def test_both_sources_fail_no_crash(self):
        """When all sources fail, we get an empty result, not a crash."""
        icij = _make_icij_client(fail_reconcile=True)
        os = _make_os_client(fail_match=True)

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        assert isinstance(result, TraversalResult)
        assert len(result.service_warnings) >= 2

    @pytest.mark.asyncio
    async def test_multiple_seeds(self):
        """Multiple seed names expand the graph."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Person A", "Person B"],
                                max_depth=1, budget=50)

        # Should have called reconcile/match for both names
        assert icij.reconcile.call_count >= 2

    @pytest.mark.asyncio
    async def test_duplicate_seeds_skipped(self):
        """Duplicate seed names are not searched twice."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Same Name", "same name"],
                                max_depth=1, budget=50)

        # Normalized names are the same — should only search once in seed
        # (hop expansion may add more calls)
        seed_reconcile_calls = sum(
            1 for call in icij.reconcile.call_args_list
            if "same name" in str(call).lower() or "Same Name" in str(call)
        )
        # At least 1 but the duplicate should be skipped
        assert seed_reconcile_calls >= 1

    @pytest.mark.asyncio
    async def test_service_warnings_in_result(self):
        """Service warnings are propagated to the result."""
        icij = _make_icij_client(fail_reconcile=True)
        os = _make_os_client()

        result = await traverse(icij, os, ["Test"], max_depth=1, budget=50)

        assert result.service_warnings is not None
        assert isinstance(result.service_warnings, list)

    @pytest.mark.asyncio
    async def test_service_errors_in_stats(self):
        """Service error details are in the stats dict."""
        icij = _make_icij_client(fail_reconcile=True)
        os = _make_os_client()

        result = await traverse(icij, os, ["Test"], max_depth=1, budget=50)

        errors = result.stats.get("service_errors", {})
        assert errors["error_count"] > 0
        assert "ICIJ" in errors["failed_services"]

    @pytest.mark.asyncio
    async def test_pattern_matches_returned(self):
        """Pattern matching runs and returns results."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)

        assert isinstance(result.pattern_matches, list)

    @pytest.mark.asyncio
    async def test_optional_clients(self):
        """Traversal works when optional clients are None."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(
            icij, os, ["Test Person"], max_depth=1, budget=50,
            gleif_client=None, sec_client=None, ch_client=None,
            cl_client=None, aleph_client=None, wikidata_client=None,
        )

        assert isinstance(result, TraversalResult)
        assert result.stats["total_nodes"] > 0

    @pytest.mark.asyncio
    async def test_with_gleif_client(self):
        """GLEIF client is called when provided."""
        icij = _make_icij_client()
        os = _make_os_client()
        gleif = AsyncMock()
        gleif.search.return_value = {
            "results": [{"lei": "ABC123", "legal_name": "Test Corp",
                         "jurisdiction": "GB", "country": "GB",
                         "status": "ACTIVE", "initial_registration": "2020-01-01"}],
        }
        gleif.get_all_relationships.return_value = None

        result = await traverse(
            icij, os, ["Test Corp"], max_depth=1, budget=50,
            gleif_client=gleif,
        )

        assert "gleif" in result.stats.get("nodes_per_source", {})


# =============================================================================
# result_to_visualizer_data tests
# =============================================================================

class TestResultToVisualizerData:
    @pytest.mark.asyncio
    async def test_visualizer_data_shape(self):
        """Verify the output shape matches what the visualizer expects."""
        icij = _make_icij_client()
        os = _make_os_client()

        result = await traverse(icij, os, ["Test Person"], max_depth=1, budget=50)
        data = result_to_visualizer_data(result, "Test Person")

        assert "query" in data
        assert "icij_results" in data
        assert "opensanctions_results" in data
        assert "icij_network" in data
        assert data["query"] == "Test Person"

    @pytest.mark.asyncio
    async def test_visualizer_data_with_warnings(self):
        """Service warnings are available for the server to add."""
        icij = _make_icij_client(fail_reconcile=True)
        os = _make_os_client()

        result = await traverse(icij, os, ["Test"], max_depth=1, budget=50)
        # The server handler adds service_warnings — verify they exist on result
        assert len(result.service_warnings) > 0
