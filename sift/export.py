"""Export investigation results to JSON and Markdown reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "investigations"


def export_json(
    investigation_data: dict,
    output_path: str | Path | None = None,
) -> Path:
    """Export investigation results as structured JSON.

    Includes all nodes, edges, pattern matches, scores, and metadata.
    Suitable for ingestion by other tools or newsroom data pipelines.
    """
    export = {
        "export_format": "sift-investigation-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "query": investigation_data.get("query", ""),
        "stats": investigation_data.get("traversal_stats", {}),
        "pattern_matches": investigation_data.get("pattern_matches", []),
        "entities": _build_entity_list(investigation_data),
        "edges": investigation_data.get("icij_network", []),
    }

    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = _slugify(investigation_data.get("query", "export"))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"{slug}-{ts}.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(export, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return output_path


def export_markdown(
    investigation_data: dict,
    output_path: str | Path | None = None,
) -> Path:
    """Export investigation as a Markdown report suitable for editorial review.

    Structured as a story memo: headline finding, key entities,
    risk assessment, pattern analysis, and source attribution.
    """
    query = investigation_data.get("query", "Investigation")
    stats = investigation_data.get("traversal_stats", {})
    patterns = investigation_data.get("pattern_matches", [])
    entities = _build_entity_list(investigation_data)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"# Investigation: {query}")
    lines.append(f"")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Tool:** Sift — Public records intelligence for investigative journalism  ")
    lines.append(f"**Sources:** ICIJ Offshore Leaks, OpenSanctions, GLEIF, SEC EDGAR, UK Companies House, CourtListener")
    lines.append(f"")

    # Executive summary
    lines.append(f"## Executive Summary")
    lines.append(f"")
    total = stats.get("total_nodes", len(entities))
    sources = stats.get("nodes_per_source", {})
    source_list = ", ".join(f"{k}: {v}" for k, v in sorted(sources.items()))
    lines.append(f"- **Entities found:** {total} ({source_list})")
    lines.append(f"- **API calls used:** {stats.get('api_calls', '?')}/{stats.get('budget', '?')}")
    lines.append(f"- **Patterns detected:** {stats.get('patterns_matched', len(patterns))}")
    sanctioned = stats.get("sanctioned", 0)
    pep = stats.get("pep", 0)
    if sanctioned:
        lines.append(f"- **Sanctioned entities:** {sanctioned}")
    if pep:
        lines.append(f"- **PEP connections:** {pep}")
    lines.append(f"")

    # High-risk entities
    high_risk = [e for e in entities if e.get("risk_score", 0) >= 20]
    high_risk.sort(key=lambda e: e.get("risk_score", 0), reverse=True)
    if high_risk:
        lines.append(f"## High-Risk Entities")
        lines.append(f"")
        lines.append(f"| Entity | Source | Risk | Confidence | Flags |")
        lines.append(f"|--------|--------|------|------------|-------|")
        for e in high_risk[:20]:
            flags = []
            if e.get("sanctioned"):
                flags.append("SANCTIONED")
            if e.get("pep"):
                flags.append("PEP")
            topics = e.get("topics", [])
            if "role.rca" in topics:
                flags.append("RCA")
            if "reg.action" in topics:
                flags.append("ENFORCEMENT")
            lines.append(
                f"| {e['name'][:40]} | {e['source']} | "
                f"{e.get('risk_score', 0)}/100 ({e.get('risk_level', '?')}) | "
                f"{e.get('confidence', 0):.0%} | "
                f"{', '.join(flags) or '-'} |"
            )
        lines.append(f"")

    # All entities by source
    lines.append(f"## Entity Inventory")
    lines.append(f"")
    by_source = {}
    for e in entities:
        src = e.get("source", "unknown")
        by_source.setdefault(src, []).append(e)

    source_labels = {
        "icij": "ICIJ Offshore Leaks", "opensanctions": "OpenSanctions",
        "gleif": "GLEIF LEI Registry", "sec": "SEC EDGAR",
        "companies_house": "UK Companies House", "courtlistener": "CourtListener",
        "both": "Cross-Referenced (Multiple Sources)",
    }
    for src in ["both", "icij", "opensanctions", "gleif", "sec",
                "companies_house", "courtlistener"]:
        group = by_source.get(src, [])
        if not group:
            continue
        label = source_labels.get(src, src)
        lines.append(f"### {label} ({len(group)} entities)")
        lines.append(f"")
        for e in group[:30]:
            risk_tag = ""
            if e.get("risk_score", 0) >= 40:
                risk_tag = f" **[{e['risk_level']}]**"
            elif e.get("risk_score", 0) >= 20:
                risk_tag = f" [{e['risk_level']}]"
            lines.append(f"- {e['name']}{risk_tag}")
            details = []
            if e.get("type"):
                details.append(e["type"])
            countries = e.get("country_codes", [])
            if countries:
                details.append(", ".join(countries[:3]))
            if e.get("investigation"):
                details.append(e["investigation"].replace("-", " "))
            if details:
                lines.append(f"  - {' | '.join(details)}")
        lines.append(f"")

    # Pattern matches
    if patterns:
        lines.append(f"## Detected Patterns")
        lines.append(f"")
        for p in patterns:
            risk = p.get("risk", "?")
            conf = p.get("confidence", "?")
            lines.append(f"### {p.get('title', p.get('pattern', '?'))} [{risk}] ({conf} confidence)")
            lines.append(f"")
            met = p.get("conditions_met", [])
            missed = p.get("conditions_missed", [])
            if met:
                lines.append(f"**Conditions met:** {', '.join(met)}")
            if missed:
                lines.append(f"**Conditions missed:** {', '.join(missed)}")
            evidence = p.get("evidence", [])
            if evidence:
                lines.append(f"")
                lines.append(f"Evidence:")
                for ev in evidence[:5]:
                    lines.append(f"- {ev}")
            lines.append(f"")

    # Caveats
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Caveats")
    lines.append(f"")
    lines.append(f"- Appearing in the ICIJ database does not indicate illegality")
    lines.append(f"- Absence from the database does not indicate absence of offshore activity")
    lines.append(f"- The ICIJ database covers 5 specific leaks, not the full offshore world")
    lines.append(f"- Name matching is fuzzy — verify identities through additional sources")
    lines.append(f"- OpenSanctions covers 320+ public lists — some lists may not be included")
    lines.append(f"- This is a point-in-time screen — sanctions lists change daily")
    lines.append(f"- Confidence scores reflect match quality, not certainty of identity")
    lines.append(f"- Risk scores are composite indicators, not legal determinations")
    lines.append(f"")

    report = "\n".join(lines)

    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = _slugify(query)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"{slug}-{ts}.md"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(report, encoding="utf-8")
    return output_path


def _build_entity_list(data: dict) -> list[dict]:
    """Build a flat entity list from investigation data."""
    entities = []

    for r in data.get("icij_results", []):
        types = r.get("types", [])
        entities.append({
            "name": r.get("name", "Unknown"),
            "type": types[0].get("name", "") if types else "",
            "source": "icij",
            "score": r.get("score"),
            "hop": r.get("hop", 0),
            "confidence": r.get("confidence", 0),
            "risk_score": r.get("risk_score", 0),
            "risk_level": r.get("risk_level", ""),
            "investigation": r.get("investigation"),
            "id": r.get("id"),
        })

    icij_entities = data.get("icij_entities", {})
    for eid, detail in icij_entities.items():
        # Enrich existing entities with country data
        countries = [c.get("str", c) for c in detail.get("country_codes", []) if c]
        for e in entities:
            if str(e.get("id")) == str(eid):
                e["country_codes"] = countries

    for r in data.get("opensanctions_results", []):
        props = r.get("properties", {})
        topics = props.get("topics", r.get("topics", []))
        source = "opensanctions"
        rid = r.get("id", "")
        # Detect new sources by ID prefix
        for prefix, src in {"gleif-": "gleif", "sec-": "sec",
                            "uk-": "companies_house", "court-": "courtlistener"}.items():
            if str(rid).startswith(prefix):
                source = src
                break

        entities.append({
            "name": r.get("caption", "Unknown"),
            "type": r.get("schema", ""),
            "source": source,
            "score": r.get("score"),
            "hop": r.get("hop", 0),
            "confidence": r.get("confidence", 0),
            "risk_score": r.get("risk_score", 0),
            "risk_level": r.get("risk_level", ""),
            "topics": topics,
            "datasets": r.get("datasets", []),
            "sanctioned": "sanction" in topics,
            "pep": "role.pep" in topics,
            "country_codes": props.get("nationality", props.get("citizenship", [])),
            "id": rid,
        })

    # Sort by risk score descending
    entities.sort(key=lambda e: (e.get("risk_score", 0), e.get("confidence", 0)),
                  reverse=True)
    return entities


def _slugify(text: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] if slug else "export"
