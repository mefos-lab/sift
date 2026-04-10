# Offshore Investigator

MCP server for financial investigations. Combines [ICIJ Offshore Leaks Database](https://offshoreleaks.icij.org/) (810,000+ offshore entities) with [OpenSanctions](https://www.opensanctions.org/) (320+ sanctions/PEP lists) in a single server with investigative skills and a pattern library.

## Tools

### ICIJ Offshore Leaks (no auth required)

| Tool | Description |
|------|-------------|
| `icij_search` | Search for a name across the offshore leaks database |
| `icij_batch_search` | Search multiple names at once (max 25) |
| `icij_entity` | Get full details on a specific entity by node ID |
| `icij_investigate` | Search + expand: find a name and return its full network |
| `icij_suggest` | Autocomplete entity names |
| `icij_extend` | Get additional properties for known entities |

### OpenSanctions (API key required — free for non-commercial use)

| Tool | Description |
|------|-------------|
| `sanctions_search` | Search across 320+ sanctions lists with faceted filtering |
| `sanctions_match` | Structured compliance screening with name + properties |
| `sanctions_entity` | Get full entity details with nested relationships |
| `sanctions_adjacent` | Walk the relationship graph — ownership, directorship, family |
| `sanctions_provenance` | Statement-level data showing which dataset contributed which fact |
| `sanctions_catalog` | List all available sanctions/PEP datasets |

## Setup

```bash
# Install
uv venv && source .venv/bin/activate
uv pip install -e .

# Set OpenSanctions API key (get free key at opensanctions.org/api)
export OPENSANCTIONS_API_KEY=your_key_here
```

## Usage with Claude Code

```json
{
  "mcpServers": {
    "investigator": {
      "command": "/path/to/.venv/bin/offshore-investigator",
      "env": {
        "OPENSANCTIONS_API_KEY": "your_key_here"
      }
    }
  }
}
```

## Investigative Skills

| Skill | Description |
|-------|-------------|
| `/investigate` | Full intelligence summary on a name |
| `/trace-network` | Walk the graph outward, map the structure |
| `/find-patterns` | Identify structural patterns in offshore arrangements |
| `/compare` | Find shared connections between names |
| `/exposure-report` | Batch due-diligence screening |
| `/jurisdiction-check` | Map jurisdictional footprint |

Skills reference the pattern library and cross-reference findings across both data sources.

## Pattern Library

The `patterns/` directory accumulates documented offshore structure patterns:

- **The Matryoshka** — nested jurisdiction chains
- **The Starburst** — hub-and-spoke via nominees
- **The Mirror** — parallel entities, jurisdictional optionality
- **The Intermediary Cluster** — shared formation agent
- **The Nominee Shield** — professional nominees as legal screen
- **The Regulatory Arbitrage Chain** — jurisdiction gap exploitation
- **The Temporal Cluster** — formation bursts correlated with events

Patterns grow through investigations. New structures are added as PROPOSED, promoted to CONFIRMED after independent corroboration, and to ESTABLISHED across multiple datasets.

## Data Sources

| Source | Entities | Auth | Scope |
|--------|----------|------|-------|
| ICIJ Offshore Leaks | 810,000+ | None | 5 leak investigations (2013-2021) |
| OpenSanctions | Varies | API key | 320+ sanctions lists, PEP databases, enforcement records |

## License

MIT
