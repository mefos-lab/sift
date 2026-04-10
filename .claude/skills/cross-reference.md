# Cross-Reference

The master investigative skill. Searches all available databases,
produces a unified intelligence report combining offshore holdings,
sanctions exposure, pattern matches, and risk assessment.

**Before running this skill**, load `patterns/INDEX.md` from the project root.

## Usage

`/cross-reference <name>` — full investigation across all sources

## Procedure

1. **ICIJ**: Use `icij_search` with the name. For top matches
   (score > 40), use `icij_entity` and `icij_extend` to get full
   details including jurisdictions and connected entities.

2. **OpenSanctions**: Use `sanctions_match` with the name (schema
   inferred from context — Person for individuals, Company for firms).
   For matches above 0.5, use `sanctions_entity` (nested=true) for
   full profile.

3. **Cross-link**: Check whether any ICIJ entity names, officers, or
   intermediaries match any OpenSanctions entries. This is the key
   step — it connects the offshore structure to the sanctions universe.

4. **Pattern analysis**: Cross-reference the combined findings against
   `patterns/INDEX.md`. Look specifically for:
   - Sanctions Evasion Structure (ICIJ entity linked to sanctioned person)
   - PEP Opacity Layer (ICIJ entity with PEP-matching officers)
   - Any structural pattern (Matryoshka, Starburst, etc.) combined
     with sanctions exposure

5. **Jurisdictional profile**: Group all entities by jurisdiction.
   Note which jurisdictions have both offshore and sanctions exposure.

6. Produce a unified report:

```
## Cross-reference report: [name]

Date: [YYYY-MM-DD]

### Executive summary

[2-3 sentences: who is this entity, what did we find, what is the
risk level? Lead with the most significant finding.]

### ⚠️ Sanctions exposure

[Sanctions matches, or "No sanctions exposure found"]

| Match | Score | Lists | Topics | Since |
|-------|-------|-------|--------|-------|

### Offshore holdings (ICIJ)

| Entity | Type | Jurisdiction | Investigation | Connected to |
|--------|------|-------------|---------------|-------------|

### Cross-links

[Entities or persons appearing in BOTH databases. This section is
the investigative core — it connects structure to enforcement.]

| Name | ICIJ role | Sanctions status | Lists |
|------|----------|-----------------|-------|

### Pattern matches

[Named patterns from the library that this structure matches]

### Jurisdictional profile

| Jurisdiction | ICIJ entities | Sanctions exposure | Risk |
|-------------|--------------|-------------------|------|

### Risk assessment

| Factor | Finding | Risk |
|--------|---------|------|
| Sanctions | [sanctioned/clear] | [HIGH/LOW] |
| Offshore structure | [pattern type or none] | [HIGH/MEDIUM/LOW] |
| Jurisdictions | [high-secrecy count] | [HIGH/MEDIUM/LOW] |
| Cross-links | [N entities in both DBs] | [CRITICAL/HIGH/LOW] |
| **Overall** | | **[CRITICAL/HIGH/MEDIUM/LOW]** |

### Recommended next steps

[Based on risk level:
- CRITICAL: Immediate review, legal consultation
- HIGH: Deep investigation, gather additional identifying info
- MEDIUM: Monitor periodically, verify identities
- LOW: Document for records, re-screen annually]
```

## Notes

- This is the most comprehensive skill — it chains all available tools
- Run time scales with the number of matches found (typically 30-60s)
- A CRITICAL finding (same entity in both ICIJ and OpenSanctions)
  is rare and significant — it means a sanctioned person or entity
  has documented offshore holdings
- For ongoing tracking after a cross-reference, use `/monitor`
