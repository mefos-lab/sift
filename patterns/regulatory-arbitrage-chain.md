# The Regulatory Arbitrage Chain

STRUCTURE: Entities positioned across multiple jurisdictions specifically to exploit gaps, asymmetries, or conflicts between those jurisdictions' reporting, tax, sanctions, or beneficial-ownership requirements. The chain is designed so that no single regulator sees the full picture.
JURISDICTIONS: Chains exploit specific regulatory seams — US (Delaware/Nevada/Wyoming LLCs with no beneficial ownership disclosure until 2024 CTA) → BVI (no public register) → EU (beneficial ownership registers with access restrictions post-2022 ECJ ruling); also Hong Kong → Samoa, Singapore → Vanuatu, UK → Crown Dependencies (Jersey, Guernsey, Isle of Man)
INDICATORS: Entities linked across jurisdictions with non-overlapping regulatory regimes; structure that would be simpler if all entities were in one jurisdiction; intermediate entities with no assets or employees that exist only to break a reporting chain; transactions routed through jurisdictions with no connection to the underlying commercial activity
RISK LEVEL: HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Paradise Papers, Pandora Papers, OpenLux investigation

## Mechanism

Regulatory arbitrage chains exploit a fundamental structural problem: financial regulation is national, but corporate structures are international. Each jurisdiction sees only the entities registered within its borders and the transactions touching its financial system. The chain is designed so that the information required to understand the full structure is distributed across jurisdictions that do not share it automatically.

Common exploitation patterns:

**Tax treaty shopping**: An entity in a low-tax jurisdiction routes income through a conduit entity in a jurisdiction with a favorable tax treaty with the source country, reducing withholding tax. The conduit entity has no substance — no employees, no office, no real activity — but the treaty applies based on registration alone.

**Reporting gap exploitation**: Jurisdiction A requires reporting of accounts held by foreign entities. Jurisdiction B does not report to Jurisdiction A under CRS (Common Reporting Standard) because it has not signed the agreement, or has signed but does not enforce it. The chain routes through Jurisdiction B to break the information flow.

**Sanctions evasion**: Sanctioned persons or entities are hidden behind layers in non-sanctioning jurisdictions. The sanctioning country sees a transaction from a seemingly unrelated entity in a neutral jurisdiction; the connection to the sanctioned party exists only in corporate records held in a non-cooperating jurisdiction.

**Beneficial ownership fragmentation**: Jurisdiction A requires a beneficial ownership register but defines "beneficial owner" as someone with 25%+ control. Jurisdiction B sets the threshold at 10%. Jurisdiction C has no requirement at all. By distributing ownership across structures in all three, the true owner falls below disclosure thresholds everywhere.

The chain's effectiveness depends on regulatory inertia: even when information-sharing agreements exist (MLATs, CRS, EU directives), they are slow, require specific predicate offenses, and depend on the requested jurisdiction's willingness and capacity to respond.

## Detection

Using the MCP tools:
1. `/investigate` an entity — note its jurisdiction, then use `/trace-network` to map connected entities and their jurisdictions
2. For each link in the chain, ask: does this jurisdiction add commercial value, or does it add regulatory opacity? Entities in jurisdictions with no connection to the underlying business activity are arbitrage nodes
3. Look for substance indicators (or their absence): entities with only a registered agent address, no employees listed, formation dates near changes in the relevant jurisdiction's regulation (e.g., entities formed in BVI just before a new EU transparency directive took effect)
4. Cross-reference jurisdictions against CRS participation lists and MLAT networks — a chain that routes through a non-CRS jurisdiction between two CRS jurisdictions is specifically designed to break automatic information exchange
5. Use `/find-patterns` to identify whether the same chain structure (same jurisdiction sequence) appears across multiple entities — repeated use of the same regulatory seam suggests deliberate design by the intermediary or advisor

## Examples

To be populated through investigations.
