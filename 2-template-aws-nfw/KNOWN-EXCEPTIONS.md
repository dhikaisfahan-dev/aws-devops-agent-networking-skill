# Known Exceptions & Intentional Configurations

> **This file is OPTIONAL.** Fill it in per environment to prevent the DevOps Agent
> from flagging intentional configurations as issues during investigation.
> If left empty, the agent will investigate everything normally.

---

## How to Use This File

1. Add entries below when you have intentional network configurations that look like "issues"
2. Upload this file alongside the SKILL.md when packaging the skill zip
3. The agent will check this file before flagging findings as problems
4. Review and update quarterly — remove expired exceptions

---

## Format

Each exception should include:
- **Resource** — What resource is affected
- **Exception** — What looks wrong but is intentional
- **Reason** — Why it's configured this way
- **Approval** — Ticket/approval reference
- **Expiry** — When to review (or "permanent")

---

## Exceptions

<!-- 
Add your environment-specific exceptions below.
Delete the examples and replace with your actual exceptions.
-->

### Example Exceptions (DELETE THESE — replace with your own)

| Resource | Exception | Reason | Approval | Expiry |
|----------|-----------|--------|----------|--------|
| vpc-isolated-001 | No internet access (no NAT GW, no IGW) | Air-gapped compliance requirement | SEC-2024-001 | Permanent |
| sg-legacy-app-sg | Allows 0.0.0.0/0:22 inbound | Legacy app requires SSH from anywhere, migration planned | NET-1234 | 2026-12-31 |
| tgw-rtb-spoke: 172.30.0.0/16 | Blackhole route | Decommissioned DC, pending route cleanup | CHG-5678 | 2026-07-01 |
| <your-rule-group> | Allows all TCP 10.0.0.0/8 → 10.0.0.0/8 | Lab environment, broad rules for testing | LAB-001 | Permanent |
| vpce-svc-xxxxx | PrivateLink endpoint pending acceptance | Waiting for provider team approval | SVC-9012 | 2026-06-15 |
| nat-gw-az-b | ErrorPortAllocation > 0 occasionally | Known high-connection workload, additional NAT planned | OPS-3456 | 2026-08-01 |
| fw-policy-id-42 | Allows all from 10.5.0.0/16 | Temporary migration rule | MIG-7890 | 2026-06-30 |
| dxvif-xxxxx | BGP flapping (1-2 times/week) | Known ISP issue, failover to VPN works | ISP-TICKET-123 | Until ISP resolves |

---

## How the Agent Uses This File

When the agent finds something that looks like an issue, it checks this file:

```
Agent finds: "Security Group sg-legacy-app-sg allows 0.0.0.0/0:22 inbound"
Agent checks: Is this in KNOWN-EXCEPTIONS.md?
  → YES: "This is a known exception (NET-1234). Not flagging as issue."
  → NO: "FINDING: Security Group allows SSH from anywhere. Recommend restricting."
```

---

## Adding New Exceptions

When you approve a new exception:

1. Add a row to the table above
2. Re-zip the skill package with this updated file
3. Re-upload to DevOps Agent (Skills → Update)

Or if using the DevOps Agent UI to create skills:
1. Edit the skill → add the exception to the instructions

---

## Reviewing Exceptions

Monthly/quarterly review checklist:
- [ ] Remove expired exceptions (past their expiry date)
- [ ] Verify permanent exceptions are still valid
- [ ] Check if migration/temporary exceptions can be closed
- [ ] Update approval references if tickets are closed
