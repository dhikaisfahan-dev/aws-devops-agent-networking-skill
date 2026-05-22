# Runbook: East-West Connectivity (Inter-VPC Communication)

## Trigger Conditions
- Application timeout connecting to service in another VPC
- Connection refused between workload VPCs
- Intermittent connectivity between VPCs

## Pre-Investigation Information Needed
- Source IP / Instance ID / ENI ID
- Destination IP / Instance ID / ENI ID
- Protocol (TCP/UDP)
- Port number
- Timestamp of issue

---

## Investigation Steps

### Step 1: Identify Source and Destination

```bash
# Get source instance details
aws ec2 describe-instances --instance-ids i-source \
  --query 'Reservations[].Instances[].{
    InstanceId:InstanceId,
    VpcId:VpcId,
    SubnetId:SubnetId,
    PrivateIp:PrivateIpAddress,
    AZ:Placement.AvailabilityZone,
    SGs:SecurityGroups[].GroupId
  }'

# Get destination instance details
aws ec2 describe-instances --instance-ids i-dest \
  --query 'Reservations[].Instances[].{
    InstanceId:InstanceId,
    VpcId:VpcId,
    SubnetId:SubnetId,
    PrivateIp:PrivateIpAddress,
    AZ:Placement.AvailabilityZone,
    SGs:SecurityGroups[].GroupId
  }'
```

### Step 2: Check Source Security Group (Outbound)

```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-source" \
  --query 'SecurityGroupRules[?IsEgress==`true`].{
    Protocol:IpProtocol,
    FromPort:FromPort,
    ToPort:ToPort,
    Destination:CidrIpv4||ReferencedGroupInfo.GroupId,
    Description:Description
  }' --output table
```

**Expected:** Outbound rule allowing traffic to destination CIDR or 0.0.0.0/0 on required port.

**If Missing:** Add outbound rule:
```bash
aws ec2 authorize-security-group-egress \
  --group-id sg-source \
  --ip-permissions IpProtocol=tcp,FromPort=PORT,ToPort=PORT,IpRanges='[{CidrIp=DEST_CIDR}]'
```

### Step 3: Check Source Subnet Route Table

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-source" \
  --query 'RouteTables[].Routes[].{
    Destination:DestinationCidrBlock,
    Target:GatewayId||TransitGatewayId||NatGatewayId||NetworkInterfaceId,
    State:State
  }' --output table
```

**Expected:** Route for destination CIDR (or 0.0.0.0/0) pointing to Transit Gateway.

**If Missing:** Add route:
```bash
aws ec2 create-route \
  --route-table-id rtb-source \
  --destination-cidr-block 0.0.0.0/0 \
  --transit-gateway-id tgw-xxxxx
```

### Step 4: Check TGW Spoke Route Table

```bash
# Find which TGW RT the source VPC is associated with
aws ec2 get-transit-gateway-route-table-associations \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --query 'Associations[?ResourceId==`vpc-source`]'

# Search for route to destination
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=DEST_CIDR"
```

**Expected:** Route pointing to Inspection VPC attachment (for centralized inspection).

**If Blackhole:** Check inspection VPC attachment state:
```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --filters "Name=resource-id,Values=vpc-inspection"
```

### Step 5: Check Inspection VPC - TGW Subnet Route Table

```bash
# Get TGW subnet in inspection VPC
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-inspection" "Name=tag:Name,Values=*tgw*" \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone}'

# Check route table
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-tgw-inspection" \
  --query 'RouteTables[].Routes[]'
```

**Expected:** 0.0.0.0/0 → Firewall Endpoint (vpce-fw) in the SAME AZ.

**Common Issue:** Route pointing to firewall endpoint in wrong AZ.

### Step 6: Check AWS Network Firewall

```bash
# Check firewall status
aws network-firewall describe-firewall \
  --firewall-name maybank-inspection-fw \
  --query 'FirewallStatus.{Status:Status,SyncStates:SyncStates}'

# Check alert logs for this traffic
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.src_ip = "SOURCE_IP" && $.event.dest_ip = "DEST_IP" }' \
  --start-time $(date -u -v-1H +%s000) \
  --query 'events[].message'

# Check flow logs
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/flow \
  --filter-pattern '{ $.event.src_ip = "SOURCE_IP" && $.event.dest_ip = "DEST_IP" }' \
  --start-time $(date -u -v-1H +%s000)
```

**If DROP found:** Check stateful rules:
```bash
aws network-firewall describe-rule-group \
  --rule-group-name east-west-rules \
  --type STATEFUL \
  --query 'RuleGroup.RulesSource'
```

**Fix:** Add allow rule:
```bash
# For Suricata-compatible rules
# pass tcp 10.0.0.0/16 any -> 10.1.0.0/16 PORT (msg:"Allow WL1 to WL2"; sid:1000001; rev:1;)
```

### Step 7: Check TGW Firewall Route Table

```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-firewall \
  --filters "Name=route-search.exact-match,Values=DEST_VPC_CIDR"
```

**Expected:** Route for destination VPC CIDR pointing to destination VPC attachment.

### Step 8: Check Destination Subnet Route Table

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-dest" \
  --query 'RouteTables[].Routes[]'
```

**Expected:** Local route for VPC CIDR (automatic).

### Step 9: Check Destination Security Group (Inbound)

```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-dest" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{
    Protocol:IpProtocol,
    FromPort:FromPort,
    ToPort:ToPort,
    Source:CidrIpv4||ReferencedGroupInfo.GroupId,
    Description:Description
  }' --output table
```

**Expected:** Inbound rule allowing source CIDR on required port.

**If Missing:** Add inbound rule:
```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-dest \
  --ip-permissions IpProtocol=tcp,FromPort=PORT,ToPort=PORT,IpRanges='[{CidrIp=SOURCE_CIDR}]'
```

### Step 10: Verify Return Path

Repeat steps 2-9 in reverse direction to ensure symmetric routing.

**Critical Check - Appliance Mode:**
```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --filters "Name=resource-id,Values=vpc-inspection" \
  --query 'TransitGatewayVpcAttachments[].Options.ApplianceModeSupport'
```

If `disable` → This causes intermittent failures. Enable it:
```bash
aws ec2 modify-transit-gateway-vpc-attachment \
  --transit-gateway-attachment-id tgw-attach-inspection \
  --options ApplianceModeSupport=enable
```

---

## Resolution Summary Template

```
ISSUE: [Description]
ROOT CAUSE: [Component] - [Specific issue]
RESOLUTION: [Action taken]
VERIFICATION: [How confirmed fixed]
PREVENTION: [What to add to monitoring/alerting]
```
