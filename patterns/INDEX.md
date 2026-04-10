# Offshore Structure Patterns

> Compact lookup table for cross-referencing during investigations.
> Each pattern describes a documented type of offshore arrangement.
> Load this before any investigative skill to check findings against
> known patterns.
>
> Patterns are accumulated through investigations. When a new structure
> is identified, it is added here as PROPOSED. When confirmed across
> multiple investigations, it is promoted to CONFIRMED or ESTABLISHED.

---

## [The Matryoshka](matryoshka.md)
STRUCTURE: Nested chain of shell companies across jurisdictions, each owning the next, creating layers of opacity.
JURISDICTIONS: Typically BVI → Panama → Seychelles or similar high-secrecy chain
INDICATORS: Entity-owns-entity chains spanning 3+ jurisdictions; same intermediary at each layer
RISK LEVEL: HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Paradise Papers, Pandora Papers

## [The Starburst](starburst.md)
STRUCTURE: One beneficial owner (or nominee acting for one) connected to dozens of entities, forming a hub-and-spoke topology.
JURISDICTIONS: Any; often concentrated in BVI or Seychelles for entity formation
INDICATORS: Single officer name appearing across 10+ entities; nominee director services
RISK LEVEL: MEDIUM (common in legitimate multi-entity businesses; HIGH when combined with nominee structures)
STATUS: ESTABLISHED
OBSERVED IN: All five investigations

## [The Mirror](mirror.md)
STRUCTURE: Parallel entities in different jurisdictions with identical or near-identical officers, providing redundancy and jurisdictional optionality.
JURISDICTIONS: Often pairs: BVI + Panama, Cayman + Jersey, Bahamas + Liechtenstein
INDICATORS: Same officer list across entities in different jurisdictions; similar entity names with different jurisdiction suffixes
RISK LEVEL: MEDIUM
STATUS: CONFIRMED
OBSERVED IN: Panama Papers, Pandora Papers

## [The Intermediary Cluster](intermediary-cluster.md)
STRUCTURE: A single intermediary (law firm, registered agent) serving as the formation agent for a cluster of entities with shared beneficial ownership that is obscured by the intermediary's consolidating role.
JURISDICTIONS: Intermediary typically in Panama, Hong Kong, Geneva, or London; entities in high-secrecy jurisdictions
INDICATORS: Same intermediary across multiple entities; entities sharing addresses; temporal clustering of formation dates
RISK LEVEL: MEDIUM
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers (Mossack Fonseca), Paradise Papers (Appleby)

## [The Nominee Shield](nominee-shield.md)
STRUCTURE: Professional nominee directors and shareholders interposed between the true beneficial owner and the entity, creating a legal screen.
JURISDICTIONS: BVI, Seychelles, Samoa, Nevis (jurisdictions with weak disclosure requirements)
INDICATORS: Same director name appearing across hundreds of unrelated entities; corporate directors (companies as directors of companies)
RISK LEVEL: HIGH
STATUS: ESTABLISHED
OBSERVED IN: All five investigations

## [The Regulatory Arbitrage Chain](regulatory-arbitrage-chain.md)
STRUCTURE: Entities positioned to exploit gaps between jurisdictions' reporting, tax, or sanctions requirements — routing transactions through the jurisdiction with the weakest applicable rule at each stage.
JURISDICTIONS: Chains typically include one EU/OECD jurisdiction (for banking access) and one or more high-secrecy jurisdictions (for opacity)
INDICATORS: Entity formation in low-regulation jurisdiction; bank accounts in high-regulation jurisdiction; transactions routed through intermediate jurisdictions
RISK LEVEL: HIGH
STATUS: CONFIRMED
OBSERVED IN: Panama Papers, Pandora Papers

## [The Temporal Cluster](temporal-cluster.md)
STRUCTURE: A burst of entity formations within a short time window (days or weeks), often correlating with external events — sanctions announcements, elections, regulatory changes, or personal events (divorce, litigation, political exposure).
JURISDICTIONS: Any
INDICATORS: Multiple entities created within 30 days with shared officers or intermediaries; formation dates correlating with known external events
RISK LEVEL: MEDIUM (may indicate legitimate business expansion; HIGH when correlated with sanctions or legal exposure)
STATUS: CONFIRMED
OBSERVED IN: Panama Papers, Pandora Papers

## [The Sanctions Evasion Structure](sanctions-evasion-structure.md)
STRUCTURE: Offshore arrangement maintaining financial system access while routing around sanctioned persons through intermediary layers — nominees, shells, or professional intermediaries obscure the sanctioned person's connection.
JURISDICTIONS: High-secrecy entity jurisdictions; banking in jurisdictions with weaker sanctions enforcement
INDICATORS: ICIJ entity whose officers/connected persons match sanctioned entries in OpenSanctions, with nominee layers interposed. Entities created after sanctions designation date are higher risk.
RISK LEVEL: HIGH
STATUS: PROPOSED
OBSERVED IN: To be confirmed through cross-referencing

## [The PEP Opacity Layer](pep-opacity-layer.md)
STRUCTURE: Offshore entities controlled by politically exposed persons through nominees designed to avoid triggering enhanced due diligence. The PEP's name does not appear in corporate records; family members, associates, or professional nominees hold formal positions.
JURISDICTIONS: Entities in high-secrecy jurisdictions; PEP based in jurisdiction with anti-corruption scrutiny
INDICATORS: ICIJ entity officers matching PEP family/associates in OpenSanctions (topic: role.pep), with nominee directors interposed. PEP's own name absent from ICIJ records.
RISK LEVEL: HIGH
STATUS: PROPOSED
OBSERVED IN: To be confirmed through cross-referencing
