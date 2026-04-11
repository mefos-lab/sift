"""Tests for export functionality."""

import json
import pytest
from pathlib import Path
from sift.export import export_json, export_markdown, _build_entity_list


class TestBuildEntityList:
    def test_builds_from_icij_results(self):
        data = {
            "icij_results": [
                {"id": "123", "name": "Test Entity", "score": 80,
                 "types": [{"id": "entity", "name": "Entity"}],
                 "hop": 0, "confidence": 0.7, "risk_score": 25},
            ],
            "icij_entities": {},
            "opensanctions_results": [],
        }
        entities = _build_entity_list(data)
        assert len(entities) == 1
        assert entities[0]["name"] == "Test Entity"
        assert entities[0]["source"] == "icij"

    def test_builds_from_os_results(self):
        data = {
            "icij_results": [],
            "icij_entities": {},
            "opensanctions_results": [
                {"id": "Q123", "caption": "Test Person", "schema": "Person",
                 "properties": {"topics": ["role.pep"]}, "datasets": ["wikidata"],
                 "hop": 0, "confidence": 0.9},
            ],
        }
        entities = _build_entity_list(data)
        assert len(entities) == 1
        assert entities[0]["pep"] is True

    def test_detects_new_source_by_id(self):
        data = {
            "icij_results": [],
            "icij_entities": {},
            "opensanctions_results": [
                {"id": "court-12345", "caption": "US v. Test",
                 "schema": "Case", "properties": {}, "datasets": ["courtlistener"],
                 "hop": 0},
            ],
        }
        entities = _build_entity_list(data)
        assert entities[0]["source"] == "courtlistener"

    def test_sorted_by_risk(self):
        data = {
            "icij_results": [
                {"id": "1", "name": "Low Risk", "score": 50,
                 "types": [{"name": "Entity"}], "hop": 0, "risk_score": 5},
                {"id": "2", "name": "High Risk", "score": 90,
                 "types": [{"name": "Entity"}], "hop": 0, "risk_score": 50},
            ],
            "icij_entities": {},
            "opensanctions_results": [],
        }
        entities = _build_entity_list(data)
        assert entities[0]["name"] == "High Risk"


class TestExportJson:
    def test_creates_file(self, tmp_path):
        data = {
            "query": "test",
            "icij_results": [],
            "icij_entities": {},
            "opensanctions_results": [],
            "icij_network": [],
            "traversal_stats": {"total_nodes": 0},
        }
        path = export_json(data, output_path=tmp_path / "test.json")
        assert path.exists()
        content = json.loads(path.read_text())
        assert content["export_format"] == "sift-investigation-v1"
        assert content["query"] == "test"

    def test_includes_pattern_matches(self, tmp_path):
        data = {
            "query": "test",
            "icij_results": [],
            "icij_entities": {},
            "opensanctions_results": [],
            "icij_network": [],
            "pattern_matches": [{"pattern": "starburst", "risk": "HIGH"}],
            "traversal_stats": {},
        }
        path = export_json(data, output_path=tmp_path / "test.json")
        content = json.loads(path.read_text())
        assert len(content["pattern_matches"]) == 1


class TestExportMarkdown:
    def test_creates_file(self, tmp_path):
        data = {
            "query": "Jeffrey Epstein",
            "icij_results": [],
            "icij_entities": {},
            "opensanctions_results": [],
            "icij_network": [],
            "traversal_stats": {"total_nodes": 5, "nodes_per_source": {"icij": 3}},
        }
        path = export_markdown(data, output_path=tmp_path / "test.md")
        assert path.exists()
        content = path.read_text()
        assert "# Investigation: Jeffrey Epstein" in content
        assert "Sift" in content
        assert "Caveats" in content

    def test_includes_risk_table(self, tmp_path):
        data = {
            "query": "test",
            "icij_results": [
                {"id": "1", "name": "High Risk Entity", "score": 90,
                 "types": [{"name": "Entity"}], "hop": 0,
                 "risk_score": 45, "risk_level": "HIGH", "confidence": 0.8},
            ],
            "icij_entities": {},
            "opensanctions_results": [],
            "icij_network": [],
            "traversal_stats": {"total_nodes": 1, "nodes_per_source": {"icij": 1}},
        }
        path = export_markdown(data, output_path=tmp_path / "test.md")
        content = path.read_text()
        assert "High-Risk Entities" in content
        assert "High Risk Entity" in content
