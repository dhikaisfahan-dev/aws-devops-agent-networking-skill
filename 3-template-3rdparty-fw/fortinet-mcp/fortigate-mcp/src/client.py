"""
FortiGate REST API Client - Multi-Device Support.

PURPOSE:
This file handles the actual HTTPS connection to FortiGate devices.
It sends API requests and returns the responses.
Think of it as the "messenger" that talks to FortiGate on behalf of the MCP server.

WHY SEPARATE FROM server.py:
- client.py = HOW to talk to FortiGate (HTTP requests, authentication)
- server.py = WHAT to ask FortiGate (tools, formatting responses)
- If FortiGate changes their API, only this file needs updating
"""

import httpx  # HTTP library for making API calls
import logging
from typing import Any, Optional

logger = logging.getLogger("fortigate-mcp")


class FortiGateClient:
    """
    Connects to a SINGLE FortiGate device via its REST API.
    
    Each FortiGate device gets its own client instance.
    The client handles:
    - HTTPS connection with API token authentication
    - Making GET requests to different API endpoints
    - Health checking (is the device reachable?)
    """

    def __init__(
        self,
        host: str,          # FortiGate IP address (e.g., "10.100.1.10")
        api_token: str,     # API token from FortiGate admin panel
        port: int = 443,    # HTTPS port (usually 443)
        verify_ssl: bool = False,  # Set True if FortiGate has valid SSL cert
        vdom: str = "root",        # Virtual Domain (most use "root")
        timeout: int = 30,         # Seconds to wait for response
    ):
        self.host = host
        self.base_url = f"https://{host}:{port}"
        self.vdom = vdom
        
        # Create the HTTP client with authentication header
        # All requests will include the API token automatically
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            verify=verify_ssl,
            timeout=timeout,
        )

    async def get(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        """
        Make a GET request to any FortiGate API path.
        Automatically adds the VDOM parameter.
        """
        if params is None:
            params = {}
        if "vdom" not in params:
            params["vdom"] = self.vdom
        response = await self._client.get(f"/api/v2/{path}", params=params)
        response.raise_for_status()  # Raises error if HTTP 4xx/5xx
        return response.json()

    async def get_monitor(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        """
        GET request to the "monitor" API.
        Monitor API = real-time data (routing table, interface status, etc.)
        """
        if params is None:
            params = {}
        if "vdom" not in params:
            params["vdom"] = self.vdom
        response = await self._client.get(f"/api/v2/monitor/{path}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_cmdb(self, path: str, params: Optional[dict] = None) -> dict[str, Any]:
        """
        GET request to the "CMDB" API.
        CMDB API = configuration data (policies, address objects, services, etc.)
        """
        if params is None:
            params = {}
        if "vdom" not in params:
            params["vdom"] = self.vdom
        response = await self._client.get(f"/api/v2/cmdb/{path}", params=params)
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """
        Simple check: can we reach this FortiGate?
        Returns True if reachable, False if not.
        """
        try:
            response = await self._client.get("/api/v2/monitor/system/status")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Close the HTTP connection."""
        await self._client.aclose()


class FortiGateManager:
    """
    Manages MULTIPLE FortiGate device connections.
    
    WHY:
    In production, you often have 2+ FortiGates (e.g., one per AZ).
    This manager lets you register all of them and query any one by name.
    
    USAGE:
    - Single device: just set FORTIGATE_HOST in .env
    - Multiple devices: create devices.json with all your FortiGates
    
    The DevOps Agent can then say:
    "list_firewall_policies on device fw-az-a"
    "list_firewall_policies on device fw-az-b"
    """

    def __init__(self):
        self._devices: dict[str, FortiGateClient] = {}  # name → client

    def add_device(
        self,
        name: str,          # Friendly name (e.g., "fw-az-a", "fw-primary")
        host: str,          # IP address
        api_token: str,     # API token
        port: int = 443,
        verify_ssl: bool = False,
        vdom: str = "root",
        timeout: int = 30,
    ):
        """Register a FortiGate device. Call this for each device you want to manage."""
        self._devices[name] = FortiGateClient(
            host=host,
            api_token=api_token,
            port=port,
            verify_ssl=verify_ssl,
            vdom=vdom,
            timeout=timeout,
        )
        logger.info(f"Registered device: {name} ({host})")

    def get_device(self, name: str) -> FortiGateClient:
        """
        Get a specific device by name.
        Raises error if device name doesn't exist.
        """
        if name not in self._devices:
            available = list(self._devices.keys())
            raise DeviceNotFoundError(
                f"Device '{name}' not found. Available devices: {available}"
            )
        return self._devices[name]

    def get_default_device(self) -> tuple[str, FortiGateClient]:
        """
        Get the first registered device.
        Used when the agent doesn't specify which device to query.
        (Works great for single-device setups)
        """
        if not self._devices:
            raise DeviceNotFoundError("No devices registered. Check your .env or devices.json")
        name = next(iter(self._devices))
        return name, self._devices[name]

    def list_devices(self) -> list[dict[str, str]]:
        """List all registered devices (name + IP)."""
        return [
            {"name": name, "host": client.host}
            for name, client in self._devices.items()
        ]

    @property
    def device_count(self) -> int:
        """How many devices are registered."""
        return len(self._devices)

    async def close_all(self):
        """Close all device connections (cleanup)."""
        for client in self._devices.values():
            await client.close()


class DeviceNotFoundError(Exception):
    """Raised when trying to access a device that isn't registered."""
    pass
