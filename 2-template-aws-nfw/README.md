# Reusable Networking Skill Template

**Status:** ✅ Ready to deploy
**Last Updated:** May 2026
**Zip:** `deploy/skill-template-aws-nfw.zip` (58KB)
**For:** Environments using AWS Network Firewall with hub-and-spoke TGW architecture

This is a generic version of the networking skill that can be uploaded to any AWS DevOps Agent Space without modification.

## How to Use

### 1. Copy this folder
```bash
cp -r skill-template/ my-environment-skill/
```

### 2. Update SKILL.md (Optional)

The template SKILL.md is **environment-agnostic** — no CIDRs or resource IDs to update. The DevOps Agent discovers all VPC CIDRs, log groups, and resource IDs dynamically via AWS API calls.

Only update if your architecture differs from the standard pattern (e.g., no Network Firewall, using Cloud WAN instead of TGW, etc.).

### 3. Copy runbooks (no changes needed)
```bash
cp -r ../runbooks/ my-environment-skill/references/runbooks/
```

### 4. Optionally add environment-specific references

Add any of these to `references/`:
- Architecture diagrams specific to your environment
- Firewall rule documentation
- VPC endpoint list
- Team escalation contacts

### 5. Package as zip
```bash
cd my-environment-skill/
zip -r my-environment-skill.zip .
```

### 6. Upload to DevOps Agent
Skills → Add skill → Upload skill → select the zip

## What's Included (Generic, No Changes Needed)

| File | Content |
|------|---------|
| `SKILL.md` | Investigation methodology, path tracing, log correlation, common root causes |
| `references/runbooks/` | 7 operational runbooks (east-west, egress, ingress, AWS services, hybrid, firewall, VPC peering) |
| `references/troubleshooting-guide.md` | Decision trees, VPC/TGW/Firewall log queries |
| `references/best-practices.md` | Design principles |
| `references/cli-reference.md` | AWS CLI commands (16 sections including VPC Peering, TGW Flow Logs) |

## Architecture Requirements

This skill assumes:
- ✅ Hub-and-spoke with Transit Gateway
- ✅ Centralized inspection VPC with AWS Network Firewall
- ✅ NAT Gateway for internet egress
- ✅ VPC Endpoints centralized in inspection VPC
- ✅ Appliance Mode enabled on inspection VPC TGW attachment
- ✅ Two TGW route tables (Spoke + Firewall)
- ✅ Security Groups only (no NACLs)

If your architecture differs (e.g., Cloud WAN, third-party firewall, NACLs), you'll need to modify the investigation methodology in SKILL.md.
