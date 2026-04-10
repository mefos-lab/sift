# Compliance Screen

Rigorous structured sanctions and PEP screening using all available
identifying properties. More thorough than `/exposure-report` — designed
for individual high-stakes compliance checks.

## Usage

`/compliance-screen <name>` — basic screen
`/compliance-screen <name> --dob 1970-05-15 --nationality RU` — with properties
`/compliance-screen <name> --id AB123456 --jurisdiction PA` — for companies

## Procedure

1. Use `sanctions_match` with the provided name and all available
   properties:
   - `birth_date` if provided (--dob)
   - `nationality` if provided (--nationality, ISO country code)
   - `id_number` if provided (--id, passport or ID number)
   - `jurisdiction` if provided (--jurisdiction, for companies)
   - `registration_number` if provided (--reg)
   - Set `threshold: 0.5` (lower than default to catch borderline matches)

2. For each match with score >= 0.5, use `sanctions_entity` to get
   full details including all datasets, properties, and nested
   relationships.

3. Use `sanctions_provenance` on top matches to determine exactly
   which dataset contributed which fact — critical for assessing
   whether the match is based on name alone or corroborated by
   multiple data points.

4. Also run `icij_search` to check for offshore holdings that may
   indicate a more complex financial structure.

5. Produce a compliance report:

```
## Compliance screening: [name]

### Subject details provided
- Name: [name]
- Date of birth: [if provided]
- Nationality: [if provided]
- ID number: [if provided]

### Risk assessment: [HIGH / MEDIUM / LOW / CLEAR]

- HIGH: Score >= 0.9, appears on active sanctions list
- MEDIUM: Score 0.7-0.9, or appears on PEP/watchlist
- LOW: Score 0.5-0.7, possible match requiring manual review
- CLEAR: No matches above threshold

### Sanctions matches

| Match | Score | Schema | Lists | Topics | Last changed |
|-------|-------|--------|-------|--------|-------------|
| ... | 0.95 | Person | OFAC SDN, EU | sanction | 2026-02-15 |

### Match provenance

[For each match: which datasets contributed which properties.
Was the match based on name only, or corroborated by DOB,
nationality, or ID number?]

### Offshore exposure (ICIJ)

[Any ICIJ matches — offshore entities, officer positions]

### Recommended next steps

- HIGH: Do not proceed without legal review. Document the match.
- MEDIUM: Escalate to compliance officer. Gather additional
  identifying information to confirm or rule out.
- LOW: Request additional documentation from subject. Re-screen
  with more properties.
- CLEAR: Document the screening for audit trail. Re-screen
  periodically using `/monitor`.
```

## Notes

- This is a point-in-time screen — sanctions lists change daily
- Always document the screening date and results for audit purposes
- Additional properties (DOB, nationality, ID) dramatically improve
  match precision — encourage gathering these before screening
- A CLEAR result means no match in OpenSanctions, not that the
  person is definitively not sanctioned — some lists may not be
  covered
