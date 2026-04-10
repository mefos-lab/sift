# Trace Network

Given a name, find it in the ICIJ database and walk the network outward
to map the full structure of connected entities, officers, intermediaries,
and addresses.

**Before running this skill**, load `patterns/INDEX.md` from the project
root. After mapping the network, identify which known patterns the
topology matches (Matryoshka, Starburst, Mirror, etc.) and note any
new structural arrangements not yet in the library.

## Usage

`/trace-network <name>` — map the offshore network around a name
`/trace-network <name> --depth 2` — walk 2 hops instead of 1

## Procedure

1. Use `icij_search` with the provided name.

2. Take the top match (highest score). Use `icij_investigate` with
   `max_results: 1` to get the full network expansion.

3. From the investigation result, identify all connected node IDs.
   For each connected node, use `icij_entity` to get its details.

4. If `--depth 2` is specified, repeat step 3 for the nodes found
   in step 3 — walking one more hop outward. Be judicious: only
   expand nodes that appear to be entities or officers (not addresses
   or generic intermediaries), and cap at 20 total lookups to avoid
   excessive API calls.

5. Produce a network map:

```
## Network trace: [name]

### Seed entity
[Name, type, jurisdiction, investigation]

### Direct connections (1 hop)

| Name | Type | Relationship | Jurisdiction |
|------|------|-------------|-------------|
| ... | Officer | officer_of | ... |
| ... | Intermediary | intermediary_of | ... |
| ... | Address | registered_address | ... |

### Extended connections (2 hops) [if depth 2]

| Name | Type | Connected via | Jurisdiction |
|------|------|--------------|-------------|
| ... | Entity | shares officer [X] with seed | ... |

### Network summary

- Total nodes: [N]
- Jurisdictions: [list]
- Key officers: [names that appear connected to multiple entities]
- Intermediaries: [law firms, registered agents]
- Pattern: [brief structural description — shell company chain,
  multi-jurisdiction layering, nominee structure, etc.]
```

## Notes

- Network traversal depends on what the ICIJ database exposes
  through the extend API. Not all relationships are available
  programmatically — the web interface at offshoreleaks.icij.org
  may show more connections.
- If the REST node endpoint is unavailable, connections will be
  limited to what the extend API returns.
- For deep network analysis, consider downloading the bulk CSV
  or Neo4j data packages from the ICIJ GitHub repo.
