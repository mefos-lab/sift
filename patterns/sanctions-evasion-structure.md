# The Sanctions Evasion Structure

STRUCTURE: An offshore arrangement where entities are structured to maintain access to the global financial system while routing transactions around sanctioned persons or jurisdictions. The sanctioned person's connection to the offshore entity is obscured through one or more intermediary layers — nominees, shell companies, or professional intermediaries.
JURISDICTIONS: Entities typically in high-secrecy jurisdictions (BVI, Seychelles, Panama); banking relationships in jurisdictions with weaker sanctions enforcement or through correspondent banking chains
INDICATORS: An ICIJ entity whose officers or connected persons match sanctioned entries in OpenSanctions, with nominee directors or intermediary entities interposed between the sanctioned person and the operating entity
RISK LEVEL: HIGH
STATUS: PROPOSED
OBSERVED IN: To be confirmed through cross-referencing ICIJ and OpenSanctions data

## Mechanism

A sanctioned person cannot directly open bank accounts, conduct transactions, or hold assets in jurisdictions that enforce the relevant sanctions regime. The evasion structure interposes one or more layers between the sanctioned person and the financial system:

1. The sanctioned person controls an entity through nominees or trusted associates who are not themselves sanctioned
2. The entity is incorporated in a jurisdiction that does not enforce the relevant sanctions or has weak due diligence requirements
3. The entity maintains banking relationships in a third jurisdiction, often through correspondent banking chains that create distance from the sanctioned person
4. Transactions are routed through the structure, appearing to originate from non-sanctioned parties

The structure may use multiple patterns simultaneously — The Matryoshka (nested entities across jurisdictions), The Nominee Shield (professional nominees as directors), and The Intermediary Cluster (a single service provider managing the structure).

## Detection

Using the MCP tools:
1. `/cross-reference` a name — search both ICIJ and OpenSanctions
2. If the name appears in both databases, examine the ICIJ network for intermediary layers between the sanctioned person and operating entities
3. Use `sanctions_provenance` to determine which sanctions list and when the designation was made — entities created AFTER the sanctions designation are higher risk
4. Check whether the ICIJ intermediary or officers have their own sanctions exposure using `sanctions_batch_match`
5. The Temporal Cluster pattern combined with a sanctions designation date is a strong indicator

## Examples

To be populated through cross-reference investigations.
