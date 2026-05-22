# Reusable Networking Skill Template (3rd Party Firewall + GWLB)

**Status:** ✅ Ready to deploy
**Last Updated:** May 2026
**Zip:** `deploy/skill-template-3rdparty-fw.zip` (45KB)
**MCP Servers:** `fortinet-mcp/` (built, not yet tested against live devices)
**For:** Environments using Fortinet FortiGate, Palo Alto VM-Series, or other 3rd party firewalls behind AWS Gateway Load Balancer (GWLB)

For environments using Fortinet FortiGate, Palo Alto VM-Series, or other 3rd party firewalls behind AWS Gateway Load Balancer (GWLB).

## How to Use

### 1. Copy this folder
```bash
cp -r skill-template-3rdparty-fw/ my-environment-skill/
```

### 2. Update SKILL.md (Optional)

The template is environment-agnostic — no CIDRs or resource IDs to update. The DevOps Agent discovers everything dynamically via AWS API.

Only update if your architecture differs from the standard pattern.

### 3. Copy runbooks
```bash
# Runbooks are shared — copy from the main runbooks folder
cp ../runbooks/*.md my-environment-skill/references/runbooks/
```

### 4. Package and upload
```bash
cd my-environment-skill/
zip -r my-skill.zip .
# Upload to DevOps Agent → Skills → Add skill → Upload skill
```

## What's Included

| File | Content |
|------|---------|
| `SKILL.md` | Investigation methodology for GWLB + 3rd party firewall architecture |
| `references/runbooks/` | Copy from main runbooks (shared) |

## Key Differences from AWS Network Firewall Template

| Aspect | AWS NFW Template | This Template |
|--------|-----------------|---------------|
| Inspection routing | → VPC Endpoint (vpce-fw) | → GWLB Endpoint (vpce-gwlb) |
| Health check | N/A (managed) | GWLB Target Group health |
| Firewall logs | CloudWatch (AWS API) | Appliance-specific (NOT AWS API) |
| Rule investigation | `aws network-firewall describe-rule-group` | Escalate to firewall team |
| Scaling | Managed | Auto Scaling Group |

## Architecture Requirements

- ✅ Hub-and-spoke with Transit Gateway
- ✅ Gateway Load Balancer (GWLB) in inspection VPC
- ✅ 3rd party firewall appliances as GWLB targets (Fortinet/Palo Alto/other)
- ✅ GWLB Endpoints in route tables
- ✅ Appliance Mode enabled on inspection VPC TGW attachment
- ✅ Two TGW route tables (Spoke + Firewall)
- ✅ Security Groups only (no NACLs)

## Limitations

- Agent CAN query Fortinet firewall rules, logs, and device status via MCP servers (FortiGate, FortiManager, FortiAnalyzer)
- Agent CANNOT query non-Fortinet appliances (Palo Alto, Cisco, Check Point) — no MCP server available yet
- Agent CAN check: GWLB health, routing, EC2 appliance status, VPC Flow Logs, TGW Flow Logs (via AWS API)
- Agent CANNOT modify firewall rules — always recommends and escalates to firewall team
- If traffic reaches a non-Fortinet appliance but doesn't pass → escalate to firewall team

## What Happens If MCP Server Is Unreachable

If the Fortinet MCP server is down, unreachable, or returns errors:

- **The agent does NOT stop investigating** — it falls back to AWS-only investigation
- The agent will still check: Security Groups, Route Tables, TGW, GWLB health, VPC Flow Logs, CloudWatch metrics
- The agent will report: "Unable to reach FortiAnalyzer/FortiManager/FortiGate MCP — firewall-level investigation unavailable"
- The agent will recommend: "Escalate to firewall team for policy/log verification"

**The skill handles this gracefully** (see SKILL.md "Decision: Which MCP Tools Are Available?" section):
```
FAZ + FMG + FGT available → Full autonomous investigation
FMG + FGT only            → Policy check OK, no log search
FGT only                  → Direct device check only
None available            → AWS-only investigation, escalate all firewall checks
```

**To prevent MCP downtime:**
- Use ECS Fargate deployment (auto-restarts crashed containers)
- Monitor MCP health endpoints (`/health`) with CloudWatch alarms
- Set `restart: unless-stopped` in Docker Compose
