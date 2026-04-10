# ICIJ MCP — Offshore Leaks Investigation Server

MCP server wrapping the ICIJ Offshore Leaks Database API. Provides
search, entity lookup, network traversal, and pattern detection across
810,000+ offshore entities from 5 major leak investigations.

## Structure

- `icij_mcp/` — MCP server and API client
- `.claude/skills/` — Investigative skills (slash commands)
- `patterns/` — Documented offshore structure patterns (accumulated over investigations)
- `investigations/` — Saved investigation reports (optional — for persistent research)

## Skills

- `/investigate <name>` — Search and summarise everything on a name
- `/trace-network <name>` — Walk the graph outward from a name
- `/find-patterns <name(s)>` — Analyse structural patterns in offshore arrangements
- `/compare <name1>, <name2>` — Find shared connections between names
- `/exposure-report <names>` — Batch due-diligence screening
- `/jurisdiction-check <name>` — Map jurisdictional footprint

## Pattern Library

The `patterns/` directory accumulates documented offshore structure
patterns over time. Each pattern is a named, reusable template
describing a specific type of offshore arrangement.

### Pattern format

Each pattern file in `patterns/` follows this structure:

```markdown
# [Pattern Name]

STRUCTURE: [1-3 sentence description of the arrangement]
JURISDICTIONS: [typical jurisdictions involved]
INDICATORS: [what signals this pattern in ICIJ data]
RISK LEVEL: HIGH / MEDIUM / LOW
OBSERVED IN: [list of investigations where this was found]

## Mechanism

[How the structure works — what it achieves for the beneficial owner,
how opacity is created, how funds or assets flow]

## Detection

[How to identify this pattern using the MCP tools — what to search
for, what entity relationships to look for, what jurisdiction
combinations signal it]

## Examples

[Specific documented instances from ICIJ data, with entity names
and node IDs where available]
```

### Using patterns during investigation

All investigative skills (`/investigate`, `/find-patterns`,
`/trace-network`) should:

1. Load `patterns/INDEX.md` before producing output
2. Cross-reference findings against known patterns
3. When a known pattern is identified, name it and cite the pattern file
4. When a NEW pattern is identified, propose adding it to the library

### Pattern lifecycle

- **PROPOSED**: Identified in a single investigation, not yet confirmed
- **CONFIRMED**: Observed in 2+ independent investigations
- **ESTABLISHED**: Observed across multiple leak datasets or jurisdictions

Patterns are never deleted — they may be marked DEPRECATED if
subsequent evidence shows they were misidentified.

## Conventions

- All investigation output uses professional, factual language
- Appearing in the ICIJ database does not indicate illegality
- Absence from the database does not indicate absence of offshore activity
- The database covers 5 specific leaks, not the full offshore world
- Name matching is fuzzy — verify identities through additional sources
- Node IDs are stable identifiers within the ICIJ database
