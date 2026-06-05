"""JARVIS MCP Server

Exposes all JARVIS tools via the Model Context Protocol (MCP).
Edge Gallery (or any MCP client) connects to this server over SSE.

URL format: http://<desktop-ip>:8765/sse
"""
from __future__ import annotations

import asyncio
import io
import logging
import socket
from typing import Any

from mcp.server import FastMCP
from mcp.types import TextContent

from jarvis import tools as tools_module
from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)
MCP_PORT: int = 8765
MCP_HOST: str = "0.0.0.0"


def get_lan_ip() -> str:
    """Best-effort LAN IP discovery."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _generate_qr_ascii(url: str) -> str:
    """Generate ASCII QR code for terminal display."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        return buf.getvalue()
    except Exception as exc:
        _log.warning("QR generation failed: %s", exc)
        return "(qrcode module missing)"


def _make_handler(tool_name: str):
    """Factory: create an async MCP tool handler wrapping dispatch_tool."""
    async def handler(**kwargs: Any) -> list[TextContent]:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: tools_module.dispatch_tool(tool_name, kwargs)
        )
        return [TextContent(type="text", text=str(result))]

    return handler


def create_server(host: str = MCP_HOST, port: int = MCP_PORT) -> FastMCP:
    """Create and configure the JARVIS MCP server."""
    mcp = FastMCP("JARVIS", host=host, port=port)

    for td in tools_module.TOOL_DEFINITIONS:
        name = td["name"]
        description = td.get("description", "")
        handler = _make_handler(name)
        handler.__name__ = name
        handler.__doc__ = description
        mcp.add_tool(handler, name=name, description=description)
        _log.debug("Registered MCP tool: %s", name)

    _log.info("Registered %d tools", len(tools_module.TOOL_DEFINITIONS))
    return mcp


def start_server(host: str = MCP_HOST, port: int = MCP_PORT) -> None:
    """Start the MCP server and print connection info."""
    logging.basicConfig(level=logging.INFO)
    mcp = create_server(host=host, port=port)
    ip = get_lan_ip()
    url = f"http://{ip}:{port}/sse"

    _log.info("=" * 56)
    _log.info("  JARVIS MCP Server")
    _log.info("  URL: %s", url)
    _log.info("=" * 56)

    # Terminal QR code
    qr = _generate_qr_ascii(url)
    for line in qr.splitlines():
        _log.info("  %s", line)

    # Mirror to Obsidian
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        ObsidianBrain().append_daily(f"[MCP] Server started at {url}")
    except Exception:
        pass

    mcp.run(transport="sse")


def main() -> None:
    """CLI entry point."""
    start_server()


__all__ = ["create_server", "start_server", "main", "get_lan_ip"]
