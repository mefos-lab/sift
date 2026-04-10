# The Intermediary Cluster

STRUCTURE: A single intermediary — law firm, corporate service provider, registered agent, or trust company — serving as formation agent for a cluster of entities that share hidden beneficial ownership or coordinated purpose. The intermediary is the visible connective tissue; the beneficial owner is not.
JURISDICTIONS: Concentrated around intermediary-heavy jurisdictions — Mossack Fonseca (Panama), Asiaciti Trust (Singapore/Samoa), Trident Trust (BVI/Jersey), Portcullis TrustNet (Cook Islands/Singapore)
INDICATORS: One intermediary connected to 50+ entities; entities within the cluster sharing incorporation jurisdiction, formation date ranges, or nominee officers; intermediary appearing repeatedly across different investigations or leaked datasets
RISK LEVEL: MEDIUM-HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers (Mossack Fonseca), Pandora Papers (Trident Trust, Asiaciti Trust, Alemán Cordero Galindo & Lee), Offshore Leaks

## Mechanism

Corporate service providers are the factories of offshore finance. A single firm can incorporate thousands of shell entities per year, supply nominee directors and shareholders from its own staff or affiliate network, maintain registered offices, and file annual returns — all for a fee. This is legal and routine. The investigative signal is not the intermediary itself but the clustering of entities behind it.

When a beneficial owner needs multiple entities (for a starburst, a matryoshka, a mirror, or all three), they typically use a single intermediary to form and manage the entire structure. The intermediary knows the full picture — it holds the formation documents, the declarations of trust, and often the real passport copies — but is bound by local law and client privilege not to disclose.

The cluster becomes investigatively significant when the intermediary's client records are leaked (as with Mossack Fonseca) or when regulatory action forces disclosure. Short of that, the intermediary is a chokepoint: all entities in the cluster connect to it, even if they share no visible officers or shareholders.

A secondary pattern: multiple unrelated beneficial owners using the same intermediary for similar structures suggests the intermediary is actively marketing particular arrangements — "tax planning packages" or "asset protection structures" — which may indicate systematic facilitation.

## Detection

Using the MCP tools:
1. `/investigate` an intermediary name (e.g., a known law firm or trust company) — note how many entities connect to it and across which jurisdictions
2. Within the cluster, use `/trace-network` on several entities to map their officer and shareholder networks — look for shared nominees, which indicates common beneficial ownership behind apparently independent entities
3. Use `/find-patterns` across the cluster to detect sub-groupings: entities formed in the same week, entities sharing the same nominee director, or entities in the same jurisdiction with sequential registration numbers
4. Cross-reference intermediary names against known leaked dataset sources (Panama Papers, Paradise Papers, Pandora Papers) — an intermediary appearing across multiple leaks indicates long-term, large-scale facilitation
5. Investigate the intermediary's other clients: if several investigated persons or sanctioned entities share the same intermediary, that elevates the risk of the entire cluster

## Examples

To be populated through investigations.
