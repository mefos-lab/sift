"""Tests for YAML pattern matcher."""

import pytest
from sift.pattern_matcher import load_patterns, match_patterns, _build_graph_index


class TestLoadPatterns:
    def test_loads_yaml_files(self):
        patterns = load_patterns()
        assert len(patterns) >= 18

    def test_each_pattern_has_detection(self):
        for p in load_patterns():
            assert "detection" in p
            assert "conditions" in p["detection"]
            assert len(p["detection"]["conditions"]) > 0

    def test_each_pattern_has_metadata(self):
        for p in load_patterns():
            assert "name" in p
            assert "risk_level" in p
            assert p["risk_level"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")


class TestMatchPatterns:
    def _make_nodes(self, nodes_data):
        """Build nodes dict from simple tuples: (id, label, type, source, props)."""
        result = {}
        for nid, label, ntype, source, props in nodes_data:
            result[nid] = {
                "id": nid, "label": label, "node_type": ntype,
                "source": source, "hop": props.get("hop", 0),
                **props,
            }
        return result

    def _make_edges(self, edges_data):
        """Build edges from tuples: (src, tgt, rel)."""
        return [{"source_id": s, "target_id": t, "relationship": r}
                for s, t, r in edges_data]

    def test_empty_graph_no_matches(self):
        result = match_patterns({}, [])
        assert result.stats["patterns_matched"] == 0

    def test_high_degree_node_triggers_starburst(self):
        # Create a hub officer connected to 15 entities
        nodes_data = [("hub", "John Nominee", "Officer", "icij", {})]
        edges_data = []
        for i in range(15):
            nid = f"e{i}"
            nodes_data.append((nid, f"Entity {i}", "Entity", "icij", {}))
            edges_data.append(("hub", nid, "officer_of"))

        nodes = self._make_nodes(nodes_data)
        edges = self._make_edges(edges_data)
        result = match_patterns(nodes, edges)

        # Should trigger starburst (hub_degree >= 10)
        pattern_names = [m.pattern_name for m in result.matches]
        assert "starburst" in pattern_names

    def test_secrecy_jurisdiction_triggers(self):
        nodes = self._make_nodes([
            ("a", "Shell Corp", "Entity", "icij", {"country_codes": ["VG"]}),
        ])
        result = match_patterns(nodes, [])

        # Should trigger nominee_shield (secrecy_jurisdiction condition)
        matched_conditions = []
        for m in result.matches:
            matched_conditions.extend(m.conditions_met)
        assert "secrecy_jurisdiction" in matched_conditions

    def test_cross_source_detection(self):
        nodes = self._make_nodes([
            ("a", "Test Corp", "Entity", "icij", {}),
            ("b", "Test Corp", "Entity", "opensanctions", {}),
            ("c", "Test Corp", "Company", "companies_house", {}),
        ])
        result = match_patterns(nodes, [])

        pattern_names = [m.pattern_name for m in result.matches]
        assert "cross_source_corroboration" in pattern_names

    def test_results_sorted_by_risk(self):
        # Create a complex graph that triggers multiple patterns
        nodes = self._make_nodes([
            ("a", "Hub Person", "Officer", "icij", {"country_codes": ["PA"]}),
        ])
        edges = self._make_edges(
            [("a", f"e{i}", "officer_of") for i in range(20)]
        )
        for i in range(20):
            nodes[f"e{i}"] = {"id": f"e{i}", "label": f"Entity {i}",
                              "node_type": "Entity", "source": "icij", "hop": 1}

        result = match_patterns(nodes, edges)
        if len(result.matches) >= 2:
            risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            for i in range(len(result.matches) - 1):
                r1 = risk_order.get(result.matches[i].risk_level, 9)
                r2 = risk_order.get(result.matches[i+1].risk_level, 9)
                assert r1 <= r2
