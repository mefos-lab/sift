# icij-mcp

MCP server for the [ICIJ Offshore Leaks Database](https://offshoreleaks.icij.org/). Provides Claude (and other MCP clients) with direct access to 810,000+ offshore entities from the Panama Papers, Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks investigations.

## Tools

| Tool | Description |
|------|-------------|
| `icij_search` | Search for a name (person, company, address) across the database |
| `icij_batch_search` | Search multiple names at once (max 25) |
| `icij_entity` | Get full details on a specific entity by node ID |
| `icij_investigate` | Search + expand: find a name and return its full network |
| `icij_suggest` | Autocomplete entity names |
| `icij_extend` | Get additional properties for known entities |

## Setup

```bash
# Install
pip install -e .

# Or with uv
uv pip install -e .
```

## Usage with Claude Code

Add to your Claude Code MCP configuration (`~/.claude/settings.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "icij": {
      "command": "icij-mcp"
    }
  }
}
```

Or run directly:

```bash
icij-mcp
```

## API

Wraps the [ICIJ Reconciliation API](https://offshoreleaks.icij.org/docs/reconciliation) and REST API. No authentication required. The ICIJ API is free and public.

### Investigations available

- `panama-papers` — Mossack Fonseca (2016)
- `paradise-papers` — Appleby / Asiaciti Trust (2017)
- `pandora-papers` — Multiple providers (2021)
- `bahamas-leaks` — Bahamas corporate registry (2016)
- `offshore-leaks` — Various providers (2013)

## License

MIT
