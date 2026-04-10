# Jurisdiction Check

Search a name in both databases and map its jurisdictional footprint,
cross-referencing offshore holdings with sanctions exposure per jurisdiction.

## Usage

`/jurisdiction-check <name>` — map jurisdictional footprint

## Procedure

1. Use `icij_search` with the provided name. For all matches with
   score > 40, use `icij_extend` with `["country_codes", "name", "sourceID"]`.

2. Group ICIJ results by jurisdiction (country code).

3. Use `sanctions_search` with the same name, filtering by each
   jurisdiction found in step 2 using the `countries` parameter.
   This reveals whether the name has sanctions exposure in the same
   jurisdictions where they have offshore holdings.

4. Produce a jurisdictional profile:

```
## Jurisdictional profile: [name]

### Matches: [N] ICIJ entities across [N] jurisdictions
### Sanctions exposure: [N] lists in [N] jurisdictions

| Jurisdiction | ICIJ entities | Types | Sanctions | Risk |
|-------------|--------------|-------|-----------|------|
| BVI | 3 | Entity (2), Officer (1) | OFAC SDN | HIGH |
| Panama | 2 | Entity, Intermediary | None | MEDIUM |

### Jurisdictional risk profile

[For each jurisdiction:
- Secrecy ranking (Financial Secrecy Index)
- Sanctions exposure in that jurisdiction
- Common uses (tax deferral, asset protection, trade routing)]

### Cross-reference findings

[Jurisdictions where BOTH offshore entities and sanctions exposure
exist are the highest-priority findings]

### Assessment

[What does the combined jurisdictional pattern suggest?]
```
