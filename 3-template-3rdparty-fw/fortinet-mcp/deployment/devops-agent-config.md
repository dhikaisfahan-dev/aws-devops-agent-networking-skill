# Connecting Fortinet MCP Servers to AWS DevOps Agent

## After Deploying (Option A or B)

You have 3 MCP servers running. Now register them in your DevOps Agent Space.

## Step 1: Get Your MCP Endpoint URLs

**Option A (EC2):**
```
FortiAnalyzer: http://<ec2-private-ip>:8001/mcp
FortiManager:  http://<ec2-private-ip>:8002/mcp
FortiGate:     http://<ec2-private-ip>:8003/mcp
```

**Option B (ECS + ALB):**
```
All via ALB: http://<alb-dns-name>/mcp
(with path-based routing per service)
```

## Step 2: Register in DevOps Agent Space

1. Open AWS DevOps Agent console (us-east-1)
2. Select your Agent Space
3. Go to **Capabilities** tab
4. Find **MCP Servers** section
5. Click **Add MCP Server** (repeat for each)

### FortiAnalyzer MCP

| Field | Value |
|-------|-------|
| Name | `fortianalyzer` |
| Transport | Streamable HTTP |
| URL | `http://<your-endpoint>:8001/mcp` |

### FortiManager MCP

| Field | Value |
|-------|-------|
| Name | `fortimanager` |
| Transport | Streamable HTTP |
| URL | `http://<your-endpoint>:8002/mcp` |

### FortiGate MCP

| Field | Value |
|-------|-------|
| Name | `fortigate` |
| Transport | Streamable HTTP |
| URL | `http://<your-endpoint>:8003/mcp` |

## Step 3: Verify

After registering, each MCP server should show **Connected** status.

Test by chatting with the agent:
```
Check the health of all FortiGate devices
```

## Step 4: Upload the Networking Skill

The skill tells the agent WHEN and HOW to use these MCP tools:

1. Go to Agent Space → **Skills**
2. Upload `skill-template-3rdparty-fw/` as a zip
3. The skill's "Available MCP Tools" section guides the agent

## Network Connectivity

The DevOps Agent must be able to reach your MCP server endpoints:

```
DevOps Agent (AWS managed, us-east-1)
    │
    │ HTTPS (must be reachable)
    ▼
Your MCP Servers (EC2 or ECS in your VPC)
    │
    │ HTTPS (port 443)
    ▼
Fortinet Appliances (FortiGate, FortiManager, FortiAnalyzer)
```

**Options for DevOps Agent → MCP connectivity:**
- Public ALB with TLS + auth token (simplest)
- PrivateLink (most secure, same AWS org)
- VPN back to your network

## Don't Have All 3 Fortinet Products?

Only register what you have. The skill handles missing tools gracefully:

| What you have | Register | Agent behavior |
|---|---|---|
| FAZ + FMG + FGT | All 3 | Full investigation |
| FAZ + FGT | 2 | Logs + direct device |
| FGT only | 1 | Direct queries only |
| None | 0 | AWS-only, escalates firewall checks |
