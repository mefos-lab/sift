"""Natural language query router — maps questions to tool calls."""

from __future__ import annotations

import re
from typing import Any


def route_query(query: str) -> list[dict]:
    """Parse a natural language query and return a list of tool calls to execute.

    Returns a list of dicts: [{"tool": "tool_name", "args": {...}, "purpose": "..."}]

    Examples:
        "Who is Jeffrey Epstein?" -> background_check
        "What companies does John Smith direct in the UK?" -> uk_search (officer)
        "Is Acme Corp sanctioned?" -> sanctions_match
        "Show me the ownership chain for HSBC" -> ownership_trace
        "Find court cases involving Trump Organization" -> court_search
        "What SEC filings mention Epstein?" -> sec_search
        "Who are the beneficial owners of company 12345678?" -> beneficial_owner
    """
    q = query.lower().strip()
    calls = []

    # Extract the subject (name/entity) from the query
    subject = _extract_subject(query)

    # Route based on intent
    if _matches(q, ["who is", "tell me about", "what do we know about",
                     "background on", "look up", "investigate",
                     "what can you find on", "profile"]):
        calls.append({
            "tool": "background_check",
            "args": {"name": subject},
            "purpose": f"Comprehensive search across all 6 sources for '{subject}'",
        })

    elif _matches(q, ["sanctioned", "sanctions", "on any lists",
                       "sanctions list", "is .* sanctioned", "pep",
                       "politically exposed"]):
        calls.append({
            "tool": "sanctions_match",
            "args": {"name": subject},
            "purpose": f"Screen '{subject}' against sanctions and PEP lists",
        })

    elif _matches(q, ["ownership", "who owns", "parent company",
                       "subsidiary", "subsidiaries", "corporate structure",
                       "ownership chain", "corporate tree"]):
        calls.append({
            "tool": "ownership_trace",
            "args": {"company": subject},
            "purpose": f"Trace corporate ownership chain for '{subject}'",
        })

    elif _matches(q, ["beneficial owner", "who controls", "psc",
                       "persons with significant control", "who really owns",
                       "ultimate owner"]):
        # Check if it's a UK company number
        if re.match(r"^\d{6,8}$", subject.strip()):
            calls.append({
                "tool": "beneficial_owner",
                "args": {"company": subject},
                "purpose": f"Identify beneficial owners of UK company {subject}",
            })
        else:
            calls.append({
                "tool": "beneficial_owner",
                "args": {"company": subject},
                "purpose": f"Identify beneficial owners of '{subject}'",
            })

    elif _matches(q, ["court case", "lawsuit", "sued", "litigation",
                       "criminal case", "indicted", "prosecution",
                       "legal proceedings"]):
        calls.append({
            "tool": "court_search",
            "args": {"query": subject},
            "purpose": f"Search US federal court records for '{subject}'",
        })

    elif _matches(q, ["sec filing", "sec edgar", "securities filing",
                       "10-k", "10-q", "8-k", "annual report",
                       "public filing"]):
        calls.append({
            "tool": "sec_search",
            "args": {"query": subject},
            "purpose": f"Search SEC EDGAR filings for '{subject}'",
        })

    elif _matches(q, ["uk company", "companies house", "uk director",
                       "british company", "registered in uk",
                       "registered in the uk"]):
        if _matches(q, ["director", "officer", "who directs"]):
            calls.append({
                "tool": "uk_search",
                "args": {"query": subject, "type": "officer"},
                "purpose": f"Search UK Companies House for officer '{subject}'",
            })
        else:
            calls.append({
                "tool": "uk_search",
                "args": {"query": subject, "type": "company"},
                "purpose": f"Search UK Companies House for '{subject}'",
            })

    elif _matches(q, ["offshore", "icij", "panama papers", "paradise papers",
                       "pandora papers", "leak", "offshore entity"]):
        calls.append({
            "tool": "icij_search",
            "args": {"query": subject},
            "purpose": f"Search ICIJ Offshore Leaks for '{subject}'",
        })

    elif _matches(q, ["lei", "legal entity identifier", "gleif",
                       "corporate registry"]):
        calls.append({
            "tool": "gleif_search",
            "args": {"query": subject},
            "purpose": f"Search GLEIF LEI registry for '{subject}'",
        })

    elif _matches(q, ["connect", "relationship", "linked to",
                       "connection between", "network", "trace"]):
        # Multi-name detection
        names = _extract_multiple_names(query)
        if len(names) >= 2:
            calls.append({
                "tool": "deep_trace",
                "args": {"names": names, "depth": 2, "budget": 60},
                "purpose": f"Trace network connections between {', '.join(names)}",
            })
        else:
            calls.append({
                "tool": "deep_trace",
                "args": {"names": [subject], "depth": 2, "budget": 50},
                "purpose": f"Deep network trace for '{subject}'",
            })

    elif _matches(q, ["monitor", "watch", "track", "new listings",
                       "changed", "recent"]):
        calls.append({
            "tool": "sanctions_monitor",
            "args": {"query": subject, "since": "2025-01-01"},
            "purpose": f"Check for new sanctions listings for '{subject}'",
        })

    elif _matches(q, ["export", "report", "save", "download", "pdf",
                       "markdown", "json"]):
        if _matches(q, ["json", "data", "structured"]):
            calls.append({
                "tool": "export_json",
                "args": {},
                "purpose": "Export investigation as structured JSON",
            })
        else:
            calls.append({
                "tool": "export_report",
                "args": {},
                "purpose": "Export investigation as Markdown report",
            })

    else:
        # Default: comprehensive background check
        calls.append({
            "tool": "background_check",
            "args": {"name": subject},
            "purpose": f"Comprehensive search across all sources for '{subject}'",
        })

    return calls


def _matches(text: str, patterns: list[str]) -> bool:
    """Check if text matches any of the patterns."""
    for p in patterns:
        if re.search(p, text):
            return True
    return False


def _extract_subject(query: str) -> str:
    """Extract the investigation subject from a natural language query."""
    q = query.strip()

    # Remove common question prefixes
    prefixes = [
        r"^who is\s+",
        r"^tell me about\s+",
        r"^what do we know about\s+",
        r"^what can you find on\s+",
        r"^look up\s+",
        r"^investigate\s+",
        r"^search (?:for|uk companies house for|sec (?:edgar )?(?:filings )?(?:for|about))\s+",
        r"^find (?:court cases involving|lawsuits (?:involving|against)|offshore entities for)\s+",
        r"^check if\s+",
        r"^is\s+",
        r"^are there (?:any )?(?:court cases|lawsuits|sanctions|filings|offshore entities) (?:for|involving|against|about)\s+",
        r"^(?:show|get|find) (?:me )?(?:the )?(?:ownership|ownership chain|structure|owners|filings|cases|beneficial owners) (?:of|for|about|chain for)\s+",
        r"^who (?:owns|controls|directs|runs)\s+",
        r"^who are the beneficial owners of (?:company )?\s*",
        r"^what (?:companies|entities|sec filings|court cases) (?:does|is|mention|involve)\s+",
        r"^what is the connection between\s+",
        r"^track (?:new )?(?:sanctions|listings) (?:for|about)\s+",
        r"^background (?:check )?on\s+",
        r"^profile\s+",
    ]

    result = q
    for prefix in prefixes:
        result = re.sub(prefix, "", result, flags=re.IGNORECASE)

    # Remove trailing question marks and common suffixes
    result = re.sub(r"\?+$", "", result)
    result = re.sub(r"\s+(?:sanctioned|on any list|in the uk|in the us)\s*$", "", result, flags=re.IGNORECASE)

    return result.strip() or q.strip()


def _extract_multiple_names(query: str) -> list[str]:
    """Extract multiple names from queries like 'connection between A and B'."""
    # Try "between X and Y"
    m = re.search(r"between\s+(.+?)\s+and\s+(.+?)(?:\?|$)", query, re.IGNORECASE)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]

    # Try "X, Y, and Z" or "X and Y"
    subject = _extract_subject(query)
    if " and " in subject:
        parts = re.split(r",?\s+and\s+", subject)
        return [p.strip() for p in parts if p.strip()]

    return [subject]
