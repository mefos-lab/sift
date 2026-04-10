# Investigate

Search the ICIJ Offshore Leaks Database for a name and produce a
structured intelligence summary.

**Before running this skill**, load `patterns/INDEX.md` from the project
root. After producing the summary, cross-reference the entity's
structure against known patterns and note any matches.

## Usage

`/investigate <name>` — person, company, or address
`/investigate <name> --investigation panama-papers` — limit to one dataset

## Procedure

1. Use `icij_search` with the provided name. If an investigation is
   specified, pass it as the `investigation` parameter.

2. For each of the top 5 matches (or fewer if less are returned):
   - Note the entity name, type, score, and ID
   - Use `icij_entity` to get full details (country codes, schema type)

3. Use `icij_extend` on all matched IDs with properties:
   `["country_codes", "name", "note", "sourceID"]`

4. Produce a structured summary:

```
## ICIJ Offshore Leaks: [name]

### Matches found: [N]

| # | Name | Type | Score | Jurisdiction | Investigation |
|---|------|------|-------|-------------|---------------|
| 1 | ... | Entity/Officer/Intermediary | ... | ... | ... |

### Details

[For each high-scoring match (score > 50), summarise what is known:
entity type, jurisdiction, connected names if available, source dataset]

### Assessment

[Brief assessment: how strong is the match? Is this likely the same
person/entity? What does the offshore structure suggest?]
```

5. If no matches are found, state that clearly. Absence from the
   database does not prove absence of offshore activity — it means
   the name does not appear in the five specific leaks ICIJ has
   published.

## Notes

- The database contains 810,000+ entities from 5 investigations
- Scores above 80 are strong matches; 50-80 are worth examining;
  below 50 are likely false positives
- The REST node API may be unavailable — the tools fall back to
  the extend API automatically
- Names in the database are often in ALL CAPS
- Search is fuzzy — try variants (full name, surname only, company
  name with and without jurisdiction suffix)
