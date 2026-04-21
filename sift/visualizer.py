"""Transform investigation data into a D3 visualization.

Supports two output modes:
- **Split** (default): writes ``investigations/<slug>/index.html`` + ``data.js``.
  Template loads D3 and data from external files.  Edit the template and refresh.
- **Portable**: writes a single self-contained HTML with D3 and data inlined.
  Good for sharing a file by email/Slack.

Supports two data modes:
- **Investigation** (default): network graph centered on a subject.
- **Scan**: findings dashboard with mini-graphs per confirmed pattern instance.
  Detected via ``data["mode"] == "scan"``.
"""

from __future__ import annotations

import json
import re
import shutil
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from sift import __version__

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "visualizations" / "investigation-viz.html"
D3_PATH = Path(__file__).resolve().parent.parent / "visualizations" / "d3.v7.min.js"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "investigations"
SHARED_DIR = OUTPUT_DIR / "_shared"


def generate_visualization(
    investigation_data: dict,
    output_path: str | Path | None = None,
    open_browser: bool = True,
    portable: bool = False,
    slug: str | None = None,
) -> Path:
    """Build an investigation visualization.

    Parameters
    ----------
    investigation_data : dict
        Keys (all optional): ``query``, ``icij_results``,
        ``icij_entities``, ``icij_extended``, ``icij_network``,
        ``opensanctions_results``, ``pattern_matches``.
    output_path : str or Path, optional
        Explicit output location.  In split mode this is the directory;
        in portable mode it is the HTML file path.
    open_browser : bool
        Open the result in the default browser.
    portable : bool
        If True, produce a single self-contained HTML file with D3 and
        data inlined (the legacy behaviour).  Default is split mode.
    slug : str, optional
        Directory name under ``investigations/``.  Derived from the
        query string when omitted.

    Returns
    -------
    Path
        The path to the generated HTML file.
    """
    # Detect scan mode vs investigation mode
    is_scan = investigation_data.get("mode") == "scan"

    if is_scan:
        data_json = _build_scan_json(investigation_data)
    else:
        nodes, edges = _build_graph(investigation_data)
        enrichment = _collect_enrichment(investigation_data)
        timeline_events = _extract_timeline_events(investigation_data, nodes)
        payload = {
            "metadata": {
                "query": investigation_data.get("query", "Investigation"),
                "generated_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
                "sift_version": __version__,
            },
            "nodes": nodes,
            "edges": edges,
            "pattern_matches": investigation_data.get("pattern_matches", []),
            "next_steps": investigation_data.get("next_steps")
                or _generate_next_steps(nodes, edges, investigation_data),
            **({"enrichment": enrichment} if enrichment else {}),
        }
        if timeline_events:
            payload["timeline_events"] = timeline_events
        data_json = json.dumps(payload, ensure_ascii=False)

    if slug is None:
        if is_scan:
            scan_types = investigation_data.get("scan_types", ["scan"])
            slug = _slugify("scan-" + "-".join(scan_types))
        else:
            slug = _slugify(investigation_data.get("query", "investigation"))

    if portable:
        return _write_portable(data_json, slug, output_path, open_browser)
    return _write_split(data_json, slug, output_path, open_browser)


# ------------------------------------------------------------------
# Split mode (default) — external data.js + index.html
# ------------------------------------------------------------------

def _ensure_shared_assets() -> None:
    """Copy D3 to the shared directory if missing or outdated."""
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    shared_d3 = SHARED_DIR / "d3.v7.min.js"
    if not shared_d3.exists() or shared_d3.stat().st_size != D3_PATH.stat().st_size:
        shutil.copy2(D3_PATH, shared_d3)


def _prepare_split_html(template: str, build_ts: int) -> str:
    """Prepare the HTML template for split mode (external D3 + data)."""
    html = template.replace("<script>__D3_INLINE__</script>\n", "")
    html = html.replace("__D3_SRC__", "d3.v7.min.js")
    html = html.replace("__BUILD_TS__", str(build_ts))
    html = html.replace("__PORTABLE_DATA_INLINE__", "")
    return html


def _write_split(
    graph_json: str,
    slug: str,
    output_path: str | Path | None,
    open_browser: bool,
) -> Path:
    """Write split files: data.js + index.html into investigations/<slug>/."""
    if output_path is not None:
        inv_dir = Path(output_path)
        if inv_dir.suffix:
            inv_dir = inv_dir.parent
    else:
        inv_dir = OUTPUT_DIR / slug

    inv_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy D3 into the investigation directory (avoids file:// cross-origin issues)
    local_d3 = inv_dir / "d3.v7.min.js"
    if not local_d3.exists() or local_d3.stat().st_size != D3_PATH.stat().st_size:
        shutil.copy2(D3_PATH, local_d3)

    # 2. Write data.js
    ts = int(datetime.now(timezone.utc).timestamp())
    data_path = inv_dir / "data.js"
    data_path.write_text(
        f"const SIFT_DATA = {graph_json};\n", encoding="utf-8",
    )

    # 2. Save raw JSON for rebuilds
    raw_path = inv_dir / "raw-data.json"
    raw_path.write_text(graph_json, encoding="utf-8")

    # 3. Write index.html
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = _prepare_split_html(template, ts)
    index_path = inv_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(index_path.as_uri())

    return index_path


# ------------------------------------------------------------------
# Portable mode — single self-contained HTML
# ------------------------------------------------------------------

def _write_portable(
    graph_json: str,
    slug: str,
    output_path: str | Path | None,
    open_browser: bool,
) -> Path:
    """Write a single self-contained HTML file with everything inlined."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    d3_js = D3_PATH.read_text(encoding="utf-8") if D3_PATH.exists() else ""

    html = template.replace("__D3_INLINE__", d3_js)
    # Remove external script tags (not needed in portable mode)
    html = re.sub(r'<script src="__D3_SRC__"></script>\n?', "", html)
    html = re.sub(r'<script src="data\.js\?v=__BUILD_TS__"></script>\n?', "", html)
    # Inline the data
    html = html.replace(
        "// __PORTABLE_DATA_INLINE__",
        f"const SIFT_DATA = {graph_json};",
    )

    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"{slug}-{ts}.html"
    else:
        output_path = Path(output_path)
        # Guard against bare query strings used as output_path (e.g.
        # "Isabel dos Santos") — if it has no directory component and
        # no .html suffix, treat it as a slug and route to OUTPUT_DIR.
        if output_path.parent == Path(".") and output_path.suffix != ".html":
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            safe_slug = _slugify(str(output_path))
            output_path = OUTPUT_DIR / f"{safe_slug}-{ts}.html"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(output_path.as_uri())

    return output_path


# ------------------------------------------------------------------
# Scan mode — findings dashboard
# ------------------------------------------------------------------


def _build_scan_json(data: dict) -> str:
    """Build the JSON payload for scan mode visualization.

    Scan results are a collection of independent findings, not a
    single network graph.  Each finding has its own mini-graph
    (the chain of entities that constitutes the pattern instance).
    """
    findings = data.get("findings", [])

    # Build mini-graph nodes/edges for each finding from its chain
    for finding in findings:
        mini_nodes: dict[str, dict] = {}
        mini_edges: list[dict] = []

        # Index entities by ID; also build a label->id lookup
        label_to_id: dict[str, str] = {}
        for entity in finding.get("entities", []):
            eid = entity["id"]
            # Pass through all entity properties for rich tooltips
            node = dict(entity)
            node.setdefault("sanctioned", False)
            node.setdefault("pep", False)
            node.setdefault("type", "Entity")
            mini_nodes[eid] = node
            label_to_id[entity.get("name", "")] = eid

        def _resolve_chain_endpoint(label: str) -> str:
            """Find or create a node for a chain endpoint label."""
            if not label:
                return ""
            # Match by label in existing entities
            if label in label_to_id:
                return label_to_id[label]
            # Check if any existing node has this label
            for nid, n in mini_nodes.items():
                if n.get("name") == label or n.get("label") == label:
                    label_to_id[label] = nid
                    return nid
            # Create a new lightweight node (e.g. a jurisdiction label)
            nid = _slugify(label)
            mini_nodes[nid] = {
                "id": nid,
                "name": label,
                "label": label,
                "type": "Jurisdiction",
                "sanctioned": False,
                "pep": False,
            }
            label_to_id[label] = nid
            return nid

        for link in finding.get("chain", []):
            from_id = _resolve_chain_endpoint(link.get("from", ""))
            to_id = _resolve_chain_endpoint(link.get("to", ""))
            if from_id and to_id and from_id != to_id:
                mini_edges.append({
                    "source": from_id,
                    "target": to_id,
                    "relationship": link.get("rel", "linked"),
                })

        # Ensure every node has a "label" key (some may only have "name")
        for n in mini_nodes.values():
            if "label" not in n:
                n["label"] = n.get("name", "Unknown")

        finding["_mini_nodes"] = list(mini_nodes.values())
        finding["_mini_edges"] = mini_edges

    return json.dumps(
        {
            "mode": "scan",
            "metadata": {
                "scan_types": data.get("scan_types", []),
                "query": data.get("query"),
                "generated_at": data.get("generated_at")
                    or datetime.now(timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    ),
                "sift_version": __version__,
            },
            "budget": data.get("budget", {}),
            "findings": findings,
            "summary": data.get("summary", {}),
        },
        ensure_ascii=False,
    )



# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _extract_timeline_events(data: dict, nodes: list[dict]) -> list[dict]:
    """Extract all datable events from investigation data for the timeline.

    Scans OpenSanctions results for sanctions designation dates,
    enforcement actions, director disqualifications, and other
    temporal events that the graph builder doesn't capture.
    Returns a list of event dicts with ``date``, ``label``,
    ``source``, ``type``, and optionally ``detail``.
    """
    events: list[dict] = []
    seen = set()  # (date, label) dedup

    def _add(date_str: str, label: str, source: str, event_type: str,
             detail: str = "") -> None:
        if not date_str or not label:
            return
        # Normalize date — take first 10 chars (YYYY-MM-DD)
        d = date_str[:10]
        if len(d) < 4:
            return
        key = (d, label[:50], event_type)
        if key in seen:
            return
        seen.add(key)
        events.append({
            "date": d,
            "label": label[:80],
            "source": source,
            "type": event_type,
            **({"detail": detail} if detail else {}),
        })

    # --- OpenSanctions results: sanctions, designations, enforcement ---
    for r in data.get("opensanctions_results", []):
        if not isinstance(r, dict):
            continue
        props = r.get("properties", {})
        caption = r.get("caption", "")

        # Sanctions designation dates
        for sanc in props.get("sanctions", []):
            if not isinstance(sanc, dict):
                continue
            sp = sanc.get("properties", {})
            for sd in sp.get("startDate", []):
                authority = ", ".join(sp.get("authority", []))[:60]
                provisions = ", ".join(sp.get("provisions", []))[:80]
                program = (sp.get("program", [""])[0] or "")[:80]
                detail_parts = []
                if authority:
                    detail_parts.append(authority)
                if program:
                    detail_parts.append(program)
                if provisions:
                    detail_parts.append(provisions)
                _add(sd, caption, "opensanctions",
                     "Sanctions Designation",
                     ". ".join(detail_parts))

            # Modification dates
            for md in sp.get("modifiedAt", []):
                _add(md, caption, "opensanctions",
                     "Sanctions Modified",
                     f"Sanctions listing modified. {', '.join(sp.get('authority', []))[:60]}")

        # Director disqualification
        for note in props.get("notes", []):
            if not isinstance(note, str):
                continue
            if "Director Disqualification" in note:
                # Try to extract date from "imposed on DD/MM/YYYY"
                import re as _re
                dm = _re.search(r"imposed on (\d{2}/\d{2}/\d{4})", note)
                if dm:
                    parts = dm.group(1).split("/")
                    iso_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    _add(iso_date, caption, "opensanctions",
                         "Director Disqualification", note[:120])

        # Entity created/modified dates from OpenSanctions
        for cd in props.get("createdAt", []):
            _add(cd, caption, "opensanctions", "Entity Listed",
                 "First listed in enforcement/sanctions database")

        # First seen / last change (use sparingly — only for sanctioned/crime entities)
        topics = props.get("topics", [])
        if any(t in topics for t in ("sanction", "crime", "crime.fin", "wanted")):
            first_seen = r.get("first_seen", "")
            if first_seen:
                _add(first_seen[:10], caption, "opensanctions",
                     "First Flagged",
                     "First appearance in OpenSanctions database")
            last_change = r.get("last_change", "")
            if last_change:
                _add(last_change[:10], caption, "opensanctions",
                     "Record Updated",
                     "Most recent update to this entity's record")

    # --- Enrichment data: Wikidata career/PEP dates ---
    for pep in data.get("wikidata_pep", []):
        if isinstance(pep, dict):
            pos = pep.get("positionLabel", "")
            start = pep.get("start", "")
            end = pep.get("end", "")
            query = data.get("query", "")
            if start:
                _add(start[:10], query, "wikidata",
                     "Position Started", f"Appointed: {pos}")
            if end:
                _add(end[:10], query, "wikidata",
                     "Position Ended", f"Left office: {pos}")

    for career in data.get("wikidata_career", []):
        if isinstance(career, dict):
            pos = career.get("positionLabel", career.get("employerLabel", ""))
            start = career.get("start", "")
            end = career.get("end", "")
            query = data.get("query", "")
            if start and pos:
                _add(start[:10], query, "wikidata",
                     "Career Event", f"Started: {pos}")
            if end and pos:
                _add(end[:10], query, "wikidata",
                     "Career Event", f"Ended: {pos}")

    # --- UK Companies House filing history ---
    for filing in data.get("uk_filing_history", []):
        if isinstance(filing, dict):
            fd = filing.get("date", "")
            desc = filing.get("description", "")
            company = filing.get("company_name", "")
            if fd:
                _add(fd, company or desc[:40], "companies_house",
                     "UK Filing", desc[:100])

    # --- Court case dates (from enrichment, not just nodes) ---
    for case in data.get("court_cases", []):
        if isinstance(case, dict):
            fd = case.get("dateFiled", case.get("date_filed", ""))
            name = case.get("caseName", case.get("case_name", ""))
            terminated = case.get("dateTerminated", "")
            if fd:
                _add(fd, name[:60], "courtlistener",
                     "Case Filed",
                     case.get("cause", "")[:100])
            if terminated:
                _add(terminated, name[:60], "courtlistener",
                     "Case Terminated", "")

    # --- UK insolvency dates ---
    for case in data.get("uk_insolvency", []):
        if isinstance(case, dict):
            for d in case.get("dates", []):
                if isinstance(d, dict) and d.get("date"):
                    _add(d["date"], case.get("type", "Insolvency"),
                         "companies_house", "Insolvency Event",
                         d.get("type", ""))
            for p in case.get("practitioners", []):
                if isinstance(p, dict) and p.get("appointed_on"):
                    _add(p["appointed_on"], p.get("name", ""),
                         "companies_house", "Practitioner Appointed",
                         p.get("role", ""))

    # --- SEC 8-K material events ---
    for event in data.get("sec_8k_events", []):
        if isinstance(event, dict):
            fd = event.get("filing_date", "")
            if fd:
                items = event.get("items", [])
                desc = "; ".join(
                    i.get("title", i.get("item", ""))
                    for i in items[:3]
                ) if items else "8-K Event"
                _add(fd, desc[:80], "sec", "Material Event", desc[:200])

    # --- SEC amendment filings ---
    for amend in data.get("sec_amendments", []):
        if isinstance(amend, dict):
            fd = amend.get("filing_date", "")
            if fd:
                _add(fd, amend.get("form", "Amendment"), "sec",
                     "Filing Amendment", f"Form {amend.get('form', '')}")

    # --- Property transactions ---
    for tx in data.get("land_transactions", []):
        if isinstance(tx, dict):
            fd = tx.get("date", "")
            if fd:
                price = tx.get("price")
                addr = tx.get("property_address", {})
                loc = f"{addr.get('street', '')} {addr.get('town', '')}".strip()
                price_str = f"£{price:,}" if price else ""
                _add(fd, loc or "Property", "land_registry",
                     "Property Transaction", f"{price_str} {loc}".strip())

    # --- Bankruptcy cases ---
    for case in data.get("court_bankruptcy", []):
        if isinstance(case, dict):
            fd = case.get("dateFiled", case.get("date_filed", ""))
            name = case.get("caseName", case.get("case_name", ""))
            if fd:
                _add(fd, name[:60], "courtlistener",
                     "Bankruptcy Filed", "")

    # Sort by date
    events.sort(key=lambda e: e["date"])
    return events


# Enrichment data keys that the viewer can display
_ENRICHMENT_KEYS = (
    "sec_financials",
    "sec_proxy",
    "sec_8k_events",
    "sec_amendments",
    "uk_accounts",
    "uk_charges",
    "uk_filing_history",
    "uk_insolvency",
    "uk_disqualified_officers",
    "sec_filings",
    "wikidata_family",
    "wikidata_career",
    "wikidata_pep",
    "court_cases",
    "court_details",
    "court_complaints",
    "court_opinions",
    "court_bankruptcy",
    "temporal_overlaps",
    "land_transactions",
    "aleph_documents",
)


def _collect_enrichment(data: dict) -> dict:
    """Extract optional enrichment data for the viewer.

    Returns a dict of only those enrichment keys that are present
    and non-empty in *data*.  Returns an empty dict (falsy) when
    no enrichment data exists.
    """
    enrichment: dict = {}
    for key in _ENRICHMENT_KEYS:
        value = data.get(key)
        if value:  # skip None, empty list, empty dict
            enrichment[key] = value
    return enrichment


def _build_graph(data: dict) -> tuple[list[dict], list[dict]]:
    # Phase 1: collect raw ICIJ nodes before dedup
    raw_icij: dict[str, dict] = {}  # original icij-{id} -> node dict
    edges: list[dict] = []

    # 1. ICIJ results
    for r in data.get("icij_results", []):
        nid = f"icij-{r['id']}"
        node_type = _icij_type(r)
        raw_icij[nid] = {
            "id": nid,
            "label": r.get("name", "Unknown"),
            "type": node_type,
            "source": "icij",
            "jurisdiction": None,
            "investigation": _extract_investigation(r.get("description", "")),
            "sanctioned": False,
            "pep": False,
            "topics": [],
            "datasets": [],
            "score": r.get("score"),
            "incorporation_date": None,
            "country_codes": [],
            "hop": r.get("hop", 0),
            "confidence": r.get("confidence", 0),
            "risk_score": r.get("risk_score", 0),
            "risk_level": r.get("risk_level", ""),
        }

    # 2. ICIJ entity details (enrich existing or add new)
    for nid_raw, detail in (data.get("icij_entities") or {}).items():
        nid = f"icij-{nid_raw}"
        countries = [c["str"] for c in detail.get("country_codes", [])]
        if nid in raw_icij:
            raw_icij[nid]["country_codes"] = countries
        else:
            names = detail.get("name", [])
            label = names[0]["str"] if names else str(nid_raw)
            raw_icij[nid] = _make_icij_node(nid, label, countries, detail)

    # 3. ICIJ extended properties (enrich)
    extended = data.get("icij_extended") or {}
    for nid_raw, row in (extended.get("rows") or {}).items():
        nid = f"icij-{nid_raw}"
        if nid in raw_icij:
            countries = [c["str"] for c in row.get("country_codes", [])]
            if countries:
                raw_icij[nid]["country_codes"] = countries
            inc = row.get("incorporation_date", [])
            if inc:
                raw_icij[nid]["incorporation_date"] = inc[0]["str"] if isinstance(inc[0], dict) else inc[0]
            jur = row.get("jurisdiction", [])
            if jur:
                raw_icij[nid]["jurisdiction"] = jur[0]["str"] if isinstance(jur[0], dict) else jur[0]

    # Phase 2: Deduplicate same-name ICIJ nodes of the same type.
    # ICIJ returns a separate Officer node for each entity relationship,
    # so "NURALI ALIYEV" appears 8 times as Officer.  We merge these into
    # a single person node and keep the network edges pointing through it.
    #
    # Entities / Intermediaries / Addresses with the same name in different
    # investigations are kept separate (they are genuinely different records).

    merge_types = {"Officer", "Person"}
    # normalized_name -> canonical id
    canonical: dict[str, str] = {}
    # original id -> canonical id  (for edge rewriting)
    id_remap: dict[str, str] = {}
    nodes_map: dict[str, dict] = {}

    for nid, node in raw_icij.items():
        if node["type"] in merge_types:
            norm = _normalize_name(node["label"])
            if norm in canonical:
                # Merge into existing canonical node
                canon_id = canonical[norm]
                canon = nodes_map[canon_id]
                # Accumulate metadata
                canon["country_codes"] = list(
                    dict.fromkeys(canon["country_codes"] + node["country_codes"])
                )
                if node["investigation"] and node["investigation"] != canon["investigation"]:
                    # Track multiple investigations
                    inv_set = set(
                        (canon.get("_investigations") or [canon["investigation"]])
                    )
                    inv_set.discard(None)
                    inv_set.add(node["investigation"])
                    canon["_investigations"] = sorted(inv_set)
                    canon["investigation"] = ", ".join(sorted(inv_set))
                if node["score"] and (not canon["score"] or node["score"] > canon["score"]):
                    canon["score"] = node["score"]
                canon["_merged_count"] = canon.get("_merged_count", 1) + 1
                id_remap[nid] = canon_id
            else:
                canonical[norm] = nid
                id_remap[nid] = nid
                node["_merged_count"] = 1
                nodes_map[nid] = node
        else:
            # Non-officer nodes kept as-is
            id_remap[nid] = nid
            nodes_map[nid] = node

    # Store base name for cross-ref matching, then update display labels
    for nid, node in nodes_map.items():
        node["_base_name"] = node["label"]
        mc = node.get("_merged_count", 1)
        if mc > 1 and node["type"] in merge_types:
            countries = node["country_codes"]
            suffix_parts = []
            if countries:
                suffix_parts.append(", ".join(countries[:3]))
            suffix_parts.append(f"{mc} entities")
            node["label"] = f"{node['label']}  ({'; '.join(suffix_parts)})"

    # 4. OpenSanctions results + new sources (GLEIF, SEC, UK, Court)
    # New sources arrive here via result_to_visualizer_data with IDs like
    # "gleif-XXX", "sec-XXX", "uk-XXX", "court-XXX" and datasets: ["gleif"] etc.
    _source_from_id = {
        "gleif-": "gleif", "sec-": "sec",
        "uk-": "companies_house", "court-": "courtlistener",
        "aleph-": "aleph", "wikidata-": "wikidata",
        "land-": "land_registry",
    }
    for r in data.get("opensanctions_results", []):
        raw_id = r['id']
        # Detect source from ID prefix
        source = "opensanctions"
        for prefix, src in _source_from_id.items():
            if str(raw_id).startswith(prefix):
                source = src
                break
        oid = raw_id if any(raw_id.startswith(p) for p in _source_from_id) else (
            raw_id if raw_id.startswith("os-") else f"os-{raw_id}"
        )
        props = r.get("properties", {})
        topics = props.get("topics", r.get("topics", []))
        nodes_map[oid] = {
            "id": oid,
            "label": r.get("caption", r.get("name", ["Unknown"])[0] if isinstance(r.get("name"), list) else "Unknown"),
            "type": r.get("schema", "Person"),
            "source": source,
            "jurisdiction": None,
            "investigation": None,
            "sanctioned": "sanction" in topics,
            "pep": "role.pep" in topics,
            "topics": topics,
            "datasets": r.get("datasets", []),
            "score": r.get("score"),
            "incorporation_date": None,
            "file_date": r.get("file_date", ""),
            "date_filed": r.get("date_filed", ""),
            "country_codes": props.get("nationality", props.get("citizenship", [])),
            "hop": r.get("hop", 0),
            "confidence": r.get("confidence", 0),
            "risk_score": r.get("risk_score", 0),
            "risk_level": r.get("risk_level", ""),
        }

    # 5. Network edges (rewrite through canonical IDs, handle mixed sources)
    seen_edges: set[tuple[str, str, str]] = set()

    def _resolve_edge_id(raw_id: str) -> str:
        """Resolve a raw edge ID to an existing node ID."""
        # Direct match — already exists in the graph
        if raw_id in nodes_map:
            return raw_id

        # Canonical remap (merged officer nodes)
        if raw_id in id_remap:
            return id_remap[raw_id]

        # Try with icij- prefix (ICIJ nodes stored as icij-{id})
        icij_key = f"icij-{raw_id}"
        if icij_key in id_remap:
            return id_remap[icij_key]
        if icij_key in nodes_map:
            return icij_key

        # Try with os- prefix (OpenSanctions nodes)
        os_key = f"os-{raw_id}"
        if os_key in nodes_map:
            return os_key

        # For IDs with source prefixes that didn't match above,
        # try stripping icij- to find the real node (e.g. icij-uk-123 -> uk-123)
        if raw_id.startswith("icij-"):
            stripped = raw_id[5:]
            if stripped in nodes_map:
                return stripped

        # Fallback: return icij- prefixed (will be created as stub)
        return icij_key

    for e in data.get("icij_network", []):
        src = _resolve_edge_id(e["source_id"])
        tgt = _resolve_edge_id(e["target_id"])
        # Ensure both endpoints exist
        for eid in (src, tgt):
            if eid not in nodes_map:
                nodes_map[eid] = _make_icij_node(eid, _readable_label(eid), [], {})
        rel = e.get("relationship", "linked")
        key = (src, tgt, rel)
        if key not in seen_edges and src != tgt:
            seen_edges.add(key)
            edges.append({"source": src, "target": tgt, "relationship": rel})

    # 6. Cross-reference merge: find matching names across sources
    icij_nodes = {k: v for k, v in nodes_map.items() if v["source"] == "icij"}
    os_nodes = {k: v for k, v in nodes_map.items() if v["source"] == "opensanctions"}
    os_merged: set[str] = set()

    # os_id -> icij_id mapping for edge rewriting after merge
    merge_remap: dict[str, str] = {}

    for icij_id, icij_n in icij_nodes.items():
        norm_icij = _normalize_name(icij_n.get("_base_name", icij_n["label"]))
        for os_id, os_n in os_nodes.items():
            norm_os = _normalize_name(os_n.get("_base_name", os_n["label"]))
            if norm_icij and norm_os and norm_icij == norm_os:
                # Merge into ICIJ node, mark as both
                icij_n["source"] = "both"
                icij_n["sanctioned"] = icij_n["sanctioned"] or os_n["sanctioned"]
                icij_n["pep"] = icij_n["pep"] or os_n["pep"]
                icij_n["topics"] = list(set(icij_n.get("topics", []) + os_n.get("topics", [])))
                icij_n["datasets"] = list(set(icij_n.get("datasets", []) + os_n.get("datasets", [])))
                if not icij_n["country_codes"] and os_n["country_codes"]:
                    icij_n["country_codes"] = os_n["country_codes"]
                os_merged.add(os_id)
                merge_remap[os_id] = icij_id

    # Remove merged OS nodes and rewrite edges to point to the merged node
    for os_id in os_merged:
        nodes_map.pop(os_id, None)

    for e in edges:
        if e["source"] in merge_remap:
            e["source"] = merge_remap[e["source"]]
        if e["target"] in merge_remap:
            e["target"] = merge_remap[e["target"]]

    # 6b. Within-source deduplication for non-ICIJ person/officer nodes.
    # OpenSanctions, Wikidata, etc. can return multiple entries for the
    # same person (different datasets, different name variants).
    person_types = {"Person", "Officer", "person", "officer"}
    name_to_canonical: dict[str, str] = {}
    within_remap: dict[str, str] = {}

    for nid, node in list(nodes_map.items()):
        if nid in os_merged:
            continue
        if node.get("type") not in person_types:
            continue
        norm = _normalize_name(node.get("_base_name", node["label"]))
        if not norm:
            continue
        if norm in name_to_canonical:
            canon_id = name_to_canonical[norm]
            canon = nodes_map[canon_id]
            # Merge flags into canonical
            canon["sanctioned"] = canon["sanctioned"] or node.get("sanctioned", False)
            canon["pep"] = canon["pep"] or node.get("pep", False)
            canon["topics"] = list(set(canon.get("topics", []) + node.get("topics", [])))
            canon["datasets"] = list(set(canon.get("datasets", []) + node.get("datasets", [])))
            if not canon["country_codes"] and node.get("country_codes"):
                canon["country_codes"] = node["country_codes"]
            if node.get("source") != canon.get("source"):
                canon["source"] = "both"
            within_remap[nid] = canon_id
        else:
            name_to_canonical[norm] = nid

    for nid in within_remap:
        nodes_map.pop(nid, None)
    for e in edges:
        if e["source"] in within_remap:
            e["source"] = within_remap[e["source"]]
        if e["target"] in within_remap:
            e["target"] = within_remap[e["target"]]

    # Remove edges that reference nodes no longer in the map, or self-loops
    live_ids = set(nodes_map.keys())
    edges = [
        e for e in edges
        if e["source"] in live_ids and e["target"] in live_ids and e["source"] != e["target"]
    ]

    # 7. Add edges between deduplicated ICIJ officers and any OS nodes
    #    with the same name that weren't fully merged (e.g. different person)
    #    — skip, we already merged above.

    # Normalize country codes to uppercase and deduplicate
    for n in nodes_map.values():
        if n.get("country_codes"):
            n["country_codes"] = list(dict.fromkeys(
                c.upper() for c in n["country_codes"] if c
            ))
        if n.get("jurisdiction"):
            n["jurisdiction"] = n["jurisdiction"].upper()

    # Clean up internal keys
    for n in nodes_map.values():
        n.pop("_merged_count", None)
        n.pop("_investigations", None)
        n.pop("_base_name", None)

    return list(nodes_map.values()), edges


def _make_icij_node(nid: str, label: str, countries: list, detail: dict) -> dict:
    return {
        "id": nid,
        "label": label,
        "type": "Officer",
        "source": "icij",
        "jurisdiction": None,
        "investigation": None,
        "sanctioned": False,
        "pep": False,
        "topics": [],
        "datasets": [],
        "score": None,
        "incorporation_date": None,
        "country_codes": countries,
        "hop": detail.get("hop", 0),
    }


def _icij_type(result: dict) -> str:
    types = result.get("types", [])
    if types:
        name = types[0].get("name", "")
        if name:
            return name
    return "Entity"


def _extract_investigation(description: str) -> str | None:
    desc_lower = description.lower()
    for inv in (
        "panama papers", "paradise papers", "pandora papers",
        "bahamas leaks", "offshore leaks",
    ):
        if inv in desc_lower:
            return inv.replace(" ", "-").lower()
    return None


def _readable_label(raw_id: str) -> str:
    """Extract a human-readable label from a raw node ID."""
    # Strip stale icij- prefix (edge resolver may prepend icij- to non-ICIJ IDs)
    if raw_id.startswith("icij-uk-") or raw_id.startswith("icij-aleph-") or \
       raw_id.startswith("icij-wikidata-") or raw_id.startswith("icij-land-") or \
       raw_id.startswith("icij-gleif-") or raw_id.startswith("icij-sec-") or \
       raw_id.startswith("icij-court-"):
        raw_id = raw_id[len("icij-"):]
    # uk-psc-12345678-mr-john-smith -> Mr John Smith
    if raw_id.startswith("uk-psc-"):
        suffix = raw_id[len("uk-psc-"):]
        # Strip leading company number if present (digits followed by dash)
        parts = suffix.split("-", 1)
        if len(parts) > 1 and parts[0].isdigit():
            suffix = parts[1]
        return suffix.replace("-", " ").title()
    # uk-12345678 -> Company 12345678
    if raw_id.startswith("uk-"):
        number = raw_id[len("uk-"):]
        if number.replace("-", "").isdigit():
            return f"Company {number}"
        return number.replace("-", " ").title()
    # aleph-abc123 -> Aleph Entity abc123
    if raw_id.startswith("aleph-"):
        return f"Aleph Entity {raw_id[len('aleph-'):]}"
    # wikidata-Q12345 -> Wikidata Q12345
    if raw_id.startswith("wikidata-"):
        return f"Wikidata {raw_id[len('wikidata-'):]}"
    # land-xxx -> Land Registry xxx
    if raw_id.startswith("land-"):
        return f"Land Registry {raw_id[len('land-'):]}"
    # gleif-xxx -> GLEIF xxx
    if raw_id.startswith("gleif-"):
        return f"GLEIF {raw_id[len('gleif-'):]}"
    # sec-xxx -> SEC xxx
    if raw_id.startswith("sec-"):
        return f"SEC {raw_id[len('sec-'):]}"
    # court-xxx -> Court xxx
    if raw_id.startswith("court-"):
        return f"Court {raw_id[len('court-'):]}"
    # icij-xxx -> strip prefix
    if raw_id.startswith("icij-"):
        return raw_id[len("icij-"):]
    # os-xxx -> strip prefix
    if raw_id.startswith("os-"):
        return raw_id[len("os-"):]
    return raw_id


def _normalize_name(name: str) -> str:
    import unicodedata
    # Decompose accented chars and strip diacritics
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase, strip non-alpha, remove common titles
    cleaned = re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()
    cleaned = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|sir|dame|lord|lady)\b", "", cleaned).strip()
    # Sort words so "DOS SANTOS ISABEL" == "ISABEL DOS SANTOS"
    return " ".join(sorted(cleaned.split()))


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] if slug else "investigation"


def _generate_next_steps(
    nodes: list[dict], edges: list[dict], data: dict,
) -> list[dict]:
    """Generate recommended next steps from the graph data.

    Called as a fallback when the investigation skill hasn't provided
    its own ``next_steps``.  Examines the actual findings to produce
    specific, actionable recommendations.
    """
    steps: list[dict] = []
    query = data.get("query", "the subject")
    patterns = data.get("pattern_matches", [])

    sanctioned = [n for n in nodes if n.get("sanctioned")]
    peps = [n for n in nodes if n.get("pep")]
    sources_found = {n.get("source") for n in nodes if n.get("source")}
    countries = set()
    for n in nodes:
        for c in n.get("country_codes", []):
            countries.add(c.upper() if c else "")
    countries.discard("")

    investigations = {
        n.get("investigation")
        for n in nodes
        if n.get("investigation")
    }
    investigations.discard(None)

    max_hop = max((n.get("hop", 0) for n in nodes), default=0)

    # Sanctions exposure
    if sanctioned:
        names = ", ".join(n.get("label", "?") for n in sanctioned[:3])
        extra = f" and {len(sanctioned) - 3} more" if len(sanctioned) > 3 else ""
        steps.append({
            "priority": "CRITICAL",
            "title": "Legal/compliance review — active sanctions exposure",
            "description": (
                f"{len(sanctioned)} sanctioned entit{'ies' if len(sanctioned) > 1 else 'y'} "
                f"identified: {names}{extra}. Consult legal counsel before any financial "
                f"transactions or business relationships involving these entities."
            ),
            "command": f"/investigate {query} --compliance",
        })

    # PEP connections
    if peps:
        steps.append({
            "priority": "HIGH",
            "title": "Enhanced Due Diligence for PEP connections",
            "description": (
                f"{len(peps)} politically exposed person{'s' if len(peps) > 1 else ''} "
                f"connected to this network. AML regulations require source-of-wealth "
                f"verification, senior management approval, and ongoing monitoring."
            ),
            "command": f"/investigate {query} --compliance",
        })

    # Deeper traversal
    if max_hop <= 2:
        steps.append({
            "priority": "RECOMMENDED",
            "title": "Deepen the network trace",
            "description": (
                f"Current traversal reached {max_hop} hop{'s' if max_hop != 1 else ''}. "
                f"Run with depth 3 to expand the perimeter — "
                f"officers and intermediaries at the network edge may have significant "
                f"connections not yet visible."
            ),
            "command": f"/investigate {query} --trace --depth 3",
        })

    # Cross-reference with associates
    def _edge_id(val):
        return val.get("id", val) if isinstance(val, dict) else val

    high_degree = sorted(
        [(n, sum(1 for e in edges if n["id"] in (
            _edge_id(e.get("source", "")),
            _edge_id(e.get("target", "")),
        ))) for n in nodes if n.get("type") in ("Officer", "Person") and n.get("hop", 0) > 0],
        key=lambda x: -x[1],
    )
    if high_degree:
        top = high_degree[0][0]
        top_label = top.get("label", "key officer")
        steps.append({
            "priority": "RECOMMENDED",
            "title": f"Investigate {top_label}",
            "description": (
                f"'{top_label}' is the most connected person in the network. "
                f"Run a separate investigation to map their full offshore footprint and "
                f"identify shared structures."
            ),
            "command": f"/investigate {top_label} --trace",
        })

    # Missing sources
    if "aleph" not in sources_found:
        steps.append({
            "priority": "RECOMMENDED",
            "title": "Add OCCRP Aleph API key",
            "description": (
                "Aleph returned no results — it may require an API key for full access. "
                "Register free at aleph.occrp.org and set ALEPH_API_KEY in .env. "
                "Aleph contains investigative documents and leaked datasets that could "
                "provide source documents for this investigation."
            ),
        })

    # High-risk patterns
    crit_patterns = [p for p in patterns if p.get("risk") in ("CRITICAL", "HIGH")]
    if crit_patterns:
        names = ", ".join(p.get("title", p.get("pattern", "")) for p in crit_patterns[:3])
        steps.append({
            "priority": "HIGH",
            "title": "Investigate high-risk structural patterns",
            "description": (
                f"{len(crit_patterns)} high/critical risk pattern{'s' if len(crit_patterns) > 1 else ''} "
                f"detected: {names}. These indicate structures commonly associated with "
                f"money laundering or sanctions evasion. See the Reference tab for details."
            ),
            "command": f"/investigate {query} --patterns",
        })

    # Monitoring
    steps.append({
        "priority": "ONGOING",
        "title": "Set up sanctions monitoring",
        "description": (
            f"Run periodic monitoring for {query} to detect new sanctions listings. "
            f"Sanctions lists change daily — a clean screen today does not guarantee "
            f"a clean screen tomorrow."
        ),
        "command": f"/investigate {query} --monitor",
    })

    return steps
