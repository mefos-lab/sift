# The Nominee Shield

STRUCTURE: Professional nominee directors and/or nominee shareholders interposed between the true beneficial owner and the entity's public-facing corporate record. The nominee holds legal title; the beneficial owner holds actual control via undisclosed side agreements.
JURISDICTIONS: Most common in jurisdictions where nominee arrangements are legal and corporate registries are not publicly searchable — BVI, Panama, Seychelles, Samoa, Vanuatu; also used in jurisdictions with public registries where the nominee provides a "clean" name (Cyprus, Hong Kong, Malta)
INDICATORS: Same individual appearing as director of 50+ unrelated entities; known nominee service companies (e.g., "Dorado Nominees Ltd", "Dorado International Ltd", "Helmores Nominees Ltd"); address matching known corporate service providers; power-of-attorney or declaration-of-trust documents in leaked data
RISK LEVEL: MEDIUM
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Offshore Leaks, Paradise Papers, Pandora Papers

## Mechanism

The nominee is the simplest and most pervasive opacity tool in offshore finance. The arrangement works through a legal fiction: the nominee is the registered director or shareholder of record, visible in any corporate filing or registry search. Behind this, an undisclosed declaration of trust or nominee agreement confirms that the nominee acts at the direction of and for the benefit of the true owner.

Nominee directors sign documents, approve resolutions, and appear in official correspondence — but they take instructions from the beneficial owner (often relayed through the intermediary). Nominee shareholders hold shares in trust but have no economic interest. The beneficial owner controls the entity without appearing anywhere in the public record.

The shield is effective because many jurisdictions do not require disclosure of nominee arrangements. Even where beneficial ownership registers exist (as under EU anti-money-laundering directives), enforcement gaps mean nominees frequently appear as the "beneficial owner" in filings.

Professional nominees are typically employees or affiliates of the corporate service provider. A single person may serve as nominee director for hundreds of entities — a workload impossible if actual directorial duties were performed. This volume is itself the tell.

The nominee shield is often combined with other patterns: it supplies the anonymous nodes in a matryoshka chain, the invisible hub in a starburst, or the matching officers in a mirror structure.

## Detection

Using the MCP tools:
1. `/investigate` an entity — note the director and shareholder names returned
2. `/investigate` each director and shareholder name separately — if a person is connected to 20+ entities, they are likely a professional nominee rather than a genuine officer
3. Check addresses: if the director's address matches the registered agent's office, this confirms a nominee arrangement (the person works for the agent, not for the entity)
4. Use `/trace-network` to follow the nominee outward — the full set of entities behind one nominee often belongs to a small number of hidden beneficial owners, identifiable by shared intermediaries or formation date clusters
5. Look for nominee "tells" in entity names: words like "Nominees", "Trustees", "Fiduciary", or "Services" in the name of an entity listed as shareholder indicate a nominee holding company rather than a genuine parent

## Examples

To be populated through investigations.
