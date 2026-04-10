# The Matryoshka

STRUCTURE: Nested chain of shell companies across jurisdictions, each owning the next, creating layers of opacity between the beneficial owner and the assets or transactions at the chain's end.
JURISDICTIONS: Typically high-secrecy chains — BVI → Panama → Seychelles; Jersey → BVI → Samoa; Liechtenstein → Panama → Niue
INDICATORS: Entity-owns-entity chains spanning 3+ jurisdictions; same intermediary at each layer; entities with no apparent commercial purpose
RISK LEVEL: HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Paradise Papers, Pandora Papers

## Mechanism

Each entity in the chain is incorporated in a different jurisdiction. The first entity (closest to the beneficial owner) is typically in a jurisdiction with strong privacy protections. Each subsequent entity adds a layer of jurisdictional complexity — to trace the chain, an investigator must navigate the corporate registry and legal system of each jurisdiction, often requiring mutual legal assistance treaties (MLATs) that can take years to process.

The structure achieves opacity through multiplication: even if one jurisdiction cooperates with investigators, the next layer requires a new legal process in a different country with different laws and different cooperation standards.

## Detection

Using the MCP tools:
1. `/investigate` a name — look for multiple entity matches across different jurisdictions
2. Check whether entities share officers or intermediaries — shared intermediaries across jurisdictions suggest a coordinated structure
3. Use `/trace-network` to walk outward — if an entity's officer is another entity (not a person), that signals a chain
4. Count jurisdictions — 3+ jurisdictions with entity-owns-entity relationships is the signature

## Examples

To be populated through investigations.
