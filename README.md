# AWS DevOps Agent - Networking Investigation Skills

Custom skills for [AWS DevOps Agent](https://aws.amazon.com/devops-agent/) that enable autonomous end-to-end network troubleshooting across complex AWS architectures.

## What This Is

Pre-built investigation skills that make the DevOps Agent a network engineer. Upload a zip file to your Agent Space — the agent immediately knows how to trace packets, check routing, query logs, and identify root causes across VPCs, Transit Gateway, firewalls, VPN, Direct Connect, and more.

## Choose Your Template

| Template | For Environments Using | Folder |
|----------|----------------------|--------|
| **AWS Network Firewall** | AWS-native firewall (managed) | `2-template-aws-nfw/` |
| **3rd Party Firewall + GWLB** | Fortinet, Palo Alto, Cisco behind Gateway Load Balancer | `3-template-3rdparty-fw/` |

Both templates are **environment-agnostic** — upload to any Agent Space without modification. The agent discovers the topology dynamically.

## Quick Start

```bash
# 1. Pick your template
# 2. Upload the zip to your DevOps Agent Space:
#    Agent Space → Skills → Add skill → Upload skill

# AWS Network Firewall environments:
# Upload: 2-template-aws-nfw/deploy/skill-template-aws-nfw.zip

# 3rd Party Firewall (Fortinet/PA) environments:
# Upload: 3-template-3rdparty-fw/deploy/skill-template-3rdparty-fw.zip
```

That's it. The agent is now a network investigation specialist.

## What the Agent Can Investigate

| Scenario | Covered |
|----------|:---:|
| East-West (inter-VPC via TGW) | ✅ |
| North-South Egress (internet via NAT GW) | ✅ |
| North-South Ingress (ALB/NLB) | ✅ |
| VPC Peering | ✅ |
| VPN (Site-to-Site) | ✅ |
| Direct Connect + DX Gateway | ✅ |
| SD-WAN + TGW Connect | ✅ |
| AWS Network Firewall | ✅ |
| 3rd Party Firewall + GWLB | ✅ |
| VPC Endpoints / PrivateLink | ✅ |
| DNS (Route 53 Resolver, PHZ sharing) | ✅ |
| ALB/NLB cross-zone, cross-VPC targets | ✅ |
| EKS/ECS networking (ENI exhaustion) | ✅ |
| Lambda VPC networking | ✅ |
| MTU / Path MTU Discovery | ✅ |
| Network ACLs (NACLs) | ✅ |
| AWS Cloud WAN | ✅ |
| Separate Egress VPC / Shared Services VPC | ✅ |
| CloudTrail (who changed what) | ✅ |
| CloudWatch network metrics | ✅ |
| VPC / TGW / Firewall Flow Logs | ✅ |

## 3rd Party Firewall: Fortinet MCP Integration

The 3rd party template includes custom MCP servers for deep firewall investigation:

| MCP Server | Tools | What It Does |
|---|---|---|
| FortiGate MCP | 11 | Query policies, routes, interfaces directly on FortiGate |
| FortiManager MCP | 10 | Query centralized policies, device status |
| FortiAnalyzer MCP | 12 | Search traffic logs, alerts, incidents |

Deploy with CloudFormation (EC2 or ECS Fargate). See `3-template-3rdparty-fw/fortinet-mcp/`.

**Without MCP:** The skill still works — agent investigates at AWS level and escalates firewall-specific checks to the team.

## Architecture Support

Both templates auto-detect and support:
- Combined Inspection + Egress VPC (single VPC)
- Separate Inspection VPC + Egress VPC
- Shared Services VPC (centralized endpoints, DNS)
- Transit Gateway OR Cloud WAN
- Single-region or multi-region

## Folder Structure

```
├── 2-template-aws-nfw/                 ← AWS Network Firewall skill
│   ├── deploy/skill-template-aws-nfw.zip   ← Upload this to Agent Space
│   ├── SKILL.md                        ← Investigation methodology
│   ├── KNOWN-EXCEPTIONS.md             ← Optional: environment exceptions
│   └── references/runbooks/ (16)       ← Operational runbooks
│
├── 3-template-3rdparty-fw/             ← 3rd Party Firewall + GWLB skill
│   ├── deploy/skill-template-3rdparty-fw.zip  ← Upload this to Agent Space
│   ├── SKILL.md                        ← MCP orchestration + investigation
│   ├── KNOWN-EXCEPTIONS.md             ← Optional: environment exceptions
│   ├── MCP-SERVERS.md                  ← Fortinet MCP reference
│   ├── fortinet-mcp/                   ← MCP server code + deployment
│   └── references/runbooks/ (16)       ← Operational runbooks
│
└── README.md                           ← This file
```

## Requirements

- AWS DevOps Agent Space (any region)
- IAM role with `AIDevOpsAgentAccessPolicy` in the monitored account
- (Optional) Fortinet MCP servers deployed for firewall-level investigation

## License

Internal use. Not affiliated with Fortinet, Palo Alto Networks, or Cisco.
