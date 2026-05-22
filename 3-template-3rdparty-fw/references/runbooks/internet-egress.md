# Runbook: Internet Egress (North-South Outbound)

## Trigger Conditions
- Application cannot reach external APIs
- HTTPS connections timing out to internet
- DNS resolves but TCP connection fails
- Specific domains blocked

## Pre-Investigation Information Needed
- Source IP / Instance ID
- Destination URL or IP
- Protocol and port (usually TCP 443)
- Error message (timeout, connection refused, etc.)

---

## Investigation Steps

### Step 1: Verify Source Security Group Allows Outbound

```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-source" \
  --query 'SecurityGroupRules[?IsEgress==`true` && (ToPort==`443` || IpProtocol==`-1`)].{
    Protocol:IpProtocol,
    Port:ToPort,
    Dest:CidrIpv4,
    Description:Description
  }'
```

**Expected:** Allow TCP 443 to 0.0.0.0/0 (or specific destination).

### Step 2: Verify Route Table Points to TGW

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-source" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]'
```

**Expected:** 0.0.0.0/0 → tgw-xxxxx

### Step 3: Verify TGW Spoke Route Table

```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=0.0.0.0/0"
```

**Expected:** 0.0.0.0/0 → Inspection VPC attachment

### Step 4: Check Firewall (GWLB + 3rd Party Appliance)

```bash
# Check GWLB target health
aws elbv2 describe-target-health \
  --target-group-arn <gwlb-target-group-arn> \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Health:TargetHealth.State}'

# If FortiAnalyzer MCP available — check if outbound traffic was blocked:
# → FortiAnalyzer MCP: search_traffic_logs
#   Filter: srcip=SOURCE_IP dstport=443
#   Look for: action=deny → firewall blocking outbound

# If FortiGate MCP available — check egress policies:
# → FortiGate MCP: list_firewall_policies
#   Look for policies with dstintf=wan/internet and action=deny

# If no MCP — escalate to firewall team:
# "Traffic passes GWLB (targets healthy) but doesn't reach internet.
#  Please check firewall egress/domain filtering rules for SOURCE_IP."
```
  --rules-source '{
    "RulesSourceList": {
      "Targets": [".existing-domain.com", ".new-domain.com"],
      "TargetTypes": ["TLS_SNI", "HTTP_HOST"],
      "GeneratedRulesType": "ALLOWLIST"
    }
  }' \
  --update-token "TOKEN_FROM_DESCRIBE"
```

### Step 5: Check Firewall Subnet Route Table

```bash
# Verify route to NAT Gateway exists
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-firewall-az-a" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]'
```

**Expected:** 0.0.0.0/0 → nat-xxxxx (NAT Gateway in same AZ)

### Step 6: Check NAT Gateway Status

```bash
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=vpc-inspection" \
  --query 'NatGateways[].{
    Id:NatGatewayId,
    State:State,
    SubnetId:SubnetId,
    PublicIP:NatGatewayAddresses[0].PublicIp,
    ConnectivityType:ConnectivityType
  }'
```

**Expected:** State = "available", has PublicIP assigned.

**Check for port exhaustion:**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Sum
```

### Step 7: Check Public Subnet Route Table

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-public-inspection" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]'
```

**Expected:** 0.0.0.0/0 → igw-xxxxx

### Step 8: Verify Internet Gateway

```bash
aws ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=vpc-inspection" \
  --query 'InternetGateways[].{Id:InternetGatewayId,State:Attachments[0].State}'
```

**Expected:** State = "available"

### Step 9: Check Return Path (Public Subnet → Firewall → TGW)

```bash
# Public subnet RT should route return traffic through firewall
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-public-inspection" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`10.0.0.0/8`]'
```

**Expected:** 10.0.0.0/8 → vpce-fw-xxxxx (firewall endpoint)

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Domain not in allowlist | Firewall alert log shows DROP | Add domain to allowlist rule group |
| NAT GW port exhaustion | ErrorPortAllocation > 0 | Add second NAT GW or reduce connections |
| NAT GW failed | State != available | Create new NAT GW, update route table |
| Missing route to NAT | No 0.0.0.0/0 in FW subnet RT | Add route 0.0.0.0/0 → nat-xxxxx |
| IGW detached | No IGW found for VPC | Attach IGW to inspection VPC |
| Asymmetric return path | Intermittent failures | Enable appliance mode on TGW attachment |
