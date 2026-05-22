# Fortinet MCP Servers

Custom-built MCP servers for integrating Fortinet firewalls with AWS DevOps Agent.

## What's Inside

```
fortinet-mcp/
├── fortigate-mcp/          ← Direct FortiGate firewall queries (multi-device)
├── fortimanager-mcp/       ← Centralized policy management
├── fortianalyzer-mcp/      ← Centralized log search & alerts
├── docker-compose.yml      ← Run all 3 together
├── deployment/
│   ├── option-a-ec2.md     ← Deploy on EC2 (simple)
│   ├── option-b-ecs.yaml   ← Deploy on ECS Fargate (production)
│   └── devops-agent-config.md  ← Register in DevOps Agent
├── BUILD-TRACKER.md        ← Build progress
└── README.md               ← This file
```

## Quick Overview

| MCP Server | Connects To | Tools | Port |
|---|---|---|---|
| **FortiGate MCP** | FortiGate directly (1 or more) | 11 tools (policies, routes, interfaces, health) | 8003 |
| **FortiManager MCP** | FortiManager (centralized mgmt) | 10 tools (devices, policies, objects) | 8002 |
| **FortiAnalyzer MCP** | FortiAnalyzer (centralized logs) | 12 tools (log search, alerts, FortiView) | 8001 |

## How It Works

```
AWS DevOps Agent
    │ "Search traffic logs for blocked traffic from 10.0.1.229"
    │
    ▼
FortiAnalyzer MCP Server (port 8001)
    │ Translates to FortiAnalyzer JSON-RPC API call
    │
    ▼
FortiAnalyzer Appliance
    │ Returns: "Policy 42 denied TCP 10.0.1.229 → 10.1.1.214:443"
    │
    ▼
DevOps Agent: "Traffic blocked by policy 42. Checking policy details..."
    │
    ▼
FortiManager MCP Server (port 8002)
    │ Gets policy 42 details
    │
    ▼
DevOps Agent: "Policy 42 denies because destination not in address group.
               Recommendation: Add 10.1.1.214 to address group 'app-servers'."
```

## Deploy

### Option A: EC2 (Simple, for lab/testing)
See `deployment/option-a-ec2.md`

### Option B: ECS Fargate (Production, always-on)
See `deployment/option-b-ecs.yaml`

## Configure

Each MCP server needs:
1. **IP address** of the Fortinet appliance it connects to
2. **API token** for authentication

| Server | Config File | What to Set |
|---|---|---|
| FortiGate | `fortigate-mcp/devices.json` | FortiGate IP(s) + token(s) |
| FortiManager | `fortimanager-mcp/.env` | FMG_HOST + FMG_API_TOKEN |
| FortiAnalyzer | `fortianalyzer-mcp/.env` | FAZ_HOST + FAZ_API_TOKEN |

## Don't Have All 3?

You don't need all 3 Fortinet products. Use what you have:

- **Only FortiGate?** → Deploy only fortigate-mcp
- **FortiGate + FortiAnalyzer?** → Deploy both (most common)
- **All 3?** → Deploy all (enterprise setup)

Comment out unused services in `docker-compose.yml`.

## Security

- All connections to Fortinet use HTTPS (port 443)
- API tokens stored in .env files (not in code)
- MCP servers are read-only (no write operations)
- Deploy in private subnet (not internet-facing)
- Use Security Groups to restrict access
