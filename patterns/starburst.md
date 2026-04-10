# The Starburst

STRUCTURE: Single beneficial owner (or small ownership group) connected to dozens of entities through nominee directors, nominee shareholders, or intermediary holding companies. Hub-and-spoke topology where the hub is deliberately obscured.
JURISDICTIONS: Hub often in a secrecy jurisdiction (BVI, Panama, Samoa); spokes distributed across jurisdictions matching specific operational needs — EU entities for market access, Caribbean entities for tax neutrality, Pacific islands for anonymity
INDICATORS: One person or entity appearing as officer/shareholder across 10+ entities; nominee directors shared across the spoke entities; entities with no visible commercial relationship sharing a common node
RISK LEVEL: HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Offshore Leaks, Pandora Papers

## Mechanism

The starburst serves a different purpose than the matryoshka. Where the matryoshka hides ownership through depth (layers), the starburst hides the scope of a single owner's holdings through breadth. A beneficial owner who controls 30 entities through nominees appears in no corporate registry. Each entity looks independent. The true scale of the network — and therefore the true scale of the owner's wealth, influence, or exposure — is invisible without mapping the full topology.

The spoke entities typically serve distinct functions: one holds real estate, another receives consulting fees, a third holds intellectual property, a fourth invoices intercompany services. By distributing assets and income streams across many entities, the beneficial owner achieves tax optimization (routing income to low-tax spokes), asset protection (no single entity holds enough to be worth pursuing), and operational compartmentalization (a legal action against one spoke does not reveal or threaten the others).

The hub itself may be a natural person, a trust, or a foundation — often in a jurisdiction that does not require disclosure of trust settlors or foundation beneficiaries.

## Detection

Using the MCP tools:
1. `/investigate` a name — if results return many entity connections across different jurisdictions, note the count and jurisdiction spread
2. For each connected entity, use `/trace-network` to identify its officers and shareholders — look for recurring names (especially nominee names like "Dorado Nominees Ltd" or individual names appearing in professional nominee capacity)
3. Map the topology: if entity A, entity B, entity C all share officer X, and officer X is a known nominee service, investigate who the nominee acts for — the hidden hub
4. Count the spokes — a single natural person or nominee service connected to 15+ entities across 3+ jurisdictions is the starburst signature
5. Use `/find-patterns` to check whether spoke entities share registered addresses, incorporation dates, or intermediary agents, which would confirm coordinated formation

## Examples

To be populated through investigations.
