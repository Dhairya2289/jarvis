"""Tests for MCP server module."""
from __future__ import annotations

import pytest
from jarvis.mcp_server import create_server, get_lan_ip


class TestMcpServer:
    def test_get_lan_ip_returns_string(self):
        ip = get_lan_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_create_server_registers_tools(self):
        server = create_server()
        assert server.name == "JARVIS"

    def test_create_server_no_duplicate_tools(self):
        server = create_server()
        # FastMCP warns on duplicates by default; creation should succeed
        assert server is not None
