"""Registration shim bridging this server's tool definitions to mcp 2.x.

Why this exists
---------------
mcp 1.x let a server hand the SDK an explicit JSON Schema per tool (via a
``@server.list_tools()`` handler returning ``Tool(inputSchema=...)``) and
dispatch every call through one ``@server.call_tool()`` function. mcp 2.0
replaced that with a tool manager that **derives** each schema from the
Python signature of a decorated function.

Migrating this server to the idiomatic 2.0 style would mean rewriting
every tool as a typed function. The schemas here are hand-authored and
carry detail a derived schema loses without extra annotation work —
enums (entity types, investigation names, OpenSanctions topics),
per-field descriptions, and required/optional distinctions. Losing any
of that is a *silent* failure: the tool still registers, the model just
calls it slightly wrong.

So instead of rewriting the schemas, this module keeps them verbatim and
adapts them to what the 2.0 tool manager wants:

1. Build a handler whose real signature matches the schema's properties
   (required params first, optional ones defaulted to ``None``), because
   the manager validates incoming arguments against the *function*
   signature, not the advertised schema.
2. Register it via ``Tool.from_function`` so all the manager's internal
   metadata is built the way it expects.
3. Overwrite the derived schema with the hand-authored one, so what is
   advertised over the wire is exactly what this repo wrote.
4. Point the handler at the existing dispatcher.

Fragility, stated plainly
-------------------------
Step 3 reaches past the public API: it writes ``tool.parameters`` and
inserts into the manager's tool dict. There is no public way to register
a pre-built schema in 2.0 — that is the whole point of the redesign — so
this is a deliberate seam, not an oversight. ``tests/test_server.py``
asserts every advertised schema is byte-identical to its source
definition, which turns a future SDK change from a silent degradation
into a failing test.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from mcp.server.mcpserver.tools.base import Tool as _ManagerTool

# JSON Schema primitive -> Python annotation, for the generated signature.
# Only the types this server's schemas actually use.
_JSON_TO_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}

Dispatch = Callable[[str, dict[str, Any]], Awaitable[Any]]


def _build_handler(name: str, schema: dict[str, Any], dispatch: Dispatch):
    """Create an async function whose signature mirrors *schema*.

    The 2.0 tool manager validates call arguments against the handler's
    signature, so a ``**kwargs`` catch-all is rejected — the parameters
    have to be real and named.
    """
    props: dict[str, dict] = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])

    params: list[str] = []
    for prop, spec in props.items():
        annotation = _JSON_TO_PY.get(spec.get("type"), "Any")
        if prop in required:
            params.append(f"{prop}: {annotation}")
        else:
            params.append(f"{prop}: Optional[{annotation}] = None")
    # Python requires defaulted parameters last; the schema's own ordering
    # doesn't guarantee that, so sort defaults to the back.
    params.sort(key=lambda p: "=" in p)

    forwarded = ", ".join(f"{p!r}: {p}" for p in props)
    source = (
        f"async def _handler({', '.join(params)}):\n"
        f"    return await _dispatch({name!r}, {{{forwarded}}})\n"
    )
    namespace: dict[str, Any] = {
        "_dispatch": dispatch, "Optional": Optional, "Any": Any,
    }
    exec(source, namespace)  # noqa: S102 - generated from our own schemas, not user input
    return namespace["_handler"]


def register_tools(server: Any, tools: list[Any], dispatch: Dispatch) -> None:
    """Register *tools* on an mcp 2.x server, preserving their schemas.

    *tools* are this repo's own tool definitions (anything exposing
    ``name``, ``description`` and ``inputSchema``). *dispatch* receives
    ``(tool_name, arguments)`` — the existing call_tool dispatcher.
    """
    for spec in tools:
        handler = _build_handler(spec.name, spec.inputSchema, dispatch)
        tool = _ManagerTool.from_function(
            handler, name=spec.name, description=spec.description,
        )
        # Advertise the hand-authored schema, not the derived one.
        tool.parameters = spec.inputSchema
        server._tool_manager._tools[spec.name] = tool
