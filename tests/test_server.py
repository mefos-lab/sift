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

`mcp` is now pinned `<2` in pyproject.toml. These tests are the part
that makes a regression loud instead of silent.
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
async def test_unknown_tool_is_handled_not_raised():
    result = await server_module.call_tool("definitely_not_a_real_tool", {})
    assert "Unknown tool" in result[0].text
