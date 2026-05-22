# Reusable Networking Skill Template (3rd Party Firewall + GWLB)

**Status:** ✅ Ready to deploy
**Last Updated:** May 2026
**Zip:** `deploy/skill-template-3rdparty-fw.zip` (50KB)
**MCP Servers:** `fortinet-mcp/` (built, not yet tested against live devices)
**For:** Environments using Fortinet FortiGate, Palo Alto VM-Series, or other 3rd party firewalls behind AWS Gateway Load Balancer (GWLB)

## How to Use

### 1. Upload the skill (no changes needed)

```bash
# The zip is ready — just upload it
# DevOps Agent → Skills → Add skill → Upload skill → select deploy/skill-template-3rdparty-fw.zip
```

### 2. Deploy Fortinet MCP Servers (optional, for Fortinet environments)

See `fortinet-mcp/` folder for deployment options:
- Option A: EC2 CloudFormation (`fortinet-mcp/deployment/option-a-ec2.yaml`)
- Option B: ECS Fargate CloudFormation (`fortinet-mcp/deployment/option-b-ecs.yaml`)

### 3. Register MCP in DevOps Agent

See `fortinet-mcp/deployment/devops-agent-config.md`

## What's Included

| File | Content |
|------|---------|
| `SKILL.md` | Full MCP orchestration, GWLB monitoring, DX Gateway, SD-WAN, Fortinet integration |
| `KNOWN-EXCEPTIONS.md` | Template for environment-specific exceptions (optional) |
| `MCP-SERVERS.md` | Fortinet MCP server links and reference |
| `references/runbooks/` | 16 operational runbooks |
| `fortinet-mcp/` | Custom MCP server code + deployment templates |

## Runbooks (16)

| Runbook | Scenario |
|---------|----------|
| east-west-connectivity | Inter-VPC via TGW + GWLB + Firewall |
| internet-egress | Outbound internet via NAT GW |
| internet-ingress | Inbound via ALB/NLB |
| aws-service-access | VPC endpoints (S3, SQS, etc.) |
| hybrid-connectivity | Direct Connect + VPN |
| gwlb-firewall-investigation | GWLB + 3rd party firewall deep-dive |
| vpc-peering | VPC Peering troubleshooting |
| dns-troubleshooting | Route 53 Resolver, private hosted zones |
| alb-nlb-troubleshooting | Cross-zone, cross-VPC targets, health checks |
| eks-ecs-networking | Pod-level, ENI exhaustion |
| mtu-pmtud-issues | MTU / Path MTU Discovery |
| privatelink-troubleshooting | Cross-account VPC endpoints |
| route53-phz-sharing | Private Hosted Zone sharing across accounts |
| lambda-vpc-networking | Lambda VPC attachment, ENI, NAT GW requirement |
| nacl-troubleshooting | Network ACLs, stateless rules, ephemeral ports |
| cloud-wan-troubleshooting | AWS Cloud WAN segments, policies, service insertion |

## Key Differences from AWS Network Firewall Template

| Aspect | AWS NFW Template | This Template |
|--------|-----------------|---------------|
| Inspection routing | → VPC Endpoint (vpce-fw) | → GWLB Endpoint (vpce-gwlb) |
| Health check | Managed by AWS | GWLB Target Group health |
| Firewall logs | CloudWatch (AWS API) | FortiAnalyzer MCP (if available) or escalate |
| Rule investigation | `aws network-firewall describe-rule-group` | FortiManager/FortiGate MCP (if available) or escalate |
| Scaling | Managed by AWS | Auto Scaling Group of EC2 appliances |
| MCP integration | Not needed | FortiGate + FortiManager + FortiAnalyzer MCP |

## Architecture Requirements

- ✅ Hub-and-spoke with Transit Gateway
- ✅ Gateway Load Balancer (GWLB) in inspection VPC
- ✅ 3rd party firewall appliances as GWLB targets (Fortinet/Palo Alto/other)
- ✅ GWLB Endpoints in route tables
- ✅ Appliance Mode enabled on inspection VPC TGW attachment
- ✅ Two TGW route tables (Spoke + Firewall)
- ✅ Security Groups only (no NACLs)
- ✅ Optional: Direct Connect Gateway, SD-WAN/TGW Connect, VPC Peering

## Fortinet MCP Servers

| Server | Tools | Connects To |
|--------|-------|---|
| FortiGate MCP | 11 tools | FortiGate directly (multi-device) |
| FortiManager MCP | 10 tools | FortiManager (centralized policy) |
| FortiAnalyzer MCP | 12 tools | FortiAnalyzer (centralized logs) |

Deploy with: `fortinet-mcp/deployment/option-a-ec2.yaml` or `option-b-ecs.yaml`

## Capabilities With and Without MCP

| MCP Available | Agent Can Do |
|---|---|
| FAZ + FMG + FGT | Full: search logs, check policies, verify device health |
| FMG + FGT (no FAZ) | Policy check + device status, no log search |
| FGT only | Direct device queries (policies, routes, interfaces) |
| None (MCP unreachable) | AWS-only: SG, RT, TGW, GWLB health, Flow Logs, CloudWatch |

## What Happens If MCP Server Is Unreachable

- **The agent does NOT stop investigating** — falls back to AWS-only
- Still checks: Security Groups, Route Tables, TGW, GWLB health, VPC Flow Logs, CloudWatch
- Reports: "Unable to reach MCP — firewall-level investigation unavailable"
- Recommends: "Escalate to firewall team for policy/log verification"

**To prevent MCP downtime:**
- Use ECS Fargate deployment (auto-restarts)
- Monitor `/health` endpoints with CloudWatch alarms
