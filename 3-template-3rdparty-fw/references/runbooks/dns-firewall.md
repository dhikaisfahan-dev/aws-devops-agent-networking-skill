# Runbook: Route 53 DNS Firewall Troubleshooting

## Trigger Conditions
- Application can't resolve a domain (NXDOMAIN) but domain is valid
- DNS queries returning unexpected responses (NODATA, custom block page)
- "Name or service not known" for specific domains
- Some domains resolve, others don't (allowlist/blocklist issue)
- DNS Firewall alert in CloudWatch

---

## Investigation Steps

### Step 1: Check if DNS Firewall Rule Groups Exist

```bash
# List DNS Firewall rule groups
aws route53resolver list-firewall-rule-groups \
  --query 'FirewallRuleGroups[].{Id:Id,Name:Name,ShareStatus:ShareStatus}'

# Check which VPCs have DNS Firewall associated
aws route53resolver list-firewall-rule-group-associations \
  --query 'FirewallRuleGroupAssociations[].{Id:Id,Name:Name,VpcId:VpcId,RuleGroupId:FirewallRuleGroupId,Priority:Priority,Status:Status}'
```

### Step 2: Check Rules in the Rule Group

```bash
# List rules (domains being blocked/allowed)
aws route53resolver list-firewall-rules \
  --firewall-rule-group-id <rule-group-id> \
  --query 'FirewallRules[].{Name:Name,Action:Action,DomainListId:FirewallDomainListId,Priority:Priority,BlockResponse:BlockResponse}'
```

**Actions:**
- `ALLOW` — Domain is permitted
- `BLOCK` — Domain is blocked (returns NXDOMAIN, NODATA, or custom response)
- `ALERT` — Domain is logged but not blocked

### Step 3: Check Domain Lists

```bash
# List domain lists
aws route53resolver list-firewall-domain-lists \
  --query 'FirewallDomainLists[].{Id:Id,Name:Name,DomainCount:DomainCount,Status:Status}'

# Get domains in a list
aws route53resolver list-firewall-domains \
  --firewall-domain-list-id <domain-list-id> \
  --query 'Domains[]'
```

**Check if the failing domain is in a BLOCK list or NOT in an ALLOW list.**

### Step 4: Check DNS Firewall Logs (CloudWatch)

```bash
# DNS Firewall logs to CloudWatch (if enabled)
aws route53resolver list-firewall-configs \
  --query 'FirewallConfigs[].{VpcId:ResourceId,FirewallFailOpen:FirewallFailOpen}'

# Query resolver query logs for blocked queries
aws logs start-query \
  --log-group-name <resolver-query-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, query_name, query_type, rcode, firewall_rule_action, firewall_rule_group_id
    | filter firewall_rule_action = "BLOCK"
    | sort @timestamp desc
    | limit 20'
```

### Step 5: Check Firewall Fail-Open Setting

```bash
aws route53resolver list-firewall-configs \
  --query 'FirewallConfigs[].{VpcId:ResourceId,FailOpen:FirewallFailOpen}'
```

**Fail-open behavior:**
- `ENABLED` — If DNS Firewall is unavailable, queries are ALLOWED (fail-open)
- `DISABLED` — If DNS Firewall is unavailable, queries are BLOCKED (fail-closed)

### Step 6: Test DNS Resolution

```bash
# From an instance in the VPC:
dig <blocked-domain.com>
# If NXDOMAIN or REFUSED → DNS Firewall blocking

# Compare with direct query bypassing firewall (if possible):
dig @8.8.8.8 <blocked-domain.com>
# If this works → DNS Firewall is the blocker
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Domain in BLOCK list | NXDOMAIN for valid domain | Remove from block list or add to allow list |
| Domain NOT in ALLOW list (allowlist mode) | NXDOMAIN | Add domain to allow list |
| Rule priority wrong | Allow rule not taking effect | Lower priority number = evaluated first |
| DNS Firewall fail-closed | All DNS fails when service issue | Change to fail-open |
| Rule group not associated with VPC | DNS Firewall not active | Associate rule group with VPC |
| Wildcard domain blocking too broadly | Subdomains blocked unintentionally | Use more specific domain entries |

---

## DNS Firewall vs Network Firewall

| Aspect | DNS Firewall | Network Firewall |
|--------|---|---|
| What it filters | DNS queries (domain names) | Network packets (IP/port/protocol) |
| Layer | DNS (Layer 7 for DNS only) | Layer 3/4 (all traffic) |
| Blocks by | Domain name | IP, port, protocol, Suricata rules |
| Use case | Block malicious domains | Block/allow network traffic |
| Where applied | VPC-level (all DNS queries) | Subnet-level (traffic through FW endpoint) |
