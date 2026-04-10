# The Temporal Cluster

STRUCTURE: A burst of entity formations within a compressed time window — days, weeks, or a few months — by the same beneficial owner, intermediary, or network. The timing correlates with external events: pending regulation, political transition, asset flight from a crisis, or anticipated sanctions.
JURISDICTIONS: Depends on the triggering event — Russian-linked entities in BVI/Cyprus/Seychelles ahead of sanctions waves (2014, 2022); Chinese-linked entities in BVI/Samoa after capital control tightening; Latin American formations in Panama/BVI coinciding with political instability or regime change
INDICATORS: 5+ entities formed through the same intermediary within a 30-day window; formation dates clustering around known regulatory or geopolitical events; entities with no subsequent activity (dormant shells created in advance for future use)
RISK LEVEL: MEDIUM-HIGH
STATUS: ESTABLISHED
OBSERVED IN: Panama Papers, Pandora Papers, FinCEN Files

## Mechanism

Entity formation takes time — selecting jurisdictions, engaging intermediaries, preparing documentation, appointing nominees. When a cluster of entities appears within a short window, it signals urgency and advance planning. The temporal pattern reveals intent that the structural pattern alone may not.

Common triggers:

**Pre-sanctions positioning**: When sanctions are anticipated (often weeks or months before formal announcement, as geopolitical signals are read by advisors and intermediaries), beneficial owners rapidly create new entities in jurisdictions outside the likely sanctions regime. These entities receive transferred assets before sanctions freeze the original holding structures.

**Capital flight**: Political or economic instability (currency devaluation, regime change, civil unrest) triggers rapid formation of offshore entities to move assets out of reach. The formation burst precedes or coincides with the crisis.

**Regulatory front-running**: When new transparency or reporting requirements are announced with an implementation deadline (e.g., EU Anti-Money Laundering Directives, US Corporate Transparency Act), entities are formed in bulk before the new rules take effect, grandfathering them under the old regime or establishing structures designed to circumvent the new one.

**Bulk shell creation**: Intermediaries sometimes create entities in bulk speculatively — forming dozens of "shelf companies" to be sold to clients later. These appear as formation bursts with no identifiable beneficial owner at incorporation time; the owner appears only when the shelf company is activated (a change of officers or shareholders months or years later).

The temporal cluster is a meta-pattern: the entities formed during the burst may individually deploy other patterns (matryoshka, starburst, mirror). The timing is what ties them together as a coordinated action rather than unrelated formations.

## Detection

Using the MCP tools:
1. `/investigate` a name or entity — note the incorporation dates of all connected entities
2. Sort connected entities by formation date — look for clusters (3+ entities within 30 days, 5+ within 90 days)
3. When a cluster appears, use `/trace-network` on each entity in the cluster to determine whether they share intermediaries, nominees, or jurisdictions — shared infrastructure confirms coordinated formation
4. Cross-reference the cluster's date range against external event timelines: sanctions announcements, regulatory implementation dates, election cycles, currency crises, FATF greylist/blacklist updates
5. Use `/find-patterns` across the cluster to determine the structural pattern deployed — a temporal cluster of matryoshka chains has different implications than a temporal cluster of dormant single-entity shells
6. Check for dormancy: entities formed in a burst but showing no subsequent activity (no officer changes, no address changes) may be pre-positioned shells awaiting activation — monitor for future changes

## Examples

To be populated through investigations.
