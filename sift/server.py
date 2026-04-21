"""Sift — MCP server for cross-referencing public financial and corporate data."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import ICIJClient, INVESTIGATIONS, ENTITY_TYPES
from .opensanctions_client import OpenSanctionsClient
from .gleif_client import GLEIFClient
from .sec_client import SECEdgarClient
from .companies_house_client import CompaniesHouseClient
from .courtlistener_client import CourtListenerClient
from .aleph_client import AlephClient
from .land_registry_client import LandRegistryClient
from .wikidata_client import WikidataClient
from .errors import ServiceTracker, api_call
from .traversal import traverse, result_to_visualizer_data
from .export import export_json, export_markdown
from .query_router import route_query


def _load_env():
    """Load API keys from .env file in the project root."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


_load_env()

server = Server("sift")

# Session state — stores the last investigation for export
_last_investigation: dict | None = None

# Core sources (no auth required)
icij_client = ICIJClient()
gleif_client = GLEIFClient()
sec_client = SECEdgarClient(
    user_agent=os.environ.get("SEC_EDGAR_USER_AGENT", "sift contact@example.com"),
)

# Sources requiring API keys — set to None if key is missing/empty
_os_key = os.environ.get("OPENSANCTIONS_API_KEY", "").strip()
os_client = OpenSanctionsClient(api_key=_os_key) if _os_key else None

_ch_key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
ch_client = CompaniesHouseClient(api_key=_ch_key) if _ch_key else None

_cl_token = os.environ.get("COURTLISTENER_API_TOKEN", "").strip()
cl_client = CourtListenerClient(api_token=_cl_token) if _cl_token else None

_aleph_key = os.environ.get("ALEPH_API_KEY", "").strip()
aleph_client = AlephClient(api_key=_aleph_key) if _aleph_key else AlephClient()

# No auth required
land_registry_client = LandRegistryClient()
wikidata_client = WikidataClient()

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
        # =================================================================
        # GLEIF LEI Registry tools
        # =================================================================
        Tool(
            name="gleif_search",
            description=(
                "Search the GLEIF LEI Registry for a company name. Returns "
                "Legal Entity Identifiers (LEIs) with legal name, jurisdiction, "
                "status, and registration details. LEIs are globally unique "
                "corporate identifiers — useful for entity resolution."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name to search for",
                    },
                    "page_size": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": "Filter by jurisdiction code (e.g. 'US-DE', 'GB', 'KY')",
                    },
                    "entity_status": {
                        "type": "string",
                        "enum": ["ACTIVE", "INACTIVE"],
                        "description": "Filter by entity status",
                    },
                    "legal_form": {
                        "type": "string",
                        "description": "Filter by legal form ID",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by entity category (e.g. 'GENERAL', 'FUND', 'BRANCH')",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="gleif_entity",
            description="Get full LEI record by LEI code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lei": {
                        "type": "string",
                        "description": "The 20-character LEI code",
                    },
                },
                "required": ["lei"],
            },
        ),
        Tool(
            name="gleif_ownership",
            description=(
                "Get corporate ownership chain for an LEI — direct parent, "
                "ultimate parent, and child entities. Critical for mapping "
                "beneficial ownership structures."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "lei": {
                        "type": "string",
                        "description": "The 20-character LEI code",
                    },
                },
                "required": ["lei"],
            },
        ),

        Tool(
            name="gleif_related",
            description=(
                "Get full corporate relationship tree for an LEI — direct parent, "
                "ultimate parent, direct children, AND all descendants (ultimate "
                "children). Deeper than gleif_ownership — returns the complete "
                "subsidiary tree."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "lei": {
                        "type": "string",
                        "description": "The 20-character LEI code",
                    },
                },
                "required": ["lei"],
            },
        ),

        # =================================================================
        # SEC EDGAR tools
        # =================================================================
        Tool(
            name="sec_search",
            description=(
                "Full-text search across SEC EDGAR filings. Search for company "
                "names, people, or topics across 10-K, 10-Q, 8-K, and other "
                "filing types. No API key required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms (company name, person, keyword)",
                    },
                    "forms": {
                        "type": "string",
                        "description": "Comma-separated form types to filter (e.g. '10-K,8-K,DEF 14A')",
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Date range as 'YYYY-MM-DD,YYYY-MM-DD' (optional)",
                    },
                    "count": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                    "start": {
                        "type": "integer",
                        "default": 0,
                        "description": "Offset for pagination (default 0)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="sec_company",
            description=(
                "Get SEC-registered company profile and recent filings by CIK number. "
                "Returns entity type, SIC code, tickers, addresses, and latest filings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_filings",
            description=(
                "Get filing list for an SEC-registered company, optionally "
                "filtered by form type (10-K, 10-Q, 8-K, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                    "form_type": {
                        "type": "string",
                        "description": "Filter by form type, e.g. '10-K' (optional)",
                    },
                },
                "required": ["cik"],
            },
        ),

        Tool(
            name="sec_financials",
            description=(
                "Get structured XBRL financial data for an SEC-registered "
                "company: revenue, total assets, liabilities, net income, "
                "cash, equity, and debt. Returns the most recent 3 annual "
                "and latest quarterly values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),

        Tool(
            name="sec_subsidiaries",
            description=(
                "Extract the subsidiary list (Exhibit 21) from a company's "
                "most recent 10-K annual report. Returns subsidiary names "
                "and their jurisdictions of incorporation. Use this to map "
                "the full corporate structure of a public company."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_related_party",
            description=(
                "Extract Item 13 (Related Party Transactions) from the "
                "latest 10-K filing. Returns counterparty names, amounts, "
                "and the full section text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_13d",
            description=(
                "Get Schedule 13D/G filings showing beneficial ownership "
                "stakes. Returns reporting person, percent of class, "
                "purpose, and source of funds."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_risk_factors",
            description=(
                "Extract Item 1A (Risk Factors) from the latest 10-K, "
                "filtered to paragraphs mentioning legal proceedings, "
                "regulatory actions, investigations, or custom keywords."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Custom keywords to filter (optional, defaults to legal/regulatory terms)",
                    },
                },
                "required": ["cik"],
            },
        ),

        Tool(
            name="sec_proxy",
            description=(
                "Extract executive compensation and board members from the "
                "latest DEF 14A proxy statement. Shows who runs the company "
                "and how much they are paid — useful for identifying insiders."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_8k",
            description=(
                "Get recent 8-K current event filings with extracted Item "
                "descriptions. 8-K filings report material events: acquisitions "
                "(2.01), officer departures (5.02), material agreements (1.01), "
                "bankruptcy (1.03), and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "description": "Max 8-K filings to return (default 5)",
                    },
                },
                "required": ["cik"],
            },
        ),
        Tool(
            name="sec_amendments",
            description=(
                "Get 10-K/A and 10-Q/A amendment filings. Companies that "
                "repeatedly amend filings may be correcting errors or responding "
                "to SEC inquiries — the existence of amendments is itself a risk "
                "signal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cik": {
                        "type": "string",
                        "description": "SEC Central Index Key (CIK) number",
                    },
                },
                "required": ["cik"],
            },
        ),

        # =================================================================
        # UK Companies House tools
        # =================================================================
        Tool(
            name="uk_search",
            description=(
                "Search UK Companies House for companies or officers/directors. "
                "Free API, covers all UK-registered companies including PSC "
                "(Persons with Significant Control) beneficial ownership data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company or officer name to search for",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["company", "officer"],
                        "default": "company",
                        "description": "Search companies or officers (default: company)",
                    },
                    "items_per_page": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="uk_company",
            description=(
                "Get full UK company profile including officers and Persons with "
                "Significant Control (beneficial ownership). Combines company "
                "details, officer list, and PSC data in one call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number (e.g. '00000001')",
                    },
                },
                "required": ["company_number"],
            },
        ),
        Tool(
            name="uk_officer_appointments",
            description=(
                "Find all UK companies where a specific officer serves as "
                "director, secretary, or other role. Use the officer_id from "
                "uk_company results. Critical for mapping officer networks."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "officer_id": {
                        "type": "string",
                        "description": "Officer ID from Companies House (from uk_company results)",
                    },
                },
                "required": ["officer_id"],
            },
        ),

        Tool(
            name="uk_filing_history",
            description=(
                "Get filing history for a UK company with gap analysis. "
                "Identifies late filings, gaps in annual filings, and address changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)",
                        "enum": [
                            "accounts", "address", "annual-return", "capital",
                            "change-of-name", "confirmation-statement",
                            "incorporation", "liquidation", "miscellaneous",
                            "mortgage", "officers", "resolution",
                        ],
                    },
                },
                "required": ["company_number"],
            },
        ),
        Tool(
            name="uk_accounts",
            description=(
                "Get accounts summary for a UK company: last accounts type "
                "and period, next due date, overdue status, and accounts filing history."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number",
                    },
                },
                "required": ["company_number"],
            },
        ),
        Tool(
            name="uk_charges",
            description=(
                "Get the charge register (secured lending) for a UK company. "
                "Shows outstanding and satisfied charges with lender names."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number",
                    },
                },
                "required": ["company_number"],
            },
        ),
        Tool(
            name="uk_confirmation_status",
            description=(
                "Get confirmation statement history and flag timeliness gaps "
                "(>14 months between filings)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number",
                    },
                },
                "required": ["company_number"],
            },
        ),

        Tool(
            name="uk_disqualified",
            description=(
                "Search or look up disqualified company directors. "
                "Provide a query to search by name, or an officer_id "
                "for full disqualification details (dates, reasons, "
                "associated companies)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name to search in disqualified directors register",
                    },
                    "officer_id": {
                        "type": "string",
                        "description": "Specific officer ID for disqualification details",
                    },
                },
            },
        ),
        Tool(
            name="uk_insolvency",
            description=(
                "Get insolvency case history for a UK company — liquidation "
                "type, dates, and appointed insolvency practitioners."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_number": {
                        "type": "string",
                        "description": "UK Companies House number",
                    },
                },
                "required": ["company_number"],
            },
        ),
        Tool(
            name="uk_dissolved_search",
            description=(
                "Search for dissolved UK companies. Useful for investigating "
                "shell companies that were created and quickly dissolved."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name to search for among dissolved companies",
                    },
                    "start_index": {
                        "type": "integer",
                        "default": 0,
                        "description": "Offset for pagination (default 0)",
                    },
                },
                "required": ["query"],
            },
        ),

        # =================================================================
        # CourtListener tools
        # =================================================================
        Tool(
            name="court_search",
            description=(
                "Search US federal court records via CourtListener. Find cases, "
                "opinions, and docket entries involving a person or company. "
                "Covers PACER/RECAP data from federal courts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms (person name, company, case topic)",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["opinions", "dockets"],
                        "default": "dockets",
                        "description": "Search opinions or docket entries (default: dockets)",
                    },
                    "court": {
                        "type": "string",
                        "description": "Court ID to filter by (optional)",
                    },
                    "filed_after": {
                        "type": "string",
                        "description": "Only cases filed after this ISO date (optional)",
                    },
                    "filed_before": {
                        "type": "string",
                        "description": "Only cases filed before this ISO date (optional)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="court_docket",
            description="Get full docket details for a US federal court case.",
            inputSchema={
                "type": "object",
                "properties": {
                    "docket_id": {
                        "type": "integer",
                        "description": "CourtListener docket ID",
                    },
                },
                "required": ["docket_id"],
            },
        ),
        Tool(
            name="court_docket_entries",
            description="Get docket entries for a US federal court case.",
            inputSchema={
                "type": "object",
                "properties": {
                    "docket_id": {
                        "type": "integer",
                        "description": "CourtListener docket ID",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default 1)",
                    },
                },
                "required": ["docket_id"],
            },
        ),
        Tool(
            name="court_parties",
            description=(
                "Get parties (plaintiffs, defendants, attorneys) for a court case."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "docket_id": {
                        "type": "integer",
                        "description": "CourtListener docket ID",
                    },
                },
                "required": ["docket_id"],
            },
        ),
        Tool(
            name="court_complaint",
            description=(
                "Get the complaint/petition text for a court case. Fetches "
                "entry #1 RECAP document and parses for amounts in dispute."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "docket_id": {
                        "type": "integer",
                        "description": "CourtListener docket ID",
                    },
                },
                "required": ["docket_id"],
            },
        ),
        Tool(
            name="court_docket_detail",
            description=(
                "Get enriched docket details: nature of suit, cause, "
                "jurisdiction type, parties, and related cases."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "docket_id": {
                        "type": "integer",
                        "description": "CourtListener docket ID",
                    },
                },
                "required": ["docket_id"],
            },
        ),

        Tool(
            name="court_opinion",
            description=(
                "Get a court opinion by ID, including the full text "
                "and author information."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "opinion_id": {
                        "type": "integer",
                        "description": "CourtListener opinion ID",
                    },
                },
                "required": ["opinion_id"],
            },
        ),
        Tool(
            name="court_judge",
            description=(
                "Search for or look up a judge/attorney. Provide a query "
                "to search by name, or a person_id for full details "
                "(positions, courts, dates)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name to search for",
                    },
                    "person_id": {
                        "type": "integer",
                        "description": "CourtListener person ID for details",
                    },
                },
            },
        ),
        Tool(
            name="court_bankruptcy",
            description=(
                "Search for bankruptcy cases. Optionally filter by "
                "chapter (7=liquidation, 11=reorganization, 13=individual)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company or person name to search for bankruptcy cases",
                    },
                    "chapter": {
                        "type": "string",
                        "enum": ["7", "11", "13"],
                        "description": "Bankruptcy chapter to filter by",
                    },
                },
                "required": ["query"],
            },
        ),

        # =================================================================
        # Compound investigation tools
        # =================================================================
        Tool(
            name="ownership_trace",
            description=(
                "Map a company's full corporate ownership structure using GLEIF, "
                "then cross-reference every entity in the chain against ICIJ "
                "Offshore Leaks and OpenSanctions. Returns the complete ownership "
                "tree with sanctions/offshore flags at each level. Use this to "
                "answer: 'who owns this company, and does anyone in the chain "
                "have offshore or sanctions exposure?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Company name to trace ownership for",
                    },
                    "lei": {
                        "type": "string",
                        "description": "LEI code if known (skips search step)",
                    },
                },
                "required": ["company"],
            },
        ),
        Tool(
            name="beneficial_owner",
            description=(
                "Identify the beneficial owners of a UK company via Companies House "
                "PSC (Persons with Significant Control) data, then screen each "
                "owner against ICIJ, OpenSanctions, SEC, and CourtListener. "
                "Returns beneficial owners with their sanctions status, offshore "
                "exposure, SEC filings, and court cases."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "UK company name or number",
                    },
                },
                "required": ["company"],
            },
        ),
        Tool(
            name="background_check",
            description=(
                "Comprehensive due diligence on a person or company. Searches all "
                "9 data sources in parallel: ICIJ Offshore Leaks (offshore entities), "
                "OpenSanctions (sanctions/PEP status), GLEIF (corporate affiliations), "
                "SEC EDGAR (US filings and enforcement), UK Companies House "
                "(UK directorships and PSC control), CourtListener (US court "
                "cases), OCCRP Aleph (investigative datasets), and Wikidata "
                "(entity enrichment/PEP). Returns a unified profile with risk indicators."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Person or company name",
                    },
                    "country": {
                        "type": "string",
                        "description": "ISO country code to help disambiguate (optional)",
                    },
                },
                "required": ["name"],
            },
        ),

        # =================================================================
        # Natural language query tool
        # =================================================================
        Tool(
            name="query",
            description=(
                "Natural language investigation query. Ask a question in plain "
                "English and Sift will route it to the appropriate tools. "
                "Examples: 'Who is Jeffrey Epstein?', 'Is Acme Corp sanctioned?', "
                "'Show me the ownership chain for HSBC', 'Find court cases "
                "involving Trump Organization', 'What SEC filings mention Epstein?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about a person or company",
                    },
                },
                "required": ["question"],
            },
        ),

        # =================================================================
        # Export tools
        # =================================================================
        Tool(
            name="export_json",
            description=(
                "Export the most recent investigation results as structured JSON. "
                "Includes all entities, edges, pattern matches, confidence and "
                "risk scores, and metadata. Pass the investigation data from a "
                "prior deep_trace call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "investigation_data": {
                        "type": "object",
                        "description": "The investigation data dict from a deep_trace result",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="export_report",
            description=(
                "Export investigation results as a Markdown report suitable for "
                "editorial review. Structured as a story memo: headline, key "
                "entities with risk scores, pattern analysis, and source attribution. "
                "Pass the investigation data from a prior deep_trace call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "investigation_data": {
                        "type": "object",
                        "description": "The investigation data dict from a deep_trace result",
                    },
                },
                "required": [],
            },
        ),

        # =================================================================
        # OCCRP Aleph tools
        # =================================================================
        Tool(
            name="aleph_search",
            description=(
                "Search OCCRP Aleph for entities across investigative datasets — "
                "company records, court filings, leaked documents from dozens of "
                "countries. Covers Panama Papers source docs, FinCEN Files, and "
                "hundreds of other datasets."
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
                        "enum": ["Person", "Company", "Organization", "LegalEntity",
                                 "Thing", "Document"],
                        "description": "Entity type filter (optional)",
                    },
                    "countries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "ISO country codes to filter by (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="aleph_entity",
            description=(
                "Get full details on an OCCRP Aleph entity by ID — includes "
                "registration numbers, addresses, jurisdiction, source dataset, "
                "and associated documents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The Aleph entity ID",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="aleph_similar",
            description=(
                "Find entities similar to a given Aleph entity — useful for "
                "cross-referencing and finding the same person or company "
                "across different leaked datasets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The Aleph entity ID to cross-reference",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max similar entities to return (default 10)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="aleph_collections",
            description=(
                "Search OCCRP Aleph datasets and investigations by keyword. "
                "Returns available collections with entity counts and country "
                "coverage — useful for finding relevant source datasets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword to search collections for",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
        ),

        Tool(
            name="aleph_expand",
            description=(
                "Expand an Aleph entity's network — discover all connected "
                "entities and relationships (ownership, directorship, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Aleph entity ID to expand",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max connected entities (default 50)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="aleph_documents",
            description=(
                "Search documents within a specific Aleph collection/dataset. "
                "Useful for finding leaked documents, contracts, or filings "
                "related to an investigation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {
                        "type": "integer",
                        "description": "Aleph collection ID to search within",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search terms (optional — omit to list all documents)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max results (default 20)",
                    },
                },
                "required": ["collection_id"],
            },
        ),
        Tool(
            name="aleph_relationships",
            description=(
                "Get entity relationships filtered by type. Returns ownership, "
                "directorship, membership, and other connections. Optionally "
                "filter by relationship schemata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Aleph entity ID",
                    },
                    "schemata": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by schema types (e.g. ['Ownership', 'Directorship'])",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results (default 50)",
                    },
                },
                "required": ["entity_id"],
            },
        ),

        # =================================================================
        # UK Land Registry tools
        # =================================================================
        Tool(
            name="land_search",
            description=(
                "Search UK HM Land Registry Price Paid Data for property "
                "transactions by street, town, or postcode. Returns transaction "
                "prices, dates, property types, and addresses. Useful for "
                "tracing real estate purchases — a key laundering endpoint."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Street name, town, or postcode to search",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max results (default 20)",
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "Minimum transaction price filter (optional)",
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "Maximum transaction price filter (optional)",
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["detached", "semi-detached", "terraced", "flat"],
                        "description": "Property type filter (optional)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="land_postcode",
            description=(
                "Get all property transactions for a UK postcode. Returns "
                "the full transaction history — prices, dates, and property "
                "details. Use this when you have a specific postcode from "
                "a company registration or address."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "UK postcode (e.g. 'SW1A 1AA')",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results (default 50)",
                    },
                },
                "required": ["postcode"],
            },
        ),

        Tool(
            name="land_transaction_chain",
            description=(
                "Get property transaction history at a specific address. "
                "Shows all sales over time — useful for identifying rapid "
                "flipping or circular transactions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paon": {
                        "type": "string",
                        "description": "Primary address object name (house number/name)",
                    },
                    "street": {
                        "type": "string",
                        "description": "Street name",
                    },
                    "town": {
                        "type": "string",
                        "description": "Town name",
                    },
                    "postcode": {
                        "type": "string",
                        "description": "UK postcode (optional, narrows results)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max results (default 20)",
                    },
                },
                "required": ["paon", "street", "town"],
            },
        ),
        Tool(
            name="land_area_stats",
            description=(
                "Get property price statistics (avg/min/max/count) by year "
                "for a town. Useful for identifying price anomalies or "
                "understanding local market context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "town": {
                        "type": "string",
                        "description": "Town name to get stats for",
                    },
                    "year_from": {
                        "type": "integer",
                        "description": "Start year filter (optional)",
                    },
                    "year_to": {
                        "type": "integer",
                        "description": "End year filter (optional)",
                    },
                },
                "required": ["town"],
            },
        ),
        Tool(
            name="land_high_value",
            description=(
                "Search for high-value property transactions in a town. "
                "High-value purchases (>£1M by default) are a key money "
                "laundering indicator in UK real estate."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "town": {
                        "type": "string",
                        "description": "Town to search",
                    },
                    "min_price": {
                        "type": "integer",
                        "default": 1000000,
                        "description": "Minimum transaction price (default £1,000,000)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Max results (default 20)",
                    },
                },
                "required": ["town"],
            },
        ),

        # =================================================================
        # Wikidata tools
        # =================================================================
        Tool(
            name="wikidata_search",
            description=(
                "Search Wikidata for people, companies, and organizations. "
                "Returns Wikidata IDs with labels and descriptions. Use this "
                "for entity enrichment — confirming identities, finding "
                "nationalities, political roles, and corporate relationships."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name to search for",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="wikidata_entity",
            description=(
                "Get full Wikidata entity details — nationality, date of birth, "
                "political positions, employer, board memberships, corporate "
                "ownership, and more. Critical for PEP identification and "
                "entity enrichment across sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID (e.g. 'Q937' for Albert Einstein)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_pep_check",
            description=(
                "Check if a person holds or held political positions via "
                "Wikidata. Returns political offices with start/end dates. "
                "Complements OpenSanctions PEP data with historical positions "
                "and lower-profile political roles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID of the person to check",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_sparql",
            description=(
                "Execute a custom SPARQL query against Wikidata. For advanced "
                "queries like finding all board members of a company, all "
                "politicians from a jurisdiction, or corporate ownership chains."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SPARQL query to execute",
                    },
                },
                "required": ["query"],
            },
        ),

        Tool(
            name="wikidata_family",
            description=(
                "Get family relationships for a person: spouse, children, "
                "parents, siblings — with dates where available."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID (e.g. Q456034)",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_career",
            description=(
                "Get education, employment, board memberships, and management "
                "roles for a person from Wikidata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_citizenship",
            description="Get country of citizenship with dates for a person.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_enrich",
            description=(
                "Deep enrichment: family, education/career, citizenship, "
                "and political positions in one call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Wikidata entity ID",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="wikidata_date_xref",
            description=(
                "Cross-reference a person's political appointment dates "
                "against company inception dates. Flags overlaps within "
                "±6 months — the strongest public-data investigative signal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Wikidata entity ID for the person",
                    },
                    "company_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Wikidata entity IDs for companies to check",
                    },
                },
                "required": ["person_id", "company_ids"],
            },
        ),

        # =================================================================
        # Scan history tools
        # =================================================================
        # =================================================================
        # Health check tool
        # =================================================================
        Tool(
            name="scan_health_check",
            description=(
                "Verify API connectivity for all data sources. Makes one "
                "lightweight probe per source and reports which are available, "
                "which have invalid keys, and which are down. Call this before "
                "running scans to avoid wasting budget on degraded sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),

        Tool(
            name="scan_history_read",
            description=(
                "Read scan history for a scan type. Returns previously used "
                "seeds, pagination offsets from the last run, run count, and "
                "metadata. Use before starting a scan to avoid re-scanning "
                "the same seeds and to resume pagination from where you left off."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scan_type": {
                        "type": "string",
                        "description": "The scan type to read history for",
                    },
                },
                "required": ["scan_type"],
            },
        ),
        Tool(
            name="scan_history_write",
            description=(
                "Record a completed scan run. Stores the seeds used, finding "
                "count, pagination offsets, and optional metadata so that "
                "subsequent runs can cover new ground."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scan_type": {
                        "type": "string",
                        "description": "The scan type that was run",
                    },
                    "seeds_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names/IDs used as seeds in this run",
                    },
                    "findings_count": {
                        "type": "integer",
                        "description": "Number of findings (pattern matches) from this run",
                    },
                    "offsets": {
                        "type": "object",
                        "description": "Pagination offsets per source (e.g. {\"opensanctions\": 20})",
                        "additionalProperties": {"type": "integer"},
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata (e.g. search term used, jurisdiction index)",
                    },
                },
                "required": ["scan_type", "seeds_used", "findings_count"],
            },
        ),

        # =================================================================
        # Deep traversal tool
        # =================================================================
        Tool(
            name="deep_trace",
            description=(
                "Multi-hop network traversal across all 9 data sources. "
                "Starts from one or more names, expands outward 1-3 hops, "
                "finding connected entities, officers, intermediaries, and "
                "sanctions exposure at each level. Searches ICIJ, OpenSanctions, "
                "GLEIF, SEC, Companies House, CourtListener, OCCRP Aleph, "
                "and Wikidata. Returns the full graph with hop distances, "
                "cross-source links, and pruning notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Seed names to trace from (1 or more)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Number of hops to expand (1-3, default 2)",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 3,
                    },
                    "budget": {
                        "type": "integer",
                        "description": "Maximum API calls to make (10-500, default 50)",
                        "default": 50,
                        "minimum": 10,
                        "maximum": 500,
                    },
                    "max_fanout": {
                        "type": "integer",
                        "description": "Skip nodes with more connections than this (default 25)",
                        "default": 25,
                    },
                    "investigation": {
                        "type": "string",
                        "description": "Limit ICIJ to a specific investigation (optional)",
                        "enum": list(INVESTIGATIONS),
                    },
                },
                "required": ["names"],
            },
        ),
    ]


def _not_configured(source: str, env_var: str) -> list[TextContent]:
    """Return a helpful message when an API key is missing."""
    return [TextContent(
        type="text",
        text=json.dumps({
            "error": f"{source} is not configured — API key missing",
            "fix": f"Set {env_var} in your .env file",
        }, indent=2),
    )]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Guard: check required clients are configured
    _os_tools = {"sanctions_search", "sanctions_match", "sanctions_entity",
                 "sanctions_adjacent", "sanctions_provenance", "sanctions_catalog",
                 "sanctions_batch_match", "sanctions_algorithms", "sanctions_monitor"}
    _ch_tools = {"uk_search", "uk_company", "uk_officer_appointments",
                 "uk_filing_history", "uk_accounts", "uk_charges",
                 "uk_confirmation_status", "uk_disqualified",
                 "uk_insolvency", "uk_dissolved_search"}
    _cl_tools = {"court_search", "court_docket", "court_docket_entries",
                 "court_parties", "court_complaint", "court_docket_detail",
                 "court_opinion", "court_judge", "court_bankruptcy"}

    global _last_investigation

    if name in _os_tools and os_client is None:
        return _not_configured("OpenSanctions", "OPENSANCTIONS_API_KEY")
    if name in _ch_tools and ch_client is None:
        return _not_configured("UK Companies House", "COMPANIES_HOUSE_API_KEY")
    if name in _cl_tools and cl_client is None:
        return _not_configured("CourtListener", "COURTLISTENER_API_TOKEN")

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

        # =============================================================
        # GLEIF tools
        # =============================================================
        elif name == "gleif_search":
            result = await gleif_client.search(
                query=arguments["query"],
                page_size=arguments.get("page_size", 10),
                jurisdiction=arguments.get("jurisdiction"),
                entity_status=arguments.get("entity_status"),
                legal_form=arguments.get("legal_form"),
                category=arguments.get("category"),
            )

        elif name == "gleif_entity":
            result = await gleif_client.get_lei(arguments["lei"])

        elif name == "gleif_ownership":
            result = await gleif_client.get_ownership(arguments["lei"])

        elif name == "gleif_related":
            result = await gleif_client.get_all_relationships(arguments["lei"])

        # =============================================================
        # SEC EDGAR tools
        # =============================================================
        elif name == "sec_search":
            result = await sec_client.search(
                query=arguments["query"],
                forms=arguments.get("forms"),
                date_range=arguments.get("date_range"),
                count=arguments.get("count", 10),
                start=arguments.get("start", 0),
            )

        elif name == "sec_company":
            result = await sec_client.get_company(arguments["cik"])

        elif name == "sec_filings":
            result = await sec_client.get_filings(
                cik=arguments["cik"],
                form_type=arguments.get("form_type"),
            )

        elif name == "sec_financials":
            result = await sec_client.get_company_facts(arguments["cik"])

        elif name == "sec_subsidiaries":
            result = await sec_client.get_subsidiary_list(arguments["cik"])

        elif name == "sec_related_party":
            result = await sec_client.get_related_party_transactions(arguments["cik"])

        elif name == "sec_13d":
            result = await sec_client.get_schedule_13d(arguments["cik"])

        elif name == "sec_risk_factors":
            result = await sec_client.get_risk_factors(
                arguments["cik"], keywords=arguments.get("keywords"),
            )

        elif name == "sec_proxy":
            result = await sec_client.get_proxy_statement(arguments["cik"])

        elif name == "sec_8k":
            result = await sec_client.get_8k_events(
                arguments["cik"], limit=arguments.get("limit", 5),
            )

        elif name == "sec_amendments":
            result = await sec_client.get_amendments(arguments["cik"])

        # =============================================================
        # UK Companies House tools
        # =============================================================
        elif name == "uk_search":
            search_type = arguments.get("type", "company")
            if search_type == "officer":
                result = await ch_client.search_officer(
                    query=arguments["query"],
                    items_per_page=arguments.get("items_per_page", 10),
                )
            else:
                result = await ch_client.search_company(
                    query=arguments["query"],
                    items_per_page=arguments.get("items_per_page", 10),
                )

        elif name == "uk_company":
            cn = arguments["company_number"]
            company, officers, pscs = await asyncio.gather(
                ch_client.get_company(cn),
                ch_client.get_officers(cn),
                ch_client.get_pscs(cn),
                return_exceptions=True,
            )
            result = {
                "company": company if not isinstance(company, Exception) else {"error": str(company)},
                "officers": officers if not isinstance(officers, Exception) else {"error": str(officers)},
                "pscs": pscs if not isinstance(pscs, Exception) else {"error": str(pscs)},
            }

        elif name == "uk_officer_appointments":
            result = await ch_client.get_officer_appointments(
                arguments["officer_id"],
            )

        elif name == "uk_filing_history":
            result = await ch_client.get_filing_history(
                arguments["company_number"],
                category=arguments.get("category"),
            )

        elif name == "uk_accounts":
            result = await ch_client.get_accounts(arguments["company_number"])

        elif name == "uk_charges":
            result = await ch_client.get_charges(arguments["company_number"])

        elif name == "uk_confirmation_status":
            result = await ch_client.get_confirmation_statements(
                arguments["company_number"],
            )

        elif name == "uk_disqualified":
            if arguments.get("officer_id"):
                result = await ch_client.get_disqualified_officer(
                    arguments["officer_id"],
                )
            elif arguments.get("query"):
                result = await ch_client.search_disqualified(
                    arguments["query"],
                )
            else:
                result = {"error": "Provide either 'query' or 'officer_id'"}

        elif name == "uk_insolvency":
            result = await ch_client.get_insolvency(arguments["company_number"])

        elif name == "uk_dissolved_search":
            result = await ch_client.search_dissolved(
                arguments["query"],
                start_index=arguments.get("start_index", 0),
            )

        # =============================================================
        # CourtListener tools
        # =============================================================
        elif name == "court_search":
            type_map = {"opinions": "o", "dockets": "r"}
            result = await cl_client.search(
                query=arguments["query"],
                type=type_map.get(arguments.get("type", "dockets"), "r"),
                court=arguments.get("court"),
                filed_after=arguments.get("filed_after"),
                filed_before=arguments.get("filed_before"),
            )

        elif name == "court_docket":
            result = await cl_client.get_docket(arguments["docket_id"])

        elif name == "court_docket_entries":
            result = await cl_client.get_docket_entries(
                arguments["docket_id"], page=arguments.get("page", 1),
            )

        elif name == "court_parties":
            result = await cl_client.get_parties(arguments["docket_id"])

        elif name == "court_complaint":
            result = await cl_client.get_complaint_text(arguments["docket_id"])

        elif name == "court_docket_detail":
            result = await cl_client.get_docket_detail(arguments["docket_id"])

        elif name == "court_opinion":
            result = await cl_client.get_opinion(arguments["opinion_id"])

        elif name == "court_judge":
            if arguments.get("person_id"):
                result = await cl_client.get_person(arguments["person_id"])
            elif arguments.get("query"):
                result = await cl_client.search_people(arguments["query"])
            else:
                result = {"error": "Provide either 'query' or 'person_id'"}

        elif name == "court_bankruptcy":
            # Map chapter to nature_of_suit codes
            chapter_codes = {"7": "422", "11": "423", "13": "424"}
            nos = chapter_codes.get(arguments.get("chapter", ""))
            result = await cl_client.search(
                query=arguments["query"],
                type="r",
                nature_of_suit=nos,
            )

        # =============================================================
        # OCCRP Aleph tools
        # =============================================================
        elif name == "aleph_search":
            result = await aleph_client.search_entities(
                query=arguments["query"],
                schema=arguments.get("schema"),
                countries=arguments.get("countries"),
                limit=arguments.get("limit", 10),
            )

        elif name == "aleph_entity":
            result = await aleph_client.get_entity(arguments["entity_id"])

        elif name == "aleph_similar":
            result = await aleph_client.get_entity_similar(
                entity_id=arguments["entity_id"],
                limit=arguments.get("limit", 10),
            )

        elif name == "aleph_collections":
            result = await aleph_client.search_collections(
                query=arguments["query"],
                limit=arguments.get("limit", 10),
            )

        elif name == "aleph_expand":
            result = await aleph_client.expand_entity(
                entity_id=arguments["entity_id"],
                limit=arguments.get("limit", 50),
            )

        elif name == "aleph_documents":
            result = await aleph_client.search_collection_documents(
                collection_id=arguments["collection_id"],
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 20),
            )

        elif name == "aleph_relationships":
            result = await aleph_client.get_entity_relationships(
                entity_id=arguments["entity_id"],
                limit=arguments.get("limit", 50),
                schemata=arguments.get("schemata"),
            )

        # =============================================================
        # UK Land Registry tools
        # =============================================================
        elif name == "land_search":
            result = await land_registry_client.search_price_paid(
                query=arguments["query"],
                limit=arguments.get("limit", 20),
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                property_type=arguments.get("property_type"),
            )

        elif name == "land_postcode":
            result = await land_registry_client.search_postcode(
                postcode=arguments["postcode"],
                limit=arguments.get("limit", 50),
            )

        elif name == "land_transaction_chain":
            result = await land_registry_client.search_address_history(
                paon=arguments["paon"],
                street=arguments["street"],
                town=arguments["town"],
                postcode=arguments.get("postcode"),
                limit=arguments.get("limit", 20),
            )

        elif name == "land_area_stats":
            result = await land_registry_client.get_area_stats(
                town=arguments["town"],
                year_from=arguments.get("year_from"),
                year_to=arguments.get("year_to"),
            )

        elif name == "land_high_value":
            result = await land_registry_client.search_high_value(
                town=arguments["town"],
                min_price=arguments.get("min_price", 1_000_000),
                limit=arguments.get("limit", 20),
            )

        # =============================================================
        # Wikidata tools
        # =============================================================
        elif name == "wikidata_search":
            result = await wikidata_client.search(
                query=arguments["query"],
                limit=arguments.get("limit", 10),
            )

        elif name == "wikidata_entity":
            result = await wikidata_client.get_entity(arguments["entity_id"])

        elif name == "wikidata_pep_check":
            result = await wikidata_client.get_pep_info(arguments["entity_id"])

        elif name == "wikidata_sparql":
            result = await wikidata_client.sparql(arguments["query"])

        elif name == "wikidata_family":
            result = await wikidata_client.get_family(arguments["entity_id"])

        elif name == "wikidata_career":
            result = await wikidata_client.get_education_career(arguments["entity_id"])

        elif name == "wikidata_citizenship":
            result = await wikidata_client.get_citizenship(arguments["entity_id"])

        elif name == "wikidata_enrich":
            result = await wikidata_client.get_deep_enrichment(arguments["entity_id"])

        elif name == "wikidata_date_xref":
            result = await wikidata_client.cross_reference_dates(
                arguments["person_id"], arguments["company_ids"],
            )

        # =============================================================
        # Natural language query
        # =============================================================
        elif name == "query":
            question = arguments["question"]
            routed = route_query(question)

            # Auto-execute single-tool queries for simple cases
            auto_execute = len(routed) == 1 and routed[0]["tool"] in (
                "background_check", "sanctions_match", "court_search",
                "sec_search", "icij_search", "gleif_search",
            )

            if auto_execute:
                # Recursively call the routed tool
                tool_name = routed[0]["tool"]
                tool_args = routed[0]["args"]
                inner_result = await call_tool(tool_name, tool_args)
                # Return the result with routing context
                result = {
                    "question": question,
                    "executed": routed[0],
                    "result": json.loads(inner_result[0].text) if inner_result else None,
                }
            else:
                result = {
                    "question": question,
                    "routed_to": routed,
                    "instructions": (
                        "The query has been parsed into tool calls. Execute each "
                        "tool in the 'routed_to' list to answer the question. "
                        "Each entry has 'tool' (the MCP tool name), 'args' "
                        "(arguments to pass), and 'purpose' (what it will find)."
                    ),
                }

        # =============================================================
        # Health check
        # =============================================================
        elif name == "scan_health_check":
            # Source-to-scan-type mapping
            scan_source_reqs = {
                "sanctions-evasion": ["ICIJ", "OpenSanctions"],
                "pep-opacity": ["OpenSanctions", "Wikidata", "ICIJ"],
                "nominee-shield": ["ICIJ", "OpenSanctions"],
                "intermediary-cluster": ["ICIJ", "OpenSanctions"],
                "beneficial-ownership-gap": ["GLEIF", "ICIJ"],
                "mass-registration": ["ICIJ"],
                "disqualified-director": ["Companies House", "OpenSanctions", "ICIJ"],
                "rapid-dissolution": ["Companies House", "OpenSanctions"],
                "phoenix-company": ["Companies House", "ICIJ"],
                "llp-opacity": ["Companies House"],
                "property-layering": ["Land Registry", "Companies House", "ICIJ"],
                "sec-amendment-cluster": ["SEC EDGAR", "OpenSanctions", "ICIJ"],
                "sec-officer-churn": ["SEC EDGAR", "OpenSanctions", "ICIJ"],
                "bankruptcy-network": ["CourtListener", "SEC EDGAR", "OpenSanctions", "ICIJ"],
            }

            async def _probe(name: str, coro):
                try:
                    await coro
                    return name, "ok", None
                except httpx.HTTPStatusError as e:
                    code = e.response.status_code
                    if code in (401, 403):
                        return name, "invalid_key", f"HTTP {code}"
                    return name, "error", f"HTTP {code}"
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    return name, "unreachable", str(type(e).__name__)
                except Exception as e:
                    return name, "error", str(e)

            probes = []
            probes.append(_probe("ICIJ", icij_client.reconcile(query="test")))
            probes.append(_probe("GLEIF", gleif_client.search("test", page_size=1)))
            probes.append(_probe("SEC EDGAR", sec_client.search("test", count=1)))
            probes.append(_probe("Wikidata", wikidata_client.search("test", limit=1)))
            probes.append(_probe("Land Registry", land_registry_client.search_price_paid("London", limit=1)))

            if os_client:
                probes.append(_probe("OpenSanctions", os_client.search("test", limit=1)))
            if ch_client:
                probes.append(_probe("Companies House", ch_client.search_company("test", items_per_page=1)))
            if cl_client:
                probes.append(_probe("CourtListener", cl_client.search("test")))
            if aleph_client:
                probes.append(_probe("Aleph", aleph_client.search_entities("test", limit=1)))

            probe_results = await asyncio.gather(*probes)

            sources = {}
            for svc_name, status, error in probe_results:
                entry = {"status": status}
                if error:
                    entry["error"] = error
                sources[svc_name] = entry

            # Mark unconfigured clients
            if os_client is None:
                sources["OpenSanctions"] = {"status": "not_configured", "env_var": "OPENSANCTIONS_API_KEY"}
            if ch_client is None:
                sources["Companies House"] = {"status": "not_configured", "env_var": "COMPANIES_HOUSE_API_KEY"}
            if cl_client is None:
                sources["CourtListener"] = {"status": "not_configured", "env_var": "COURTLISTENER_API_TOKEN"}
            if aleph_client is None:
                sources["Aleph"] = {"status": "not_configured", "env_var": "ALEPH_API_KEY"}

            degraded = [s for s, info in sources.items() if info["status"] != "ok"]
            affected_scans = {}
            for scan, reqs in scan_source_reqs.items():
                missing = [r for r in reqs if r in degraded]
                if missing:
                    affected_scans[scan] = missing

            result = {
                "sources": sources,
                "degraded": degraded,
                "affected_scans": affected_scans,
            }

        # =============================================================
        # Scan history tools
        # =============================================================
        elif name == "scan_history_read":
            from sift.scan_history import get_summary
            result = get_summary(arguments["scan_type"])

        elif name == "scan_history_write":
            from sift.scan_history import ScanRecord, save_record
            record = ScanRecord(
                scan_type=arguments["scan_type"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                seeds_used=arguments["seeds_used"],
                findings_count=arguments["findings_count"],
                last_offset=arguments.get("offsets", {}),
                metadata=arguments.get("metadata", {}),
            )
            save_record(record)
            result = {"status": "saved", "scan_type": record.scan_type}

        # =============================================================
        # Export tools
        # =============================================================
        elif name == "export_json":
            data = arguments.get("investigation_data") or _last_investigation
            if not data:
                result = {"error": "No investigation data available. Run deep_trace or background_check first."}
            else:
                path = export_json(data)
                result = {"exported": str(path), "format": "json"}

        elif name == "export_report":
            data = arguments.get("investigation_data") or _last_investigation
            if not data:
                result = {"error": "No investigation data available. Run deep_trace or background_check first."}
            else:
                path = export_markdown(data)
                result = {"exported": str(path), "format": "markdown"}

        # =============================================================
        # Compound investigation tools
        # =============================================================
        elif name == "ownership_trace":
            company = arguments["company"]
            lei = arguments.get("lei")
            ot_tracker = ServiceTracker()

            # Step 1: Find LEI
            if not lei:
                gleif_search = await gleif_client.search(company, page_size=3)
                matches = gleif_search.get("results", [])
                if not matches:
                    result = {"error": f"No LEI found for '{company}'",
                              "suggestion": "Try a more specific company name"}
                    return [TextContent(type="text",
                                        text=json.dumps(result, indent=2, ensure_ascii=False))]
                lei = matches[0]["lei"]
                lei_entity = matches[0]
            else:
                lei_entity = await gleif_client.get_lei(lei)

            # Step 2: Get full ownership tree
            ownership = await gleif_client.get_all_relationships(lei)

            # Step 3: Collect all LEIs in the chain
            all_leis = [lei]
            if ownership.get("direct_parent"):
                all_leis.append(ownership["direct_parent"])
            if ownership.get("ultimate_parent"):
                all_leis.append(ownership["ultimate_parent"])
            all_leis.extend(ownership.get("direct_children", [])[:20])
            all_leis = list(dict.fromkeys(all_leis))  # dedupe

            # Step 4: Look up each LEI and cross-reference
            chain = []
            for chain_lei in all_leis:
                entry = {"lei": chain_lei, "role": "subject"}
                if chain_lei == ownership.get("direct_parent"):
                    entry["role"] = "direct_parent"
                elif chain_lei == ownership.get("ultimate_parent"):
                    entry["role"] = "ultimate_parent"
                elif chain_lei != lei:
                    entry["role"] = "subsidiary"

                # Get entity details
                details = await api_call(
                    ot_tracker, "GLEIF", "/lei",
                    lambda l=chain_lei: gleif_client.get_lei(l))
                if details:
                    entry["legal_name"] = details.get("legal_name", "")
                    entry["jurisdiction"] = details.get("jurisdiction", "")
                    entry["country"] = details.get("country", "")
                    entry["status"] = details.get("status", "")
                else:
                    entry["legal_name"] = chain_lei

                # Cross-reference against ICIJ
                entity_name = entry.get("legal_name", chain_lei)
                icij_res = await api_call(
                    ot_tracker, "ICIJ", "/reconcile",
                    lambda n=entity_name: icij_client.reconcile(query=n))
                if icij_res:
                    icij_matches = [r for r in icij_res.get("result", [])[:3]
                                    if r.get("score", 0) > 50]
                    if icij_matches:
                        entry["icij_matches"] = [{
                            "name": m["name"], "score": m["score"],
                            "id": m["id"],
                            "type": m.get("types", [{}])[0].get("name", ""),
                        } for m in icij_matches]

                # Cross-reference against OpenSanctions
                if os_client:
                    os_res = await api_call(
                        ot_tracker, "OpenSanctions", "/match",
                        lambda n=entity_name: os_client.match(
                            queries={"q0": {"schema": "LegalEntity",
                                            "properties": {"name": [n]}}},
                            threshold=0.7,
                        ))
                    if os_res:
                        os_matches = []
                        for qv in os_res.get("responses", {}).values():
                            for r in qv.get("results", [])[:3]:
                                if r.get("score", 0) >= 0.7:
                                    os_matches.append({
                                        "caption": r.get("caption", ""),
                                        "score": r.get("score"),
                                        "topics": r.get("properties", {}).get(
                                            "topics", r.get("topics", [])),
                                        "datasets": r.get("datasets", []),
                                    })
                        if os_matches:
                            entry["sanctions_matches"] = os_matches

                chain.append(entry)

            result = {
                "company": company,
                "lei": lei,
                "ownership": {
                    "direct_parent": ownership.get("direct_parent"),
                    "ultimate_parent": ownership.get("ultimate_parent"),
                    "direct_subsidiaries": len(ownership.get("direct_children", [])),
                    "all_descendants": len(ownership.get("all_children", [])),
                },
                "chain": chain,
                "flags": {
                    "icij_exposure": any("icij_matches" in e for e in chain),
                    "sanctions_exposure": any("sanctions_matches" in e for e in chain),
                },
            }
            if ot_tracker.warnings:
                result["service_warnings"] = ot_tracker.warnings

        elif name == "beneficial_owner":
            if ch_client is None:
                return _not_configured("UK Companies House", "COMPANIES_HOUSE_API_KEY")
            company = arguments["company"]

            # Step 1: Find the company
            cn = company
            company_data = None
            if not company.isdigit():
                search = await ch_client.search_company(company, items_per_page=3)
                items = search.get("items", [])
                if not items:
                    result = {"error": f"No UK company found for '{company}'"}
                    return [TextContent(type="text",
                                        text=json.dumps(result, indent=2, ensure_ascii=False))]
                cn = items[0]["company_number"]
                company_data = items[0]

            # Step 2: Get company + PSCs
            co, pscs = await asyncio.gather(
                ch_client.get_company(cn),
                ch_client.get_pscs(cn),
                return_exceptions=True,
            )
            if isinstance(co, Exception):
                co = {"error": str(co)}
            if isinstance(pscs, Exception):
                pscs = {"items": [], "error": str(pscs)}

            # Step 3: Screen each PSC across all sources
            psc_profiles = []
            for psc in pscs.get("items", [])[:10]:
                psc_name = psc.get("name", "")
                if not psc_name:
                    continue

                profile = {
                    "name": psc_name,
                    "natures_of_control": psc.get("natures_of_control", []),
                    "nationality": psc.get("nationality", ""),
                    "country_of_residence": psc.get("country_of_residence", ""),
                }

                # Screen in parallel (skip unavailable sources)
                async def _noop():
                    return None
                checks = await asyncio.gather(
                    icij_client.reconcile(query=psc_name),
                    os_client.match(
                        queries={"q0": {"schema": "Thing",
                                        "properties": {"name": [psc_name]}}},
                        threshold=0.6,
                    ) if os_client else _noop(),
                    sec_client.search(psc_name, count=3),
                    cl_client.search(psc_name, type="r") if cl_client else _noop(),
                    return_exceptions=True,
                )

                # ICIJ
                if not isinstance(checks[0], Exception):
                    icij_hits = [r for r in checks[0].get("result", [])[:3]
                                 if r.get("score", 0) > 50]
                    if icij_hits:
                        profile["icij"] = [{
                            "name": m["name"], "score": m["score"],
                            "type": m.get("types", [{}])[0].get("name", ""),
                        } for m in icij_hits]

                # OpenSanctions
                if not isinstance(checks[1], Exception):
                    os_hits = []
                    for qv in checks[1].get("responses", {}).values():
                        for r in qv.get("results", [])[:3]:
                            if r.get("score", 0) >= 0.6:
                                os_hits.append({
                                    "caption": r.get("caption", ""),
                                    "score": r.get("score"),
                                    "topics": r.get("properties", {}).get(
                                        "topics", r.get("topics", [])),
                                })
                    if os_hits:
                        profile["sanctions"] = os_hits

                # SEC
                if not isinstance(checks[2], Exception):
                    sec_hits = checks[2].get("results", [])[:3]
                    if sec_hits:
                        profile["sec_filings"] = [{
                            "entity": h.get("entity_name", ""),
                            "form": h.get("form", ""),
                            "date": h.get("file_date", ""),
                        } for h in sec_hits]

                # CourtListener
                if not isinstance(checks[3], Exception):
                    court_hits = checks[3].get("results", [])[:3]
                    if court_hits:
                        profile["court_cases"] = [{
                            "case": h.get("caseName", h.get("case_name", "")),
                            "court": h.get("court", ""),
                            "filed": h.get("dateFiled", h.get("date_filed", "")),
                        } for h in court_hits]

                psc_profiles.append(profile)

            result = {
                "company_number": cn,
                "company": co,
                "beneficial_owners": psc_profiles,
                "flags": {
                    "icij_exposure": any("icij" in p for p in psc_profiles),
                    "sanctions_exposure": any("sanctions" in p for p in psc_profiles),
                    "litigation": any("court_cases" in p for p in psc_profiles),
                },
            }

        elif name == "background_check":
            query_name = arguments["name"]
            country = arguments.get("country")

            # Search all 9 sources in parallel
            os_kwargs = {"query": query_name, "limit": 5}
            if country:
                os_kwargs["countries"] = [country]

            async def _noop():
                return None
            checks = await asyncio.gather(
                icij_client.reconcile(query=query_name),
                os_client.search(**os_kwargs) if os_client else _noop(),
                gleif_client.search(query_name, page_size=5),
                sec_client.search(query_name, count=5),
                ch_client.search_company(query_name, items_per_page=5) if ch_client else _noop(),
                cl_client.search(query_name, type="r") if cl_client else _noop(),
                aleph_client.search_entities(query_name, limit=5),
                wikidata_client.search(query_name, limit=5),
                _noop(),  # land_registry placeholder (address-based, not name-based)
                return_exceptions=True,
            )

            def _safe(idx):
                r = checks[idx]
                if r is None or isinstance(r, Exception):
                    return None
                return r

            profile = {"name": query_name, "sources": {}}

            # ICIJ
            icij_r = _safe(0)
            if icij_r:
                hits = [r for r in icij_r.get("result", [])[:5]
                        if r.get("score", 0) > 40]
                if hits:
                    profile["sources"]["icij"] = {
                        "count": len(hits),
                        "results": [{
                            "name": h["name"],
                            "score": h["score"],
                            "type": h.get("types", [{}])[0].get("name", ""),
                            "id": h["id"],
                        } for h in hits],
                    }

            # OpenSanctions
            os_r = _safe(1)
            if os_r:
                hits = os_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["opensanctions"] = {
                        "count": os_r.get("total", {}).get("value", len(hits)),
                        "results": [{
                            "caption": h.get("caption", ""),
                            "schema": h.get("schema", ""),
                            "topics": h.get("properties", {}).get(
                                "topics", h.get("topics", [])),
                            "datasets": h.get("datasets", []),
                        } for h in hits],
                    }

            # GLEIF
            gleif_r = _safe(2)
            if gleif_r:
                hits = gleif_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["gleif"] = {
                        "count": gleif_r.get("total", 0),
                        "results": [{
                            "lei": h["lei"],
                            "legal_name": h["legal_name"],
                            "jurisdiction": h["jurisdiction"],
                            "country": h["country"],
                            "status": h["status"],
                        } for h in hits],
                    }

            # SEC
            sec_r = _safe(3)
            if sec_r:
                hits = sec_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["sec_edgar"] = {
                        "count": sec_r.get("total", 0),
                        "results": [{
                            "entity_name": h.get("entity_name", ""),
                            "form": h.get("form", ""),
                            "file_date": h.get("file_date", ""),
                            "description": h.get("file_description", ""),
                        } for h in hits],
                    }

            # UK Companies House
            ch_r = _safe(4)
            if ch_r:
                hits = ch_r.get("items", [])[:5]
                if hits:
                    profile["sources"]["companies_house"] = {
                        "count": ch_r.get("total_results", len(hits)),
                        "results": [{
                            "company_number": h.get("company_number", ""),
                            "title": h.get("title", ""),
                            "status": h.get("company_status", ""),
                            "address": h.get("address_snippet", ""),
                        } for h in hits],
                    }

            # CourtListener
            cl_r = _safe(5)
            if cl_r:
                hits = cl_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["courtlistener"] = {
                        "count": cl_r.get("count", len(hits)),
                        "results": [{
                            "case_name": h.get("caseName",
                                               h.get("case_name", "")),
                            "court": h.get("court", ""),
                            "date_filed": h.get("dateFiled",
                                                h.get("date_filed", "")),
                        } for h in hits],
                    }

            # OCCRP Aleph
            aleph_r = _safe(6)
            if aleph_r:
                hits = aleph_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["aleph"] = {
                        "count": aleph_r.get("total", len(hits)),
                        "results": [{
                            "name": h.get("name", ""),
                            "schema": h.get("schema", ""),
                            "countries": h.get("countries", []),
                            "jurisdiction": h.get("jurisdiction", ""),
                            "datasets": h.get("datasets", []),
                        } for h in hits],
                    }

            # Wikidata
            wd_r = _safe(7)
            if wd_r:
                hits = wd_r.get("results", [])[:5]
                if hits:
                    profile["sources"]["wikidata"] = {
                        "count": wd_r.get("total", len(hits)),
                        "results": [{
                            "id": h.get("id", ""),
                            "label": h.get("label", ""),
                            "description": h.get("description", ""),
                        } for h in hits],
                    }

            # Phase 2: enrichment checks (parallel, triggered by phase 1 hits)
            phase2_tasks = []
            phase2_labels = []

            # CH insolvency for first company found
            ch_companies = profile.get("sources", {}).get(
                "companies_house", {}).get("results", [])
            if ch_client and ch_companies:
                cn = ch_companies[0].get("company_number", "")
                if cn:
                    phase2_tasks.append(ch_client.get_insolvency(cn))
                    phase2_labels.append("insolvency")

            # Disqualified directors check for first company's name
            if ch_client and ch_companies:
                title = ch_companies[0].get("title", "")
                if title:
                    phase2_tasks.append(ch_client.search_disqualified(title))
                    phase2_labels.append("disqualified")

            # SEC amendments + 8-K for first CIK found
            sec_hits = profile.get("sources", {}).get(
                "sec_edgar", {}).get("results", [])
            if sec_hits:
                cik = sec_hits[0].get("cik", "")
                if cik:
                    phase2_tasks.append(sec_client.get_amendments(cik))
                    phase2_labels.append("amendments")
                    phase2_tasks.append(sec_client.get_8k_events(cik, limit=3))
                    phase2_labels.append("8k_events")

            # Bankruptcy search
            if cl_client:
                phase2_tasks.append(cl_client.search(
                    query_name, nature_of_suit="422"))
                phase2_labels.append("bankruptcy")

            # Fire all phase 2 in parallel
            insolvency_data = None
            disqualified_data = None
            amendments_data = None
            events_8k_data = None
            bankruptcy_data = None

            if phase2_tasks:
                p2_results = await asyncio.gather(
                    *phase2_tasks, return_exceptions=True)
                for label, res in zip(phase2_labels, p2_results):
                    if isinstance(res, Exception):
                        continue
                    if label == "insolvency":
                        insolvency_data = res
                    elif label == "disqualified":
                        disqualified_data = res
                    elif label == "amendments":
                        amendments_data = res
                    elif label == "8k_events":
                        events_8k_data = res
                    elif label == "bankruptcy":
                        bankruptcy_data = res

            # Add enrichment to profile
            if insolvency_data and insolvency_data.get("cases"):
                profile["insolvency"] = insolvency_data["cases"]
            if disqualified_data and disqualified_data.get("items"):
                profile["disqualified_officers"] = disqualified_data["items"]
            if amendments_data and amendments_data.get("amendments"):
                profile["amendments"] = amendments_data["amendments"]
            if events_8k_data and events_8k_data.get("events"):
                profile["material_events"] = events_8k_data["events"]
            if bankruptcy_data and bankruptcy_data.get("count", 0) > 0:
                profile["bankruptcy_cases"] = bankruptcy_data.get("results", [])[:3]

            # Risk summary
            sources_found = list(profile["sources"].keys())
            profile["risk_indicators"] = {
                "sources_matched": len(sources_found),
                "sources_list": sources_found,
                "offshore_exposure": "icij" in sources_found,
                "sanctions_pep": any(
                    any(t in topic
                        for t in ["sanction", "role.pep", "crime"])
                    for r in profile.get("sources", {}).get(
                        "opensanctions", {}).get("results", [])
                    for topic in r.get("topics", [])
                ),
                "litigation": "courtlistener" in sources_found,
                "sec_filings": "sec_edgar" in sources_found,
                "insolvency": bool(profile.get("insolvency")),
                "disqualified_directors": bool(profile.get("disqualified_officers")),
                "filing_amendments": len(profile.get("amendments", [])),
                "material_events": len(profile.get("material_events", [])),
                "bankruptcy": bool(profile.get("bankruptcy_cases")),
            }

            result = profile

            # Save for export
            _last_investigation = result

        elif name == "deep_trace":
            names = arguments["names"]
            depth = arguments.get("depth", 2)
            budget = arguments.get("budget", 50)
            max_fanout = arguments.get("max_fanout", 25)
            investigation = arguments.get("investigation")

            traversal_result = await traverse(
                icij_client=icij_client,
                os_client=os_client,
                seed_names=names,
                max_depth=depth,
                budget=budget,
                max_fanout=max_fanout,
                investigation=investigation,
                gleif_client=gleif_client,
                sec_client=sec_client,
                ch_client=ch_client,
                cl_client=cl_client,
                aleph_client=aleph_client,
                wikidata_client=wikidata_client,
                land_registry_client=land_registry_client,
            )

            result = result_to_visualizer_data(traversal_result, ", ".join(names))
            result["traversal_stats"] = traversal_result.stats
            if traversal_result.pruned:
                result["pruned_nodes"] = traversal_result.pruned
            if traversal_result.pattern_matches:
                result["pattern_matches"] = traversal_result.pattern_matches
            if traversal_result.service_warnings:
                result["service_warnings"] = traversal_result.service_warnings

            # Save for export
            _last_investigation = result

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
