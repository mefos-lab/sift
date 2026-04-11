"""Tests for entity normalization."""

import pytest
from sift.normalizer import (
    normalize_graph, _extract_country, _normalize_name,
    _normalize_address, _looks_like_address,
)


class TestExtractCountry:
    def test_country_name(self):
        assert _extract_country("123 Main St, United States of America") == "US"

    def test_city_name(self):
        assert _extract_country("16 EPSTEIN TEL AVIV") == "IL"

    def test_malta_city(self):
        assert _extract_country("22, JEFFREY, TAL-BAJJADA STREET, QORMI") == "MT"

    def test_us_state_abbrev(self):
        assert _extract_country("10 Brown Street; Claremont; WA 60..") == "US"

    def test_no_country(self):
        assert _extract_country("SOME RANDOM TEXT") is None

    def test_singapore(self):
        assert _extract_country("25 Greenwood Crescent; Singapore") == "SG"

    def test_uk(self):
        assert _extract_country("10a Warren Street, London W1T 5LF") == "GB"


class TestNormalizeName:
    def test_case_normalization(self):
        assert _normalize_name("William Brown") == _normalize_name("WILLIAM BROWN")

    def test_punctuation_removal(self):
        assert _normalize_name("SMITH, John") == _normalize_name("SMITH John")

    def test_corporate_suffix_removal(self):
        assert _normalize_name("ACME LTD") == _normalize_name("ACME LIMITED")
        assert _normalize_name("TEST CORP.") == _normalize_name("TEST CORP")

    def test_whitespace_normalization(self):
        assert _normalize_name("John  Smith") == _normalize_name("John Smith")


class TestNormalizeAddress:
    def test_formatting_variations(self):
        a1 = _normalize_address("22, JEFFREY, TAL-BAJJADA STREET,..")
        a2 = _normalize_address("22, JEFFREY , TAL-BAJJADA STREET, ..")
        assert a1 == a2

    def test_trailing_country_removed(self):
        a1 = _normalize_address("74 TAL-BAJJADA STREET, QORMI, MALTA")
        a2 = _normalize_address("74, TAL-BAJJADA STREET, QORMI")
        assert a1 == a2

    def test_punctuation_stripped(self):
        a = _normalize_address("123 Main St., Suite 100")
        assert "." not in a
        assert "," not in a


class TestLooksLikeAddress:
    def test_street_address(self):
        assert _looks_like_address("10 Brown Street; Claremont")

    def test_suite_address(self):
        assert _looks_like_address("Suite 100, Floor 5")

    def test_number_prefix(self):
        assert _looks_like_address("22, JEFFREY, TAL-BAJJADA STREET")

    def test_not_address(self):
        assert not _looks_like_address("Jeffrey Epstein")
        assert not _looks_like_address("ACME CORPORATION LTD")


class TestNormalizeGraph:
    """Integration tests with mock GraphNode-like dicts."""

    def _make_node(self, nid, label, source="icij", node_type="Entity",
                   hop=0, **props):
        class FakeNode:
            pass
        n = FakeNode()
        n.id = nid
        n.label = label
        n.source = source
        n.node_type = node_type
        n.hop = hop
        n.properties = dict(props)
        return n

    def _make_edge(self, src, tgt, rel="connected"):
        class FakeEdge:
            pass
        e = FakeEdge()
        e.source_id = src
        e.target_id = tgt
        e.relationship = rel
        return e

    def test_deduplicates_same_name(self):
        nodes = {
            "a": self._make_node("a", "WILLIAM BROWN"),
            "b": self._make_node("b", "William Brown"),
        }
        edges = [self._make_edge("a", "b")]
        nodes, edges, log = normalize_graph(nodes, edges)
        assert len(nodes) == 1
        assert log.total_merged == 1

    def test_extracts_country_from_address(self):
        nodes = {
            "a": self._make_node("a", "16 EPSTEIN TEL AVIV", node_type="Address"),
        }
        nodes, _, log = normalize_graph(nodes, [])
        n = list(nodes.values())[0]
        assert "IL" in n.properties.get("country_codes", [])
        assert log.countries_extracted >= 1

    def test_preserves_distinct_entities(self):
        nodes = {
            "a": self._make_node("a", "Jeffrey Epstein", source="icij"),
            "b": self._make_node("b", "Kenneth Epstein", source="icij"),
        }
        nodes, _, log = normalize_graph(nodes, [])
        assert len(nodes) == 2

    def test_log_records_merges(self):
        nodes = {
            "a": self._make_node("a", "74, TAL-BAJJADA STREET, QORMI", node_type="Address"),
            "b": self._make_node("b", "74 TAL-BAJJADA STREET, QORMI, MALTA", node_type="Address"),
        }
        nodes, _, log = normalize_graph(nodes, [])
        assert len(log.duplicates_merged) == 1
        assert log.duplicates_merged[0]["kept"]
        assert log.duplicates_merged[0]["merged"]
