# Sift — Investigative Journalism MCP Server

MCP server for financial crime investigation and investigative
journalism. Cross-references 9 data sources: ICIJ Offshore Leaks,
OpenSanctions, GLEIF LEI Registry, SEC EDGAR, UK Companies House,
CourtListener (US court records), OCCRP Aleph (investigative datasets),
UK Land Registry (property transactions), and Wikidata (entity
enrichment and PEP identification).

## Structure

- `sift/` — MCP server, API clients, traversal engine, visualizer
- `.claude/skills/` — Investigation skill (slash command)
- `patterns/` — Documented offshore structure patterns (accumulated over investigations)
- `visualizations/` — D3 HTML template for interactive investigation visualizations
- `investigations/` — Generated investigation reports and visualizations

## Data Sources

| Source | Coverage | Auth |
|--------|----------|------|
| ICIJ Offshore Leaks | 810K+ entities from 5 leak investigations | None |
| OpenSanctions | 320+ sanctions lists, PEP databases, enforcement records | API key |
| GLEIF LEI Registry | Global corporate identifiers + ownership chains | None |
| SEC EDGAR | US public company filings, 10-K/10-Q/8-K | User-Agent only |
| UK Companies House | UK company records, officers, PSC (beneficial ownership) | Free API key |
| CourtListener | US federal court records (PACER/RECAP) | Free token |
| OCCRP Aleph | Investigative datasets, company records, leaked documents | Optional API key |
| UK Land Registry | Property transaction prices and addresses (England/Wales) | None |
| Wikidata | Structured data on people, companies, political roles | None |

## Skill

One unified skill with modes:

```
/investigate <name>                          — full cross-reference (default)
/investigate <name> --trace                  — multi-hop network traversal
/investigate <name> --trace --depth 3        — deep network walk (3 hops)
/investigate <name> --patterns               — structural pattern analysis
/investigate <name> --compliance             — rigorous sanctions/PEP screening
/investigate <name> --monitor                — check for new sanctions listings
/investigate <name> --jurisdiction           — jurisdictional footprint
/investigate <name1>, <name2>                — find connections between subjects
/investigate <name1>, <name2>, <name3>, ...  — merged network, find shared links
```

All modes search ICIJ, OpenSanctions, and (when available) GLEIF, SEC,
Companies House, and CourtListener. Cross-references findings, detects
structural patterns, and offers interactive D3 network visualization.

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

`/investigate` (all modes) should:

1. Load `patterns/INDEX.yaml` before producing output
2. Cross-reference findings against known patterns
3. When a known pattern is identified, name it and cite the pattern file
4. When a NEW pattern is identified, propose adding it to the library

### Pattern lifecycle

- **PROPOSED**: Identified in a single investigation, not yet confirmed
- **CONFIRMED**: Observed in 2+ independent investigations
- **ESTABLISHED**: Observed across multiple leak datasets or jurisdictions

Patterns are never deleted — they may be marked DEPRECATED if
subsequent evidence shows they were misidentified.

## MCP Setup

Add to `.mcp.json` in the project root (already present):

```json
{
  "mcpServers": {
    "sift": {
      "command": ".venv/bin/python",
      "args": ["-m", "sift.server"]
    }
  }
}
```

Requires a Python venv with dependencies installed:
```
python3 -m venv .venv
.venv/bin/pip install mcp httpx
```

## Configuration

Create a `.env` file in the project root:

```
OPENSANCTIONS_API_KEY=<your-key>          # Required — get from opensanctions.org
SEC_EDGAR_USER_AGENT=sift contact@you.com # Required — any name + email
COMPANIES_HOUSE_API_KEY=<your-key>        # Optional — get from developer.company-information.service.gov.uk
COURTLISTENER_API_TOKEN=<your-token>      # Optional — get from courtlistener.com/profile/api/
ALEPH_API_KEY=<your-key>                  # Optional — get from aleph.occrp.org (register free)
```

ICIJ, GLEIF, SEC EDGAR, UK Land Registry, and Wikidata work without
keys. OpenSanctions requires a free API key. Companies House,
CourtListener, and OCCRP Aleph are optional — if keys are missing,
those sources still work (Aleph has public access) or are silently
skipped.

## Error Handling

All external API calls MUST use `api_call()` from `sift/errors.py`.
Never use bare `try/except` around HTTP calls — the shared handler
provides consistent error tracking and surfaces warnings to users.

```python
from sift.errors import ServiceTracker, api_call

tracker = ServiceTracker()

# Pass a lambda so the call can be retried on transient errors
# (HTTP 429/500/502/503/504, timeouts, connection failures).
# Up to 3 total attempts (1 + 2 retries) with exponential backoff.
result = await api_call(tracker, "ICIJ", "/reconcile",
                        lambda: icij_client.reconcile(query=name))

# At the end, attach warnings to the response:
if tracker.warnings:
    result["service_warnings"] = tracker.warnings
```

When a service fails, the traversal continues with remaining sources
and the response includes `service_warnings` like:
`"ICIJ (/reconcile) is returning errors, skipping for now (3 failures) — HTTP 500"`

**Important**: Always pass a `lambda` (not a bare coroutine) to
`api_call` so retries work. In loop bodies, capture loop variables
with default args: `lambda n=name: client.search(n)`.

### Rate limits

`api_call()` enforces per-service rate limits automatically via
`SERVICE_RATE_LIMITS` in `sift/errors.py`. When adding a new data
source, look up its documented rate limit and add an entry:

```python
SERVICE_RATE_LIMITS: dict[str, float] = {
    "ICIJ":             0.25,   # 4 req/s   (undocumented — polite)
    "OpenSanctions":    0.20,   # 5 req/s   (monthly quota only)
    "GLEIF":            1.00,   # 1 req/s   (60/min documented)
    "SEC EDGAR":        0.12,   # ~8 req/s  (10/s documented)
    "Companies House":  0.50,   # 2 req/s   (600/5min documented)
    "CourtListener":    0.75,   # ~1.3 req/s (5000/hr documented)
    "Aleph":            2.00,   # 0.5 req/s (30/min anon documented)
    "Wikidata":         0.50,   # 2 req/s   (conservative)
    "Land Registry":    0.50,   # 2 req/s   (undocumented — conservative)
}
```

The value is the minimum seconds between requests. When a service
name isn't in the dict, no throttling is applied — so always add
new services here.

## Conventions

- All investigation output uses professional, factual language
- Appearing in the ICIJ database does not indicate illegality
- Absence from the database does not indicate absence of offshore activity
- The database covers 5 specific leaks, not the full offshore world
- Name matching is fuzzy — verify identities through additional sources
- Node IDs are stable identifiers within the ICIJ database
