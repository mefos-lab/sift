"""Tests for the investigation visualizer.

Verifies that next_steps and enrichment data flow through
generate_visualization() into the output HTML/JS correctly.
"""

import json
import pytest
from pathlib import Path
from sift.visualizer import generate_visualization


@pytest.fixture
def sample_investigation():
    """Minimal investigation data with next_steps."""
    return {
        "query": "Test Subject",
        "icij_results": [
            {
                "id": "12345",
                "name": "TEST ENTITY",
                "score": 80.0,
                "types": [{"id": "entity", "name": "Entity"}],
                "description": "Test entity from Panama Papers",
                "hop": 0,
                "confidence": 0.8,
                "risk_score": 50,
                "risk_level": "MEDIUM",
            }
        ],
        "icij_entities": {},
        "icij_network": [],
        "opensanctions_results": [],
        "pattern_matches": [],
        "next_steps": [
            {
                "priority": "CRITICAL",
                "title": "Legal review required",
                "description": "Subject is on UK FCDO sanctions list. Immediate legal counsel needed.",
            },
            {
                "priority": "HIGH",
                "title": "Trace connected entities",
                "description": "Run /investigate Test Subject --trace --depth 3",
            },
            {
                "priority": "RECOMMENDED",
                "title": "Expand with Aleph",
                "description": "Register at aleph.occrp.org for source documents.",
            },
            {
                "priority": "ONGOING",
                "title": "Monitor sanctions",
                "description": "Run /investigate Test Subject --monitor monthly.",
            },
        ],
    }


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "test-investigation"


class TestNextStepsE2E:
    def test_next_steps_in_split_output(self, sample_investigation, output_dir):
        """next_steps appear in data.js when using split mode."""
        path = generate_visualization(
            sample_investigation,
            output_path=output_dir,
            open_browser=False,
            slug="test-subject",
        )
        assert path.exists()

        # Read data.js and extract the JSON
        data_js = (path.parent / "data.js").read_text()
        assert data_js.startswith("const SIFT_DATA = ")
        json_str = data_js.split("const SIFT_DATA = ", 1)[1].rsplit(";", 1)[0]
        data = json.loads(json_str)

        # Verify next_steps are present and correct
        assert "next_steps" in data
        steps = data["next_steps"]
        assert len(steps) == 4
        assert steps[0]["priority"] == "CRITICAL"
        assert steps[0]["title"] == "Legal review required"
        assert "UK FCDO" in steps[0]["description"]
        assert steps[1]["priority"] == "HIGH"
        assert steps[2]["priority"] == "RECOMMENDED"
        assert steps[3]["priority"] == "ONGOING"

    def test_next_steps_in_portable_output(self, sample_investigation, tmp_path):
        """next_steps appear in portable single-file HTML."""
        path = generate_visualization(
            sample_investigation,
            output_path=tmp_path / "test.html",
            open_browser=False,
            portable=True,
        )
        assert path.exists()
        html = path.read_text()

        # The data should be inlined in the HTML
        assert "Legal review required" in html
        assert "CRITICAL" in html
        assert "UK FCDO" in html

    def test_next_steps_in_html_template(self, sample_investigation, output_dir):
        """The HTML template references overviewNextSteps for rendering."""
        path = generate_visualization(
            sample_investigation,
            output_path=output_dir,
            open_browser=False,
            slug="test-subject",
        )
        html = path.read_text()
        # Template should have the next steps rendering code
        assert "overviewNextSteps" in html
        assert "buildNextSteps" in html
        assert "next_steps" in html

    def test_auto_generated_next_steps(self, output_dir):
        """When no next_steps provided, auto-generation kicks in."""
        data = {
            "query": "Auto Test",
            "icij_results": [
                {
                    "id": "99999",
                    "name": "SANCTIONED PERSON",
                    "score": 90.0,
                    "types": [{"id": "officer", "name": "Officer"}],
                    "description": "Test",
                    "hop": 0,
                    "confidence": 0.9,
                    "risk_score": 80,
                    "risk_level": "HIGH",
                }
            ],
            "opensanctions_results": [
                {
                    "id": "os-1",
                    "caption": "SANCTIONED PERSON",
                    "name": "SANCTIONED PERSON",
                    "schema": "Person",
                    "properties": {"topics": ["sanction"]},
                    "datasets": ["us_ofac_sdn"],
                    "score": 0.95,
                    "hop": 0,
                    "confidence": 0.95,
                    "risk_score": 90,
                    "risk_level": "CRITICAL",
                    "topics": ["sanction"],
                }
            ],
            "icij_entities": {},
            "icij_network": [],
            "pattern_matches": [],
            # No next_steps provided — should auto-generate
        }
        path = generate_visualization(
            data,
            output_path=output_dir,
            open_browser=False,
            slug="auto-test",
        )
        data_js = (path.parent / "data.js").read_text()
        json_str = data_js.split("const SIFT_DATA = ", 1)[1].rsplit(";", 1)[0]
        parsed = json.loads(json_str)

        # Auto-generated next_steps should exist
        assert "next_steps" in parsed
        steps = parsed["next_steps"]
        assert len(steps) > 0
        # Should have at least one step about sanctions
        priorities = [s["priority"] for s in steps]
        assert "CRITICAL" in priorities or "HIGH" in priorities


class TestEnrichmentPassthrough:
    def test_enrichment_data_passes_through(self, sample_investigation, output_dir):
        """Enrichment data keys are included in output when present."""
        sample_investigation["sec_financials"] = [
            {"metric": "revenue", "value": 1000000, "period": "2024-09-30"}
        ]
        sample_investigation["uk_charges"] = [
            {"charge_number": 1, "status": "outstanding", "persons_entitled": ["HSBC"]}
        ]
        path = generate_visualization(
            sample_investigation,
            output_path=output_dir,
            open_browser=False,
            slug="enrichment-test",
        )
        data_js = (path.parent / "data.js").read_text()
        json_str = data_js.split("const SIFT_DATA = ", 1)[1].rsplit(";", 1)[0]
        data = json.loads(json_str)

        assert "enrichment" in data
        assert "sec_financials" in data["enrichment"]
        assert "uk_charges" in data["enrichment"]
        assert data["enrichment"]["sec_financials"][0]["metric"] == "revenue"

    def test_no_enrichment_when_empty(self, sample_investigation, output_dir):
        """No enrichment key in output when no enrichment data exists."""
        path = generate_visualization(
            sample_investigation,
            output_path=output_dir,
            open_browser=False,
            slug="no-enrichment-test",
        )
        data_js = (path.parent / "data.js").read_text()
        json_str = data_js.split("const SIFT_DATA = ", 1)[1].rsplit(";", 1)[0]
        data = json.loads(json_str)

        assert "enrichment" not in data
