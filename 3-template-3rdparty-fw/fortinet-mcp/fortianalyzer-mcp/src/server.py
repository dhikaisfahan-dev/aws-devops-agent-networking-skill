"""FortiAnalyzer MCP Server - Production Ready."""

import os
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import FortiAnalyzerClient, FortiAnalyzerAPIError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("fortianalyzer-mcp")

client: FortiAnalyzerClient = None


def get_client() -> FortiAnalyzerClient:
    """Get or create FortiAnalyzer client."""
    global client
    if client is None:
        client = FortiAnalyzerClient(
            host=os.environ["FAZ_HOST"],
            api_token=os.environ["FAZ_API_TOKEN"],
            port=int(os.getenv("FAZ_PORT", "443")),
            verify_ssl=os.getenv("FAZ_VERIFY_SSL", "false").lower() == "true",
            adom=os.getenv("FAZ_ADOM", "root"),
            timeout=int(os.getenv("FAZ_TIMEOUT", "60")),
        )
    return client


app = Server("fortianalyzer-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available FortiAnalyzer tools."""
    return [
        Tool(
            name="health_check",
            description="Check if FortiAnalyzer is online and reachable",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_system_status",
            description="Get FortiAnalyzer system status including version, hostname, disk usage, and HA status",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_devices",
            description="List all devices reporting logs to FortiAnalyzer with connection status and last log time",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
        Tool(
            name="search_traffic_logs",
            description="Search firewall traffic logs. Filter by source IP, destination IP, port, action (allow/deny), and time range. Essential for investigating blocked or allowed traffic.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Log filter (e.g., 'srcip=10.0.1.229 dstip=10.1.1.214 dstport=443')",
                    },
                    "time_range": {
                        "type": "integer",
                        "description": "Time range in seconds to look back (default: 3600 = 1 hour)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 50)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="search_security_logs",
            description="Search IPS, antivirus, and web filter security logs. Use to find threat detections, attack signatures, and blocked malware.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Log filter (e.g., 'srcip=10.0.1.229' or 'attack=*sql*')",
                    },
                    "time_range": {
                        "type": "integer",
                        "description": "Time range in seconds (default: 3600)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 50)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="search_event_logs",
            description="Search system event logs including VPN events, HA failovers, admin logins, and configuration changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Log filter (e.g., 'logdesc=*vpn*' or 'action=login')",
                    },
                    "time_range": {
                        "type": "integer",
                        "description": "Time range in seconds (default: 3600)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 50)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_alerts",
            description="Get security alerts from FortiAnalyzer. Shows blocked attacks, policy violations, and anomalies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Optional filter for alerts",
                    },
                    "time_range": {
                        "type": "integer",
                        "description": "Time range in seconds (default: 86400 = 24 hours)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_log_stats",
            description="Get log volume statistics — total logs, logs per device, logs per type. Use to verify if a device is sending logs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
        Tool(
            name="get_top_sources",
            description="Get top traffic sources by bandwidth or session count (FortiView). Use to identify heavy talkers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_range": {"type": "integer", "description": "Time range in seconds (default: 3600)"},
                    "limit": {"type": "integer", "description": "Number of results (default: 20)"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_top_destinations",
            description="Get top traffic destinations by bandwidth or session count (FortiView)",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_range": {"type": "integer", "description": "Time range in seconds (default: 3600)"},
                    "limit": {"type": "integer", "description": "Number of results (default: 20)"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_top_threats",
            description="Get top security threats detected (FortiView). Shows attack names, severity, and affected hosts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_range": {"type": "integer", "description": "Time range in seconds (default: 86400)"},
                    "limit": {"type": "integer", "description": "Number of results (default: 20)"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_incidents",
            description="List security incidents tracked in FortiAnalyzer with status, severity, and affected assets",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a FortiAnalyzer tool."""
    faz = get_client()
    adom = arguments.get("adom", os.getenv("FAZ_ADOM", "root"))

    try:
        if name == "health_check":
            is_healthy = await faz.health_check()
            result = {
                "status": "healthy" if is_healthy else "unreachable",
                "host": os.environ["FAZ_HOST"],
            }

        elif name == "get_system_status":
            result = await faz.get("/sys/status")

        elif name == "list_devices":
            devices = await faz.get(f"/dvmdb/adom/{adom}/device")
            result = []
            for d in devices if isinstance(devices, list) else []:
                result.append({
                    "name": d.get("name"),
                    "ip": d.get("ip"),
                    "sn": d.get("sn"),
                    "platform_str": d.get("platform_str"),
                    "os_ver": d.get("os_ver"),
                    "conn_status": d.get("conn_status"),
                    "last_checked": d.get("last_checked"),
                })

        elif name == "search_traffic_logs":
            filter_str = arguments.get("filter", "")
            time_range = arguments.get("time_range", 3600)
            limit = arguments.get("limit", 50)
            result = await faz.query_logs(
                log_type="traffic",
                filter=filter_str,
                time_range=time_range,
                limit=limit,
            )

        elif name == "search_security_logs":
            filter_str = arguments.get("filter", "")
            time_range = arguments.get("time_range", 3600)
            limit = arguments.get("limit", 50)
            result = await faz.query_logs(
                log_type="attack",
                filter=filter_str,
                time_range=time_range,
                limit=limit,
            )

        elif name == "search_event_logs":
            filter_str = arguments.get("filter", "")
            time_range = arguments.get("time_range", 3600)
            limit = arguments.get("limit", 50)
            result = await faz.query_logs(
                log_type="event",
                filter=filter_str,
                time_range=time_range,
                limit=limit,
            )

        elif name == "get_alerts":
            filter_str = arguments.get("filter", "")
            time_range = arguments.get("time_range", 86400)
            result = await faz.get(
                f"/eventmgmt/adom/{adom}/alerts",
                filter=filter_str,
                time_range=time_range,
            )

        elif name == "get_log_stats":
            result = await faz.get(f"/logview/adom/{adom}/logfiles/state")

        elif name == "get_top_sources":
            time_range = arguments.get("time_range", 3600)
            limit = arguments.get("limit", 20)
            result = await faz.get_fortiview("top-sources", time_range=time_range, limit=limit)

        elif name == "get_top_destinations":
            time_range = arguments.get("time_range", 3600)
            limit = arguments.get("limit", 20)
            result = await faz.get_fortiview("top-destinations", time_range=time_range, limit=limit)

        elif name == "get_top_threats":
            time_range = arguments.get("time_range", 86400)
            limit = arguments.get("limit", 20)
            result = await faz.get_fortiview("top-threats", time_range=time_range, limit=limit)

        elif name == "get_incidents":
            result = await faz.get(f"/incidentmgmt/adom/{adom}/incidents")

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except FortiAnalyzerAPIError as e:
        error_msg = f"FortiAnalyzer API error: {e.code} - {e.message}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]
    except httpx.ConnectError as e:
        error_msg = f"Cannot connect to FortiAnalyzer at {os.environ['FAZ_HOST']}: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]


async def main():
    """Run the MCP server."""
    logger.info(f"Starting FortiAnalyzer MCP Server (host: {os.getenv('FAZ_HOST', 'not set')})")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
