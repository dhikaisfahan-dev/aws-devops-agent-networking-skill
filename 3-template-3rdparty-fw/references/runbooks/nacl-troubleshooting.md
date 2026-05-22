# Runbook: Network ACL (NACL) Troubleshooting

## Trigger Conditions
- Traffic blocked despite Security Group allowing it
- Asymmetric connectivity (one direction works, other doesn't)
- Intermittent connectivity with ephemeral port issues
- "Connection refused" when SG rules look correct
- Legacy environment with NACLs configured

---

## Key Difference: NACL vs Security Group

| Aspect | Security Group | NACL |
|--------|---------------|------|
| Stateful | ✅ Yes (return traffic auto-allowed) | ❌ No (must explicitly allow return) |
| Level | Instance/ENI level | Subnet level |
| Rules | Allow only | Allow AND Deny |
| Evaluation | All rules evaluated | Rules evaluated in order (lowest number first) |
| Default | Deny all inbound, allow all outbound | Allow all (default NACL) |

**CRITICAL:** NACLs are STATELESS. If you allow inbound port 443, you must ALSO allow outbound ephemeral ports (1024-65535) for the return traffic.

---

## Investigation Steps

### Step 1: Check if NACLs Exist on the Subnet

```bash
# Get NACL associated with the subnet
aws ec2 describe-network-acls \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query 'NetworkAcls[0].{Id:NetworkAclId,IsDefault:IsDefault,Entries:Entries}'
```

**If IsDefault=true:** Default NACL allows all traffic. NACLs are NOT the issue.
**If IsDefault=false:** Custom NACL — check rules below.

### Step 2: Check NACL Inbound Rules

```bash
aws ec2 describe-network-acls \
  --network-acl-ids <nacl-id> \
  --query 'NetworkAcls[0].Entries[?Egress==`false`].{RuleNum:RuleNumber,Action:RuleAction,Protocol:Protocol,Port:PortRange,CIDR:CidrBlock}' \
  --output table
```

**Rules are evaluated in order (lowest RuleNumber first).** First match wins.
- Rule 100: ALLOW TCP 443 from 0.0.0.0/0
- Rule 200: DENY TCP 22 from 0.0.0.0/0
- Rule *: DENY all (implicit, always last)

### Step 3: Check NACL Outbound Rules

```bash
aws ec2 describe-network-acls \
  --network-acl-ids <nacl-id> \
  --query 'NetworkAcls[0].Entries[?Egress==`true`].{RuleNum:RuleNumber,Action:RuleAction,Protocol:Protocol,Port:PortRange,CIDR:CidrBlock}' \
  --output table
```

**CRITICAL: Must allow ephemeral ports outbound for return traffic:**
- Linux: ports 32768-65535
- Windows: ports 49152-65535
- Safe range: 1024-65535 (covers all OS)

### Step 4: Check Both Source AND Destination NACLs

```bash
# Source subnet NACL
aws ec2 describe-network-acls \
  --filters "Name=association.subnet-id,Values=<source-subnet-id>" \
  --query 'NetworkAcls[0].NetworkAclId'

# Destination subnet NACL
aws ec2 describe-network-acls \
  --filters "Name=association.subnet-id,Values=<dest-subnet-id>" \
  --query 'NetworkAcls[0].NetworkAclId'

# Traffic must pass BOTH NACLs:
# Source NACL outbound → Destination NACL inbound (forward)
# Destination NACL outbound → Source NACL inbound (return)
```

### Step 5: Check VPC Flow Logs for NACL Blocks

```bash
# VPC Flow Logs show REJECT if NACL blocks traffic
# (Flow Logs don't distinguish SG reject vs NACL reject)
aws logs start-query \
  --log-group-name <flow-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, action
    | filter action = "REJECT"
    | sort @timestamp desc
    | limit 20'
```

**If SG allows but Flow Log shows REJECT → NACL is blocking.**

### Step 6: Common NACL Patterns

**Allow all (equivalent to no NACL):**
```
Inbound:  Rule 100 ALLOW all from 0.0.0.0/0
Outbound: Rule 100 ALLOW all to 0.0.0.0/0
```

**Allow web traffic with return:**
```
Inbound:
  Rule 100 ALLOW TCP 443 from 0.0.0.0/0
  Rule 110 ALLOW TCP 80 from 0.0.0.0/0
  Rule 120 ALLOW TCP 1024-65535 from 0.0.0.0/0  ← RETURN TRAFFIC
  Rule * DENY all

Outbound:
  Rule 100 ALLOW TCP 443 to 0.0.0.0/0
  Rule 110 ALLOW TCP 80 to 0.0.0.0/0
  Rule 120 ALLOW TCP 1024-65535 to 0.0.0.0/0  ← RETURN TRAFFIC
  Rule * DENY all
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Ephemeral ports not allowed outbound | Inbound works, response never returns | Add ALLOW TCP 1024-65535 outbound |
| Ephemeral ports not allowed inbound | Outbound works, response blocked | Add ALLOW TCP 1024-65535 inbound |
| DENY rule before ALLOW | Traffic blocked despite ALLOW rule | Move ALLOW rule to lower number (higher priority) |
| NACL on wrong subnet | Some instances work, others don't | Check which subnet has the custom NACL |
| NACL blocks ICMP | Ping fails but TCP works | Add ALLOW ICMP (-1) rule |
| Cross-subnet NACL | Intra-VPC traffic blocked | Check NACLs on BOTH source and destination subnets |

---

## Decision: Is It NACL or Security Group?

```
Traffic blocked (Flow Log shows REJECT)?
├── Check Security Group first (most common cause)
│   └── SG allows the traffic? → Then it's NACL
├── Check NACL on source subnet (outbound rules)
├── Check NACL on destination subnet (inbound rules)
├── Check NACL return path:
│   ├── Destination NACL outbound (ephemeral ports)
│   └── Source NACL inbound (ephemeral ports)
└── If default NACL (allows all) → Not NACL, recheck SG
```
