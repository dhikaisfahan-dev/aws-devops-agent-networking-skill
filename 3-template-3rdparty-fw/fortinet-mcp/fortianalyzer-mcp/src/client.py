"""
FortiAnalyzer JSON-RPC API Client.

PURPOSE:
This file handles the HTTPS connection to FortiAnalyzer.
FortiAnalyzer is the CENTRALIZED LOGGING platform for Fortinet.
It collects logs from all FortiGate devices and provides:
- Traffic log search (who connected where, was it allowed/denied)
- Security alerts (attacks detected, malware blocked)
- FortiView analytics (top talkers, top threats)
- Incident management

Like FortiManager, it uses JSON-RPC protocol (not REST).

WHY THIS IS IMPORTANT FOR NETWORK INVESTIGATION:
When the DevOps Agent needs to know "did the firewall block this traffic?",
it queries FortiAnalyzer — because FortiAnalyzer has ALL the logs from ALL firewalls.
"""

import httpx  # HTTP library
import logging
from typing import Any, Optional

logger = logging.getLogger("fortianalyzer-mcp")


class FortiAnalyzerClient:
    """
    Connects to FortiAnalyzer via its JSON-RPC API.
    
    FortiAnalyzer collects logs from all FortiGate devices.
    Usually you have ONE FortiAnalyzer receiving logs from many FortiGates.
    
    Key capabilities:
    - Search traffic logs (find specific connections)
    - Search security logs (find attacks/threats)
    - Get alerts (blocked traffic, policy violations)
    - FortiView (top sources, destinations, threats)
    - Incidents (tracked security events)
    """

    def __init__(
        self,
        host: str,          # FortiAnalyzer IP (e.g., "10.100.1.30")
        api_token: str,     # API token from FortiAnalyzer admin panel
        port: int = 443,    # HTTPS port
        verify_ssl: bool = False,  # Set True if valid SSL cert
        adom: str = "root",        # Administrative Domain
        timeout: int = 60,         # Longer timeout (log queries can be slow)
    ):
        self.base_url = f"https://{host}:{port}"
        self.api_token = api_token
        self.adom = adom
        self.timeout = timeout
        
        # Create HTTP client
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=verify_ssl,
            timeout=timeout,
        )
        self._request_id = 1

    async def _request(self, method: str, params: list[dict]) -> dict[str, Any]:
        """
        Make a JSON-RPC request to FortiAnalyzer.
        
        Same protocol as FortiManager — send JSON to /jsonrpc endpoint.
        """
        payload = {
            "method": method,
            "params": params,
            "session": self.api_token,
            "id": self._request_id,
        }
        self._request_id += 1

        response = await self._client.post("/jsonrpc", json=payload)
        response.raise_for_status()
        result = response.json()

        # Check for API errors
        if result.get("result"):
            status = result["result"][0].get("status", {})
            if status.get("code", 0) != 0:
                raise FortiAnalyzerAPIError(
                    code=status.get("code"),
                    message=status.get("message", "Unknown error"),
                )

        return result

    async def get(self, url: str, **kwargs) -> Any:
        """
        GET data from FortiAnalyzer.
        
        Example: await faz.get("/dvmdb/adom/root/device")  → list devices
        """
        params = [{"url": url, **kwargs}]
        result = await self._request("get", params)
        return result.get("result", [{}])[0].get("data", [])

    async def exec(self, url: str, data: Optional[dict] = None) -> Any:
        """
        EXECUTE an action (e.g., run a report, rescan IOCs).
        """
        params = [{"url": url}]
        if data:
            params[0]["data"] = data
        result = await self._request("exec", params)
        return result.get("result", [{}])[0].get("data", {})

    async def query_logs(
        self,
        log_type: str = "traffic",  # "traffic", "attack", "event", "virus", "webfilter"
        filter: str = "",           # Filter string (e.g., "srcip=10.0.1.229 dstip=10.1.1.214")
        time_range: int = 3600,     # How far back to search (seconds). 3600 = 1 hour
        limit: int = 50,            # Max number of results
    ) -> Any:
        """
        Search logs in FortiAnalyzer.
        
        THIS IS THE MOST IMPORTANT METHOD FOR INVESTIGATION.
        
        The DevOps Agent uses this to answer:
        "Did the firewall see this traffic? Was it allowed or denied?"
        
        Parameters:
        - log_type: What kind of logs to search
          - "traffic" = firewall policy logs (allow/deny decisions)
          - "attack" = IPS/IDS detections
          - "event" = system events (VPN, HA, admin actions)
          - "virus" = antivirus detections
          - "webfilter" = web filtering logs
        
        - filter: Search criteria
          - "srcip=10.0.1.229" = from this source IP
          - "dstip=10.1.1.214" = to this destination IP
          - "dstport=443" = to this port
          - "action=deny" = only blocked traffic
          - Combine: "srcip=10.0.1.229 dstip=10.1.1.214 dstport=443"
        
        - time_range: How far back (in seconds)
          - 3600 = last 1 hour
          - 86400 = last 24 hours
        
        Returns: List of log entries matching the filter
        """
        params = [{
            "url": f"/logview/adom/{self.adom}/logfiles/data",
            "apiver": 3,
            "devid": "",
            "logtype": log_type,
            "filter": filter,
            "time-range": time_range,
            "limit": limit,
        }]
        result = await self._request("get", params)
        return result.get("result", [{}])[0].get("data", [])

    async def get_fortiview(
        self,
        view_type: str,         # "top-sources", "top-destinations", "top-threats"
        time_range: int = 3600, # How far back
        limit: int = 20,        # Top N results
    ) -> Any:
        """
        Get FortiView analytics data.
        
        FortiView = pre-built dashboards showing top talkers, threats, etc.
        Useful for quick overview of what's happening on the network.
        """
        params = [{
            "url": f"/fortiview/adom/{self.adom}",
            "apiver": 3,
            "view-type": view_type,
            "time-range": time_range,
            "limit": limit,
        }]
        result = await self._request("get", params)
        return result.get("result", [{}])[0].get("data", [])

    async def health_check(self) -> bool:
        """Check if FortiAnalyzer is reachable."""
        try:
            result = await self._request("get", [{"url": "/sys/status"}])
            return result.get("result", [{}])[0].get("status", {}).get("code") == 0
        except Exception:
            return False

    async def close(self):
        """Close the HTTP connection."""
        await self._client.aclose()


class FortiAnalyzerAPIError(Exception):
    """
    Raised when FortiAnalyzer returns an error.
    
    Common errors:
    - -6: Invalid URL
    - -10: No permission  
    - -11: Invalid session (token expired)
    - -2: Object not found
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"FortiAnalyzer API error {code}: {message}")
