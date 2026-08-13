"""Smoke tests for the MCP server module itself.

These exist to close a real blind spot: nothing in this suite imported
`sift/server.py`, so the server could fail to load entirely and all
238 other tests would still pass green.

That is not hypothetical. The sibling repo (mefos-lab/packed) hit
exactly this: its `mcp>=1.0.0` spec was unpinned, pip resolved to mcp
2.0.0, and mcp 2.0 removed the `@server.list_tools()` /
`@server.call_tool()` decorator API both servers are built on. Its
server stopped importing and the test suite never noticed. Sift had
the identical unpinned spec and the identical missing coverage, and
was only still working because its virtualenv happened to hold an
older mcp.

This server now runs on mcp 2.x via `sift/mcp_compat.py`, which keeps
the hand-authored tool schemas instead of letting 2.0 derive them from
function signatures. That shim writes a private attribute of the SDK's
tool manager, because 2.0 offers no public way to register a pre-built
schema. `test_registered_schemas_match_definitions` is what makes that
seam safe: if a future SDK release breaks it, the schemas stop matching
and this fails loudly, rather than the server quietly advertising
degraded schemas the model then calls wrong.
"""

import pytest

import sift.server as server_module


@pytest.mark.asyncio
async def test_server_module_imports_and_lists_tools():
    """The decorator API must still be intact and tools must register."""
    tools = await server_module.list_tools()
    assert len(tools) > 0


@pytest.mark.asyncio
async def test_every_tool_has_name_description_and_schema():
    for tool in await server_module.list_tools():
        assert tool.name, "tool missing a name"
        assert tool.description, f"{tool.name} missing a description"
        assert tool.inputSchema, f"{tool.name} missing an inputSchema"


@pytest.mark.asyncio
async def test_tool_names_are_unique():
    names = [t.name for t in await server_module.list_tools()]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_every_source_family_is_represented():
    """Guards against a whole family of tools failing to register."""
    names = [t.name for t in await server_module.list_tools()]
    for prefix in (
        "icij_", "sanctions_", "gleif_", "sec_", "uk_", "court_",
        "aleph_", "land_", "wikidata_",
    ):
        assert any(n.startswith(prefix) for n in names), f"no {prefix}* tools registered"


@pytest.mark.asyncio
async def test_registered_schemas_match_definitions():
    """Every schema the SDK advertises must equal the one we authored.

    This is the guard on the mcp_compat shim. A derived-schema regression
    is silent — the tool still registers, it just loses enums, field
    descriptions or required/optional distinctions — so compare exactly.
    """
    definitions = await server_module.list_tools()
    await server_module._register()
    advertised = {t.name: t for t in await server_module.server.list_tools()}

    assert len(advertised) == len(definitions)
    for d in definitions:
        a = advertised.get(d.name)
        assert a is not None, f"{d.name} was not registered"
        assert a.input_schema == d.inputSchema, f"{d.name} schema drifted from its definition"
        assert a.description == d.description, f"{d.name} description drifted"


@pytest.mark.asyncio
async def test_enums_survive_registration():
    """Spot-check the detail most easily lost by signature-derived schemas."""
    await server_module._register()
    advertised = {t.name: t for t in await server_module.server.list_tools()}
    icij = advertised["icij_search"].input_schema["properties"]
    assert icij["entity_type"]["enum"], "icij_search entity_type enum lost"
    assert icij["investigation"]["enum"], "icij_search investigation enum lost"
    sanctions = advertised["sanctions_search"].input_schema["properties"]
    assert sanctions["schema"]["enum"] == ["Person", "Company", "Organization", "LegalEntity"]
    assert sanctions["topics"]["items"]["enum"], "sanctions_search topics enum lost"


@pytest.mark.asyncio
async def test_unknown_tool_is_handled_not_raised():
    result = await server_module.call_tool("definitely_not_a_real_tool", {})
    assert "Unknown tool" in result[0].text
