# Jurisdiction Check

Search a name in the ICIJ database and group results by jurisdiction,
revealing where someone structures their offshore presence.

## Usage

`/jurisdiction-check <name>` — map jurisdictional footprint

## Procedure

1. Use `icij_search` with the provided name.

2. For all matches with score > 40, use `icij_extend` with
   `["country_codes", "name", "sourceID"]`.

3. Group results by jurisdiction (country code).

4. Produce a jurisdictional profile:

```
## Jurisdictional profile: [name]

### Matches: [N] across [N] jurisdictions

| Jurisdiction | Entities | Types | Investigations |
|-------------|----------|-------|----------------|
| BVI | 3 | Entity (2), Officer (1) | Panama Papers |
| Panama | 2 | Entity, Intermediary | Panama Papers, Pandora Papers |

### Jurisdictional risk profile

[For each jurisdiction, note its characteristics:
- Secrecy ranking (Financial Secrecy Index if known)
- Whether it requires beneficial ownership disclosure
- Common uses (tax deferral, asset protection, trade routing)]

### Assessment

[What does the jurisdictional pattern suggest? Multi-jurisdiction
layering? Concentration in high-secrecy jurisdictions? Use of
jurisdictions known for specific purposes?]
```
