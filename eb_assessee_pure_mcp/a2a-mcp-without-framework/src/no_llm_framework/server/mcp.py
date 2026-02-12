import asyncio
from pathlib import Path

from jinja2 import Template
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

dir_path = Path(__file__).parent

with Path(dir_path / "tool.jinja").open("r") as f:
    template = Template(f.read())


async def get_mcp_tool_prompt(url: str, bearer_token: str | None = None) -> str:
    """Get the MCP tool prompt for a given URL.

    Args:
        url (str): The URL of the MCP tool.
        bearer_token (str | None, optional): The bearer token for authentication. Defaults to None.

    Returns:
        str: The MCP tool prompt.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    async with streamablehttp_client(url=url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resources = await session.list_tools()
            print(f"Got tools: {[tool.name for tool in resources.tools]}")
            r = template.render(tools=resources.tools)
            # write r in a file, append
            with open(dir_path / "tool_prompt.txt", "a") as f:
                f.write(r)
            return r


async def call_mcp_tool(
    url: str,
    tool_name: str,
    arguments: dict | None = None,
    bearer_token: str | None = None,
) -> CallToolResult:
    """Call an MCP tool with the given URL and tool name.

    Args:
        url (str): The URL of the MCP tool.
        tool_name (str): The name of the tool to call.
        arguments (dict | None, optional): The arguments to pass to the tool. Defaults to None.
        bearer_token (str | None, optional): The bearer token for authentication. Defaults to None.

    Returns:
        CallToolResult: The result of the tool call.
    """  # noqa: E501
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    async with streamablehttp_client(url=url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"Calling tool {tool_name} with arguments {arguments}")
            r = await session.call_tool(tool_name, arguments=arguments)
            print(f"Got tool result: {r}")
            return r


if __name__ == "__main__":
    url = "http://localhost:9000/mcp/"
    bearer_token = "456"

    print(asyncio.run(get_mcp_tool_prompt(url, bearer_token)))
    result = asyncio.run(call_mcp_tool(url, "a-skubsjmw", bearer_token=bearer_token))
    for content in result.content:
        if isinstance(content, TextContent):
            print(content.text)
