"""Multi-hop graph traversal across ICIJ and OpenSanctions."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import ServiceTracker, api_call


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
    service_warnings: list[str] = field(default_factory=list)


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
    aleph_client: Any | None = None,
    wikidata_client: Any | None = None,
    land_registry_client: Any | None = None,
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
    aleph_client : OCCRP Aleph client (optional)
    wikidata_client : Wikidata client (optional)
    land_registry_client : UK Land Registry client (optional)
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    pruned: list[str] = []
    visited_names: set[str] = set()
    api_calls = 0
    tracker = ServiceTracker()

    async def _api(coro_or_factory, *, service: str = "unknown", endpoint: str = ""):
        nonlocal api_calls
        if api_calls >= budget:
            return None
        api_calls += 1
        # Per-service rate limiting + retries handled inside api_call()
        return await api_call(tracker, service, endpoint, coro_or_factory)

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

    # ── Helper: ingest raw results into graph ───────────────

    def _ingest_icij(res, hop: int):
        if not res:
            return
        for r in res.get("result", [])[:10]:
            nid = f"icij-{r['id']}"
            _add_node(nid, "icij", r["name"], _icij_type(r), hop, {
                "score": r.get("score"),
                "investigation": _inv_from_desc(r.get("description", "")),
                "description": r.get("description", ""),
            })

    def _ingest_os(res, hop: int):
        if not res:
            return
        for qval in res.get("responses", {}).values():
            for r in qval.get("results", [])[:10]:
                oid = f"os-{r['id']}"
                props = r.get("properties", {})
                topics = props.get("topics", r.get("topics", []))
                _add_node(oid, "opensanctions", r.get("caption", "?"),
                          r.get("schema", "Person"), hop, {
                    "score": r.get("score"),
                    "topics": topics,
                    "datasets": r.get("datasets", []),
                    "sanctioned": "sanction" in topics,
                    "pep": "role.pep" in topics,
                    "country_codes": props.get("nationality",
                                               props.get("citizenship", [])),
                })

    def _ingest_gleif(res, hop: int):
        if not res:
            return
        for r in res.get("results", [])[:5]:
            lei = r.get("lei", "")
            if lei:
                nid = f"gleif-{lei}"
                _add_node(nid, "gleif", r.get("legal_name", lei),
                          "Company", hop, {
                    "lei": lei,
                    "jurisdiction": r.get("jurisdiction", ""),
                    "country_codes": [r["country"]] if r.get("country") else [],
                    "status": r.get("status", ""),
                    "incorporation_date": r.get("initial_registration", ""),
                })

    def _ingest_sec(res, hop: int):
        if not res:
            return
        for r in res.get("results", [])[:5]:
            cik = str(r.get("cik", ""))
            if cik:
                nid = f"sec-{cik}"
                file_date = r.get("file_date", "")
                _add_node(nid, "sec", r.get("entity_name", cik),
                          "Company", hop, {
                    "cik": cik,
                    "filing_type": r.get("filing_type", ""),
                    "file_date": file_date,
                    "incorporation_date": file_date,
                })

    def _ingest_ch(res, hop: int):
        if not res:
            return
        for r in res.get("items", [])[:5]:
            cn = r.get("company_number", "")
            if cn:
                nid = f"uk-{cn}"
                _add_node(nid, "companies_house",
                          r.get("title", cn), "Company", hop, {
                    "company_number": cn,
                    "company_status": r.get("company_status", ""),
                    "address": r.get("address_snippet", ""),
                    "incorporation_date": r.get("date_of_creation", ""),
                })

    def _ingest_cl(res, hop: int):
        if not res:
            return
        for r in res.get("results", [])[:3]:
            did = r.get("docket_id") or r.get("id")
            if did:
                nid = f"court-{did}"
                date_filed = r.get("dateFiled", r.get("date_filed", ""))
                _add_node(nid, "courtlistener",
                          r.get("caseName", r.get("case_name", str(did))),
                          "Case", hop, {
                    "docket_id": did,
                    "court": r.get("court", ""),
                    "date_filed": date_filed,
                    "incorporation_date": date_filed,
                })

    def _ingest_aleph(res, hop: int):
        if not res:
            return
        for r in res.get("results", [])[:5]:
            aid = r.get("id", "")
            if aid:
                nid = f"aleph-{aid}"
                _add_node(nid, "aleph", r.get("name", aid),
                          r.get("schema", "Thing"), hop, {
                    "aleph_id": aid,
                    "countries": r.get("countries", []),
                    "country_codes": r.get("countries", []),
                    "jurisdiction": r.get("jurisdiction", ""),
                    "registration_number": r.get("registration_number", ""),
                    "datasets": r.get("datasets", []),
                    "incorporation_date": r.get("incorporation_date", ""),
                })

    def _ingest_wikidata(res, hop: int):
        if not res:
            return
        for r in res.get("results", [])[:3]:
            wid = r.get("id", "")
            if wid:
                nid = f"wikidata-{wid}"
                _add_node(nid, "wikidata", r.get("label", wid),
                          "Entity", hop, {
                    "wikidata_id": wid,
                    "description": r.get("description", ""),
                })

    # ── Hop 0: Seed — all sources in parallel ───────────────

    for name in seed_names:
        norm = _normalize(name)
        if norm in visited_names:
            continue
        visited_names.add(norm)

        # Build list of (coroutine, ingest_fn) pairs for all available sources
        kwargs = {"query": name}
        if investigation:
            kwargs["investigation"] = investigation

        seed_tasks = [
            _api(lambda kw=kwargs: icij_client.reconcile(**kw),
                 service="ICIJ", endpoint="/reconcile"),
        ]
        seed_ingestors = [_ingest_icij]

        if os_client:
            seed_tasks.append(_api(lambda n=name: os_client.match(
                queries={"q0": {"schema": "Thing", "properties": {"name": [n]}}},
                threshold=0.5,
            ), service="OpenSanctions", endpoint="/match"))
            seed_ingestors.append(_ingest_os)

        if gleif_client:
            seed_tasks.append(_api(lambda n=name: gleif_client.search(n, page_size=5),
                                   service="GLEIF", endpoint="/search"))
            seed_ingestors.append(_ingest_gleif)
        if sec_client:
            seed_tasks.append(_api(lambda n=name: sec_client.search(n, count=5),
                                   service="SEC EDGAR", endpoint="/efts/search"))
            seed_ingestors.append(_ingest_sec)
        if ch_client:
            seed_tasks.append(_api(lambda n=name: ch_client.search_company(n, items_per_page=5),
                                   service="Companies House", endpoint="/search/companies"))
            seed_ingestors.append(_ingest_ch)
        if cl_client:
            seed_tasks.append(_api(lambda n=name: cl_client.search(n, type="r"),
                                   service="CourtListener", endpoint="/search"))
            seed_ingestors.append(_ingest_cl)
        if aleph_client:
            seed_tasks.append(_api(lambda n=name: aleph_client.search_entities(n, limit=5),
                                   service="Aleph", endpoint="/entities"))
            seed_ingestors.append(_ingest_aleph)
        if wikidata_client:
            seed_tasks.append(_api(lambda n=name: wikidata_client.search(n, limit=3),
                                   service="Wikidata", endpoint="/search"))
            seed_ingestors.append(_ingest_wikidata)

        # Fire all sources concurrently
        results = await asyncio.gather(*seed_tasks)

        # Ingest results into graph (synchronous — fast dict ops)
        for res, ingest in zip(results, seed_ingestors):
            ingest(res, 0)

    # ── Hops 1..N — expand frontier nodes in parallel ───────

    for hop in range(1, max_depth + 1):
        if api_calls >= budget:
            break

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

        # ── Define per-node expansion as an async task ──

        async def _expand_node(fnode: GraphNode):
            """Expand a single frontier node across all relevant sources."""
            if api_calls >= budget:
                return

            # ── OpenSanctions: get_adjacent + ICIJ cross-bridge ──
            if os_client and fnode.source in ("opensanctions", "both") and fnode.id.startswith("os-"):
                entity_id = fnode.id[3:]
                adj = await _api(lambda eid=entity_id: os_client.get_adjacent(
                    eid, limit=max_fanout + 1,
                ), service="OpenSanctions", endpoint="/adjacent")
                if adj:
                    results = adj.get("results", [])
                    if len(results) > max_fanout:
                        pruned.append(fnode.id)
                        return
                    # Collect names needing ICIJ cross-bridge
                    bridge_tasks = []
                    bridge_ids = []
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

                        if is_new and api_calls < budget:
                            aname = ar.get("caption", "")
                            anorm = _normalize(aname)
                            if anorm and anorm not in visited_names:
                                visited_names.add(anorm)
                                bridge_tasks.append(_api(
                                    lambda n=aname: icij_client.reconcile(query=n),
                                    service="ICIJ", endpoint="/reconcile"))
                                bridge_ids.append(aid)

                    # Fire all ICIJ cross-bridges in parallel
                    if bridge_tasks:
                        bridge_results = await asyncio.gather(*bridge_tasks)
                        for aid, br_res in zip(bridge_ids, bridge_results):
                            if br_res:
                                for br in br_res.get("result", [])[:5]:
                                    if br.get("score", 0) > 50:
                                        bid = f"icij-{br['id']}"
                                        _add_node(bid, "icij", br["name"],
                                                  _icij_type(br), hop, {
                                            "score": br.get("score"),
                                            "investigation": _inv_from_desc(
                                                br.get("description", "")),
                                        })
                                        _add_edge(aid, bid, "cross-reference", hop)

            # ── ICIJ: get_node details + reconcile + OS cross-bridge ──
            if fnode.source in ("icij", "both") and fnode.id.startswith("icij-"):
                node_id = int(fnode.id[5:])
                fname = fnode.label
                fnorm = _normalize(fname)
                is_address = fnode.node_type == "Address"

                # Always fetch node details (countries, metadata)
                parallel = [
                    _api(lambda nid=node_id: icij_client.get_node(nid),
                         service="ICIJ", endpoint="/nodes"),
                ]
                # Don't re-reconcile address strings — reconcile is for
                # name matching, not address lookup.  Address nodes are
                # kept in the graph as location data; entities registered
                # at the address come through entity/officer expansion.
                do_reconcile = not is_address and fnorm not in visited_names
                if do_reconcile:
                    visited_names.add(fnorm)
                    parallel.append(
                        _api(lambda n=fname: icij_client.reconcile(query=n),
                             service="ICIJ", endpoint="/reconcile"))
                if os_client and fnorm:
                    parallel.append(
                        _api(lambda n=fname: os_client.match(
                            queries={"q0": {"schema": "Thing", "properties": {"name": [n]}}},
                            threshold=0.7,
                        ), service="OpenSanctions", endpoint="/match"))

                parallel_results = await asyncio.gather(*parallel)
                idx = 0

                # Detail
                detail = parallel_results[idx]; idx += 1
                if detail:
                    countries = [c["str"] for c in detail.get("country_codes", [])]
                    fnode.properties["country_codes"] = countries

                # Reconcile
                if do_reconcile:
                    icij_res2 = parallel_results[idx]; idx += 1
                    if icij_res2:
                        for r in icij_res2.get("result", [])[:8]:
                            rid = f"icij-{r['id']}"
                            if rid == fnode.id:
                                continue
                            rtype = _icij_type(r)
                            _add_node(rid, "icij", r["name"], rtype, hop, {
                                "score": r.get("score"),
                                "investigation": _inv_from_desc(
                                    r.get("description", "")),
                            })
                            if rtype == "Intermediary":
                                rel = "intermediary_of"
                            elif rtype == "Officer":
                                rel = "co_officer"
                            elif rtype == "Address":
                                rel = "registered_at"
                            else:
                                rel = "connected"
                            _add_edge(fnode.id, rid, rel, hop)

                # OS cross-bridge
                if os_client and fnorm:
                    os_bridge = parallel_results[idx]; idx += 1
                    if os_bridge:
                        for qval in os_bridge.get("responses", {}).values():
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

            # ── GLEIF: ownership chain ──
            if gleif_client and fnode.id.startswith("gleif-") and api_calls < budget:
                lei = fnode.id[6:]
                ownership = await _api(lambda l=lei: gleif_client.get_ownership(l),
                                       service="GLEIF", endpoint="/ownership")
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

            # ── Companies House: PSCs + OS cross-bridge ──
            if ch_client and fnode.id.startswith("uk-") and api_calls < budget:
                cn = fnode.id[3:]
                pscs = await _api(lambda c=cn: ch_client.get_pscs(c),
                                  service="Companies House", endpoint="/pscs")
                if pscs:
                    # Collect PSC names for batch OS cross-bridge
                    psc_bridge_tasks = []
                    psc_bridge_ids = []
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
                            if os_client and api_calls < budget:
                                pnorm = _normalize(psc_name)
                                if pnorm and pnorm not in visited_names:
                                    visited_names.add(pnorm)
                                    psc_bridge_tasks.append(
                                        _api(lambda n=psc_name: os_client.match(
                                            queries={"q0": {"schema": "Thing",
                                                            "properties": {"name": [n]}}},
                                            threshold=0.7,
                                        ), service="OpenSanctions", endpoint="/match"))
                                    psc_bridge_ids.append(psc_id)

                    # Fire all PSC→OS bridges in parallel
                    if psc_bridge_tasks:
                        psc_results = await asyncio.gather(*psc_bridge_tasks)
                        for psc_id, os_br in zip(psc_bridge_ids, psc_results):
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

            # ── Aleph: similar entities ──
            if aleph_client and fnode.id.startswith("aleph-") and api_calls < budget:
                aleph_id = fnode.id[6:]
                similar = await _api(lambda aid=aleph_id: aleph_client.get_entity_similar(
                    aid, limit=max_fanout,
                ), service="Aleph", endpoint="/similar")
                if similar:
                    for sr in similar.get("results", [])[:max_fanout]:
                        sid = sr.get("id", "")
                        if sid:
                            snid = f"aleph-{sid}"
                            _add_node(snid, "aleph", sr.get("name", sid),
                                      sr.get("schema", "Thing"), hop, {
                                "aleph_id": sid,
                                "countries": sr.get("countries", []),
                                "country_codes": sr.get("countries", []),
                                "jurisdiction": sr.get("jurisdiction", ""),
                                "datasets": sr.get("datasets", []),
                            })
                            _add_edge(fnode.id, snid, "similar_entity", hop)

        # ── Expand all frontier nodes in parallel ──
        await asyncio.gather(*[_expand_node(fn) for fn in frontier])

    # ── Normalize ────────────────────────────────────────────
    from .normalizer import normalize_graph
    pre_count = len(nodes)
    nodes, edges, norm_log = normalize_graph(nodes, edges)
    post_count = len(nodes)

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
            "deduplicated": pre_count - post_count,
            "normalization": norm_log.to_dict(),
            "patterns_matched": pattern_results.stats["patterns_matched"],
            "service_errors": tracker.to_dict(),
        },
        pattern_matches=[
            {
                "pattern": m.pattern_name,
                "title": m.title,
                "description": m.description,
                "sources": m.sources,
                "status": m.status,
                "references": m.references,
                "risk": m.risk_level,
                "confidence": m.confidence,
                "conditions_met": m.conditions_met,
                "conditions_missed": m.conditions_missed,
                "evidence": m.evidence[:5],
            }
            for m in pattern_results.matches
        ],
        service_warnings=tracker.warnings,
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
                         "uk-": "companies_house", "court-": "courtlistener",
                         "aleph-": "aleph", "wikidata-": "wikidata",
                         "land-": "land_registry"}

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
                        "incorporation_date": n.properties.get("incorporation_date", ""),
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
