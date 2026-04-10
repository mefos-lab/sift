"""MCP server for the ICIJ Offshore Leaks Database."""

import json
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import ICIJClient, INVESTIGATIONS, ENTITY_TYPES

server = Server("icij-offshore-leaks")
client = ICIJClient()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="icij_search",
            description=(
                "Search the ICIJ Offshore Leaks Database for a name. "
                "Matches against 810,000+ offshore entities from Panama Papers, "
                "Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks. "
                "Returns matching entities with scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name to search for (person, company, or address)",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ENTITY_TYPES,
                        "description": "Filter by entity type (optional)",
                    },
                    "investigation": {
                        "type": "string",
                        "enum": INVESTIGATIONS,
                        "description": "Limit to a specific investigation (optional)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="icij_batch_search",
            description=(
                "Search for multiple names at once (max 25). "
                "More efficient than individual searches when checking a list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 25,
                        "description": "List of names to search for",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ENTITY_TYPES,
                        "description": "Filter all queries by entity type (optional)",
                    },
                    "investigation": {
                        "type": "string",
                        "enum": INVESTIGATIONS,
                        "description": "Limit to a specific investigation (optional)",
                    },
                },
                "required": ["names"],
            },
        ),
        Tool(
            name="icij_entity",
            description=(
                "Get full details on a specific offshore entity by its ICIJ node ID. "
                "Returns the entity's name, type, jurisdiction, source, "
                "and linked nodes (officers, intermediaries, addresses)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "integer",
                        "description": "The ICIJ node ID",
                    },
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="icij_investigate",
            description=(
                "Given a name, search the ICIJ database and return the full "
                "network for the top match: the entity itself plus all connected "
                "nodes (officers, intermediaries, addresses). This chains search "
                "and entity lookup into a single investigative query."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of person, company, or entity to investigate",
                    },
                    "investigation": {
                        "type": "string",
                        "enum": INVESTIGATIONS,
                        "description": "Limit to a specific investigation (optional)",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 3,
                        "description": "Number of top matches to expand (default 3)",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="icij_suggest",
            description=(
                "Autocomplete entity names in the ICIJ database. "
                "Useful for finding the correct spelling or verifying "
                "whether an entity exists before a full search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "Beginning of the name to autocomplete",
                    },
                },
                "required": ["prefix"],
            },
        ),
        Tool(
            name="icij_extend",
            description=(
                "Get additional properties (e.g., country codes, dates) "
                "for entities you already have node IDs for."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of ICIJ node IDs",
                    },
                    "properties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Property names to retrieve (e.g., 'country_codes')",
                    },
                },
                "required": ["node_ids", "properties"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "icij_search":
            result = await client.reconcile(
                query=arguments["query"],
                entity_type=arguments.get("entity_type"),
                investigation=arguments.get("investigation"),
            )

        elif name == "icij_batch_search":
            names = arguments["names"]
            queries = {}
            for i, n in enumerate(names[:25]):
                q: dict = {"query": n}
                if arguments.get("entity_type"):
                    q["type"] = arguments["entity_type"]
                queries[f"q{i}"] = q
            result = await client.batch_reconcile(
                queries=queries,
                investigation=arguments.get("investigation"),
            )

        elif name == "icij_entity":
            result = await client.get_node(arguments["node_id"])

        elif name == "icij_investigate":
            search_result = await client.reconcile(
                query=arguments["name"],
                investigation=arguments.get("investigation"),
            )
            candidates = search_result.get("result", [])
            max_results = arguments.get("max_results", 3)
            network = []
            for candidate in candidates[:max_results]:
                node_id = candidate.get("id")
                if node_id:
                    try:
                        node_id_int = int(str(node_id).split("/")[-1])
                        details = await client.get_node(node_id_int)
                        network.append({
                            "match": candidate,
                            "details": details,
                        })
                    except (ValueError, httpx.HTTPStatusError) as e:
                        network.append({
                            "match": candidate,
                            "error": str(e),
                        })
            result = {
                "query": arguments["name"],
                "matches_found": len(candidates),
                "expanded": len(network),
                "network": network,
            }

        elif name == "icij_suggest":
            result = await client.suggest_entity(arguments["prefix"])

        elif name == "icij_extend":
            result = await client.extend(
                ids=arguments["node_ids"],
                properties=arguments["properties"],
            )

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )]

    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"ICIJ API error: {e.response.status_code} — {e.response.text[:500]}",
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


def main():
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
