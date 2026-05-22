# Runbook: AWS Network Firewall Investigation

## Trigger Conditions
- Traffic being dropped by firewall
- Need to add new allow rules
- Firewall performance issues
- Rule ordering problems
- Firewall endpoint health issues

## Pre-Investigation Information Needed
- Source and destination IPs
- Protocol and port
- Expected behavior (allow/deny)
- Firewall name/ARN
- Time window of issue

---

## Investigation Steps

### Step 1: Check Firewall Status

```bash
aws network-firewall describe-firewall \
  --firewall-name maybank-inspection-fw \
  --query '{
    Status: FirewallStatus.Status,
    ConfigSync: FirewallStatus.ConfigurationSyncStateSummary,
    Endpoints: FirewallStatus.SyncStates
  }'
```

**Expected:**
- Status: "READY"
- ConfigurationSyncStateSummary: "IN_SYNC"
- Each AZ endpoint should show "IN_SYNC"

**If NOT IN_SYNC:** Wait for sync to complete or check for configuration errors.

### Step 2: Identify Firewall Endpoints

```bash
aws network-firewall describe-firewall \
  --firewall-name maybank-inspection-fw \
  --query 'FirewallStatus.SyncStates' \
  --output json
```

Output shows endpoint IDs per AZ:
```json
{
  "ap-southeast-1a": {
    "Attachment": {
      "SubnetId": "subnet-fw-az-a",
      "EndpointId": "vpce-fw-az-a-xxxxx",
      "Status": "READY"
    }
  },
  "ap-southeast-1b": {
    "Attachment": {
      "SubnetId": "subnet-fw-az-b",
      "EndpointId": "vpce-fw-az-b-xxxxx",
      "Status": "READY"
    }
  }
}
```

### Step 3: Check Firewall Policy Structure

```bash
aws network-firewall describe-firewall-policy \
  --firewall-policy-name maybank-policy \
  --query '{
    StatelessDefaultActions: FirewallPolicy.StatelessDefaultActions,
    StatelessFragmentDefaultActions: FirewallPolicy.StatelessFragmentDefaultActions,
    StatelessRuleGroups: FirewallPolicy.StatelessRuleGroupReferences[].{Priority:Priority,ARN:ResourceArn},
    StatefulRuleGroupOrder: FirewallPolicy.StatefulEngineOptions.RuleOrder,
    StatefulDefaultActions: FirewallPolicy.StatefulDefaultActions,
    StatefulRuleGroups: FirewallPolicy.StatefulRuleGroupReferences[].{Priority:Priority,ARN:ResourceArn}
  }'
```

### Step 4: Check Alert Logs (What's Being Blocked)

```bash
# Recent alerts (blocked traffic)
aws logs start-query \
  --log-group-name /aws/network-firewall/alert \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string '
    fields @timestamp, event.src_ip, event.dest_ip, event.src_port, event.dest_port, 
           event.proto, event.alert.action, event.alert.signature, event.alert.signature_id
    | filter event.alert.action = "blocked"
    | sort @timestamp desc
    | limit 100
  '

# Wait and get results
sleep 5
aws logs get-query-results --query-id "QUERY_ID"
```

### Step 5: Check Flow Logs (What's Passing Through)

```bash
aws logs start-query \
  --log-group-name /aws/network-firewall/flow \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string '
    fields @timestamp, event.src_ip, event.dest_ip, event.src_port, event.dest_port,
           event.proto, event.app_proto, event.flow.bytes_toserver, event.flow.bytes_toclient
    | filter event.src_ip = "SOURCE_IP" and event.dest_ip = "DEST_IP"
    | sort @timestamp desc
    | limit 50
  '
```

### Step 6: Examine Stateless Rules

```bash
aws network-firewall describe-rule-group \
  --rule-group-name stateless-base-rules \
  --type STATELESS \
  --query 'RuleGroup.RulesSource.StatelessRulesAndCustomActions.StatelessRules[].{
    Priority:Priority,
    Actions:RuleDefinition.Actions,
    MatchAttributes:RuleDefinition.MatchAttributes
  }'
```

**Typical stateless rule structure:**
```
Priority 1: Pass established TCP (SYN+ACK, ACK) → aws:pass
Priority 5: Drop known bad IPs → aws:drop
Priority 99: Forward all remaining → aws:forward_to_sfe (stateful engine)
```

### Step 7: Examine Stateful Rules

```bash
# List all stateful rule groups
aws network-firewall describe-firewall-policy \
  --firewall-policy-name maybank-policy \
  --query 'FirewallPolicy.StatefulRuleGroupReferences[].{Priority:Priority,ARN:ResourceArn}'

# Check each rule group
aws network-firewall describe-rule-group \
  --rule-group-name east-west-rules \
  --type STATEFUL \
  --query '{
    RuleOrder:RuleGroup.StatefulRuleOptions.RuleOrder,
    RulesSource:RuleGroup.RulesSource
  }'
```

**Rule formats:**

Suricata-compatible rules:
```
pass tcp 10.0.0.0/16 any -> 10.1.0.0/16 443 (msg:"Allow WL1 to WL2 HTTPS"; sid:1000001; rev:1;)
pass tcp 10.0.0.0/16 any -> 10.1.0.0/16 3306 (msg:"Allow WL1 to WL2 MySQL"; sid:1000002; rev:1;)
drop tcp any any -> any any (msg:"Drop all other TCP"; sid:9999999; rev:1;)
```

Domain list rules:
```json
{
  "RulesSourceList": {
    "Targets": [".amazonaws.com", ".github.com", ".docker.io"],
    "TargetTypes": ["TLS_SNI", "HTTP_HOST"],
    "GeneratedRulesType": "ALLOWLIST"
  }
}
```

5-tuple rules:
```json
{
  "StatefulRules": [
    {
      "Action": "PASS",
      "Header": {
        "Protocol": "TCP",
        "Source": "10.0.0.0/16",
        "SourcePort": "ANY",
        "Direction": "FORWARD",
        "Destination": "10.1.0.0/16",
        "DestinationPort": "443"
      },
      "RuleOptions": [{"Keyword": "sid", "Settings": ["1"]}]
    }
  ]
}
```

### Step 8: Check Rule Evaluation Order

```bash
# Check if using STRICT_ORDER or DEFAULT_ACTION_ORDER
aws network-firewall describe-firewall-policy \
  --firewall-policy-name maybank-policy \
  --query 'FirewallPolicy.StatefulEngineOptions.RuleOrder'
```

**STRICT_ORDER:** Rules evaluated by priority number (lower = first). First match wins.
**DEFAULT_ACTION_ORDER:** Pass rules evaluated first, then drop rules, then alert rules.

**Recommendation:** Use STRICT_ORDER for predictable behavior.

### Step 9: Add New Allow Rule

```bash
# Get current rule group (need update token)
DESCRIBE=$(aws network-firewall describe-rule-group \
  --rule-group-name east-west-rules \
  --type STATEFUL)

UPDATE_TOKEN=$(echo $DESCRIBE | jq -r '.UpdateToken')

# Update with new rule (Suricata format)
aws network-firewall update-rule-group \
  --rule-group-name east-west-rules \
  --type STATEFUL \
  --rules 'pass tcp 10.0.0.0/16 any -> 10.2.0.0/16 8080 (msg:"Allow WL1 to WL3 port 8080"; sid:1000010; rev:1;)
pass tcp 10.1.0.0/16 any -> 10.2.0.0/16 8080 (msg:"Allow WL2 to WL3 port 8080"; sid:1000011; rev:1;)' \
  --update-token "$UPDATE_TOKEN"
```

### Step 10: Verify Rule Change Propagation

```bash
# Check sync status after rule change
aws network-firewall describe-firewall \
  --firewall-name maybank-inspection-fw \
  --query 'FirewallStatus.ConfigurationSyncStateSummary'

# Wait until IN_SYNC (may take 30-60 seconds)
```

---

## Firewall Performance Investigation

### Check Firewall Metrics

```bash
# Dropped packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name DroppedPackets \
  --dimensions Name=FirewallName,Value=maybank-inspection-fw Name=AvailabilityZone,Value=ap-southeast-1a \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Passed packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name PassedPackets \
  --dimensions Name=FirewallName,Value=maybank-inspection-fw \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Received packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name ReceivedPackets \
  --dimensions Name=FirewallName,Value=maybank-inspection-fw \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### Check for Capacity Issues

```bash
# TLS inspection can be resource-intensive
# Monitor these metrics for capacity planning
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name StreamExceptionPolicyPackets \
  --dimensions Name=FirewallName,Value=maybank-inspection-fw \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| No matching allow rule | Alert log shows "blocked" | Add pass rule for the traffic pattern |
| Rule priority wrong | Wrong rule matches first | Adjust priority numbers (STRICT_ORDER) |
| Default action DROP | New traffic blocked | Add explicit allow before default drop |
| Stateless not forwarding | Traffic never reaches stateful | Add aws:forward_to_sfe action |
| Config not synced | Rules not taking effect | Wait for IN_SYNC status |
| Domain not in allowlist | HTTPS blocked | Add domain to allowlist rule group |
| Asymmetric routing | Stateful drops return | Enable appliance mode on TGW attachment |
| Wrong rule format | Rule group update fails | Verify Suricata syntax or 5-tuple format |

---

## Rule Writing Best Practices

1. **Always include `sid` (signature ID)** - Required for Suricata rules
2. **Use `rev` for versioning** - Increment when modifying rules
3. **Add `msg` for documentation** - Helps identify rule purpose in logs
4. **Be specific** - Use exact CIDRs and ports, not `any any`
5. **Test in alert mode first** - Use `alert` action before `drop`
6. **Order matters** - In STRICT_ORDER, first match wins
7. **Consider both directions** - Use `<>` for bidirectional or separate rules
8. **Group related rules** - Use separate rule groups for east-west, north-south, etc.
