"""Transform investigation data into a standalone D3 visualization."""

from __future__ import annotations

import json
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "visualizations" / "investigation-viz.html"
D3_PATH = Path(__file__).resolve().parent.parent / "visualizations" / "d3.v7.min.js"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "investigations"
PLACEHOLDER = "__INVESTIGATION_DATA__"
D3_PLACEHOLDER = "__D3_INLINE__"


def generate_visualization(
    investigation_data: dict,
    output_path: str | Path | None = None,
    open_browser: bool = True,
) -> Path:
    """Build a standalone HTML visualization from investigation results.

    Parameters
    ----------
    investigation_data : dict
        Keys (all optional):
        - ``query``: the original search string
        - ``icij_results``: list of ICIJ reconcile result dicts
        - ``icij_entities``: dict mapping node_id -> entity detail dict
        - ``icij_extended``: dict from ``icij_extend`` (has ``rows`` key)
        - ``icij_network``: list of edge dicts ``{"source_id", "target_id", "relationship"}``
        - ``opensanctions_results``: list of OpenSanctions search/match result dicts
    output_path : str or Path, optional
        Where to write the HTML file.  Defaults to ``investigations/<query>-<timestamp>.html``.
    open_browser : bool
        Open the file in the default browser after writing.

    Returns
    -------
    Path
        The path to the generated HTML file.
    """
    nodes, edges = _build_graph(investigation_data)
    graph_json = json.dumps(
        {
            "metadata": {
                "query": investigation_data.get("query", "Investigation"),
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            },
            "nodes": nodes,
            "edges": edges,
            "pattern_matches": investigation_data.get("pattern_matches", []),
        },
        ensure_ascii=False,
    )

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    d3_js = D3_PATH.read_text(encoding="utf-8") if D3_PATH.exists() else ""
    html = template.replace(D3_PLACEHOLDER, d3_js).replace(PLACEHOLDER, graph_json)

    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = _slugify(investigation_data.get("query", "investigation"))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"{slug}-{ts}.html"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(output_path.as_uri())

    return output_path


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

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
        }

    # 5. Network edges (rewrite through canonical IDs, handle mixed sources)
    seen_edges: set[tuple[str, str, str]] = set()

    def _resolve_edge_id(raw_id: str) -> str:
        """Resolve a raw edge ID to an existing node ID."""
        # If the raw_id already has a prefix and exists, use it directly
        if raw_id.startswith("os-") and raw_id in nodes_map:
            return raw_id
        if raw_id.startswith("icij-"):
            if raw_id in id_remap:
                return id_remap[raw_id]
            if raw_id in nodes_map:
                return raw_id

        # Try canonical remap with icij- prefix (for merged officer nodes)
        icij_key = f"icij-{raw_id}"
        if icij_key in id_remap:
            return id_remap[icij_key]

        # Try os- prefix (for OpenSanctions nodes referenced by raw ID)
        os_key = f"os-{raw_id}"
        if os_key in nodes_map:
            return os_key

        # Try icij- prefix directly
        if icij_key in nodes_map:
            return icij_key

        # Last resort: check if already-prefixed os- version exists
        if raw_id.startswith("os-"):
            return raw_id

        # Fallback: return icij- prefixed (will be created as stub)
        return icij_key

    for e in data.get("icij_network", []):
        src = _resolve_edge_id(e["source_id"])
        tgt = _resolve_edge_id(e["target_id"])
        # Ensure both endpoints exist
        for eid in (src, tgt):
            if eid not in nodes_map:
                nodes_map[eid] = _make_icij_node(eid, eid, [], {})
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

    # Remove edges that reference nodes no longer in the map, or self-loops
    live_ids = set(nodes_map.keys())
    edges = [
        e for e in edges
        if e["source"] in live_ids and e["target"] in live_ids and e["source"] != e["target"]
    ]

    # 7. Add edges between deduplicated ICIJ officers and any OS nodes
    #    with the same name that weren't fully merged (e.g. different person)
    #    — skip, we already merged above.

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


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] if slug else "investigation"
