# Find Patterns

Analyse a set of search results from both ICIJ and OpenSanctions to
identify structural patterns in offshore arrangements — shared
jurisdictions, common intermediaries, repeated structures, temporal
clustering, network topology, and sanctions exposure.

**Before running this skill**, load `patterns/INDEX.md` from the project
root. Cross-reference all findings against the known pattern library.
When a known pattern is matched, name it and cite the pattern file.
When a NEW pattern is identified that is not in the library, propose
adding it with a PROPOSED status.

## Usage

`/find-patterns <name>` — analyse patterns around a single entity
`/find-patterns <name1>, <name2>, ...` — analyse patterns across multiple names
`/find-patterns --jurisdiction BVI` — analyse patterns within a jurisdiction

## Procedure

### Step 1: Data gathering

1. Use `icij_search` (or `icij_batch_search` for multiple names) to
   find all matches. For each match with score > 40, use `icij_entity`
   and `icij_extend` with `["country_codes", "name", "note", "sourceID"]`.

2. Use `sanctions_search` (or `sanctions_batch_match` for multiple names)
   to find sanctions/PEP matches for the same names.

### Step 2: Structural analysis

Analyse the ICIJ results for:

**Jurisdictional patterns**: Which jurisdictions appear most? Is there
multi-jurisdiction layering? Do jurisdictions correlate with secrecy
rankings?

**Intermediary patterns**: Do multiple entities share the same
intermediary? Is it a known enabler? Same intermediary across
investigations?

**Officer patterns**: Same officers across multiple entities? Nominee
directors (one name on dozens of entities)? Family connections?

**Temporal patterns**: Entities created in clusters? Correlating with
sanctions announcements, elections, regulatory changes?

**Structural patterns**: Shell company chains (Matryoshka), hub-and-spoke
(Starburst), parallel entities (Mirror), shared formation agent
(Intermediary Cluster), professional nominees (Nominee Shield),
jurisdiction gap exploitation (Regulatory Arbitrage Chain), formation
bursts (Temporal Cluster).

### Step 3: Sanctions overlay

For each entity or officer identified in Step 2, check sanctions exposure:

1. Use `sanctions_match` on key names found in the ICIJ network
2. For sanctioned entities, use `sanctions_provenance` to determine
   WHICH sanctions list and WHEN they were listed
3. Check for the **Sanctions Evasion Structure** pattern: ICIJ entities
   connected to sanctioned persons through intermediary layers
4. Check for the **PEP Opacity Layer** pattern: ICIJ entities with
   officers matching PEP entries in OpenSanctions

### Step 4: Report

```
## Pattern analysis: [name(s) or jurisdiction]

### Data summary
- ICIJ entities examined: [N]
- OpenSanctions matches: [N]
- Jurisdictions: [list with counts]
- Investigations: [which leaks]
- Intermediaries: [list with counts]

### Patterns identified

#### [Pattern name] (from patterns/INDEX.md)
- Evidence: [which entities/connections demonstrate this]
- Significance: [what this pattern typically indicates]
- Confidence: HIGH/MEDIUM/LOW

### Sanctions overlay

| Entity/Officer | ICIJ role | Sanctioned | Lists | Listed since |
|---------------|-----------|-----------|-------|-------------|
| ... | Officer of [entity] | Yes | OFAC SDN | 2022-03-15 |

[Flag Sanctions Evasion Structure or PEP Opacity Layer if identified]

### Red flags
[Specific indicators warranting further investigation]

### New patterns
[Any structural arrangement not in the current library — propose
with PROPOSED status for addition to patterns/INDEX.md]

### Limitations
[What the data does NOT show]
```

## Notes

- The sanctions overlay is what distinguishes this from a pure ICIJ
  analysis — it connects offshore structures to enforcement reality
- A structure that matches a known pattern AND has sanctioned nodes
  is the highest-risk finding
- Propose new patterns when a structure is identified that doesn't
  match any existing pattern in the library
