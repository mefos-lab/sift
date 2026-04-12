# Open Investigator

[![Tests](https://img.shields.io/badge/tests-23%20passing-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)]()

An MCP server for financial investigations. Combines the [ICIJ Offshore Leaks Database](https://offshoreleaks.icij.org/) with [OpenSanctions](https://www.opensanctions.org/) in a single server, with investigative skills and a pattern library for identifying offshore financial structures.

> [!NOTE]
> This is an investigative research tool, not a compliance product. Appearing in the ICIJ database does not indicate illegality. Absence from the database does not indicate absence of offshore activity. Always verify findings against primary sources before drawing conclusions.

## What it does

**17 MCP tools** across two data sources let you search, match, and traverse financial networks:

- **ICIJ Offshore Leaks** — 810,000+ offshore entities from the Panama Papers, Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks investigations
- **OpenSanctions** — 320+ sanctions lists, PEP databases, and enforcement records (OFAC, EU, UN, UK HMT, and more)

**9 investigative skills** chain these tools into workflows — from quick name searches to full cross-database intelligence reports.

**9 documented patterns** describe known offshore structures, accumulated and refined through investigations.

## Quick start

```bash
# Clone and install
git clone https://github.com/mefos-lab/sift.git
cd sift
uv venv && source .venv/bin/activate
uv pip install -e .

# Set your OpenSanctions API key (free for open data projects at opensanctions.org/api)
export OPENSANCTIONS_API_KEY=your_key_here

# Run the server
open-investigator
```

### Add to Claude Code

Add to your `~/.claude/settings.json` or project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "investigator": {
      "command": "/path/to/open-investigator/.venv/bin/open-investigator"
    }
  }
}
```

The server loads API keys from a `.env` file in the project root:

```bash
# open-investigator/.env
OPENSANCTIONS_API_KEY=your_key_here
```

> [!IMPORTANT]
> The ICIJ tools work without any API key. The OpenSanctions tools require a free API key — get one at [opensanctions.org/api](https://www.opensanctions.org/api/). Free for non-commercial and open data projects. The `.env` file is gitignored — your key stays local.

## Tools

### ICIJ Offshore Leaks (no auth required)

| Tool | Description |
|------|-------------|
| `icij_search` | Search for a name across 810K+ offshore entities |
| `icij_batch_search` | Search up to 25 names at once |
| `icij_entity` | Get full details on an entity by node ID |
| `icij_investigate` | Search + expand: return the full network for top matches |
| `icij_suggest` | Autocomplete entity names |
| `icij_suggest_property` | Autocomplete property names |
| `icij_suggest_type` | Autocomplete entity type names |
| `icij_extend` | Get additional properties for known entities |

### OpenSanctions (API key required)

| Tool | Description |
|------|-------------|
| `sanctions_search` | Full-text search with faceted filtering (country, topic, dataset) |
| `sanctions_match` | Structured screening with name + birth date + nationality + ID |
| `sanctions_batch_match` | Screen multiple names in one request |
| `sanctions_entity` | Full entity details with nested relationships |
| `sanctions_adjacent` | Walk the relationship graph (ownership, directorship, family) |
| `sanctions_provenance` | Statement-level data: which dataset contributed which fact |
| `sanctions_catalog` | List all 320+ available datasets |
| `sanctions_algorithms` | List available matching algorithms |
| `sanctions_monitor` | Check for new listings since a specific date |

## Skills

All skills search both databases and cross-reference findings.

| Skill | Description |
|-------|-------------|
| `/investigate <name>` | Unified intelligence summary — offshore holdings + sanctions exposure |
| `/trace-network <name>` | Walk the graph outward, flag sanctioned nodes |
| `/find-patterns <name>` | Structural pattern analysis with sanctions overlay |
| `/compare <name1>, <name2>` | Find shared connections and sanctions links between names |
| `/exposure-report <names>` | Batch dual-source due-diligence screening |
| `/jurisdiction-check <name>` | Map jurisdictional footprint with sanctions cross-reference |
| `/monitor <name>` | Check for new sanctions listings since a date |
| `/compliance-screen <name>` | Rigorous structured sanctions/PEP screening |
| `/cross-reference <name>` | The master skill — full investigation across all sources |

## Examples

### Investigate a name

```
> /investigate Mossack Fonseca

## Intelligence report: Mossack Fonseca

### ⚠️ Sanctions exposure
No matches in OpenSanctions (320+ lists checked).

### Offshore holdings (ICIJ)
| # | Name | Type | Score | Jurisdiction | Investigation |
|---|------|------|-------|-------------|---------------|
| 1 | MOSSACK FONSECA & CO. | Intermediary | 83 | Panama | Panama Papers |
| 2 | MOSSACK FONSECA LIMITED | Entity | 65 | Panama | Panama Papers |
| 3 | MOSSACK FONSECA GUATEMALA | Intermediary | 60 | Guatemala | Panama Papers |
...
```

### Batch exposure report

```
> /exposure-report Vladimir Putin, Roman Abramovich, Igor Sechin, Alisher Usmanov

## Exposure Report

Names screened: 4
Databases: ICIJ Offshore Leaks + OpenSanctions

| Status | Count |
|--------|-------|
| CRITICAL (both databases) | 1 |
| SANCTIONS HIT | 3 |
| OFFSHORE HIT | 1 |
| CLEAR | 0 |

### ⚠️ Critical (offshore + sanctioned)
| Name | ICIJ match | Sanctions lists | Score |
|------|-----------|-----------------|-------|
| Igor Sechin | Officer of 2 entities | OFAC SDN, EU, UK | 0.98 |
...
```

### Monitor for new sanctions

```
> /monitor Prigozhin --since 2026-01-01

## Monitoring report: Prigozhin

Period: 2026-01-01 to 2026-04-10
Status: NO NEW LISTINGS

Last known listings predate the monitoring period.
Next check recommended in 30 days.
```

### Cross-reference

```
> /cross-reference Alisher Usmanov

## Cross-reference report: Alisher Usmanov

### Executive summary
Alisher Usmanov appears in both ICIJ Offshore Leaks and OpenSanctions.
He is sanctioned by the EU, UK, and other jurisdictions since 2022,
with multiple offshore entities documented in the Panama Papers.
Risk level: CRITICAL.

### ⚠️ Sanctions exposure
| Match | Score | Lists | Topics |
|-------|-------|-------|--------|
| Alisher Burhanovich USMANOV | 0.99 | EU, UK HMT, AU, CH | sanction |

### Offshore holdings (ICIJ)
| Entity | Type | Jurisdiction | Investigation |
|--------|------|-------------|---------------|
| DORADO ASSET MANAGEMENT | Entity | BVI | Panama Papers |
...

### Risk assessment
| Factor | Finding | Risk |
|--------|---------|------|
| Sanctions | Active on EU, UK, AU, CH lists | HIGH |
| Offshore | Multiple BVI entities | HIGH |
| Cross-links | Same person in both databases | CRITICAL |
| **Overall** | | **CRITICAL** |
```

## Pattern Library

The `patterns/` directory documents known offshore structures. Patterns are accumulated through investigations and cross-referenced by skills.

| Pattern | Structure | Risk | Status |
|---------|-----------|------|--------|
| [The Matryoshka](patterns/matryoshka.md) | Nested jurisdiction chains | HIGH | ESTABLISHED |
| [The Starburst](patterns/starburst.md) | Hub-and-spoke via nominees | MEDIUM | ESTABLISHED |
| [The Mirror](patterns/mirror.md) | Parallel entities, jurisdictional optionality | MEDIUM | CONFIRMED |
| [The Intermediary Cluster](patterns/intermediary-cluster.md) | Shared formation agent | MEDIUM | ESTABLISHED |
| [The Nominee Shield](patterns/nominee-shield.md) | Professional nominees as legal screen | HIGH | ESTABLISHED |
| [The Regulatory Arbitrage Chain](patterns/regulatory-arbitrage-chain.md) | Jurisdiction gap exploitation | HIGH | CONFIRMED |
| [The Temporal Cluster](patterns/temporal-cluster.md) | Formation bursts correlated with events | MEDIUM | CONFIRMED |
| [The Sanctions Evasion Structure](patterns/sanctions-evasion-structure.md) | Routing around sanctioned persons | HIGH | PROPOSED |
| [The PEP Opacity Layer](patterns/pep-opacity-layer.md) | PEP-connected entities with nominee cover | HIGH | PROPOSED |

### Pattern lifecycle

- **PROPOSED** — identified in a single investigation
- **CONFIRMED** — observed in 2+ independent investigations
- **ESTABLISHED** — observed across multiple leak datasets or jurisdictions

> [!TIP]
> When `/find-patterns` or `/trace-network` identifies a structure not in the library, it proposes a new pattern with PROPOSED status. Over time, the library grows through investigations — the same accumulation model used in research frameworks.

## Data sources

| Source | Entities | Auth | Coverage |
|--------|----------|------|----------|
| [ICIJ Offshore Leaks](https://offshoreleaks.icij.org/) | 810,000+ | None | 5 leak investigations (2013–2021), 200+ countries, 80+ years |
| [OpenSanctions](https://www.opensanctions.org/) | Varies | API key | 320+ sanctions/PEP lists, updated continuously |

> [!NOTE]
> These databases cover specific leaks and specific sanctions lists — not the full offshore or sanctions universe. The ICIJ data comes from 5 providers; many others exist. OpenSanctions aggregates public lists; some jurisdictions maintain non-public designations.

## Development

```bash
# Install dev dependencies
uv pip install -e .
uv pip install pytest pytest-asyncio

# Run tests (23 tests, mock transport — no API calls)
.venv/bin/python3 -m pytest tests/ -v

# Verify server loads
.venv/bin/python3 -c "from open_investigator.server import server; print('OK')"
```

## Future data sources

The architecture supports adding additional data sources as new clients and tools within the same server:

- **OpenCorporates** — 200M+ company records from 140+ jurisdictions (pending API access)
- **SEC EDGAR** — US public company filings and beneficial ownership
- **UK Companies House** — UK company records with persons of significant control
- **GLEIF** — Legal Entity Identifiers mapping corporate hierarchies globally

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

This tool is built on the extraordinary work of:

- The [International Consortium of Investigative Journalists](https://www.icij.org/) and the hundreds of journalists who produced the Panama Papers, Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks investigations
- [OpenSanctions](https://www.opensanctions.org/) for aggregating and publishing sanctions data as a public good
- The journalists and sources who risked their safety to make this data available — including [Daphne Caruana Galizia](https://en.wikipedia.org/wiki/Daphne_Caruana_Galizia), who was investigating the Panama Papers when she was assassinated in 2017
