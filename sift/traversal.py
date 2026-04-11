"""Multi-hop graph traversal across ICIJ and OpenSanctions."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    source: str  # "icij" | "opensanctions" | "both"
    label: str
    node_type: str
    hop: int
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relationship: str
    hop: int


@dataclass
class TraversalResult:
    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]
    pruned: list[str]
    budget_exhausted: bool
    stats: dict
    pattern_matches: list[dict] = field(default_factory=list)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _inv_from_desc(desc: str) -> str | None:
    dl = desc.lower()
    for inv in ("panama papers", "paradise papers", "pandora papers",
                "bahamas leaks", "offshore leaks"):
        if inv in dl:
            return inv.replace(" ", "-")
    return None


def _icij_type(r: dict) -> str:
    types = r.get("types", [])
    return types[0].get("name", "Entity") if types else "Entity"


async def traverse(
    icij_client: Any,
    os_client: Any,
    seed_names: list[str],
    max_depth: int = 2,
    budget: int = 50,
    max_fanout: int = 25,
    investigation: str | None = None,
    gleif_client: Any | None = None,
    sec_client: Any | None = None,
    ch_client: Any | None = None,
    cl_client: Any | None = None,
) -> TraversalResult:
    """Breadth-first traversal across multiple databases.

    Parameters
    ----------
    icij_client, os_client : Core API client instances
    seed_names : Starting names to search
    max_depth : Maximum hops from seed (1-3)
    budget : Maximum total API calls
    max_fanout : Skip nodes with more connections than this
    investigation : Limit ICIJ to a specific leak dataset
    gleif_client : GLEIF LEI Registry client (optional)
    sec_client : SEC EDGAR client (optional)
    ch_client : UK Companies House client (optional)
    cl_client : CourtListener client (optional)
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    pruned: list[str] = []
    visited_names: set[str] = set()
    api_calls = 0
    sem = asyncio.Semaphore(3)

    async def _api(coro):
        nonlocal api_calls
        if api_calls >= budget:
            return None
        async with sem:
            api_calls += 1
            await asyncio.sleep(0.15)
            return await coro

    def _add_node(nid: str, source: str, label: str, ntype: str, hop: int,
                  props: dict | None = None) -> bool:
        """Add node if new. Returns True if newly added."""
        if nid in nodes:
            existing = nodes[nid]
            if source != existing.source and existing.source != "both":
                existing.source = "both"
            return False
        nodes[nid] = GraphNode(
            id=nid, source=source, label=label, node_type=ntype,
            hop=hop, properties=props or {},
        )
        return True

    def _add_edge(src: str, tgt: str, rel: str, hop: int):
        if src != tgt and not any(
            e.source_id == src and e.target_id == tgt and e.relationship == rel
            for e in edges
        ):
            edges.append(GraphEdge(src, tgt, rel, hop))

    # ── Hop 0: Seed ──────────────────────────────────────────

    for name in seed_names:
        norm = _normalize(name)
        if norm in visited_names:
            continue
        visited_names.add(norm)

        # ICIJ search
        kwargs = {"query": name}
        if investigation:
            kwargs["investigation"] = investigation
        icij_res = await _api(icij_client.reconcile(**kwargs))
        if icij_res:
            for r in icij_res.get("result", [])[:10]:
                nid = f"icij-{r['id']}"
                _add_node(nid, "icij", r["name"], _icij_type(r), 0, {
                    "score": r.get("score"),
                    "investigation": _inv_from_desc(r.get("description", "")),
                    "description": r.get("description", ""),
                })

        # OpenSanctions match
        if os_client is None:
            os_res = None
        else:
            os_res = await _api(os_client.match(
                queries={"q0": {"schema": "Thing", "properties": {"name": [name]}}},
                threshold=0.5,
            ))
        if os_res:
            for qkey, qval in os_res.get("responses", {}).items():
                for r in qval.get("results", [])[:10]:
                    oid = f"os-{r['id']}"
                    props = r.get("properties", {})
                    topics = props.get("topics", r.get("topics", []))
                    _add_node(oid, "opensanctions", r.get("caption", "?"),
                              r.get("schema", "Person"), 0, {
                        "score": r.get("score"),
                        "topics": topics,
                        "datasets": r.get("datasets", []),
                        "sanctioned": "sanction" in topics,
                        "pep": "role.pep" in topics,
                        "country_codes": props.get("nationality",
                                                   props.get("citizenship", [])),
                    })

        # GLEIF search
        if gleif_client and api_calls < budget:
            gleif_res = await _api(gleif_client.search(name, page_size=5))
            if gleif_res:
                for r in gleif_res.get("results", [])[:5]:
                    lei = r.get("lei", "")
                    if lei:
                        nid = f"gleif-{lei}"
                        _add_node(nid, "gleif", r.get("legal_name", lei),
                                  "Company", 0, {
                            "lei": lei,
                            "jurisdiction": r.get("jurisdiction", ""),
                            "country_codes": [r["country"]] if r.get("country") else [],
                            "status": r.get("status", ""),
                        })

        # SEC EDGAR search
        if sec_client and api_calls < budget:
            try:
                sec_res = await _api(sec_client.search(name, count=5))
                if sec_res:
                    for r in sec_res.get("results", [])[:5]:
                        cik = str(r.get("cik", ""))
                        if cik:
                            nid = f"sec-{cik}"
                            _add_node(nid, "sec", r.get("entity_name", cik),
                                      "Company", 0, {
                                "cik": cik,
                                "filing_type": r.get("filing_type", ""),
                                "file_date": r.get("file_date", ""),
                            })
            except Exception:
                pass  # SEC rate limits or connectivity issues

        # UK Companies House search
        if ch_client and api_calls < budget:
            try:
                ch_res = await _api(ch_client.search_company(name, items_per_page=5))
                if ch_res:
                    for r in ch_res.get("items", [])[:5]:
                        cn = r.get("company_number", "")
                        if cn:
                            nid = f"uk-{cn}"
                            _add_node(nid, "companies_house",
                                      r.get("title", cn), "Company", 0, {
                                "company_number": cn,
                                "company_status": r.get("company_status", ""),
                                "address": r.get("address_snippet", ""),
                            })
            except Exception:
                pass  # No API key or connectivity issues

        # CourtListener search
        if cl_client and api_calls < budget:
            try:
                cl_res = await _api(cl_client.search(name, type="r"))
                if cl_res:
                    for r in cl_res.get("results", [])[:3]:
                        did = r.get("docket_id") or r.get("id")
                        if did:
                            nid = f"court-{did}"
                            _add_node(nid, "courtlistener",
                                      r.get("caseName", r.get("case_name", str(did))),
                                      "Case", 0, {
                                "docket_id": did,
                                "court": r.get("court", ""),
                                "date_filed": r.get("dateFiled", r.get("date_filed", "")),
                            })
            except Exception:
                pass  # No token or connectivity issues

    # ── Hops 1..N ────────────────────────────────────────────

    for hop in range(1, max_depth + 1):
        if api_calls >= budget:
            break

        # Build frontier: nodes from previous hop to expand
        frontier = [n for n in nodes.values() if n.hop == hop - 1]

        # Prioritize: sanctioned > PEP > RCA > others
        def _priority(n: GraphNode) -> int:
            p = n.properties
            if p.get("sanctioned"):
                return 0
            if p.get("pep"):
                return 1
            if "role.rca" in p.get("topics", []):
                return 2
            return 3
        frontier.sort(key=_priority)

        for fnode in frontier:
            if api_calls >= budget:
                break

            # ── Expand OpenSanctions nodes via get_adjacent ──
            if os_client and fnode.source in ("opensanctions", "both") and fnode.id.startswith("os-"):
                entity_id = fnode.id[3:]
                adj = await _api(os_client.get_adjacent(
                    entity_id, limit=max_fanout + 1,
                ))
                if adj:
                    results = adj.get("results", [])
                    if len(results) > max_fanout:
                        pruned.append(fnode.id)
                        continue
                    for ar in results:
                        aid = f"os-{ar['id']}"
                        aprops = ar.get("properties", {})
                        atopics = aprops.get("topics", ar.get("topics", []))
                        is_new = _add_node(aid, "opensanctions",
                                           ar.get("caption", "?"),
                                           ar.get("schema", "Unknown"), hop, {
                            "topics": atopics,
                            "datasets": ar.get("datasets", []),
                            "sanctioned": "sanction" in atopics,
                            "pep": "role.pep" in atopics,
                            "country_codes": aprops.get("nationality",
                                                        aprops.get("citizenship", [])),
                        })
                        rel = ar.get("schema", "related").lower()
                        _add_edge(fnode.id, aid, rel, hop)

                        # Cross-source bridge: check ICIJ for this name
                        if is_new and api_calls < budget:
                            aname = ar.get("caption", "")
                            anorm = _normalize(aname)
                            if anorm and anorm not in visited_names:
                                visited_names.add(anorm)
                                icij_bridge = await _api(
                                    icij_client.reconcile(query=aname)
                                )
                                if icij_bridge:
                                    for br in icij_bridge.get("result", [])[:5]:
                                        if br.get("score", 0) > 50:
                                            bid = f"icij-{br['id']}"
                                            _add_node(bid, "icij", br["name"],
                                                      _icij_type(br), hop, {
                                                "score": br.get("score"),
                                                "investigation": _inv_from_desc(
                                                    br.get("description", "")),
                                            })
                                            _add_edge(aid, bid, "cross-reference", hop)

            # ── Expand ICIJ nodes via name re-search ──
            if fnode.source in ("icij", "both") and fnode.id.startswith("icij-"):
                node_id = int(fnode.id[5:])
                # Get entity details for richer data
                detail = await _api(icij_client.get_node(node_id))
                if detail:
                    countries = [c["str"] for c in detail.get("country_codes", [])]
                    fnode.properties["country_codes"] = countries

                # Search for the node's name to find co-occurring entities
                fname = fnode.label
                fnorm = _normalize(fname)
                if fnorm not in visited_names:
                    visited_names.add(fnorm)
                    icij_res2 = await _api(icij_client.reconcile(query=fname))
                    if icij_res2:
                        for r in icij_res2.get("result", [])[:8]:
                            rid = f"icij-{r['id']}"
                            if rid == fnode.id:
                                continue
                            rtype = _icij_type(r)
                            is_new = _add_node(rid, "icij", r["name"],
                                              rtype, hop, {
                                "score": r.get("score"),
                                "investigation": _inv_from_desc(
                                    r.get("description", "")),
                            })
                            # Infer relationship from types
                            if rtype == "Intermediary":
                                rel = "intermediary_of"
                            elif rtype == "Officer":
                                rel = "co_officer"
                            elif rtype == "Address":
                                rel = "registered_at"
                            else:
                                rel = "connected"
                            _add_edge(fnode.id, rid, rel, hop)

                # Cross-source bridge: check OpenSanctions
                if os_client and fnorm:
                    os_bridge = await _api(os_client.match(
                        queries={"q0": {"schema": "Thing", "properties": {"name": [fname]}}},
                        threshold=0.7,
                    ))
                    if os_bridge:
                        for qkey, qval in os_bridge.get("responses", {}).items():
                            for r in qval.get("results", [])[:3]:
                                if r.get("score", 0) >= 0.7:
                                    oid = f"os-{r['id']}"
                                    oprops = r.get("properties", {})
                                    otopics = oprops.get("topics",
                                                         r.get("topics", []))
                                    _add_node(oid, "opensanctions",
                                              r.get("caption", "?"),
                                              r.get("schema", "Person"), hop, {
                                        "topics": otopics,
                                        "datasets": r.get("datasets", []),
                                        "sanctioned": "sanction" in otopics,
                                        "pep": "role.pep" in otopics,
                                        "country_codes": oprops.get(
                                            "nationality",
                                            oprops.get("citizenship", [])),
                                    })
                                    _add_edge(fnode.id, oid, "cross-reference", hop)

            # ── Expand GLEIF nodes via ownership chain ──
            if gleif_client and fnode.id.startswith("gleif-") and api_calls < budget:
                lei = fnode.id[6:]
                ownership = await _api(gleif_client.get_ownership(lei))
                if ownership:
                    for parent_lei in [ownership.get("direct_parent"),
                                       ownership.get("ultimate_parent")]:
                        if parent_lei and parent_lei != lei:
                            pid = f"gleif-{parent_lei}"
                            _add_node(pid, "gleif", parent_lei,
                                      "Company", hop, {"lei": parent_lei})
                            _add_edge(fnode.id, pid, "parent_of", hop)
                    for child_lei in ownership.get("children", []):
                        cid = f"gleif-{child_lei}"
                        _add_node(cid, "gleif", child_lei,
                                  "Company", hop, {"lei": child_lei})
                        _add_edge(fnode.id, cid, "subsidiary", hop)

            # ── Expand UK Companies House nodes via PSCs ──
            if ch_client and fnode.id.startswith("uk-") and api_calls < budget:
                cn = fnode.id[3:]
                try:
                    pscs = await _api(ch_client.get_pscs(cn))
                    if pscs:
                        for psc in pscs.get("items", [])[:10]:
                            psc_name = psc.get("name", "")
                            if psc_name:
                                psc_id = f"uk-psc-{cn}-{_normalize(psc_name)[:20]}"
                                _add_node(psc_id, "companies_house",
                                          psc_name, "Person", hop, {
                                    "natures_of_control": psc.get(
                                        "natures_of_control", []),
                                    "nationality": psc.get("nationality", ""),
                                })
                                _add_edge(fnode.id, psc_id,
                                          "person_with_significant_control", hop)
                                # Cross-bridge PSC to OpenSanctions
                                if os_client and api_calls < budget:
                                    pnorm = _normalize(psc_name)
                                    if pnorm and pnorm not in visited_names:
                                        visited_names.add(pnorm)
                                        os_br = await _api(os_client.match(
                                            queries={"q0": {"schema": "Thing",
                                                            "properties": {"name": [psc_name]}}},
                                            threshold=0.7,
                                        ))
                                        if os_br:
                                            for qv in os_br.get("responses", {}).values():
                                                for r in qv.get("results", [])[:2]:
                                                    if r.get("score", 0) >= 0.7:
                                                        oid = f"os-{r['id']}"
                                                        oprops = r.get("properties", {})
                                                        otopics = oprops.get("topics",
                                                                             r.get("topics", []))
                                                        _add_node(oid, "opensanctions",
                                                                  r.get("caption", "?"),
                                                                  r.get("schema", "Person"),
                                                                  hop, {
                                                            "topics": otopics,
                                                            "datasets": r.get("datasets", []),
                                                            "sanctioned": "sanction" in otopics,
                                                            "pep": "role.pep" in otopics,
                                                        })
                                                        _add_edge(psc_id, oid,
                                                                  "cross-reference", hop)
                except Exception:
                    pass

    # ── Build stats ──────────────────────────────────────────

    hop_counts = {}
    for n in nodes.values():
        hop_counts[n.hop] = hop_counts.get(n.hop, 0) + 1

    source_counts = {}
    for n in nodes.values():
        source_counts[n.source] = source_counts.get(n.source, 0) + 1

    sanctioned = sum(1 for n in nodes.values()
                     if n.properties.get("sanctioned"))
    pep = sum(1 for n in nodes.values() if n.properties.get("pep"))

    # ── Pattern matching ──────────────────────────────────────
    from .pattern_matcher import match_patterns
    pattern_results = match_patterns(nodes, edges)

    # ── Scoring ─────────────────────────────────────────────
    from .scoring import compute_confidence, compute_risk_score
    seed_query = " ".join(seed_names)
    for n in nodes.values():
        node_dict = {"label": n.label, "source": n.source, "node_type": n.node_type,
                     "hop": n.hop, "score": n.properties.get("score"),
                     "sanctioned": n.properties.get("sanctioned"),
                     "pep": n.properties.get("pep"),
                     "topics": n.properties.get("topics", []),
                     "country_codes": n.properties.get("country_codes", []),
                     "jurisdiction": n.properties.get("jurisdiction"),
                     "investigation": n.properties.get("investigation"),
                     "datasets": n.properties.get("datasets", []),
                     "properties": n.properties}
        n.properties["confidence"] = round(compute_confidence(node_dict, seed_query), 3)
        risk = compute_risk_score(node_dict)
        n.properties["risk_score"] = risk["score"]
        n.properties["risk_level"] = risk["level"]
        n.properties["risk_factors"] = risk["factors"]

    return TraversalResult(
        nodes=nodes,
        edges=edges,
        pruned=pruned,
        budget_exhausted=api_calls >= budget,
        stats={
            "api_calls": api_calls,
            "budget": budget,
            "max_depth": max_depth,
            "nodes_per_hop": hop_counts,
            "nodes_per_source": source_counts,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "sanctioned": sanctioned,
            "pep": pep,
            "pruned_count": len(pruned),
            "patterns_matched": pattern_results.stats["patterns_matched"],
        },
        pattern_matches=[
            {
                "pattern": m.pattern_name,
                "title": m.title,
                "risk": m.risk_level,
                "confidence": m.confidence,
                "conditions_met": m.conditions_met,
                "conditions_missed": m.conditions_missed,
                "evidence": m.evidence[:5],
            }
            for m in pattern_results.matches
        ],
    )


def result_to_visualizer_data(
    result: TraversalResult,
    query: str,
) -> dict:
    """Convert a TraversalResult into the dict shape expected by
    ``visualizer.generate_visualization``.
    """
    icij_results = []
    icij_entities = {}
    os_results = []
    icij_network = []

    # Prefix-to-source mapping for new sources
    _new_source_types = {"gleif-": "gleif", "sec-": "sec",
                         "uk-": "companies_house", "court-": "courtlistener"}

    for n in result.nodes.values():
        if n.id.startswith("icij-"):
            raw_id = n.id[5:]
            icij_results.append({
                "id": raw_id,
                "name": n.label,
                "score": n.properties.get("score"),
                "types": [{"id": n.node_type.lower(), "name": n.node_type}],
                "description": n.properties.get("description", ""),
                "hop": n.hop,
                "confidence": n.properties.get("confidence", 0),
                "risk_score": n.properties.get("risk_score", 0),
                "risk_level": n.properties.get("risk_level", ""),
            })
            countries = n.properties.get("country_codes", [])
            if countries:
                icij_entities[raw_id] = {
                    "country_codes": [{"str": c} for c in countries],
                }
        elif n.id.startswith("os-"):
            topics = n.properties.get("topics", [])
            os_results.append({
                "id": n.id[3:],
                "caption": n.label,
                "schema": n.node_type,
                "score": n.properties.get("score"),
                "properties": {
                    "topics": topics,
                    "nationality": n.properties.get("country_codes", []),
                },
                "datasets": n.properties.get("datasets", []),
                "topics": topics,
                "hop": n.hop,
                "confidence": n.properties.get("confidence", 0),
                "risk_score": n.properties.get("risk_score", 0),
                "risk_level": n.properties.get("risk_level", ""),
            })
        else:
            # New sources — emit as opensanctions_results format for
            # compatibility with the visualizer (which handles os- nodes)
            for prefix, source in _new_source_types.items():
                if n.id.startswith(prefix):
                    os_results.append({
                        "id": n.id,
                        "caption": n.label,
                        "schema": n.node_type,
                        "score": n.properties.get("score"),
                        "file_date": n.properties.get("file_date", ""),
                        "date_filed": n.properties.get("date_filed", ""),
                        "properties": {
                            "topics": n.properties.get("topics", []),
                            "nationality": n.properties.get("country_codes", []),
                        },
                        "datasets": [source],
                        "topics": n.properties.get("topics", []),
                        "hop": n.hop,
                        "confidence": n.properties.get("confidence", 0),
                        "risk_score": n.properties.get("risk_score", 0),
                        "risk_level": n.properties.get("risk_level", ""),
                    })
                    break

    def _strip_prefix(nid: str) -> str:
        """Strip the source prefix from a node ID for edge serialization."""
        for prefix in ("icij-", "os-"):
            if nid.startswith(prefix):
                return nid[len(prefix):]
        return nid  # Keep full ID for new sources

    for e in result.edges:
        icij_network.append({
            "source_id": _strip_prefix(e.source_id),
            "target_id": _strip_prefix(e.target_id),
            "relationship": e.relationship,
        })

    return {
        "query": query,
        "icij_results": icij_results,
        "icij_entities": icij_entities,
        "opensanctions_results": os_results,
        "icij_network": icij_network,
        "traversal_stats": result.stats,
        "pattern_matches": result.pattern_matches,
    }
