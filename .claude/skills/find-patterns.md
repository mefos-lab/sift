# Find Patterns

Analyse a set of ICIJ search results to identify structural patterns
in offshore arrangements — shared jurisdictions, common intermediaries,
repeated structures, temporal clustering, and network topology.

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

### For a single name or list of names:

1. Use `icij_search` (or `icij_batch_search` for multiple names) to
   find all matches.

2. For each match with score > 40, use `icij_entity` to get details
   including jurisdiction and type.

3. Use `icij_extend` on all matched IDs with properties:
   `["country_codes", "name", "note", "sourceID"]`

4. Analyse the results for the following pattern types:

**Jurisdictional patterns:**
- Which jurisdictions appear most frequently?
- Is there a multi-jurisdiction layering structure (e.g., entity in BVI,
  intermediary in Panama, address in Geneva)?
- Do the jurisdictions correlate with known secrecy or tax haven rankings?

**Intermediary patterns:**
- Do multiple entities share the same intermediary (law firm, registered agent)?
- Is the intermediary a known enabler (Mossack Fonseca, Asiaciti Trust, etc.)?
- Does the same intermediary appear across different investigations?

**Officer patterns:**
- Do the same officers (directors, shareholders, beneficial owners) appear
  across multiple entities?
- Are nominee directors used (the same name appearing as officer for
  dozens of entities)?
- Are there family connections (shared surnames)?

**Temporal patterns:**
- Were entities created in clusters (same month/year)?
- Do creation dates correlate with known events (sanctions announcements,
  elections, regulatory changes)?
- Is there a pattern of entities being created shortly before or after
  significant political or economic events?

**Structural patterns:**
- Shell company chains (entity owns entity owns entity)
- Circular ownership (A owns B owns C owns A)
- Star topology (one officer connected to many entities)
- Layered opacity (each hop adds a jurisdiction and an intermediary)

### For a jurisdiction analysis:

1. Use `icij_suggest` with common entity name patterns for the
   jurisdiction (e.g., "Limited" for BVI, "S.A." for Panama).

2. Use `icij_search` filtered by the jurisdiction where possible.

3. Analyse the structural patterns described above across the
   jurisdiction's entities.

5. Produce a pattern report:

```
## Pattern analysis: [name(s) or jurisdiction]

### Data summary
- Entities examined: [N]
- Jurisdictions: [list with counts]
- Investigations: [which leaks these appeared in]
- Intermediaries: [list with counts]

### Patterns identified

#### [Pattern type]: [specific finding]
- Evidence: [which entities/connections demonstrate this]
- Significance: [what this pattern typically indicates]
- Confidence: [HIGH/MEDIUM/LOW based on data strength]

### Red flags
[List specific indicators that warrant further investigation:
- Nominee structures
- Jurisdictional layering
- Temporal clustering around events
- Shared intermediaries across unrelated entities
- Connections to sanctioned jurisdictions or persons]

### Limitations
[What the data does NOT show — beneficial ownership may be hidden
behind nominees, the database only covers 5 specific leaks, absence
of evidence is not evidence of absence]
```

## Pattern vocabulary

For reference, common offshore structure types:

- **Shell company**: Entity with no operations, used to hold assets or
  route payments
- **Nominee structure**: Directors/shareholders who act on behalf of the
  true beneficial owner
- **Layered structure**: Multiple entities in different jurisdictions,
  each owning the next, creating opacity through jurisdictional complexity
- **Mirror structure**: Parallel entities in different jurisdictions with
  the same officers, providing redundancy
- **Starburst**: One central figure connected to many entities, suggesting
  a portfolio of offshore vehicles
- **Pipeline**: Linear chain of entities routing funds through
  progressively more opaque jurisdictions

## Notes

- The ICIJ database is not a sanctions list. Appearing in it does not
  indicate illegality — many offshore structures are legal.
- The value of pattern analysis is identifying structures that COULD
  facilitate illicit activity, not proving that they do.
- For investigative work, patterns identified here should be
  cross-referenced against sanctions lists (OpenSanctions), corporate
  registries, and beneficial ownership databases.
- The database covers 5 specific leaks. There are many offshore
  providers and jurisdictions not represented.
