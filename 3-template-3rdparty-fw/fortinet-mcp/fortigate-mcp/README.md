# FortiGate MCP Server

Production-ready MCP server for FortiGate firewall investigation and management.

## Tools (10)

| Tool | Description |
|------|-------------|
| `health_check` | Check if FortiGate is online |
| `get_system_status` | Firmware, hostname, serial, uptime |
| `list_firewall_policies` | List all policies (src, dst, service, action) |
| `get_firewall_policy` | Get single policy detail by ID |
| `list_address_objects` | List address objects (subnet, FQDN, range) |
| `list_service_objects` | List service objects (TCP/UDP ports) |
| `get_routing_table` | Active routing table |
| `list_interfaces` | Interface status (up/down, IP, speed, zone) |
| `list_static_routes` | Static route configuration |
| `get_ha_status` | HA cluster status |

## Quick Start

### Environment Variables

```bash
export FORTIGATE_HOST=10.100.1.10
export FORTIGATE_API_TOKEN=your-api-token
export FORTIGATE_PORT=443
export FORTIGATE_VERIFY_SSL=false
export FORTIGATE_VDOM=root
export LOG_LEVEL=INFO
```

### Run Locally (stdio mode)

```bash
pip install -e .
python -m src.server
```

### Run with Docker

```bash
docker build -t fortigate-mcp .
docker run -e FORTIGATE_HOST=10.100.1.10 -e FORTIGATE_API_TOKEN=your-token fortigate-mcp
```

### Kiro / Claude Desktop Config

```json
{
  "mcpServers": {
    "fortigate": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/fortigate-mcp",
      "env": {
        "FORTIGATE_HOST": "10.100.1.10",
        "FORTIGATE_API_TOKEN": "your-token",
        "FORTIGATE_VERIFY_SSL": "false"
      }
    }
  }
}
```

## FortiGate API Token Setup

1. Login to FortiGate web UI
2. Go to System → Administrators
3. Create new REST API Admin
4. Set profile (read-only recommended for investigation)
5. Copy the generated API token

## Security

- Read-only by default (no write operations)
- API token stored in environment variable (not in code)
- SSL verification configurable (enable for production)
- No credentials logged
