# Sift

[![Tests](https://img.shields.io/badge/tests-211%20passing-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![Data Sources](https://img.shields.io/badge/data%20sources-9-orange)]()

An [MCP server](https://modelcontextprotocol.io/) for financial crime investigation and investigative journalism. Cross-references **9 data sources** with **63 tools**, **18 detection patterns**, and interactive D3 visualizations.

![Network Graph](docs/images/network-graph.png)

> [!NOTE]
> This is an investigative research tool, not a compliance product. Appearing in the ICIJ database does not indicate illegality. Absence from the database does not indicate absence of offshore activity. Always verify findings against primary sources before drawing conclusions.

## What it does

Sift searches across 9 independent databases simultaneously, cross-references findings, detects structural patterns, and produces interactive visualizations — turning hours of manual cross-referencing into seconds.

**One command** runs a full investigation:

```
/investigate Isabel dos Santos
```

This triggers a parallel search across all 9 sources, builds a network graph, identifies sanctions exposure, detects offshore patterns, and generates an interactive visualization with 8 analytical views.

![Investigation Overview](docs/images/investigation-overview.png)

## Data sources

| Source | Coverage | Auth | Tools |
|--------|----------|------|-------|
| [ICIJ Offshore Leaks](https://offshoreleaks.icij.org/) | 810K+ entities from 5 leak investigations | None | 8 |
| [OpenSanctions](https://www.opensanctions.org/) | 320+ sanctions lists, PEP databases, enforcement records | API key | 9 |
| [GLEIF LEI Registry](https://www.gleif.org/) | Global corporate identifiers + ownership chains | None | 3 |
| [SEC EDGAR](https://www.sec.gov/edgar) | US public company filings, 10-K/10-Q/8-K | User-Agent | 8 |
| [UK Companies House](https://developer-specs.company-information.service.gov.uk/) | UK company records, officers, beneficial ownership (PSC) | Free API key | 7 |
| [CourtListener](https://www.courtlistener.com/) | US federal court records (PACER/RECAP) | Free token | 6 |
| [OCCRP Aleph](https://aleph.occrp.org/) | Investigative datasets, company records, leaked documents | Optional API key | 4 |
| [UK Land Registry](https://landregistry.data.gov.uk/) | Property transaction prices (England/Wales) | None | 2 |
| [Wikidata](https://www.wikidata.org/) | Structured data on people, companies, political roles | None | 7 |

Plus **9 cross-source tools**: `deep_trace` (multi-hop network traversal), `ownership_trace`, `beneficial_owner`, `background_check`, `query` (natural language), `export_json`, `export_report`, and more.

**63 tools total** across all sources.

## Quick start

```bash
# Clone and install
git clone https://github.com/mefos-lab/sift.git
cd sift
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your keys (see Configuration below)

# Add to Claude Code MCP config (.mcp.json in project root)
```

### MCP configuration

Add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "sift": {
      "command": "/path/to/sift/.venv/bin/python",
      "args": ["-m", "sift.server"]
    }
  }
}
```

### Configuration

Create a `.env` file in the sift project root:

```bash
OPENSANCTIONS_API_KEY=<your-key>          # Required — get free at opensanctions.org/api
SEC_EDGAR_USER_AGENT=sift contact@you.com # Required for SEC — any name + email
COMPANIES_HOUSE_API_KEY=<your-key>        # Optional — free at developer.company-information.service.gov.uk
COURTLISTENER_API_TOKEN=<your-token>      # Optional — free at courtlistener.com
ALEPH_API_KEY=<your-key>                  # Optional — free at aleph.occrp.org
```

ICIJ, GLEIF, UK Land Registry, and Wikidata work without keys. OpenSanctions requires a free API key. The remaining sources are optional — if keys are missing, those sources are silently skipped.

## The `/investigate` skill

One unified skill with multiple modes:

```
/investigate <name>                          — full cross-reference (default)
/investigate <name> --trace                  — multi-hop network traversal
/investigate <name> --trace --depth 3        — deep network walk (3 hops)
/investigate <name> --patterns               — structural pattern analysis
/investigate <name> --compliance             — rigorous sanctions/PEP screening
/investigate <name> --monitor                — check for new sanctions listings
/investigate <name> --jurisdiction           — jurisdictional footprint
/investigate <name1>, <name2>                — find connections between subjects
/investigate --scan sanctions-evasion        — exploratory pattern hunt (no target)
/investigate --scan all                      — run all 8 scan types
```

### Example: Full investigation

```
/investigate Isabel dos Santos
```

Searches all 9 sources in parallel, then:
- Identifies **sanctions exposure** (UK FCDO, US Kleptocracy list, UK Companies House disqualification)
- Finds **ICIJ Officer** records in Paradise Papers (Malta corporate registry)
- Maps **family network** — father (President of Angola), siblings (PEPs, sanction-linked)
- Detects **patterns** — sanctions evasion, PEP opacity layer, cross-source corroboration
- Produces an **interactive visualization** with network graph, ownership tree, jurisdiction flow, timeline, and more

### Example: Network trace

```
/investigate Alexander Lukashenko --trace --depth 2
```

Expands outward from the seed name, hop by hop:
- **Hop 0**: Direct matches across all sources
- **Hop 1**: Connected entities — officers, shareholders, intermediaries
- **Hop 2**: Second-degree connections — co-officers, shared addresses

At each hop, cross-source bridges link findings between databases (e.g., an ICIJ entity officer checked against OpenSanctions).

### Example: Multi-name connection analysis

```
/investigate Isabel dos Santos, Sindika Dokolo
```

Runs a single unified traversal with both names as seeds, then identifies **connection points** — shared entities, intermediaries, jurisdictions, or sanctions bridges where the two networks overlap.

### Example: Compliance screening

```
/investigate Igor Sechin --compliance --nationality RU --dob 1960-09-07
```

Rigorous structured screening with all available identifying properties for precise matching. Designed for KYC/AML workflows.

### Example: Sanctions monitoring

```
/investigate Isabel dos Santos --monitor --since 2026-01-01
```

Checks for new sanctions listings since a specific date. Designed for ongoing monitoring of previously screened subjects.

### Example: Scan mode

```
/investigate --scan sanctions-evasion
```

Hunts for structural patterns across the data sources without requiring a target name. Available scan types:

| Scan type | What it finds |
|-----------|--------------|
| `sanctions-evasion` | Sanctioned persons with ICIJ offshore presence |
| `pep-opacity` | PEP family members behind offshore structures |
| `nominee-shield` | Professional nominee directors across mass entities |
| `intermediary-cluster` | Formation agents managing large entity portfolios |
| `rapid-dissolution` | Short-lived UK companies with suspicious characteristics |
| `llp-opacity` | UK LLPs with opaque corporate partners in secrecy jurisdictions |
| `beneficial-ownership-gap` | Entities with no disclosed beneficial owner |
| `mass-registration` | Addresses hosting large numbers of registered entities |

![Scan Dashboard](docs/images/scan-overview.png)

## Visualization

Every investigation can generate an interactive D3 visualization with 8 analytical views:

| View | What it shows |
|------|--------------|
| **Overview** | Intelligence assessment, key findings, risk level |
| **Network Graph** | Interactive force-directed graph, filterable by source and depth |
| **Ownership Tree** | GLEIF corporate hierarchy |
| **Source Coverage** | Which sources contributed which findings |
| **Corporate Structure** | Vertical org chart with pattern annotations |
| **Jurisdiction Flow** | Sankey diagram of person-to-jurisdiction connections |
| **Timeline** | Chronological narrative across all sources |
| **Source Matrix** | Cross-source entity resolution |

See the [Gallery](docs/gallery.md) for screenshots of all views.

## Pattern library

The `patterns/` directory contains 18 documented detection patterns, each with machine-readable YAML rules evaluated against the traversal graph:

| Category | Patterns |
|----------|----------|
| **Structural** (ICIJ) | Matryoshka, Starburst, Mirror, Intermediary Cluster, Nominee Shield, Regulatory Arbitrage Chain, Temporal Cluster |
| **Sanctions & PEP** | Sanctions Evasion, PEP Opacity Layer |
| **Graph Topology** | Circular Ownership, Scatter-Gather, Network Chokepoint |
| **Shell Indicators** | Shell Company Seven-Factor Screen, Mass Registration, Beneficial Ownership Gap |
| **UK Typologies** | LLP Opacity Vehicle, Rapid Dissolution |
| **Cross-Source** | Cross-Source Corroboration, Name Variant Obfuscation |

Patterns are derived from FATF typologies, ICIJ methodology, Moody's shell company indicators, FinCEN Files analysis, UK National Risk Assessment, and academic AML research. Each pattern file includes provenance citations.

### Pattern lifecycle

- **PROPOSED** — identified in a single investigation
- **CONFIRMED** — observed in 2+ independent investigations
- **ESTABLISHED** — observed across multiple leak datasets or jurisdictions

## Architecture

```
sift/
  server.py              — MCP server (63 tools)
  traversal.py           — Multi-hop parallel graph traversal engine
  errors.py              — Resilient error handling, retries, per-service rate limiting
  pattern_matcher.py     — YAML pattern evaluation engine
  scoring.py             — Confidence and risk scoring
  normalizer.py          — Entity deduplication and normalization
  visualizer.py          — D3 visualization generator
  export.py              — JSON and Markdown export
  query_router.py        — Natural language query routing
  client.py              — ICIJ Offshore Leaks API client
  opensanctions_client.py
  gleif_client.py
  sec_client.py
  companies_house_client.py
  courtlistener_client.py
  aleph_client.py
  land_registry_client.py
  wikidata_client.py

patterns/                — 18 YAML detection patterns with provenance
visualizations/          — D3 HTML template
.claude/skills/          — /investigate skill definition
tests/                   — 211 tests (mocked HTTP, no API calls)
```

### Error handling and rate limiting

All external API calls go through a centralized error handler (`sift/errors.py`) that provides:

- **Per-service rate limiting** based on documented API terms
- **Retries** with exponential backoff for transient errors (HTTP 429/500/502/503/504)
- **Service tracking** — when a source is having issues, the response includes warnings like `"ICIJ (/reconcile) is returning errors, skipping for now (2 failures)"`

The traversal engine runs all 9 sources in parallel during the seed phase and expands all frontier nodes concurrently during hop expansion, with per-service rate limiters preventing overload.

## Development

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio

# Run tests (211 tests, mocked HTTP — no API calls)
pytest tests/ -v

# Run the server directly
python -m sift.server
```

## Contributing

If you'd like to contribute, consider setting a repo-specific git
identity to keep your personal information out of the commit history:

```bash
git config user.name "your-handle"
git config user.email "your-anonymous-email"
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

This tool is built on the extraordinary work of:

- The [International Consortium of Investigative Journalists](https://www.icij.org/) and the hundreds of journalists who produced the Panama Papers, Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks investigations
- [OpenSanctions](https://www.opensanctions.org/) for aggregating and publishing sanctions data as a public good
- The journalists and sources who risked their safety to make this data available — including [Daphne Caruana Galizia](https://en.wikipedia.org/wiki/Daphne_Caruana_Galizia), who was investigating the Panama Papers when she was assassinated in 2017
