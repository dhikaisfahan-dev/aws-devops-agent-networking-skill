# Fortinet MCP Servers - Build Tracker

## Progress

| MCP Server | Status | Tools | Docker | Tested |
|---|---|---|---|---|
| **FortiGate MCP** | ✅ Built | 11/11 | ✅ | ❌ (no device to test) |
| **FortiManager MCP** | ✅ Built | 10/10 | ✅ | ❌ (no device to test) |
| **FortiAnalyzer MCP** | ✅ Built | 12/12 | ✅ | ❌ (no device to test) |

## Deployment

| Item | Status |
|---|---|
| docker-compose.yml | ✅ Done |
| Option A: EC2 guide | ✅ Done |
| Option B: ECS CloudFormation | ✅ Done |
| DevOps Agent config guide | ✅ Done |
| README.md | ✅ Done |

## FortiGate MCP - Planned Tools

| # | Tool | API Endpoint | Purpose |
|---|------|---|---|
| 1 | `health_check` | GET /api/v2/monitor/system/status | Check if FortiGate is online |
| 2 | `get_system_status` | GET /api/v2/monitor/system/status | System info, firmware, uptime |
| 3 | `list_firewall_policies` | GET /api/v2/cmdb/firewall/policy | List all policies |
| 4 | `get_firewall_policy` | GET /api/v2/cmdb/firewall/policy/{id} | Get policy detail |
| 5 | `list_address_objects` | GET /api/v2/cmdb/firewall/address | List address objects |
| 6 | `list_service_objects` | GET /api/v2/cmdb/firewall.service/custom | List service objects |
| 7 | `get_routing_table` | GET /api/v2/monitor/router/ipv4 | Active routing table |
| 8 | `list_interfaces` | GET /api/v2/monitor/system/interface | Interface status |
| 9 | `list_static_routes` | GET /api/v2/cmdb/router/static | Static route config |
| 10 | `get_ha_status` | GET /api/v2/monitor/system/ha-peer | HA cluster status |

## FortiManager MCP - Planned Tools (Traditional)

| # | Tool | API Call | Purpose |
|---|------|---|---|
| 1 | `list_devices` | get /dvmdb/device | List managed devices |
| 2 | `get_device_status` | get /dvmdb/device/{name} | Device detail + status |
| 3 | `list_policy_packages` | get /pm/pkg/adom/{adom} | List policy packages |
| 4 | `get_firewall_policies` | get /pm/config/adom/{adom}/pkg/{pkg}/firewall/policy | Policies in a package |
| 5 | `get_firewall_policy_detail` | get /pm/config/adom/{adom}/pkg/{pkg}/firewall/policy/{id} | Single policy detail |
| 6 | `list_address_objects` | get /pm/config/adom/{adom}/obj/firewall/address | Address objects |
| 7 | `list_service_objects` | get /pm/config/adom/{adom}/obj/firewall/service/custom | Service objects |
| 8 | `list_adoms` | get /dvmdb/adom | List ADOMs |
| 9 | `get_device_interfaces` | exec /sys/proxy/json (get interfaces) | Interfaces via device proxy |
| 10 | `get_install_status` | get /securityconsole/install/status | Policy install status |

## FortiAnalyzer MCP - Planned Tools

| # | Tool | API Call | Purpose |
|---|------|---|---|
| 1 | `search_traffic_logs` | /logview/adom/{adom}/logfiles/data | Search traffic logs |
| 2 | `search_security_logs` | /logview/adom/{adom}/logfiles/data | Search IPS/AV logs |
| 3 | `get_alerts` | /eventmgmt/alerts | Get security alerts |
| 4 | `get_alert_detail` | /eventmgmt/alerts/{id} | Alert detail |
| 5 | `list_devices` | /dvmdb/device | List devices reporting to FAZ |
| 6 | `get_log_stats` | /logview/adom/{adom}/logfiles/state | Log statistics |
| 7 | `get_top_sources` | /fortiview/adom/{adom} | Top traffic sources |
| 8 | `get_top_destinations` | /fortiview/adom/{adom} | Top destinations |
| 9 | `get_top_threats` | /fortiview/adom/{adom} | Top threats |
| 10 | `get_incidents` | /incidentmgmt/incidents | List incidents |
| 11 | `run_report` | /report/adom/{adom}/run | Generate report |
| 12 | `get_system_status` | /sys/status | FAZ system status |

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastMCP (Model Context Protocol SDK)
- **HTTP Client:** httpx (async)
- **Transport:** HTTP (streamable) + stdio
- **Docker:** Alpine-based, multi-stage build
- **Auth:** Bearer token for MCP endpoint, API token for Fortinet
