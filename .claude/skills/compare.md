# Compare

Search two or more names in both ICIJ and OpenSanctions, identify shared
connections, and flag sanctions exposure.

## Usage

`/compare <name1>, <name2>` — find connections between two names
`/compare <name1>, <name2>, <name3>` — find connections among three

## Procedure

1. Split input on commas, trim whitespace.

2. **ICIJ**: Use `icij_batch_search` with all names. For each name,
   collect matches with score > 40. Use `icij_extend` on all matched
   IDs with `["country_codes", "name", "note", "sourceID"]`.

3. **OpenSanctions**: Use `sanctions_batch_match` with all names.
   Note sanctions status and scores.

4. For each pair, check for:
   - **Shared ICIJ entities**: Both names as officers of the same entity
   - **Shared intermediaries**: Same law firm or registered agent
   - **Shared jurisdictions**: Entities in the same jurisdictions
   - **Shared addresses**: Entities at the same registered address
   - **Sanctions link**: One name sanctioned + connected to the other via ICIJ

5. Produce a comparison report:

```
## Comparison: [name1] vs [name2]

### Sanctions status

| Name | Sanctioned | Score | Lists |
|------|-----------|-------|-------|
| [name1] | Yes/No | ... | ... |
| [name2] | Yes/No | ... | ... |

[If one is sanctioned and connected to the other through ICIJ,
flag this prominently as a CRITICAL finding.]

### ICIJ matches

[name1]: [N] matches — [top jurisdictions]
[name2]: [N] matches — [top jurisdictions]

### Connections found

| Type | Detail | Strength |
|------|--------|----------|
| Shared entity | Both officers of [entity] in [jurisdiction] | STRONG |
| Shared intermediary | Both used [intermediary] | MEDIUM |
| Sanctions link | [name1] sanctioned, connected to [name2] via [entity] | CRITICAL |

### Assessment

[What do the connections and sanctions exposure suggest together?]
```
