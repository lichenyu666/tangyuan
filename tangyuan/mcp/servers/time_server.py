"""内置 MCP time server：开箱可用的外部工具示例。"""

from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("time")


@mcp.tool()
def get_current_time() -> str:
    """返回当前本地时间（YYYY-MM-DD HH:MM:SS）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def get_current_date() -> str:
    """返回当前本地日期（YYYY-MM-DD）。"""
    return datetime.now().strftime("%Y-%m-%d")


if __name__ == "__main__":
    mcp.run()
