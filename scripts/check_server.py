"""Start the MCP server the way Cursor does and confirm it answers.

uv run python scripts/check_server.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "blender_mcp"],
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = await session.list_tools()
        print(f"{len(tools.tools)} tools exposed:")
        for tool in tools.tools:
            summary = (tool.description or "").strip().splitlines()[0]
            print(f"  - {tool.name}: {summary}")

        print("\nCalling blender_status...")
        result = await session.call_tool("blender_status", {})
        payload = result.structured_content or json.loads(result.content[0].text)
        print(json.dumps(payload, indent=2))

        if result.is_error:
            print("\nblender_status reported an error.")
            return 1

    print("\nServer is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
