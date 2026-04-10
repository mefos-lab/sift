# The Mirror

STRUCTURE: Two or more parallel entities in different jurisdictions with identical or near-identical officer lists, formation dates, and corporate structures. The entities mirror each other, providing jurisdictional optionality and redundancy.
JURISDICTIONS: Commonly paired across jurisdictions with different treaty networks or regulatory regimes — BVI + Cyprus, Panama + Hong Kong, Cayman Islands + Luxembourg, Jersey + Singapore
INDICATORS: Entities with matching officer sets in different jurisdictions; near-simultaneous incorporation dates; identical intermediary agent; entity names that are variants of each other (e.g., "Westfield Holdings Ltd" in BVI and "Westfield Enterprises SA" in Panama)
RISK LEVEL: MEDIUM-HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Paradise Papers

## Mechanism

The mirror structure provides optionality. By maintaining parallel entities in jurisdictions with different double-taxation treaties, different sanctions exposure, different reporting requirements, and different political stability profiles, the beneficial owner can route transactions through whichever entity offers the most advantageous treatment at any given time.

A common configuration: one entity in a jurisdiction with EU treaty access (Luxembourg, Cyprus, Malta) and a mirror in a high-secrecy jurisdiction (BVI, Panama). Legitimate-looking transactions flow through the treaty entity; transactions requiring opacity flow through the secrecy entity. If one jurisdiction tightens regulations or begins cooperating with foreign investigators, operations shift to the mirror without any visible restructuring.

The mirror also functions as a contingency. If one entity is frozen, seized, or subjected to legal process, the mirror continues to operate. Assets can be pre-positioned across both entities so that no single jurisdiction can reach the full holding.

The key tell is that mirrors have no independent commercial rationale. Two entities with identical officers doing the same thing in different jurisdictions only makes sense as a structural hedge.

## Detection

Using the MCP tools:
1. `/investigate` a name — note if the same person appears as officer of entities in two or more jurisdictions
2. Use `/trace-network` on each entity — compare officer lists, shareholder lists, and intermediary agents across the pair
3. Look for near-simultaneous incorporation: entities formed within days or weeks of each other with matching officers are likely coordinated
4. Check for name similarity: search for the distinctive word in an entity name (e.g., "Westfield") across all datasets — mirrors often share a root name with different suffixes or jurisdiction-specific legal forms (Ltd, SA, GmbH, LLC)
5. Investigate the intermediary: if the same law firm or registered agent formed both entities, that confirms coordinated creation and likely common beneficial ownership

## Examples

To be populated through investigations.
