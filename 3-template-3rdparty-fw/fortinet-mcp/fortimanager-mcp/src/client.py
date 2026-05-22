"""
FortiManager JSON-RPC API Client.

PURPOSE:
This file handles the HTTPS connection to FortiManager.
FortiManager uses a different API style than FortiGate:
- FortiGate uses REST API (simple GET/POST to URLs)
- FortiManager uses JSON-RPC (send JSON commands to one endpoint: /jsonrpc)

Think of JSON-RPC like sending a letter:
- You always send it to the same address (/jsonrpc)
- Inside the letter you specify: what method (get/set/exec) and what URL path

WHY SEPARATE FROM server.py:
- client.py = HOW to talk to FortiManager (JSON-RPC protocol, authentication)
- server.py = WHAT to ask FortiManager (tools, formatting responses)
"""

import httpx  # HTTP library for making API calls
import logging
from typing import Any, Optional

logger = logging.getLogger("fortimanager-mcp")


class FortiManagerClient:
    """
    Connects to FortiManager via its JSON-RPC API.
    
    FortiManager is the CENTRALIZED management platform.
    It manages multiple FortiGate devices, their policies, and objects.
    Usually you have ONE FortiManager managing many FortiGates.
    
    Authentication: Uses an API token (session token) in every request.
    """

    def __init__(
        self,
        host: str,          # FortiManager IP (e.g., "10.100.1.20")
        api_token: str,     # API token from FortiManager admin panel
        port: int = 443,    # HTTPS port
        verify_ssl: bool = False,  # Set True if valid SSL cert
        adom: str = "root",        # Administrative Domain (most use "root")
        timeout: int = 30,         # Seconds to wait for response
    ):
        self.base_url = f"https://{host}:{port}"
        self.api_token = api_token
        self.adom = adom
        self.timeout = timeout
        
        # Create HTTP client (all requests go to /jsonrpc endpoint)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=verify_ssl,
            timeout=timeout,
        )
        # Request counter (each JSON-RPC request needs a unique ID)
        self._request_id = 1

    async def _request(self, method: str, url: str, data: Optional[dict] = None) -> dict[str, Any]:
        """
        Make a JSON-RPC request to FortiManager.
        
        This is the core method — all other methods use this.
        
        Parameters:
        - method: "get" (read data), "set" (update), "add" (create), "exec" (execute action)
        - url: The API path (e.g., "/dvmdb/device" for device list)
        - data: Optional data payload (for set/add operations)
        
        Returns: The JSON response from FortiManager
        """
        # Build the JSON-RPC payload
        payload = {
            "method": method,           # What action: get, set, add, exec
            "params": [{"url": url}],   # What resource to act on
            "session": self.api_token,  # Authentication token
            "id": self._request_id,     # Unique request ID
        }
        
        # Add data if provided (for write operations)
        if data:
            payload["params"][0]["data"] = data

        self._request_id += 1

        # Send the request to /jsonrpc (always the same endpoint)
        response = await self._client.post("/jsonrpc", json=payload)
        response.raise_for_status()
        result = response.json()

        # Check if FortiManager returned an error
        if result.get("result"):
            status = result["result"][0].get("status", {})
            if status.get("code", 0) != 0:
                raise FortiManagerAPIError(
                    code=status.get("code"),
                    message=status.get("message", "Unknown error"),
                )

        return result

    async def get(self, url: str) -> Any:
        """
        GET data from FortiManager.
        Use for: listing devices, reading policies, getting objects.
        
        Example: await fmg.get("/dvmdb/device")  → list all devices
        """
        result = await self._request("get", url)
        return result.get("result", [{}])[0].get("data", [])

    async def exec(self, url: str, data: Optional[dict] = None) -> Any:
        """
        EXECUTE an action on FortiManager.
        Use for: installing policies, running scripts, proxy commands.
        
        Example: await fmg.exec("/sys/proxy/json", data={...})
        """
        result = await self._request("exec", url, data)
        return result.get("result", [{}])[0].get("data", {})

    async def health_check(self) -> bool:
        """
        Check if FortiManager is reachable.
        Returns True if online, False if not.
        """
        try:
            result = await self._request("get", "/sys/status")
            return result.get("result", [{}])[0].get("status", {}).get("code") == 0
        except Exception:
            return False

    async def close(self):
        """Close the HTTP connection."""
        await self._client.aclose()


class FortiManagerAPIError(Exception):
    """
    Raised when FortiManager returns an error in its response.
    
    Common error codes:
    - -6: Invalid URL (wrong API path)
    - -10: No permission
    - -11: Invalid session (token expired or wrong)
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"FortiManager API error {code}: {message}")
