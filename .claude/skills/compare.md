# Compare

Search two or more names in the ICIJ database and identify shared
connections — entities, intermediaries, addresses, or jurisdictions.

## Usage

`/compare <name1>, <name2>` — find connections between two names
`/compare <name1>, <name2>, <name3>` — find connections among three

## Procedure

1. Split the input on commas to get individual names. Trim whitespace.

2. Use `icij_batch_search` with all names (max 25).

3. For each name, collect all matches with score > 40. Use `icij_extend`
   on all matched IDs with properties:
   `["country_codes", "name", "note", "sourceID"]`

4. For each pair of names, check for:
   - **Shared entities**: Do both names appear as officers of the same entity?
   - **Shared intermediaries**: Were both names' entities set up by the
     same law firm or registered agent?
   - **Shared jurisdictions**: Do both names have entities in the same
     jurisdictions? (Weaker signal — many people use the same jurisdictions)
   - **Shared addresses**: Do any entities share a registered address?

5. Produce a comparison report:

```
## ICIJ comparison: [name1] vs [name2]

### [Name 1]: [N] matches
[Top matches with type, jurisdiction]

### [Name 2]: [N] matches
[Top matches with type, jurisdiction]

### Connections found

| Connection type | Detail |
|----------------|--------|
| Shared entity | Both are officers of [entity name] in [jurisdiction] |
| Shared intermediary | Both used [intermediary] for entity formation |
| Shared jurisdiction | Both have entities in [jurisdiction] |
| Shared address | Entities registered at [address] |

### Connection strength
- STRONG: shared entity or shared address (direct structural link)
- MEDIUM: shared intermediary (suggests same professional network)
- WEAK: shared jurisdiction only (may be coincidental)

### No connection found
[If no connections are identified, state this clearly. Absence of
connection in the ICIJ database does not prove absence of connection —
only that these 5 specific leaks do not document one.]
```

## Notes

- This comparison operates within the ICIJ database only. For a
  comprehensive connection analysis, cross-reference with corporate
  registries, court filings, and sanctions databases.
- Common intermediaries (Mossack Fonseca handled 200,000+ entities) —
  a shared intermediary is a weaker signal than a shared entity.
- The database may have multiple entries for the same person under
  different name spellings. Try variants if initial search fails.
