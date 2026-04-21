"""Pattern matcher — evaluates YAML detection rules against traversal results."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PATTERNS_DIR = Path(__file__).resolve().parent.parent / "patterns"


@dataclass
class PatternMatch:
    """A single pattern match result."""
    pattern_name: str
    title: str
    risk_level: str
    confidence: str  # "high", "medium", "low"
    conditions_met: list[str]
    conditions_missed: list[str]
    evidence: list[str]
    description: str
    sources: list[str] = field(default_factory=list)
    status: str = ""
    references: list[dict] = field(default_factory=list)


@dataclass
class MatchResults:
    """All pattern matches for a traversal result."""
    matches: list[PatternMatch]
    stats: dict


def load_patterns(patterns_dir: Path | None = None) -> list[dict]:
    """Load all YAML pattern files."""
    d = patterns_dir or PATTERNS_DIR
    patterns = []
    for f in sorted(d.glob("*.yaml")):
        if f.name == "INDEX.yaml":
            continue
        try:
            patterns.append(yaml.safe_load(f.read_text()))
        except Exception:
            pass
    return patterns


def match_patterns(
    nodes: dict[str, Any],
    edges: list[Any],
    patterns: list[dict] | None = None,
) -> MatchResults:
    """Evaluate all patterns against a traversal graph.

    Parameters
    ----------
    nodes : dict mapping node ID -> GraphNode (or dict with same fields)
    edges : list of GraphEdge (or dicts with source_id, target_id, relationship)
    patterns : loaded patterns (if None, loads from disk)

    Returns
    -------
    MatchResults with all detected pattern matches
    """
    if patterns is None:
        patterns = load_patterns()

    # Build graph indexes for efficient evaluation
    graph = _build_graph_index(nodes, edges)
    matches = []

    for pattern in patterns:
        result = _evaluate_pattern(pattern, graph)
        if result:
            matches.append(result)

    # Sort by risk level then confidence
    risk_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    conf_order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda m: (risk_order.get(m.risk_level, 9),
                                 conf_order.get(m.confidence, 9)))

    return MatchResults(
        matches=matches,
        stats={
            "patterns_evaluated": len(patterns),
            "patterns_matched": len(matches),
            "high_confidence": sum(1 for m in matches if m.confidence == "high"),
            "critical_risk": sum(1 for m in matches if m.risk_level == "CRITICAL"),
            "high_risk": sum(1 for m in matches if m.risk_level == "HIGH"),
        },
    )


# ------------------------------------------------------------------
# Graph index
# ------------------------------------------------------------------

@dataclass
class _GraphIndex:
    """Pre-computed indexes over the traversal graph."""
    nodes: dict[str, dict]
    edges: list[dict]
    # Adjacency
    out_edges: dict[str, list[dict]]  # node_id -> outgoing edges
    in_edges: dict[str, list[dict]]   # node_id -> incoming edges
    # By type
    nodes_by_type: dict[str, list[dict]]
    nodes_by_source: dict[str, list[dict]]
    # Degree
    degree: dict[str, int]
    out_degree: dict[str, int]
    in_degree: dict[str, int]
    # Address clustering
    address_clusters: dict[str, list[str]]  # normalized address -> node IDs
    # Jurisdiction sets
    jurisdictions: set[str]
    # All sources present
    sources: set[str]


def _build_graph_index(nodes: dict, edges: list) -> _GraphIndex:
    """Build lookup indexes for pattern evaluation."""
    # Normalize nodes to dicts
    node_map = {}
    for nid, n in nodes.items():
        if hasattr(n, "__dict__"):
            nd = {"id": n.id, "source": n.source, "label": n.label,
                  "node_type": n.node_type, "hop": n.hop}
            nd.update(n.properties)
            node_map[nid] = nd
        elif isinstance(n, dict):
            node_map[nid] = n
        else:
            node_map[nid] = {"id": nid}

    # Normalize edges to dicts
    edge_list = []
    for e in edges:
        if hasattr(e, "source_id"):
            edge_list.append({"source_id": e.source_id, "target_id": e.target_id,
                              "relationship": e.relationship})
        elif isinstance(e, dict):
            edge_list.append(e)

    # Build adjacency
    out_edges = defaultdict(list)
    in_edges = defaultdict(list)
    degree = defaultdict(int)
    out_degree = defaultdict(int)
    in_degree = defaultdict(int)
    for e in edge_list:
        src, tgt = e.get("source_id", ""), e.get("target_id", "")
        out_edges[src].append(e)
        in_edges[tgt].append(e)
        degree[src] += 1
        degree[tgt] += 1
        out_degree[src] += 1
        in_degree[tgt] += 1

    # By type
    nodes_by_type = defaultdict(list)
    nodes_by_source = defaultdict(list)
    jurisdictions = set()
    sources = set()
    for n in node_map.values():
        ntype = (n.get("node_type") or n.get("type") or "").lower()
        nodes_by_type[ntype].append(n)
        src = n.get("source", "")
        nodes_by_source[src].append(n)
        sources.add(src)
        for cc in n.get("country_codes", []):
            if cc:
                jurisdictions.add(cc)
        jur = n.get("jurisdiction")
        if jur:
            jurisdictions.add(jur)

    # Address clustering
    address_clusters = defaultdict(list)
    for n in node_map.values():
        ntype = (n.get("node_type") or n.get("type") or "").lower()
        if ntype == "address":
            norm = re.sub(r"[^a-z0-9 ]", "", n.get("label", "").lower()).strip()
            if norm:
                address_clusters[norm].append(n.get("id", ""))

    return _GraphIndex(
        nodes=node_map, edges=edge_list,
        out_edges=dict(out_edges), in_edges=dict(in_edges),
        nodes_by_type=dict(nodes_by_type), nodes_by_source=dict(nodes_by_source),
        degree=dict(degree), out_degree=dict(out_degree), in_degree=dict(in_degree),
        address_clusters=dict(address_clusters),
        jurisdictions=jurisdictions, sources=sources,
    )


# ------------------------------------------------------------------
# Pattern evaluation
# ------------------------------------------------------------------

def _evaluate_pattern(pattern: dict, graph: _GraphIndex) -> PatternMatch | None:
    """Evaluate a single pattern against the graph. Returns None if no match."""
    detection = pattern.get("detection", {})
    conditions = detection.get("conditions", [])
    if not conditions:
        return None

    met = []
    missed = []
    evidence = []

    for cond in conditions:
        cond_id = cond.get("id", "unknown")
        optional = cond.get("optional", False)
        result = _evaluate_condition(cond, graph)
        if result:
            met.append(cond_id)
            evidence.extend(result if isinstance(result, list) else [result])
        elif not optional:
            missed.append(cond_id)

    if not met:
        return None

    # Determine confidence from scoring rules
    scoring = detection.get("scoring", {})
    confidence = _score_confidence(met, missed, scoring)

    if confidence is None:
        return None

    return PatternMatch(
        pattern_name=pattern.get("name", "unknown"),
        title=pattern.get("title", ""),
        risk_level=pattern.get("risk_level", "MEDIUM"),
        confidence=confidence,
        conditions_met=met,
        conditions_missed=missed,
        evidence=evidence,
        description=pattern.get("description", ""),
        sources=pattern.get("sources", []),
        status=pattern.get("status", ""),
        references=pattern.get("references", []),
    )


def _score_confidence(met: list[str], missed: list[str], scoring: dict) -> str | None:
    """Determine confidence tier from met/missed conditions and scoring rules."""
    met_set = set(met)

    # Check high first
    high_req = scoring.get("high")
    if high_req:
        if high_req == "all_conditions_met" and not missed:
            return "high"
        elif isinstance(high_req, list) and all(c in met_set for c in high_req):
            return "high"
        elif isinstance(high_req, str) and high_req in met_set:
            return "high"

    # Check medium
    med_req = scoring.get("medium")
    if med_req:
        if isinstance(med_req, list) and all(c in met_set for c in med_req):
            return "medium"
        elif isinstance(med_req, str) and med_req in met_set:
            return "medium"

    # Check low
    low_req = scoring.get("low")
    if low_req:
        if isinstance(low_req, list) and all(c in met_set for c in low_req):
            return "low"
        elif isinstance(low_req, str) and low_req in met_set:
            return "low"

    # Fallback: if anything matched, it's at least low
    if met:
        return "low"

    return None


# ------------------------------------------------------------------
# Condition evaluators
# ------------------------------------------------------------------

SECRECY_JURISDICTIONS = {
    "VG", "SC", "PA", "KY", "BZ", "WS", "MH", "KN",  # Classic offshore
    "BM", "GG", "JE", "IM", "LI", "MC", "AD",         # European secrecy
    "HK", "SG", "MO", "LB",                             # Asian centers
}

HIGH_RISK_JURISDICTIONS = {
    # FATF grey/black list + EU high-risk third countries
    "MM", "SS", "SY", "YE", "IR", "KP",
    "AF", "BF", "CM", "CD", "HT", "MZ", "NG", "PH",
    "SN", "ZA", "TZ", "VE", "VN",
}


def _evaluate_condition(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Evaluate a single detection condition. Returns evidence list or None."""
    ctype = cond.get("type", "")

    if ctype == "node_degree":
        return _eval_node_degree(cond, graph)
    elif ctype == "path_length":
        return _eval_path_length(cond, graph)
    elif ctype == "jurisdiction_count":
        return _eval_jurisdiction_count(cond, graph)
    elif ctype == "jurisdiction_risk":
        return _eval_jurisdiction_risk(cond, graph)
    elif ctype == "jurisdiction_mix":
        return _eval_jurisdiction_mix(cond, graph)
    elif ctype == "address_clustering":
        return _eval_address_clustering(cond, graph)
    elif ctype == "shared_node":
        return _eval_shared_node(cond, graph)
    elif ctype == "temporal_cluster":
        return _eval_temporal_cluster(cond, graph)
    elif ctype == "cycle_detection":
        return _eval_cycle_detection(cond, graph)
    elif ctype == "cross_source_match":
        return _eval_cross_source(cond, graph)
    elif ctype == "source_count":
        return _eval_source_count(cond, graph)
    elif ctype == "missing_field" or ctype == "missing_relationship":
        return _eval_missing(cond, graph)
    elif ctype == "officer_overlap":
        return _eval_officer_overlap(cond, graph)
    elif ctype == "centrality":
        return _eval_centrality(cond, graph)
    elif ctype == "multi_path":
        return _eval_multi_path(cond, graph)
    elif ctype == "entity_type_match" or ctype == "node_type_match":
        return _eval_type_match(cond, graph)
    elif ctype == "name_match":
        return _eval_name_match(cond, graph)
    elif ctype == "name_obfuscation":
        return _eval_name_obfuscation(cond, graph)
    elif ctype == "name_obfuscation_jurisdiction":
        return _eval_name_obfuscation_jurisdiction(cond, graph)
    elif ctype == "insolvency_status":
        return _eval_insolvency_status(cond, graph)
    elif ctype == "officer_disqualification":
        return _eval_officer_disqualification(cond, graph)
    elif ctype == "sec_event_type":
        return _eval_sec_event_type(cond, graph)
    elif ctype == "amendment_count":
        return _eval_amendment_count(cond, graph)
    elif ctype == "property_value":
        return _eval_property_value(cond, graph)
    elif ctype == "bankruptcy_filing":
        return _eval_bankruptcy_filing(cond, graph)
    elif ctype == "temporal_range":
        return _eval_temporal_range(cond, graph)
    elif ctype == "jurisdiction_mismatch":
        return _eval_jurisdiction_mismatch(cond, graph)
    elif ctype == "entity_status":
        return _eval_entity_status(cond, graph)
    elif ctype == "temporal_sequence":
        return _eval_temporal_sequence(cond, graph)

    return None


def _eval_node_degree(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if any node exceeds a degree threshold."""
    min_deg = cond.get("min_degree", 10)
    node_types = cond.get("node_type", [])
    if isinstance(node_types, str):
        node_types = [node_types]
    node_types = [t.lower() for t in node_types]
    direction = cond.get("direction")

    hits = []
    for nid, n in graph.nodes.items():
        ntype = (n.get("node_type") or n.get("type") or "").lower()
        if node_types and ntype not in node_types:
            continue
        if direction == "outgoing":
            deg = graph.out_degree.get(nid, 0)
        elif direction == "incoming":
            deg = graph.in_degree.get(nid, 0)
        else:
            deg = graph.degree.get(nid, 0)
        if deg >= min_deg:
            hits.append(f"{n.get('label', nid)} has degree {deg} (threshold: {min_deg})")

    return hits if hits else None


def _eval_path_length(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if any path of min_length exists through specified relationships."""
    min_len = cond.get("min_length", 3)
    rels = cond.get("relationship", [])
    if isinstance(rels, str):
        rels = [rels]
    rels_set = set(rels) if rels else None

    # BFS from each node looking for long paths
    for start_id in graph.nodes:
        visited = {start_id}
        frontier = [(start_id, 0)]
        max_depth = 0
        while frontier:
            nid, depth = frontier.pop(0)
            if depth > max_depth:
                max_depth = depth
            if max_depth >= min_len:
                return [f"Path of length {max_depth}+ found from {graph.nodes[start_id].get('label', start_id)}"]
            for e in graph.out_edges.get(nid, []):
                if rels_set and e.get("relationship", "") not in rels_set:
                    continue
                tgt = e["target_id"]
                if tgt not in visited and tgt in graph.nodes:
                    visited.add(tgt)
                    frontier.append((tgt, depth + 1))

    return None


def _eval_jurisdiction_count(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if enough distinct jurisdictions are present."""
    min_count = cond.get("min_count", 3)
    if len(graph.jurisdictions) >= min_count:
        jurs = sorted(graph.jurisdictions)[:10]
        return [f"{len(graph.jurisdictions)} jurisdictions: {', '.join(jurs)}"]
    return None


def _eval_jurisdiction_risk(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if any entity is in a high-secrecy/risk jurisdiction."""
    target_jurs = set(cond.get("jurisdictions", []))
    if not target_jurs:
        target_jurs = SECRECY_JURISDICTIONS

    found = graph.jurisdictions & target_jurs
    if found:
        return [f"Entities in secrecy jurisdictions: {', '.join(sorted(found))}"]
    return None


def _eval_jurisdiction_mix(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for mix of regulated + secrecy jurisdictions."""
    regulated = set(cond.get("regulated_jurisdictions", []))
    secrecy = set(cond.get("secrecy_jurisdictions", []))
    if not regulated:
        regulated = {"GB", "DE", "FR", "NL", "CH", "US", "SG", "HK"}
    if not secrecy:
        secrecy = SECRECY_JURISDICTIONS

    found_reg = graph.jurisdictions & regulated
    found_sec = graph.jurisdictions & secrecy
    if found_reg and found_sec:
        return [f"Mixed jurisdictions — regulated: {', '.join(sorted(found_reg))}; "
                f"secrecy: {', '.join(sorted(found_sec))}"]
    return None


def _eval_address_clustering(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if any address is shared by many entities."""
    min_entities = cond.get("min_entities_per_address", 10)
    hits = []
    for addr, nids in graph.address_clusters.items():
        if len(nids) >= min_entities:
            hits.append(f"Address shared by {len(nids)} entities: {addr[:50]}")
    return hits if hits else None


def _eval_shared_node(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if a node type appears multiple times in the graph."""
    target_types = cond.get("node_type", [])
    if isinstance(target_types, str):
        target_types = [target_types]
    target_types = [t.lower() for t in target_types]
    min_occ = cond.get("min_occurrences", 2)

    for ntype in target_types:
        nodes = graph.nodes_by_type.get(ntype, [])
        if len(nodes) >= min_occ:
            names = [n.get("label", "?")[:30] for n in nodes[:5]]
            return [f"{len(nodes)} {ntype} nodes found: {', '.join(names)}"]
    return None


def _eval_temporal_cluster(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for burst of entity formations in a time window."""
    # This is a simplified check — looks for incorporation_date clustering
    window = cond.get("window_days", 30)
    min_ents = cond.get("min_entities", 3)

    dates = []
    for n in graph.nodes.values():
        inc = n.get("incorporation_date") or n.get("initial_registration")
        if inc and isinstance(inc, str) and len(inc) >= 10:
            dates.append((inc[:10], n.get("label", "?")))

    if len(dates) < min_ents:
        return None

    dates.sort()
    # Sliding window
    for i in range(len(dates) - min_ents + 1):
        d1 = dates[i][0]
        d2 = dates[i + min_ents - 1][0]
        try:
            from datetime import datetime
            dt1 = datetime.strptime(d1, "%Y-%m-%d")
            dt2 = datetime.strptime(d2, "%Y-%m-%d")
            if (dt2 - dt1).days <= window:
                names = [d[1][:25] for d in dates[i:i+min_ents]]
                return [f"{min_ents} entities formed within {window} days: {', '.join(names)}"]
        except ValueError:
            continue

    return None


def _eval_cycle_detection(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Detect directed cycles in the graph."""
    max_len = cond.get("max_cycle_length", 5)
    rels = cond.get("relationship", [])
    if isinstance(rels, str):
        rels = [rels]
    rels_set = set(rels) if rels else None

    # DFS-based cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in graph.nodes}

    def _dfs(nid, depth, path):
        if depth > max_len:
            return None
        color[nid] = GRAY
        for e in graph.out_edges.get(nid, []):
            if rels_set and e.get("relationship", "") not in rels_set:
                continue
            tgt = e["target_id"]
            if tgt not in color:
                continue
            if color[tgt] == GRAY:
                cycle_start = path.index(tgt) if tgt in path else -1
                if cycle_start >= 0:
                    cycle = path[cycle_start:] + [tgt]
                    names = [graph.nodes.get(n, {}).get("label", n)[:20] for n in cycle]
                    return f"Cycle detected: {' -> '.join(names)}"
            elif color[tgt] == WHITE:
                result = _dfs(tgt, depth + 1, path + [tgt])
                if result:
                    return result
        color[nid] = BLACK
        return None

    for nid in graph.nodes:
        if color.get(nid) == WHITE:
            result = _dfs(nid, 0, [nid])
            if result:
                return [result]

    return None


def _eval_cross_source(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for entities appearing in multiple sources."""
    source_a = cond.get("source_a", "icij")
    source_b = cond.get("source_b", "opensanctions")
    topic = cond.get("opensanctions_topic")

    nodes_a = graph.nodes_by_source.get(source_a, [])
    nodes_b = graph.nodes_by_source.get(source_b, [])
    both = graph.nodes_by_source.get("both", [])

    if both:
        names = [n.get("label", "?")[:30] for n in both[:3]]
        return [f"Cross-source match ({source_a} + {source_b}): {', '.join(names)}"]

    # Check for name overlaps
    names_a = {_norm(n.get("label", "")) for n in nodes_a}
    hits = []
    for n in nodes_b:
        if topic and topic not in n.get("topics", []):
            continue
        if _norm(n.get("label", "")) in names_a:
            hits.append(f"{n.get('label', '?')} found in both {source_a} and {source_b}")

    return hits if hits else None


def _eval_source_count(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if entities appear in N+ sources."""
    min_sources = cond.get("min_sources", 3)
    active = {s for s in graph.sources if s and s != "both"}
    if "both" in graph.sources:
        active.add("icij")
        active.add("opensanctions")
    if len(active) >= min_sources:
        return [f"Data found across {len(active)} sources: {', '.join(sorted(active))}"]
    return None


def _eval_missing(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for entities missing expected fields/relationships."""
    field_name = cond.get("field", "")
    node_type = (cond.get("node_type") or "").lower()

    hits = []
    for n in graph.nodes.values():
        ntype = (n.get("node_type") or n.get("type") or "").lower()
        if node_type and ntype != node_type:
            continue

        if cond.get("type") == "missing_relationship":
            rel = cond.get("relationship", "")
            direction = cond.get("direction", "incoming")
            nid = n.get("id", "")
            edges = graph.in_edges.get(nid, []) if direction == "incoming" else graph.out_edges.get(nid, [])
            rel_edges = [e for e in edges if e.get("relationship") == rel] if rel else edges
            if not rel_edges:
                hits.append(f"{n.get('label', '?')[:30]} has no {rel or 'any'} relationships")
        else:
            if not n.get(field_name):
                hits.append(f"{n.get('label', '?')[:30]} missing {field_name}")

    # Only flag if a meaningful proportion
    if len(hits) >= 2:
        return hits[:5]
    return None


def _eval_officer_overlap(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for entities sharing officers across jurisdictions."""
    min_shared = cond.get("min_shared_officers", 2)

    # Build entity -> officers mapping
    entity_officers = defaultdict(set)
    for e in graph.edges:
        if e.get("relationship") in ("officer_of", "co_officer"):
            entity_officers[e["target_id"]].add(e["source_id"])
            entity_officers[e["source_id"]].add(e["target_id"])

    # Find pairs sharing officers
    entities = list(entity_officers.keys())
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            shared = entity_officers[entities[i]] & entity_officers[entities[j]]
            if len(shared) >= min_shared:
                n1 = graph.nodes.get(entities[i], {})
                n2 = graph.nodes.get(entities[j], {})
                return [f"{n1.get('label', '?')[:25]} and {n2.get('label', '?')[:25]} share {len(shared)} officers"]

    return None


def _eval_centrality(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Simplified betweenness centrality check."""
    percentile = cond.get("percentile", 95)

    if len(graph.nodes) < 5:
        return None

    # Approximate betweenness: count how many shortest paths pass through each node
    # Full betweenness is O(VE), this is a simplified version using degree as proxy
    degrees = sorted(graph.degree.values())
    if not degrees:
        return None

    threshold_idx = int(len(degrees) * percentile / 100)
    threshold = degrees[min(threshold_idx, len(degrees) - 1)]

    if threshold < 3:
        return None

    hits = []
    for nid, deg in graph.degree.items():
        if deg >= threshold:
            n = graph.nodes.get(nid, {})
            hits.append(f"{n.get('label', nid)[:30]} degree={deg} (95th pctile={threshold})")

    return hits[:3] if hits else None


def _eval_multi_path(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if multiple paths exist between pairs of nodes."""
    min_paths = cond.get("min_paths", 3)
    max_hops = cond.get("max_hop_length", 3)

    # Check hop-0 nodes with high fan-out
    hop0 = [n for n in graph.nodes.values() if n.get("hop", 0) == 0]
    for src in hop0:
        sid = src.get("id", "")
        if graph.out_degree.get(sid, 0) >= min_paths:
            # Check if multiple paths reach a common destination
            targets = defaultdict(int)
            for e in graph.out_edges.get(sid, []):
                tid = e["target_id"]
                for e2 in graph.out_edges.get(tid, []):
                    targets[e2["target_id"]] += 1
            for tid, count in targets.items():
                if count >= min_paths and tid != sid:
                    tn = graph.nodes.get(tid, {})
                    return [f"{min_paths}+ paths from {src.get('label', '')[:20]} reach {tn.get('label', '')[:20]}"]

    return None


def _eval_type_match(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for specific node type combinations."""
    director_types = cond.get("director_type", [])
    if isinstance(director_types, str):
        director_types = [director_types]
    director_types = [t.lower() for t in director_types]

    for e in graph.edges:
        if e.get("relationship") in ("officer_of", "co_officer"):
            src_node = graph.nodes.get(e["source_id"], {})
            src_type = (src_node.get("node_type") or src_node.get("type") or "").lower()
            if src_type in director_types:
                return [f"Corporate director: {src_node.get('label', '?')[:30]} (type: {src_type})"]

    return None


def _eval_name_match(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for entities with similar names in different jurisdictions."""
    threshold = cond.get("similarity_threshold", 0.8)

    entities = [n for n in graph.nodes.values()
                if (n.get("node_type") or n.get("type") or "").lower() in ("entity", "company")]

    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            n1, n2 = entities[i], entities[j]
            name1 = _norm(n1.get("label", ""))
            name2 = _norm(n2.get("label", ""))
            if not name1 or not name2:
                continue
            # Simple similarity: shared word ratio
            words1 = set(name1.split())
            words2 = set(name2.split())
            if not words1 or not words2:
                continue
            overlap = len(words1 & words2) / max(len(words1), len(words2))
            if overlap >= threshold:
                return [f"Similar names: '{n1.get('label', '')[:25]}' and '{n2.get('label', '')[:25]}' (similarity: {overlap:.0%})"]

    return None


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _strip_accents(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein edit distance."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


def _clean_person_name(name: str) -> str:
    """Normalize a person name for fuzzy comparison: strip accents,
    lowercase, remove titles, remove non-alpha, sort words."""
    cleaned = _strip_accents(name).lower()
    cleaned = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|sir|dame|lord|lady)\b", "", cleaned)
    cleaned = re.sub(r"[^a-z ]", "", cleaned).strip()
    return " ".join(sorted(cleaned.split()))


def _eval_name_obfuscation(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Detect person names with small edit distances (potential obfuscation)."""
    max_dist = cond.get("max_edit_distance", 2)
    min_len = cond.get("min_name_length", 6)
    target_types = cond.get("node_types", ["Officer", "Person"])
    target_lower = {t.lower() for t in target_types}

    persons = [
        n for n in graph.nodes.values()
        if (n.get("type") or "").lower() in target_lower
    ]

    # Build normalized names
    cleaned = []
    for n in persons:
        c = _clean_person_name(n.get("label", ""))
        if len(c) >= min_len:
            cleaned.append((c, n))

    hits = []
    seen_pairs = set()
    for i in range(len(cleaned)):
        for j in range(i + 1, len(cleaned)):
            name_a, node_a = cleaned[i]
            name_b, node_b = cleaned[j]
            # Skip if names are identical (already merged or same person)
            if name_a == name_b:
                continue
            dist = _edit_distance(name_a, name_b)
            if 0 < dist <= max_dist:
                pair_key = tuple(sorted([name_a, name_b]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                label_a = node_a.get("label", "?")[:30]
                label_b = node_b.get("label", "?")[:30]
                jur_a = ", ".join(node_a.get("country_codes", []) or ["?"])
                jur_b = ", ".join(node_b.get("country_codes", []) or ["?"])
                hits.append(
                    f"Name variant: '{label_a}' ({jur_a}) ↔ "
                    f"'{label_b}' ({jur_b}) — "
                    f"edit distance {dist}"
                )
    return hits if hits else None


def _eval_name_obfuscation_jurisdiction(
    cond: dict, graph: _GraphIndex,
) -> list[str] | None:
    """Detect name variants appearing across different jurisdictions."""
    max_dist = cond.get("max_edit_distance", 2)
    min_jur = cond.get("min_jurisdictions", 2)
    target_types = cond.get("node_types", ["Officer", "Person", "Entity", "Company"])
    target_lower = {t.lower() for t in target_types}

    entities = [
        n for n in graph.nodes.values()
        if (n.get("type") or "").lower() in target_lower
           and n.get("country_codes")
    ]

    cleaned = []
    for n in entities:
        c = _clean_person_name(n.get("label", ""))
        if len(c) >= 6:
            cleaned.append((c, n))

    # Group by fuzzy name clusters
    clusters: dict[str, list] = {}
    assigned: dict[int, str] = {}

    for i, (name, node) in enumerate(cleaned):
        matched_cluster = None
        for rep, members in clusters.items():
            if _edit_distance(name, rep) <= max_dist:
                matched_cluster = rep
                break
        if matched_cluster:
            clusters[matched_cluster].append((name, node))
        else:
            clusters[name] = [(name, node)]

    hits = []
    for rep, members in clusters.items():
        if len(members) < 2:
            continue
        # Collect unique jurisdictions across variants
        all_jur = set()
        unique_names = set()
        for name, node in members:
            unique_names.add(name)
            for c in node.get("country_codes", []):
                all_jur.add(c)
        if len(all_jur) >= min_jur and len(unique_names) > 1:
            labels = [m[1].get("label", "?")[:25] for m in members[:4]]
            hits.append(
                f"Name variants across {len(all_jur)} jurisdictions "
                f"({', '.join(sorted(all_jur))}): "
                f"{' / '.join(labels)}"
            )

    return hits if hits else None


# ------------------------------------------------------------------
# New condition evaluators — corporate distress & enrichment signals
# ------------------------------------------------------------------

def _eval_insolvency_status(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes with insolvency flags or specific insolvency types."""
    target_statuses = cond.get("statuses", [])
    if isinstance(target_statuses, str):
        target_statuses = [target_statuses]
    target_set = {s.lower() for s in target_statuses} if target_statuses else None
    hits = []
    for n in graph.nodes.values():
        if n.get("insolvency") or n.get("insolvency_status"):
            status = (n.get("insolvency_status") or n.get("company_status") or "").lower()
            ins_type = ""
            cases = n.get("insolvency_cases", [])
            if cases and isinstance(cases, list) and isinstance(cases[0], dict):
                ins_type = cases[0].get("type", "").lower()
            if target_set:
                if status in target_set or ins_type in target_set:
                    hits.append(f"{n.get('label', '?')[:30]} — {ins_type or status}")
            else:
                hits.append(f"{n.get('label', '?')[:30]} — insolvency detected")
    return hits if hits else None


def _eval_officer_disqualification(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes flagged as disqualified directors."""
    hits = []
    for n in graph.nodes.values():
        if n.get("disqualified"):
            hits.append(f"{n.get('label', '?')[:30]} — disqualified director")
    return hits if hits else None


def _eval_sec_event_type(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes with specific SEC 8-K item types."""
    target_items = cond.get("items", [])
    if isinstance(target_items, str):
        target_items = [target_items]
    target_set = set(target_items) if target_items else None
    hits = []
    for n in graph.nodes.values():
        events = n.get("sec_8k_items") or n.get("material_events") or []
        if not isinstance(events, list):
            continue
        for ev in events:
            item_num = ev.get("item", "") if isinstance(ev, dict) else str(ev)
            if target_set is None or item_num in target_set:
                hits.append(f"{n.get('label', '?')[:30]} — 8-K Item {item_num}")
    return hits if hits else None


def _eval_amendment_count(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes with filing amendment counts exceeding a threshold."""
    min_count = cond.get("min_count", 2)
    hits = []
    for n in graph.nodes.values():
        count = n.get("amendment_count", 0)
        if isinstance(count, (int, float)) and count >= min_count:
            hits.append(f"{n.get('label', '?')[:30]} — {int(count)} amendments")
    return hits if hits else None


def _eval_property_value(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes with property values exceeding a threshold."""
    min_value = cond.get("min_value", 1_000_000)
    hits = []
    for n in graph.nodes.values():
        price = n.get("price") or n.get("property_price") or 0
        if isinstance(price, (int, float)) and price >= min_value:
            hits.append(f"{n.get('label', '?')[:30]} — £{int(price):,}")
    return hits if hits else None


def _eval_bankruptcy_filing(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check for nodes with bankruptcy status."""
    hits = []
    for n in graph.nodes.values():
        if n.get("bankruptcy") or n.get("bankruptcy_status") or n.get("chapter"):
            chapter = n.get("chapter", "")
            hits.append(
                f"{n.get('label', '?')[:30]} — bankruptcy"
                + (f" (Chapter {chapter})" if chapter else "")
            )
    return hits if hits else None


def _eval_temporal_range(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if a date span between two fields is within max_days."""
    from datetime import datetime
    field_start = cond.get("field_start", "incorporation_date")
    field_end = cond.get("field_end", "dissolution_date")
    max_days = cond.get("max_days", 730)
    hits = []
    for n in graph.nodes.values():
        start_str = n.get(field_start, "")
        end_str = n.get(field_end, "")
        if not start_str or not end_str:
            continue
        try:
            start = datetime.fromisoformat(start_str[:10])
            end = datetime.fromisoformat(end_str[:10])
            delta = (end - start).days
            if 0 < delta <= max_days:
                hits.append(
                    f"{n.get('label', '?')[:30]} — {delta} days "
                    f"({start_str[:10]} to {end_str[:10]})"
                )
        except (ValueError, TypeError):
            continue
    return hits if hits else None


def _eval_jurisdiction_mismatch(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if entity officers are from different jurisdictions than the entity."""
    entity_jur = cond.get("entity_jurisdiction", "").upper()
    exclude_jur = cond.get("officer_jurisdictions_exclude", "").upper()
    hits = []
    for nid, n in graph.nodes.items():
        ntype = (n.get("node_type") or n.get("type") or "").lower()
        if ntype not in ("entity", "company"):
            continue
        jur = (n.get("jurisdiction") or "").upper()
        if entity_jur and jur != entity_jur:
            continue
        for edge in graph.out_edges.get(nid, []) + graph.in_edges.get(nid, []):
            other_id = edge["target_id"] if edge["source_id"] == nid else edge["source_id"]
            other = graph.nodes.get(other_id, {})
            other_type = (other.get("node_type") or other.get("type") or "").lower()
            if other_type not in ("officer", "person"):
                continue
            other_nat = (other.get("nationality") or "").upper()
            other_codes = [c.upper() for c in other.get("country_codes", [])]
            if exclude_jur:
                if (other_nat and other_nat != exclude_jur) or \
                   (other_codes and exclude_jur not in other_codes):
                    hits.append(
                        f"{other.get('label', '?')[:25]} "
                        f"directs {n.get('label', '?')[:25]} ({jur})"
                    )
    return hits if hits else None


def _eval_entity_status(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if any entity has a status matching the provided list."""
    target_statuses = cond.get("statuses", [])
    if isinstance(target_statuses, str):
        target_statuses = [target_statuses]
    target_set = {s.lower() for s in target_statuses}
    hits = []
    for n in graph.nodes.values():
        status = (n.get("status") or n.get("company_status") or "").lower()
        if status in target_set:
            hits.append(f"{n.get('label', '?')[:30]} — status: {status}")
    return hits if hits else None


def _eval_temporal_sequence(cond: dict, graph: _GraphIndex) -> list[str] | None:
    """Check if one date field occurs after another reference date field."""
    from datetime import datetime
    entity_field = cond.get("entity_date", "incorporation_date")
    ref_field = cond.get("reference_date", "sanctions_designation_date")
    entity_after = cond.get("entity_after_reference", True)
    hits = []
    for n in graph.nodes.values():
        entity_date_str = n.get(entity_field, "")
        ref_date_str = n.get(ref_field, "")
        if not entity_date_str or not ref_date_str:
            continue
        try:
            entity_date = datetime.fromisoformat(entity_date_str[:10])
            ref_date = datetime.fromisoformat(ref_date_str[:10])
            if entity_after and entity_date > ref_date:
                hits.append(
                    f"{n.get('label', '?')[:30]} — {entity_field} "
                    f"({entity_date_str[:10]}) after {ref_field} "
                    f"({ref_date_str[:10]})"
                )
            elif not entity_after and entity_date < ref_date:
                hits.append(
                    f"{n.get('label', '?')[:30]} — {entity_field} "
                    f"({entity_date_str[:10]}) before {ref_field} "
                    f"({ref_date_str[:10]})"
                )
        except (ValueError, TypeError):
            continue
    return hits if hits else None
