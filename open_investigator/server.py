"""MCP server for financial investigations — ICIJ Offshore Leaks + OpenSanctions."""

import json
import os
import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import ICIJClient, INVESTIGATIONS, ENTITY_TYPES
from .opensanctions_client import OpenSanctionsClient

server = Server("open-investigator")
icij_client = ICIJClient()
os_client = OpenSanctionsClient(api_key=os.environ.get("OPENSANCTIONS_API_KEY"))

OPENSANCTIONS_TOPICS = [
    "sanction", "debarment", "crime", "crime.fin", "crime.terror",
    "crime.cyber", "crime.traffick", "crime.war", "poi", "role.pep",
    "role.rca", "role.judge", "role.civil",
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # =====================================================================
        # ICIJ Offshore Leaks tools
        # =====================================================================
        Tool(
            name="icij_search",
            description=(
                "Search the ICIJ Offshore Leaks Database for a name. "
                "Matches against 810,000+ offshore entities from Panama Papers, "
                "Paradise Papers, Pandora Papers, Bahamas Leaks, and Offshore Leaks."
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
                "Search for multiple names at once in ICIJ (max 25). "
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
                "Get full details on a specific ICIJ offshore entity by node ID."
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
                "Search ICIJ and return the full network for top matches: "
                "the entity plus all connected nodes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name to investigate",
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
            description="Autocomplete entity names in the ICIJ database.",
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
            description="Get additional properties for ICIJ entities by node ID.",
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

        # =====================================================================
        # OpenSanctions tools
        # =====================================================================
        Tool(
            name="sanctions_search",
            description=(
                "Search OpenSanctions for a name across 320+ sanctions lists, "
                "PEP databases, and enforcement records. Supports faceted "
                "filtering by country, topic, dataset, and entity schema."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name or keyword to search for",
                    },
                    "schema": {
                        "type": "string",
                        "enum": ["Person", "Company", "Organization", "LegalEntity"],
                        "description": "Entity type filter (optional)",
                    },
                    "countries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "ISO country codes to filter by (optional)",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": OPENSANCTIONS_TOPICS},
                        "description": "Topic filters: sanction, crime, role.pep, etc. (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10, max 500)",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Pagination offset (default 0)",
                    },
                    "changed_since": {
                        "type": "string",
                        "description": "Only return entities changed after this ISO date (e.g. 2025-01-01) (optional)",
                    },
                    "datasets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific datasets (optional)",
                    },
                    "fuzzy": {
                        "type": "boolean",
                        "default": True,
                        "description": "Toggle fuzzy matching (default true)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="sanctions_match",
            description=(
                "Structured matching against OpenSanctions — screen a person or "
                "company with name + additional properties (birth date, nationality, "
                "registration number) for precise sanctions/PEP matching. "
                "Returns scored results (0.0-1.0). Use this for compliance screening."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of person or company",
                    },
                    "schema": {
                        "type": "string",
                        "enum": ["Person", "Company", "Organization", "LegalEntity"],
                        "default": "Person",
                        "description": "Entity type (default: Person)",
                    },
                    "birth_date": {
                        "type": "string",
                        "description": "Date of birth (YYYY-MM-DD) for persons (optional)",
                    },
                    "nationality": {
                        "type": "string",
                        "description": "ISO country code for nationality (optional)",
                    },
                    "id_number": {
                        "type": "string",
                        "description": "ID or passport number (optional)",
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": "Jurisdiction for companies (optional)",
                    },
                    "registration_number": {
                        "type": "string",
                        "description": "Company registration number (optional)",
                    },
                    "threshold": {
                        "type": "number",
                        "default": 0.7,
                        "description": "Minimum match score (0.0-1.0, default 0.7)",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": OPENSANCTIONS_TOPICS},
                        "description": "Topic filters (optional)",
                    },
                    "algorithm": {
                        "type": "string",
                        "description": "Scoring algorithm to use (optional — see sanctions_algorithms tool)",
                    },
                    "changed_since": {
                        "type": "string",
                        "description": "Only return entities changed after this ISO date (optional)",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="sanctions_entity",
            description=(
                "Get full details on an OpenSanctions entity by ID, including "
                "all properties, dataset memberships, and nested related entities."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The OpenSanctions entity ID",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="sanctions_adjacent",
            description=(
                "Get entities related to a given OpenSanctions entity — "
                "ownership, directorship, family, associates. This is the "
                "network traversal tool for walking relationship graphs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The OpenSanctions entity ID to expand",
                    },
                    "property_name": {
                        "type": "string",
                        "description": "Filter to a specific relationship type (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max related entities to return (default 50)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="sanctions_provenance",
            description=(
                "Get statement-level provenance for an entity — which dataset "
                "contributed which fact. Critical for assessing data quality "
                "and understanding which sanctions list includes this entity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The OpenSanctions entity ID",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max statements to return (default 50)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="sanctions_catalog",
            description=(
                "List all available datasets in OpenSanctions — sanctions lists, "
                "PEP databases, enforcement records. Shows dataset names, "
                "publishers, entity counts, and last updated dates."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="sanctions_batch_match",
            description=(
                "Screen multiple names against OpenSanctions in a single request. "
                "Efficient for bulk compliance screening of name lists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of names to screen",
                    },
                    "schema": {
                        "type": "string",
                        "enum": ["Person", "Company", "Organization", "LegalEntity"],
                        "default": "Person",
                        "description": "Entity type for all queries (default: Person)",
                    },
                    "threshold": {
                        "type": "number",
                        "default": 0.7,
                        "description": "Minimum match score (0.0-1.0, default 0.7)",
                    },
                    "algorithm": {
                        "type": "string",
                        "description": "Scoring algorithm to use (optional)",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": OPENSANCTIONS_TOPICS},
                        "description": "Topic filters (optional)",
                    },
                },
                "required": ["names"],
            },
        ),
        Tool(
            name="sanctions_algorithms",
            description=(
                "List available scoring algorithms for OpenSanctions matching. "
                "Use the algorithm name with sanctions_match or sanctions_batch_match."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="sanctions_monitor",
            description=(
                "Check for new additions to sanctions lists since a given date. "
                "Useful for ongoing monitoring of a name against list updates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name to monitor",
                    },
                    "since": {
                        "type": "string",
                        "description": "ISO date to check from (e.g. 2025-06-01)",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": OPENSANCTIONS_TOPICS},
                        "description": "Topic filters (optional)",
                    },
                },
                "required": ["query", "since"],
            },
        ),
        Tool(
            name="icij_suggest_property",
            description="Autocomplete property names in the ICIJ database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "Beginning of the property name to autocomplete",
                    },
                },
                "required": ["prefix"],
            },
        ),
        Tool(
            name="icij_suggest_type",
            description="Autocomplete entity type names in the ICIJ database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "Beginning of the type name to autocomplete",
                    },
                },
                "required": ["prefix"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        # =================================================================
        # ICIJ tools
        # =================================================================
        if name == "icij_search":
            result = await icij_client.reconcile(
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
            result = await icij_client.batch_reconcile(
                queries=queries,
                investigation=arguments.get("investigation"),
            )

        elif name == "icij_entity":
            result = await icij_client.get_node(arguments["node_id"])

        elif name == "icij_investigate":
            search_result = await icij_client.reconcile(
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
                        details = await icij_client.get_node(node_id_int)
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
            result = await icij_client.suggest_entity(arguments["prefix"])

        elif name == "icij_extend":
            result = await icij_client.extend(
                ids=arguments["node_ids"],
                properties=arguments["properties"],
            )

        # =================================================================
        # OpenSanctions tools
        # =================================================================
        elif name == "sanctions_search":
            result = await os_client.search(
                query=arguments["query"],
                schema=arguments.get("schema"),
                countries=arguments.get("countries"),
                topics=arguments.get("topics"),
                limit=arguments.get("limit", 10),
                offset=arguments.get("offset", 0),
                changed_since=arguments.get("changed_since"),
                datasets=arguments.get("datasets"),
                fuzzy=arguments.get("fuzzy", True),
            )

        elif name == "sanctions_match":
            props: dict[str, list[str]] = {"name": [arguments["name"]]}
            if arguments.get("birth_date"):
                props["birthDate"] = [arguments["birth_date"]]
            if arguments.get("nationality"):
                props["nationality"] = [arguments["nationality"]]
            if arguments.get("id_number"):
                props["idNumber"] = [arguments["id_number"]]
            if arguments.get("jurisdiction"):
                props["jurisdiction"] = [arguments["jurisdiction"]]
            if arguments.get("registration_number"):
                props["registrationNumber"] = [arguments["registration_number"]]

            schema = arguments.get("schema", "Person")
            queries = {
                "q0": {"schema": schema, "properties": props},
            }
            result = await os_client.match(
                queries=queries,
                threshold=arguments.get("threshold", 0.7),
                topics=arguments.get("topics"),
                algorithm=arguments.get("algorithm"),
                changed_since=arguments.get("changed_since"),
            )

        elif name == "sanctions_entity":
            result = await os_client.get_entity(arguments["entity_id"])

        elif name == "sanctions_adjacent":
            result = await os_client.get_adjacent(
                entity_id=arguments["entity_id"],
                property_name=arguments.get("property_name"),
                limit=arguments.get("limit", 50),
            )

        elif name == "sanctions_provenance":
            result = await os_client.get_statements(
                entity_id=arguments["entity_id"],
                limit=arguments.get("limit", 50),
            )

        elif name == "sanctions_catalog":
            result = await os_client.get_catalog()

        elif name == "sanctions_batch_match":
            schema = arguments.get("schema", "Person")
            queries = {}
            for i, n in enumerate(arguments["names"]):
                queries[f"q{i}"] = {
                    "schema": schema,
                    "properties": {"name": [n]},
                }
            result = await os_client.match(
                queries=queries,
                threshold=arguments.get("threshold", 0.7),
                topics=arguments.get("topics"),
                algorithm=arguments.get("algorithm"),
            )

        elif name == "sanctions_algorithms":
            result = await os_client.get_algorithms()

        elif name == "sanctions_monitor":
            result = await os_client.search(
                query=arguments["query"],
                changed_since=arguments["since"],
                topics=arguments.get("topics"),
            )

        elif name == "icij_suggest_property":
            result = await icij_client.suggest_property(arguments["prefix"])

        elif name == "icij_suggest_type":
            result = await icij_client.suggest_type(arguments["prefix"])

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False),
        )]

    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"API error: {e.response.status_code} — {e.response.text[:500]}",
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
