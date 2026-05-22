# Reusable Networking Skill Template (AWS Network Firewall)

**Status:** ✅ Ready to deploy
**Last Updated:** May 2026
**Zip:** `deploy/skill-template-aws-nfw.zip` (58KB)
**For:** Environments using AWS Network Firewall with hub-and-spoke TGW architecture

This skill can be uploaded to any AWS DevOps Agent Space without modification. The agent discovers the environment dynamically.

## How to Use

### 1. Upload directly (no changes needed)

```bash
# The zip is ready — just upload it
# DevOps Agent → Skills → Add skill → Upload skill → select deploy/skill-template-aws-nfw.zip
```

### 2. Or customize first (optional)

```bash
# Copy folder, add environment-specific files, re-zip
cp -r 2-template-aws-nfw/ my-skill/
# Add KNOWN-EXCEPTIONS.md entries if needed
# Add architecture diagrams if desired
cd my-skill/ && zip -r my-skill.zip SKILL.md KNOWN-EXCEPTIONS.md references/
```

## What's Included

| File | Content |
|------|---------|
| `SKILL.md` | Investigation methodology, path tracing, log correlation, DX Gateway, SD-WAN, common root causes |
| `KNOWN-EXCEPTIONS.md` | Template for environment-specific exceptions (optional, fill in per environment) |
| `references/runbooks/` | 22 operational runbooks |
| `references/troubleshooting-guide.md` | Decision trees, VPC/TGW/Firewall/CloudTrail/CloudWatch log queries |
| `references/best-practices.md` | Design principles for SG, RT, TGW, Firewall, Endpoints |
| `references/cli-reference.md` | AWS CLI commands (19 sections) |

## Runbooks (22)

| Runbook | Scenario |
|---------|----------|
| east-west-connectivity | Inter-VPC via TGW + Firewall |
| internet-egress | Outbound internet via NAT GW |
| internet-ingress | Inbound via ALB/NLB |
| aws-service-access | VPC endpoints (S3, SQS, etc.) |
| hybrid-connectivity | Direct Connect + VPN |
| firewall-investigation | AWS Network Firewall deep-dive |
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
| ipv6-dual-stack | IPv6 routing, EIGW, SG/NACL for IPv6, TGW IPv6 |
| dns-firewall | Route 53 DNS Firewall, domain blocking/allowing |
| throttling-quotas | NAT GW limits, TGW bandwidth, endpoint throughput |
| timeout-keepalive-issues | Idle timeouts, TCP keepalive, ALB/NAT/FW timeouts |
| multi-account-networking | RAM sharing, cross-account TGW/endpoints/PHZ |
| global-accelerator | GA health checks, endpoint routing, failover |

## Architecture Requirements

- ✅ Hub-and-spoke with Transit Gateway
- ✅ Centralized inspection VPC with AWS Network Firewall
- ✅ NAT Gateway for internet egress
- ✅ VPC Endpoints centralized in inspection VPC
- ✅ Appliance Mode enabled on inspection VPC TGW attachment
- ✅ Two TGW route tables (Spoke + Firewall)
- ✅ Security Groups only (no NACLs)
- ✅ Optional: Direct Connect Gateway, SD-WAN/TGW Connect, VPC Peering

If your architecture uses 3rd party firewalls (Fortinet/Palo Alto) + GWLB instead of AWS Network Firewall, use the `3-template-3rdparty-fw/` template instead.
