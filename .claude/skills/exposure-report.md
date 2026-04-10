# Exposure Report

Batch-screen a list of names against BOTH the ICIJ Offshore Leaks Database
and OpenSanctions, producing a unified due-diligence summary.

**Before running this skill**, load `patterns/INDEX.md` from the project root.

## Usage

`/exposure-report <name1>, <name2>, <name3>, ...` — screen a list
`/exposure-report --file <path>` — screen names from a file (one per line)

## Procedure

1. Parse names from input (comma-separated) or file (newline-separated).

2. **Dual-source screening** — run in parallel:
   a. `icij_batch_search` with all names (batches of 25)
   b. `sanctions_batch_match` with all names (batches of 25)

3. For each name, classify:
   - **CRITICAL**: Appears in BOTH databases (offshore + sanctioned)
   - **SANCTIONS HIT** (score >= 0.7): Strong match in OpenSanctions
   - **OFFSHORE HIT** (score >= 70): Strong match in ICIJ
   - **POSSIBLE**: Moderate matches in either database
   - **CLEAR**: No strong matches in either database

4. For each CRITICAL or SANCTIONS HIT, use `sanctions_entity` to get
   full details (which lists, topics, datasets).

5. For each CRITICAL or OFFSHORE HIT, use `icij_entity` to get
   jurisdiction and type details.

6. Produce an exposure report:

```
## Exposure Report

Date: [YYYY-MM-DD]
Names screened: [N]
Databases: ICIJ Offshore Leaks + OpenSanctions (320+ lists)

### Summary

| Status | Count |
|--------|-------|
| CRITICAL (both databases) | [N] |
| SANCTIONS HIT | [N] |
| OFFSHORE HIT | [N] |
| POSSIBLE | [N] |
| CLEAR | [N] |

### ⚠️ Critical (offshore + sanctioned)

| Name | ICIJ match | Jurisdiction | Sanctions lists | Score |
|------|-----------|-------------|-----------------|-------|

### Sanctions hits

| Name | Match | Score | Lists | Topics |
|------|-------|-------|-------|--------|

### Offshore hits

| Name | Match | Score | Type | Jurisdiction | Investigation |
|------|-------|-------|------|-------------|---------------|

### Clear

[List of names with no strong matches in either database]

### Caveats

[Standard caveats about database coverage, false positives, etc.]
```

## Notes

- CRITICAL status (both databases) warrants immediate investigation
- Processing scales linearly — ~2 seconds per batch of 25
- For CRITICAL findings, consider running `/investigate` on each
