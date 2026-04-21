"""Confidence and risk scoring for investigation entities."""

from __future__ import annotations

import re
from typing import Any

# Jurisdiction risk tiers (higher = riskier)
SECRECY_JURISDICTIONS = {
    "VG", "SC", "PA", "KY", "BZ", "WS", "MH", "KN",
    "BM", "GG", "JE", "IM", "LI", "MC", "AD",
    "VI", "AI", "TC", "MS",  # UK/US overseas territories used offshore
}
HIGH_RISK_JURISDICTIONS = {
    "MM", "SS", "SY", "YE", "IR", "KP",
    "AF", "BF", "CM", "CD", "HT", "MZ", "NG", "PH",
}


def compute_confidence(node: dict, seed_name: str) -> float:
    """Compute match confidence (0.0-1.0) for how likely a node is
    genuinely related to the investigation seed.

    Factors:
    - Name similarity to seed (strongest signal)
    - Match score from source API
    - Country overlap with other seed matches
    - Entity type relevance
    - Corroboration across sources
    """
    score = 0.0
    label = node.get("label", "")
    node_type = (node.get("node_type") or node.get("type") or "").lower()

    # 1. Name similarity (0-0.4)
    name_sim = _name_similarity(label, seed_name)
    score += name_sim * 0.4

    # 2. API match score (0-0.25)
    api_score = node.get("score") or node.get("properties", {}).get("score")
    if api_score is not None:
        if isinstance(api_score, (int, float)):
            # ICIJ scores are 0-100, OpenSanctions are 0-1
            normalized = api_score / 100.0 if api_score > 1 else api_score
            score += min(normalized, 1.0) * 0.25

    # 3. Source (0-0.15)
    source = node.get("source", "")
    if source == "both":
        score += 0.15  # Cross-source corroboration
    elif source in ("icij", "opensanctions"):
        score += 0.10
    elif source in ("courtlistener", "sec"):
        score += 0.08
    else:
        score += 0.05

    # 4. Hop distance penalty (0 to -0.2)
    hop = node.get("hop", 0)
    if hop == 0:
        pass  # No penalty for direct matches
    elif hop == 1:
        score -= 0.05
    elif hop == 2:
        score -= 0.12
    else:
        score -= 0.20

    # 5. Entity type relevance (0-0.1)
    if node_type in ("officer", "person"):
        score += 0.10
    elif node_type in ("entity", "company", "organization"):
        score += 0.08
    elif node_type == "intermediary":
        score += 0.06
    elif node_type == "case":
        score += 0.07
    elif node_type == "address":
        score += 0.02

    # 6. Risk flags boost (0-0.1)
    props = node.get("properties", {}) if isinstance(node.get("properties"), dict) else {}
    if node.get("sanctioned") or props.get("sanctioned"):
        score += 0.10
    elif node.get("pep") or props.get("pep"):
        score += 0.07
    topics = node.get("topics", []) or props.get("topics", [])
    if "role.rca" in topics:
        score += 0.03

    return max(0.0, min(1.0, score))


def compute_risk_score(node: dict, pattern_hits: list[str] | None = None) -> dict:
    """Compute composite risk score (0-100) for an entity.

    Returns dict with score, level, and factor breakdown.

    Factors:
    - Sanctions status (0-30)
    - PEP exposure (0-20)
    - Jurisdiction risk (0-15)
    - Offshore structure indicators (0-15)
    - Pattern matches (0-10)
    - Cross-source exposure (0-10)
    - Court/litigation exposure (0-10)
    - Corporate distress (0-10)
    """
    factors = {}
    total = 0

    props = node.get("properties", {}) if isinstance(node.get("properties"), dict) else {}
    topics = node.get("topics", []) or props.get("topics", [])
    source = node.get("source", "")

    # 1. Sanctions (0-30)
    sanctions_score = 0
    if node.get("sanctioned") or props.get("sanctioned") or "sanction" in topics:
        sanctions_score = 30
    elif "sanction.counter" in topics:
        sanctions_score = 15
    elif "reg.action" in topics:
        sanctions_score = 20
    elif "debarment" in topics:
        sanctions_score = 18
    elif "crime" in topics or "crime.fin" in topics:
        sanctions_score = 25
    factors["sanctions"] = sanctions_score
    total += sanctions_score

    # 2. PEP (0-20)
    pep_score = 0
    if node.get("pep") or props.get("pep") or "role.pep" in topics:
        pep_score = 20
    elif "role.rca" in topics:
        pep_score = 12
    elif "role.pol" in topics:
        pep_score = 15
    factors["pep"] = pep_score
    total += pep_score

    # 3. Jurisdiction (0-15)
    jur_score = 0
    countries = node.get("country_codes", []) or props.get("country_codes", [])
    if isinstance(countries, str):
        countries = [countries]
    for c in countries:
        c_upper = c.upper() if isinstance(c, str) else ""
        if c_upper in HIGH_RISK_JURISDICTIONS:
            jur_score = max(jur_score, 15)
        elif c_upper in SECRECY_JURISDICTIONS:
            jur_score = max(jur_score, 10)
    jurisdiction = node.get("jurisdiction") or props.get("jurisdiction", "")
    if isinstance(jurisdiction, str):
        j_upper = jurisdiction.upper().split("-")[0] if jurisdiction else ""
        if j_upper in HIGH_RISK_JURISDICTIONS:
            jur_score = max(jur_score, 15)
        elif j_upper in SECRECY_JURISDICTIONS:
            jur_score = max(jur_score, 10)
    factors["jurisdiction"] = jur_score
    total += jur_score

    # 4. Offshore indicators (0-15)
    offshore_score = 0
    node_type = (node.get("node_type") or node.get("type") or "").lower()
    if source == "icij" or source == "both":
        offshore_score += 8  # Being in ICIJ at all is a signal
    if node_type == "intermediary":
        offshore_score += 4
    investigation = node.get("investigation") or props.get("investigation", "")
    if investigation:
        offshore_score += 3
    factors["offshore"] = min(offshore_score, 15)
    total += factors["offshore"]

    # 5. Pattern matches (0-10)
    pattern_score = 0
    if pattern_hits:
        pattern_score = min(len(pattern_hits) * 3, 10)
    factors["patterns"] = pattern_score
    total += pattern_score

    # 6. Cross-source (0-10)
    cross_score = 0
    if source == "both":
        cross_score = 10
    datasets = node.get("datasets", []) or props.get("datasets", [])
    if len(datasets) >= 3:
        cross_score = max(cross_score, 8)
    elif len(datasets) >= 2:
        cross_score = max(cross_score, 5)
    factors["cross_source"] = cross_score
    total += cross_score

    # 7. Litigation/court exposure (0-10)
    court_score = 0
    if source == "courtlistener":
        court_score = 8
    if "role.rca" in topics:
        # Close associate flag often indicates documented connections
        court_score = max(court_score, 5)
    factors["litigation"] = court_score
    total += court_score

    # 8. Corporate distress (0-10)
    distress_score = 0
    if props.get("insolvency") or props.get("insolvency_status"):
        distress_score += 5
    if props.get("disqualified"):
        distress_score += 5
    if props.get("bankruptcy") or props.get("bankruptcy_status") or props.get("chapter"):
        distress_score += 3
    amendment_count = props.get("amendment_count", 0)
    if isinstance(amendment_count, (int, float)) and amendment_count >= 3:
        distress_score += 2
    factors["corporate_distress"] = min(distress_score, 10)
    total += factors["corporate_distress"]

    # Determine level
    if total >= 60:
        level = "CRITICAL"
    elif total >= 40:
        level = "HIGH"
    elif total >= 20:
        level = "MEDIUM"
    elif total >= 5:
        level = "LOW"
    else:
        level = "MINIMAL"

    return {
        "score": min(total, 100),
        "level": level,
        "factors": factors,
    }


def _name_similarity(name1: str, name2: str) -> float:
    """Compute name similarity (0.0-1.0) using token overlap."""
    n1 = _normalize(name1)
    n2 = _normalize(name2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    words1 = set(n1.split())
    words2 = set(n2.split())
    if not words1 or not words2:
        return 0.0

    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    jaccard = intersection / union if union else 0.0

    # Also check if one name contains the other
    containment = 0.0
    if n1 in n2 or n2 in n1:
        containment = 0.8

    return max(jaccard, containment)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
