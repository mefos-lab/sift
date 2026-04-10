# Exposure Report

Batch-screen a list of names against the ICIJ Offshore Leaks Database
and produce a due-diligence summary showing who appears and who doesn't.

## Usage

`/exposure-report <name1>, <name2>, <name3>, ...` — screen a list of names
`/exposure-report --file <path>` — screen names from a file (one per line)

## Procedure

1. Parse names from the input (comma-separated) or file (newline-separated).
   Trim whitespace.

2. Process in batches of 25 using `icij_batch_search`.

3. For each name, classify the result:
   - **HIT** (score >= 70): Strong match — likely the same person/entity
   - **POSSIBLE** (score 40-69): Worth examining — may be same or different
   - **CLEAR** (score < 40 or no results): No strong match found

4. For each HIT, use `icij_entity` to get jurisdiction and type details.

5. Produce an exposure report:

```
## ICIJ Exposure Report

Date: [YYYY-MM-DD]
Names screened: [N]
Database: ICIJ Offshore Leaks (Panama Papers, Paradise Papers,
  Pandora Papers, Bahamas Leaks, Offshore Leaks)

### Summary

| Status | Count |
|--------|-------|
| HIT | [N] |
| POSSIBLE | [N] |
| CLEAR | [N] |

### Hits (score >= 70)

| Name searched | Match | Type | Score | Jurisdiction | Investigation |
|--------------|-------|------|-------|-------------|---------------|
| ... | ... | ... | ... | ... | ... |

### Possible matches (score 40-69)

| Name searched | Match | Type | Score | Jurisdiction | Investigation |
|--------------|-------|------|-------|-------------|---------------|
| ... | ... | ... | ... | ... | ... |

### Clear (no strong match)

[List of names with no results or only low-score matches]

### Caveats

- This report screens against 5 specific data leaks. Many offshore
  jurisdictions and service providers are not represented.
- A CLEAR result means the name was not found in these specific
  leaks, not that the person has no offshore holdings.
- HIT means a name match, not confirmed identity. Common names may
  produce false positives. Verify against additional sources.
- The ICIJ database does not constitute a sanctions list. Appearing
  in it does not indicate illegality.
```

## Notes

- For lists longer than 25, the skill batches automatically.
- Processing time scales linearly with list size — expect ~2 seconds
  per batch of 25.
- For high-stakes due diligence, supplement with OpenSanctions,
  corporate registries, and beneficial ownership databases.
- Consider searching name variants (maiden names, transliterations,
  company names with and without jurisdiction suffixes).
