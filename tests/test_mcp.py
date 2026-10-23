import asyncio

import pytest
from bibfixer.mcp import build_server


def test_mcp_server_exposes_reference_tools() -> None:
    pytest.importorskip("mcp")
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert names == {"validate_references", "curate_references", "polish_references"}
    polish = next(tool for tool in tools if tool.name == "polish_references")
    assert polish.description
    assert "repair" in polish.description.lower()
