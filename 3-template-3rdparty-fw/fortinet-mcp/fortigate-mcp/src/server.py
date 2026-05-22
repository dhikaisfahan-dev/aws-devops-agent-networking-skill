"""FortiGate MCP Server - Multi-Device, Production Ready."""

import os
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .client import FortiGateManager, DeviceNotFoundError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("fortigate-mcp")

manager = FortiGateManager()


def init_devices():
    """
    Load FortiGate devices from devices.json config file.
    
    The config file lists all FortiGate devices to manage.
    - 1 device? Just have 1 entry in the JSON.
    - 2+ devices? Add more entries.
    """
    config_file = os.getenv("FORTIGATE_CONFIG_FILE", "devices.json")

    if not os.path.exists(config_file):
        logger.error(f"Config file not found: {config_file}")
        logger.error("Copy devices.json.template to devices.json and fill in your FortiGate details.")
        return

    with open(config_file) as f:
        config = json.load(f)

    for name, device_config in config.get("devices", {}).items():
        manager.add_device(
            name=name,
            host=device_config["host"],
            api_token=device_config["api_token"],
            port=device_config.get("port", 443),
            verify_ssl=device_config.get("verify_ssl", False),
            vdom=device_config.get("vdom", "root"),
            timeout=device_config.get("timeout", 30),
        )

    if manager.device_count == 0:
        logger.warning("No devices loaded. Check your devices.json file.")


def resolve_device(arguments: dict) -> tuple[str, Any]:
    """Resolve which device to use from arguments."""
    device_name = arguments.get("device")
    if device_name:
        return device_name, manager.get_device(device_name)
    else:
        return manager.get_default_device()


# Initialize devices on import
init_devices()

# Create MCP server
app = Server("fortigate-mcp")


DEVICE_PARAM = {
    "device": {
        "type": "string",
        "description": "Device name (optional — uses default if only one device registered). Use 'list_devices' to see available devices.",
    }
}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available FortiGate tools."""
    return [
        Tool(
            name="list_devices",
            description="List all registered FortiGate devices with their names and IPs. Use device names in other tool calls.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="health_check",
            description="Check if a FortiGate device is online and reachable",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
        Tool(
            name="get_system_status",
            description="Get FortiGate system status including firmware version, hostname, serial number, uptime",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
        Tool(
            name="list_firewall_policies",
            description="List all firewall policies with source, destination, service, and action",
            inputSchema={
                "type": "object",
                "properties": {
                    **DEVICE_PARAM,
                    "filter": {"type": "string", "description": "Optional filter (e.g., 'name=@web')"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_firewall_policy",
            description="Get detailed information about a specific firewall policy by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    **DEVICE_PARAM,
                    "policy_id": {"type": "integer", "description": "The policy ID number"},
                },
                "required": ["policy_id"],
            },
        ),
        Tool(
            name="list_address_objects",
            description="List all firewall address objects (subnets, IP ranges, FQDNs)",
            inputSchema={
                "type": "object",
                "properties": {
                    **DEVICE_PARAM,
                    "filter": {"type": "string", "description": "Optional filter"},
                },
                "required": [],
            },
        ),
        Tool(
            name="list_service_objects",
            description="List all firewall service objects (TCP/UDP ports)",
            inputSchema={
                "type": "object",
                "properties": {
                    **DEVICE_PARAM,
                    "filter": {"type": "string", "description": "Optional filter"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_routing_table",
            description="Get the active routing table showing all routes, next-hops, and interfaces",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
        Tool(
            name="list_interfaces",
            description="List all network interfaces with status (up/down), IP, speed, and zone",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
        Tool(
            name="list_static_routes",
            description="List all configured static routes",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
        Tool(
            name="get_ha_status",
            description="Get High Availability cluster status",
            inputSchema={"type": "object", "properties": {**DEVICE_PARAM}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a FortiGate tool."""
    try:
        # list_devices doesn't need a device connection
        if name == "list_devices":
            result = manager.list_devices()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # All other tools need a device
        device_name, fgt = resolve_device(arguments)

        if name == "health_check":
            is_healthy = await fgt.health_check()
            result = {"device": device_name, "host": fgt.host, "status": "healthy" if is_healthy else "unreachable"}

        elif name == "get_system_status":
            data = await fgt.get_monitor("system/status")
            result = {"device": device_name, **data.get("results", data)}

        elif name == "list_firewall_policies":
            params = {}
            if arguments.get("filter"):
                params["filter"] = arguments["filter"]
            data = await fgt.get_cmdb("firewall/policy", params)
            policies = data.get("results", [])
            result = []
            for p in policies:
                result.append({
                    "policyid": p.get("policyid"),
                    "name": p.get("name"),
                    "srcintf": [i.get("name") for i in p.get("srcintf", [])],
                    "dstintf": [i.get("name") for i in p.get("dstintf", [])],
                    "srcaddr": [a.get("name") for a in p.get("srcaddr", [])],
                    "dstaddr": [a.get("name") for a in p.get("dstaddr", [])],
                    "service": [s.get("name") for s in p.get("service", [])],
                    "action": p.get("action"),
                    "status": p.get("status"),
                    "logtraffic": p.get("logtraffic"),
                })

        elif name == "get_firewall_policy":
            policy_id = arguments["policy_id"]
            data = await fgt.get_cmdb(f"firewall/policy/{policy_id}")
            result = data.get("results", [{}])
            if isinstance(result, list) and len(result) > 0:
                result = result[0]

        elif name == "list_address_objects":
            params = {}
            if arguments.get("filter"):
                params["filter"] = arguments["filter"]
            data = await fgt.get_cmdb("firewall/address", params)
            objects = data.get("results", [])
            result = [
                {"name": o.get("name"), "type": o.get("type"), "subnet": o.get("subnet"),
                 "fqdn": o.get("fqdn"), "start-ip": o.get("start-ip"), "end-ip": o.get("end-ip")}
                for o in objects
            ]

        elif name == "list_service_objects":
            params = {}
            if arguments.get("filter"):
                params["filter"] = arguments["filter"]
            data = await fgt.get_cmdb("firewall.service/custom", params)
            objects = data.get("results", [])
            result = [
                {"name": o.get("name"), "protocol": o.get("protocol"),
                 "tcp-portrange": o.get("tcp-portrange"), "udp-portrange": o.get("udp-portrange")}
                for o in objects
            ]

        elif name == "get_routing_table":
            data = await fgt.get_monitor("router/ipv4")
            result = data.get("results", [])

        elif name == "list_interfaces":
            data = await fgt.get_monitor("system/interface")
            interfaces = data.get("results", [])
            result = [
                {"name": i.get("name"), "ip": i.get("ip"), "status": i.get("link"),
                 "speed": i.get("speed"), "type": i.get("type"), "zone": i.get("zone")}
                for i in interfaces
            ]

        elif name == "list_static_routes":
            data = await fgt.get_cmdb("router/static")
            routes = data.get("results", [])
            result = [
                {"seq-num": r.get("seq-num"), "dst": r.get("dst"), "gateway": r.get("gateway"),
                 "device": r.get("device"), "distance": r.get("distance"), "status": r.get("status")}
                for r in routes
            ]

        elif name == "get_ha_status":
            data = await fgt.get_monitor("system/ha-peer")
            result = {"device": device_name, **data.get("results", data)}

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except DeviceNotFoundError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]


async def main():
    """Run the MCP server."""
    logger.info(f"Starting FortiGate MCP Server ({manager.device_count} devices registered)")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
