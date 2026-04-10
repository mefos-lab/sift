# Investigate

Search both ICIJ Offshore Leaks and OpenSanctions for a name and produce
a unified intelligence summary.

**Before running this skill**, load `patterns/INDEX.md` from the project
root. After producing the summary, cross-reference the entity's
structure against known patterns and note any matches.

## Usage

`/investigate <name>` — person, company, or address
`/investigate <name> --investigation panama-papers` — limit ICIJ to one dataset

## Procedure

1. **ICIJ search**: Use `icij_search` with the provided name. If an
   investigation is specified, pass it as the `investigation` parameter.

2. For each of the top 5 ICIJ matches (or fewer if less are returned):
   - Note the entity name, type, score, and ID
   - Use `icij_entity` to get full details (country codes, schema type)

3. Use `icij_extend` on all matched IDs with properties:
   `["country_codes", "name", "note", "sourceID"]`

4. **Sanctions check**: Use `sanctions_match` with the same name.
   Include any known properties (birth date, nationality) if the user
   provided them. Check the match results for sanctions designations,
   PEP status, and enforcement records.

5. If any ICIJ entity's officers or connected names appear in the
   sanctions results, flag this connection prominently.

6. Produce a structured summary:

```
## Intelligence report: [name]

### ⚠️ Sanctions exposure [if any matches found]

| Name | Score | Lists | Topics |
|------|-------|-------|--------|
| ... | 0.92 | OFAC SDN, EU sanctions | sanction |

[If sanctioned, this section appears FIRST. If no sanctions exposure,
note "No matches in OpenSanctions (320+ lists checked)."]

### Offshore holdings (ICIJ)

| # | Name | Type | Score | Jurisdiction | Investigation |
|---|------|------|-------|-------------|---------------|
| 1 | ... | Entity/Officer/Intermediary | ... | ... | ... |

### Details

[For each high-scoring match (score > 50), summarise what is known:
entity type, jurisdiction, connected names if available, source dataset]

### Pattern matches

[Cross-reference against patterns/INDEX.md. Name any matching patterns.]

### Assessment

[Unified assessment: offshore structure + sanctions exposure + pattern
matches. What does the combined picture suggest?]
```

7. If no matches are found in either database, state that clearly.

## Notes

- ICIJ: 810,000+ entities from 5 investigations (no auth required)
- OpenSanctions: 320+ sanctions/PEP lists (requires API key)
- Sanctions scores above 0.9 are high confidence; 0.7-0.9 investigate
- ICIJ scores above 80 are strong; 50-80 worth examining
- A name appearing in BOTH databases is a significant finding
