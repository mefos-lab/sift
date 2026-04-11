"""Entity normalization — deduplicate, classify, merge, and extract structure."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# Country extraction patterns
_COUNTRY_PATTERNS = {
    "united states of america": "US", "united states": "US", "usa": "US",
    "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "british virgin islands": "VG", "virgin islands": "VI",
    "cayman islands": "KY", "isle of man": "IM", "jersey": "JE",
    "guernsey": "GG", "bermuda": "BM", "gibraltar": "GI",
    "hong kong": "HK", "singapore": "SG", "switzerland": "CH",
    "luxembourg": "LU", "liechtenstein": "LI", "monaco": "MC",
    "panama": "PA", "seychelles": "SC", "bahamas": "BS",
    "belize": "BZ", "samoa": "WS", "marshall islands": "MH",
    "nevis": "KN", "barbados": "BB", "mauritius": "MU",
    "israel": "IL", "malta": "MT", "cyprus": "CY",
    "australia": "AU", "canada": "CA", "new zealand": "NZ",
    "germany": "DE", "france": "FR", "netherlands": "NL",
    "ireland": "IE", "spain": "ES", "italy": "IT",
    "portugal": "PT", "belgium": "BE", "austria": "AT",
    "denmark": "DK", "sweden": "SE", "norway": "NO",
    "finland": "FI", "greece": "GR", "poland": "PL",
    "czech republic": "CZ", "romania": "RO", "hungary": "HU",
    "russia": "RU", "china": "CN", "japan": "JP",
    "south korea": "KR", "india": "IN", "brazil": "BR",
    "mexico": "MX", "argentina": "AR", "colombia": "CO",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE",
    "united arab emirates": "AE", "dubai": "AE", "qatar": "QA",
    "saudi arabia": "SA", "turkey": "TR", "egypt": "EG",
}

# Cities to country codes
_CITY_COUNTRY = {
    "tel aviv": "IL", "jerusalem": "IL", "haifa": "IL",
    "london": "GB", "edinburgh": "GB", "manchester": "GB",
    "new york": "US", "los angeles": "US", "chicago": "US",
    "washington": "US", "miami": "US", "san francisco": "US",
    "boston": "US", "dallas": "US", "seattle": "US",
    "hong kong": "HK", "singapore": "SG", "dubai": "AE",
    "zurich": "CH", "geneva": "CH", "bern": "CH",
    "panama city": "PA", "nassau": "BS", "road town": "VG",
    "george town": "KY", "douglas": "IM", "st helier": "JE",
    "hamilton": "BM", "victoria": "SC", "valletta": "MT",
    "nicosia": "CY", "bridgetown": "BB", "port louis": "MU",
    "tokyo": "JP", "beijing": "CN", "shanghai": "CN",
    "paris": "FR", "berlin": "DE", "amsterdam": "NL",
    "dublin": "IE", "madrid": "ES", "rome": "IT",
    "lisbon": "PT", "brussels": "BE", "vienna": "AT",
    "copenhagen": "DK", "stockholm": "SE", "oslo": "NO",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "sydney": "AU", "melbourne": "AU",
    "qormi": "MT", "sliema": "MT", "naxxar": "MT", "mosta": "MT",
    "skopje": "MK", "athens": "GR",
}

# US state abbreviations (for address detection)
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


@dataclass
class NormalizationLog:
    """Record of what was changed during normalization."""
    countries_extracted: int = 0
    addresses_classified: int = 0
    duplicates_merged: list = field(default_factory=list)
    cross_source_merged: list = field(default_factory=list)

    @property
    def total_merged(self) -> int:
        return len(self.duplicates_merged) + len(self.cross_source_merged)

    def to_dict(self) -> dict:
        return {
            "countries_extracted": self.countries_extracted,
            "addresses_classified": self.addresses_classified,
            "duplicates_merged": self.duplicates_merged,
            "cross_source_merged": self.cross_source_merged,
            "total_merged": self.total_merged,
        }


def normalize_graph(nodes: dict, edges: list) -> tuple[dict, list, NormalizationLog]:
    """Normalize a traversal graph: deduplicate, classify, merge, extract.

    Parameters
    ----------
    nodes : dict mapping node_id -> GraphNode
    edges : list of GraphEdge

    Returns
    -------
    (normalized_nodes, normalized_edges, log) — deduplicated, enriched, with audit trail
    """
    log = NormalizationLog()

    # Step 1: Extract countries from address labels
    log.countries_extracted = _enrich_countries(nodes)

    # Step 2: Classify nodes (is this an address, a person, a real entity?)
    log.addresses_classified = _classify_nodes(nodes)

    # Step 3: Deduplicate by normalized name + type
    id_remap, dedup_log = _deduplicate(nodes)
    log.duplicates_merged = dedup_log

    # Step 4: Rewrite edges through merged IDs
    edges = _rewrite_edges(edges, id_remap, nodes)

    # Step 5: Merge cross-source duplicates (same name, different source)
    id_remap2, cross_log = _merge_cross_source(nodes)
    log.cross_source_merged = cross_log
    if id_remap2:
        edges = _rewrite_edges(edges, id_remap2, nodes)

    return nodes, edges, log


def _enrich_countries(nodes: dict) -> int:
    """Extract country codes from address labels and entity names."""
    count = 0
    for n in nodes.values():
        props = n.properties if hasattr(n, "properties") else n
        existing = props.get("country_codes", [])
        if existing:
            continue

        label = (n.label if hasattr(n, "label") else n.get("label", "")).lower()
        extracted = _extract_country(label)
        if extracted:
            if hasattr(n, "properties"):
                n.properties["country_codes"] = list(set(existing + [extracted]))
            else:
                n["country_codes"] = list(set(existing + [extracted]))
            count += 1
    return count


def _extract_country(text: str) -> str | None:
    """Try to extract a country code from text."""
    text_lower = text.lower().strip()

    # Check country names
    for pattern, code in _COUNTRY_PATTERNS.items():
        if pattern in text_lower:
            return code

    # Check city names
    for city, code in _CITY_COUNTRY.items():
        if city in text_lower:
            return code

    # Check US state abbreviations in address-like strings
    words = text_lower.replace(",", " ").replace(";", " ").split()
    for w in words:
        if w.upper() in _US_STATES and len(w) == 2:
            return "US"

    return None


def _classify_nodes(nodes: dict) -> int:
    """Tag nodes with relevance classification. Returns address count."""
    count = 0
    for n in nodes.values():
        label = n.label if hasattr(n, "label") else n.get("label", "")
        ntype = (n.node_type if hasattr(n, "node_type") else n.get("node_type", n.get("type", ""))).lower()

        is_addr = ntype == "address" or _looks_like_address(label)
        if hasattr(n, "properties"):
            n.properties["_is_address"] = is_addr
        else:
            n["_is_address"] = is_addr
        if is_addr:
            count += 1
    return count


def _looks_like_address(label: str) -> bool:
    """Heuristic: does this label look like a street address?"""
    label_lower = label.lower()
    # Address indicators
    address_words = ["street", "road", "avenue", "drive", "lane", "blvd",
                     "boulevard", "crescent", "place", "way", "court",
                     "terrace", "close", "square", "park", "house",
                     "flat", "suite", "floor", "unit", "p.o. box",
                     "po box", "c/o", "attn:"]
    for word in address_words:
        if word in label_lower:
            return True

    # Starts with a number followed by a street-like word
    if re.match(r"^\d+[\s,]", label):
        return True

    return False


def _normalize_name(name: str) -> str:
    """Normalize a name for deduplication matching."""
    # Remove common suffixes/prefixes
    n = name.upper().strip()
    # Remove punctuation variations
    n = re.sub(r"[.,;:'\"\-()']", " ", n)
    # Normalize whitespace
    n = re.sub(r"\s+", " ", n).strip()
    # Remove common corporate suffixes for comparison
    for suffix in [" LTD", " LIMITED", " INC", " INC.", " CORP",
                   " CORP.", " S.A.", " SA", " AG", " GMBH",
                   " LLC", " LLP", " PLC"]:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    return n


def _normalize_address(addr: str) -> str:
    """Aggressively normalize an address for deduplication."""
    a = addr.upper().strip()
    # Remove all punctuation
    a = re.sub(r"[.,;:'\"\-/\\()']", " ", a)
    # Normalize whitespace
    a = re.sub(r"\s+", " ", a).strip()
    # Remove trailing country names (already extracted)
    for country in ["MALTA", "UNITED KINGDOM", "UNITED STATES OF AMERICA",
                     "ISRAEL", "BARBADOS", "CANADA", "AUSTRALIA"]:
        if a.endswith(country):
            a = a[:-len(country)].strip()
    # Remove trailing postal codes
    a = re.sub(r"\s+[A-Z]{1,2}\d{1,2}\s*\d?[A-Z]{0,2}\s*$", "", a)
    a = re.sub(r"\s+\d{4,6}\s*$", "", a)
    return a.strip()


def _deduplicate(nodes: dict) -> tuple[dict[str, str], list[dict]]:
    """Merge duplicate nodes (same normalized name + type + source).

    Returns (id_remap, merge_log)
    """
    id_remap = {}
    merge_log = []
    # Group by (normalized_name, type, source)
    groups = defaultdict(list)
    for nid, n in nodes.items():
        label = n.label if hasattr(n, "label") else n.get("label", "")
        ntype = (n.node_type if hasattr(n, "node_type") else n.get("node_type", n.get("type", ""))).lower()
        source = n.source if hasattr(n, "source") else n.get("source", "")
        props = n.properties if hasattr(n, "properties") else n
        is_addr = props.get("_is_address", False) or ntype == "address"
        norm = _normalize_address(label) if is_addr else _normalize_name(label)
        key = (norm, ntype, source)
        groups[key].append(nid)

    for key, nids in groups.items():
        if len(nids) <= 1:
            continue
        # Keep the first, remap the rest
        canonical = nids[0]
        canon_label = nodes[canonical].label if hasattr(nodes[canonical], "label") else nodes[canonical].get("label", "")
        merged_labels = []
        for other in nids[1:]:
            other_label = nodes[other].label if hasattr(nodes[other], "label") else nodes[other].get("label", "")
            merged_labels.append(other_label)
            id_remap[other] = canonical
            _merge_node_props(nodes[canonical], nodes[other])
            del nodes[other]
        merge_log.append({
            "kept": canon_label,
            "merged": merged_labels,
            "reason": "same normalized name, type, and source",
        })

    return id_remap, merge_log


def _merge_cross_source(nodes: dict) -> tuple[dict[str, str], list[dict]]:
    """Merge nodes with the same name across different sources."""
    id_remap = {}
    merge_log = []
    # Group by normalized name only (ignoring source)
    name_groups = defaultdict(list)
    for nid, n in nodes.items():
        label = n.label if hasattr(n, "label") else n.get("label", "")
        ntype = (n.node_type if hasattr(n, "node_type") else n.get("node_type", n.get("type", ""))).lower()
        # Only merge person/officer nodes cross-source (not addresses or generic entities)
        if ntype in ("officer", "person"):
            name_groups[_normalize_name(label)].append(nid)

    for name, nids in name_groups.items():
        if len(nids) <= 1:
            continue
        # Check they're from different sources
        source_map = {}
        for nid in nids:
            n = nodes[nid]
            src = n.source if hasattr(n, "source") else n.get("source", "")
            source_map[nid] = src
        if len(set(source_map.values())) <= 1:
            continue

        # Merge into the one with the highest confidence
        def _conf(nid):
            n = nodes[nid]
            props = n.properties if hasattr(n, "properties") else n
            return props.get("confidence", 0)

        nids_sorted = sorted(nids, key=_conf, reverse=True)
        canonical = nids_sorted[0]
        canon_node = nodes[canonical]
        canon_label = canon_node.label if hasattr(canon_node, "label") else canon_node.get("label", "")
        # Mark as multi-source
        if hasattr(canon_node, "source"):
            canon_node.source = "both"
        else:
            canon_node["source"] = "both"

        merged_from = []
        for other in nids_sorted[1:]:
            other_label = nodes[other].label if hasattr(nodes[other], "label") else nodes[other].get("label", "")
            merged_from.append(f"{other_label} [{source_map[other]}]")
            id_remap[other] = canonical
            _merge_node_props(canon_node, nodes[other])
            del nodes[other]

        merge_log.append({
            "kept": f"{canon_label} [{source_map[canonical]}]",
            "merged": merged_from,
            "reason": "same person across different sources",
        })

    return id_remap, merge_log


def _merge_node_props(canonical, other):
    """Merge properties from other node into canonical."""
    if hasattr(canonical, "properties"):
        c_props = canonical.properties
        o_props = other.properties if hasattr(other, "properties") else other
    else:
        c_props = canonical
        o_props = other

    # Merge country codes
    c_countries = set(c_props.get("country_codes", []))
    o_countries = set(o_props.get("country_codes", []))
    merged_countries = list(c_countries | o_countries)
    if merged_countries:
        c_props["country_codes"] = [c for c in merged_countries if c]

    # Take higher confidence
    if o_props.get("confidence", 0) > c_props.get("confidence", 0):
        c_props["confidence"] = o_props["confidence"]

    # Take higher risk
    if o_props.get("risk_score", 0) > c_props.get("risk_score", 0):
        c_props["risk_score"] = o_props["risk_score"]
        c_props["risk_level"] = o_props.get("risk_level", "")

    # Merge topics
    c_topics = set(c_props.get("topics", []))
    o_topics = set(o_props.get("topics", []))
    if c_topics | o_topics:
        c_props["topics"] = list(c_topics | o_topics)

    # Merge datasets
    c_ds = set(c_props.get("datasets", []))
    o_ds = set(o_props.get("datasets", []))
    if c_ds | o_ds:
        c_props["datasets"] = list(c_ds | o_ds)

    # Inherit flags
    if o_props.get("sanctioned"):
        c_props["sanctioned"] = True
    if o_props.get("pep"):
        c_props["pep"] = True


def _rewrite_edges(edges: list, id_remap: dict, nodes: dict) -> list:
    """Rewrite edge endpoints through remap, remove dangling and self-loops."""
    live_ids = set(nodes.keys())
    seen = set()
    result = []

    for e in edges:
        if hasattr(e, "source_id"):
            src = id_remap.get(e.source_id, e.source_id)
            tgt = id_remap.get(e.target_id, e.target_id)
            rel = e.relationship
        else:
            src = id_remap.get(e.get("source_id", ""), e.get("source_id", ""))
            tgt = id_remap.get(e.get("target_id", ""), e.get("target_id", ""))
            rel = e.get("relationship", "")

        if src == tgt:
            continue
        if src not in live_ids or tgt not in live_ids:
            continue
        key = (src, tgt, rel)
        if key in seen:
            continue
        seen.add(key)

        if hasattr(e, "source_id"):
            e.source_id = src
            e.target_id = tgt
            result.append(e)
        else:
            result.append({"source_id": src, "target_id": tgt, "relationship": rel})

    return result
