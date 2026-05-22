"""FortiManager MCP Server - Traditional Mode (Production Ready)."""

import os
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import FortiManagerClient, FortiManagerAPIError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("fortimanager-mcp")

client: FortiManagerClient = None


def get_client() -> FortiManagerClient:
    """Get or create FortiManager client."""
    global client
    if client is None:
        client = FortiManagerClient(
            host=os.environ["FMG_HOST"],
            api_token=os.environ["FMG_API_TOKEN"],
            port=int(os.getenv("FMG_PORT", "443")),
            verify_ssl=os.getenv("FMG_VERIFY_SSL", "false").lower() == "true",
            adom=os.getenv("FMG_ADOM", "root"),
            timeout=int(os.getenv("FMG_TIMEOUT", "30")),
        )
    return client


app = Server("fortimanager-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available FortiManager tools."""
    return [
        Tool(
            name="health_check",
            description="Check if FortiManager is online and reachable",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_system_status",
            description="Get FortiManager system status including version, hostname, and HA status",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_adoms",
            description="List all Administrative Domains (ADOMs) on FortiManager",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_devices",
            description="List all managed FortiGate devices with connection status, firmware version, and IP",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
        Tool(
            name="get_device_status",
            description="Get detailed status of a specific managed device including HA, connection state, and platform info",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_name": {"type": "string", "description": "Device name as registered in FortiManager"}
                },
                "required": ["device_name"],
            },
        ),
        Tool(
            name="list_policy_packages",
            description="List all policy packages in an ADOM. Policy packages contain firewall policies assigned to devices.",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
        Tool(
            name="get_firewall_policies",
            description="Get all firewall policies in a policy package. Shows source, destination, service, action for each rule.",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"},
                    "package": {"type": "string", "description": "Policy package name"}
                },
                "required": ["package"],
            },
        ),
        Tool(
            name="get_firewall_policy_detail",
            description="Get detailed information about a specific firewall policy by ID, including all objects and settings",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"},
                    "package": {"type": "string", "description": "Policy package name"},
                    "policy_id": {"type": "integer", "description": "Policy ID number"}
                },
                "required": ["package", "policy_id"],
            },
        ),
        Tool(
            name="list_address_objects",
            description="List all firewall address objects in an ADOM (subnets, FQDNs, IP ranges, groups)",
            inputSchema={
                "type": "object",
                "properties": {
                    "adom": {"type": "string", "description": "ADOM name (default: root)"}
                },
                "required": [],
            },
        ),
        Tool(
            name="list_service_objects",
            description="List all firewall service objects in an ADOM (TCP/UDP port definitions)",
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
    """Execute a FortiManager tool."""
    fmg = get_client()
    adom = arguments.get("adom", os.getenv("FMG_ADOM", "root"))

    try:
        if name == "health_check":
            is_healthy = await fmg.health_check()
            result = {
                "status": "healthy" if is_healthy else "unreachable",
                "host": os.environ["FMG_HOST"],
            }

        elif name == "get_system_status":
            result = await fmg.get("/sys/status")

        elif name == "list_adoms":
            result = await fmg.get("/dvmdb/adom")

        elif name == "list_devices":
            devices = await fmg.get(f"/dvmdb/adom/{adom}/device")
            result = []
            for d in devices if isinstance(devices, list) else []:
                result.append({
                    "name": d.get("name"),
                    "ip": d.get("ip"),
                    "sn": d.get("sn"),
                    "platform_str": d.get("platform_str"),
                    "os_ver": d.get("os_ver"),
                    "conn_status": d.get("conn_status"),
                    "ha_mode": d.get("ha_mode"),
                    "desc": d.get("desc"),
                })

        elif name == "get_device_status":
            device_name = arguments["device_name"]
            result = await fmg.get(f"/dvmdb/device/{device_name}")

        elif name == "list_policy_packages":
            result = await fmg.get(f"/pm/pkg/adom/{adom}")

        elif name == "get_firewall_policies":
            package = arguments["package"]
            policies = await fmg.get(f"/pm/config/adom/{adom}/pkg/{package}/firewall/policy")
            result = []
            for p in policies if isinstance(policies, list) else []:
                result.append({
                    "policyid": p.get("policyid"),
                    "name": p.get("name"),
                    "srcintf": p.get("srcintf"),
                    "dstintf": p.get("dstintf"),
                    "srcaddr": p.get("srcaddr"),
                    "dstaddr": p.get("dstaddr"),
                    "service": p.get("service"),
                    "action": p.get("action"),
                    "status": p.get("status"),
                    "logtraffic": p.get("logtraffic"),
                    "comments": p.get("comments"),
                })

        elif name == "get_firewall_policy_detail":
            package = arguments["package"]
            policy_id = arguments["policy_id"]
            result = await fmg.get(f"/pm/config/adom/{adom}/pkg/{package}/firewall/policy/{policy_id}")

        elif name == "list_address_objects":
            objects = await fmg.get(f"/pm/config/adom/{adom}/obj/firewall/address")
            result = []
            for obj in objects if isinstance(objects, list) else []:
                result.append({
                    "name": obj.get("name"),
                    "type": obj.get("type"),
                    "subnet": obj.get("subnet"),
                    "fqdn": obj.get("fqdn"),
                    "start-ip": obj.get("start-ip"),
                    "end-ip": obj.get("end-ip"),
                    "comment": obj.get("comment"),
                })

        elif name == "list_service_objects":
            objects = await fmg.get(f"/pm/config/adom/{adom}/obj/firewall/service/custom")
            result = []
            for obj in objects if isinstance(objects, list) else []:
                result.append({
                    "name": obj.get("name"),
                    "protocol": obj.get("protocol"),
                    "tcp-portrange": obj.get("tcp-portrange"),
                    "udp-portrange": obj.get("udp-portrange"),
                    "comment": obj.get("comment"),
                })

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except FortiManagerAPIError as e:
        error_msg = f"FortiManager API error: {e.code} - {e.message}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]
    except httpx.ConnectError as e:
        error_msg = f"Cannot connect to FortiManager at {os.environ['FMG_HOST']}: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]


async def main():
    """Run the MCP server."""
    logger.info(f"Starting FortiManager MCP Server (host: {os.getenv('FMG_HOST', 'not set')})")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
