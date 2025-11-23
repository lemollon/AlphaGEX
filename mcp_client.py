"""
MCP Client for AlphaGEX
Connects to MCP servers running on Render and provides a simple interface for tool calls.
"""

import os
import json
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime


class MCPClient:
    """Client for connecting to MCP servers over HTTP/SSE"""

    def __init__(self, server_url: str, api_key: Optional[str] = None):
        """
        Initialize MCP client

        Args:
            server_url: Base URL of MCP server (e.g., https://alphagex-mcp-market-data.onrender.com)
            api_key: Optional API key for authentication
        """
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

        self._request_id = 0
        self._tools_cache = None

    def _get_next_id(self) -> int:
        """Get next request ID"""
        self._request_id += 1
        return self._request_id

    def _make_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make MCP JSON-RPC request

        Args:
            method: MCP method name (e.g., "tools/list", "tools/call")
            params: Method parameters

        Returns:
            Response result
        """
        request_data = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": method,
            "params": params or {}
        }

        try:
            response = self.session.post(
                f"{self.server_url}/message",
                json=request_data,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                raise MCPError(
                    result["error"].get("code"),
                    result["error"].get("message")
                )

            return result.get("result", {})

        except requests.exceptions.RequestException as e:
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}")

    def initialize(self) -> Dict[str, Any]:
        """Initialize connection to MCP server"""
        return self._make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "alphagex-client",
                "version": "1.0.0"
            }
        })

    def list_tools(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        List available tools on the MCP server

        Args:
            force_refresh: Force refresh of tools cache

        Returns:
            List of tool definitions
        """
        if self._tools_cache is None or force_refresh:
            result = self._make_request("tools/list")
            self._tools_cache = result.get("tools", [])

        return self._tools_cache

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on the MCP server

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        result = self._make_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        # Extract content from MCP response format
        content = result.get("content", [])
        if content and len(content) > 0:
            first_content = content[0]
            if first_content.get("type") == "text":
                # Parse JSON response
                try:
                    return json.loads(first_content.get("text", "{}"))
                except json.JSONDecodeError:
                    return first_content.get("text")

        return result

    def health_check(self) -> bool:
        """
        Check if MCP server is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.server_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False


class MCPError(Exception):
    """MCP protocol error"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"MCP Error {code}: {message}")


class MCPConnectionError(Exception):
    """MCP connection error"""
    pass


# =============================================================================
# Convenience Functions for AlphaGEX Services
# =============================================================================

def get_market_data_client() -> MCPClient:
    """Get client for market data MCP server"""
    url = os.getenv("MCP_MARKET_DATA_URL", "http://localhost:8080")
    api_key = os.getenv("MCP_API_KEY")
    return MCPClient(url, api_key)


def get_intelligence_client() -> MCPClient:
    """Get client for intelligence MCP server"""
    url = os.getenv("MCP_INTELLIGENCE_URL", "http://localhost:8081")
    api_key = os.getenv("MCP_API_KEY")
    return MCPClient(url, api_key)


def get_execution_client() -> MCPClient:
    """Get client for execution MCP server"""
    url = os.getenv("MCP_EXECUTION_URL", "http://localhost:8082")
    api_key = os.getenv("MCP_API_KEY")
    return MCPClient(url, api_key)


def get_learning_client() -> MCPClient:
    """Get client for learning MCP server"""
    url = os.getenv("MCP_LEARNING_URL", "http://localhost:8083")
    api_key = os.getenv("MCP_API_KEY")
    return MCPClient(url, api_key)


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example: Connect to market data MCP server
    client = get_market_data_client()

    # Initialize connection
    print("Initializing connection...")
    init_result = client.initialize()
    print(f"✅ Connected to {init_result['serverInfo']['name']} v{init_result['serverInfo']['version']}")

    # List available tools
    print("\n📋 Available tools:")
    tools = client.list_tools()
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    # Call a tool
    print("\n📊 Fetching GEX data for SPY...")
    try:
        result = client.call_tool("getTradingVolatilityGEX", {
            "symbol": "SPY",
            "include_history": False
        })
        print(f"✅ Net GEX: {result.get('net_gex')}")
        print(f"✅ Flip Point: {result.get('flip_point')}")
        print(f"✅ Dealer Positioning: {result.get('dealer_positioning')}")
    except MCPError as e:
        print(f"❌ Tool call failed: {e}")
    except MCPConnectionError as e:
        print(f"❌ Connection failed: {e}")

    # Health check
    print("\n🏥 Health check...")
    healthy = client.health_check()
    print(f"{'✅' if healthy else '❌'} Server health: {'OK' if healthy else 'FAILED'}")
