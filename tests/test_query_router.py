"""Tests for natural language query router."""

import pytest
from sift.query_router import route_query, _extract_subject


class TestRouteQuery:
    def test_who_is_routes_to_background(self):
        calls = route_query("Who is Jeffrey Epstein?")
        assert calls[0]["tool"] == "background_check"
        assert "Jeffrey Epstein" in calls[0]["args"]["name"]

    def test_sanctioned_routes_to_match(self):
        calls = route_query("Is HSBC sanctioned?")
        assert calls[0]["tool"] == "sanctions_match"

    def test_ownership_routes_to_trace(self):
        calls = route_query("Show me the ownership chain for Goldman Sachs")
        assert calls[0]["tool"] == "ownership_trace"

    def test_court_cases_routes_to_search(self):
        calls = route_query("Find court cases involving Trump Organization")
        assert calls[0]["tool"] == "court_search"

    def test_sec_filings_routes_to_sec(self):
        calls = route_query("What SEC filings mention Kushner?")
        assert calls[0]["tool"] == "sec_search"

    def test_beneficial_owner_routes(self):
        calls = route_query("Who are the beneficial owners of company 12345678?")
        assert calls[0]["tool"] == "beneficial_owner"

    def test_connection_between_two_names(self):
        calls = route_query("What is the connection between Epstein and Maxwell?")
        assert calls[0]["tool"] == "deep_trace"
        assert len(calls[0]["args"]["names"]) == 2

    def test_offshore_routes_to_icij(self):
        calls = route_query("Are there any offshore entities for Putin?")
        assert calls[0]["tool"] == "icij_search"

    def test_monitor_routes_to_monitor(self):
        calls = route_query("Track new sanctions for Deripaska")
        assert calls[0]["tool"] == "sanctions_monitor"
        assert "since" in calls[0]["args"]

    def test_unknown_defaults_to_background(self):
        calls = route_query("Acme Corporation")
        assert calls[0]["tool"] == "background_check"

    def test_uk_company_routes(self):
        calls = route_query("Search UK Companies House for Appleby")
        assert calls[0]["tool"] == "uk_search"


class TestExtractSubject:
    def test_who_is(self):
        assert _extract_subject("Who is Jeffrey Epstein?") == "Jeffrey Epstein"

    def test_tell_me_about(self):
        assert _extract_subject("Tell me about HSBC") == "HSBC"

    def test_plain_name(self):
        assert _extract_subject("Acme Corp") == "Acme Corp"

    def test_find_prefix(self):
        subject = _extract_subject("Find court cases involving Trump")
        assert "Trump" in subject

    def test_removes_question_mark(self):
        subject = _extract_subject("Who is Putin?")
        assert "?" not in subject
