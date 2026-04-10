# Trace Network

Given a name, find it in both databases and walk the network outward,
mapping offshore structures and flagging sanctioned nodes.

**Before running this skill**, load `patterns/INDEX.md` from the project
root. After mapping the network, identify which known patterns the
topology matches and note any new structural arrangements.

## Usage

`/trace-network <name>` — map the offshore network around a name
`/trace-network <name> --depth 2` — walk 2 hops instead of 1

## Procedure

1. Use `icij_investigate` with `max_results: 1` to get the top match
   and its ICIJ network expansion.

2. From the ICIJ results, collect all connected node IDs. For each,
   use `icij_entity` to get details.

3. **Sanctions overlay**: For each entity/officer name found in the
   ICIJ network, run `sanctions_match` to check sanctions exposure.
   If a node is sanctioned, use `sanctions_entity` (nested=true) to
   pull its full sanctions profile and connected entities.

4. If `--depth 2`, expand one more hop outward from ICIJ nodes (cap
   at 20 total lookups).

5. Produce a network map:

```
## Network trace: [name]

### Seed entity
[Name, type, jurisdiction, investigation]
[Sanctions status: sanctioned/clear]

### Network map

| Name | Type | Relationship | Jurisdiction | ⚠️ Sanctioned |
|------|------|-------------|-------------|---------------|
| ... | Officer | officer_of | BVI | Yes — OFAC SDN |
| ... | Intermediary | intermediary_of | Panama | No |
| ... | Entity | connected | Seychelles | Yes — EU list |

### Sanctioned nodes detail

[For each sanctioned node, show which lists, topics, and the
sanctions entity's own connections from OpenSanctions]

### Pattern matches

[Cross-reference the network topology against patterns/INDEX.md:
Matryoshka (jurisdiction chains), Starburst (hub-and-spoke),
Nominee Shield (professional nominees), etc.]

### Network summary

- Total nodes: [N]
- Sanctioned nodes: [N]
- Jurisdictions: [list]
- Key officers: [names connected to multiple entities]
- Intermediaries: [law firms, registered agents]
- Pattern: [structural description]
- Risk level: [based on sanctions exposure + pattern type]
```

## Notes

- Sanctioned nodes in an offshore network are the highest-priority
  finding — they indicate potential sanctions evasion structures
- The Sanctions Evasion Structure pattern specifically looks for
  ICIJ entities connected to sanctioned persons through intermediaries
- For deep analysis, download the ICIJ bulk CSV or Neo4j packages
