# Runbook: VPC Peering Troubleshooting

## Trigger Conditions
- Cannot communicate between peered VPCs
- VPC peering connection in pending/failed state
- DNS resolution not working across peered VPCs
- Security group references not working cross-VPC

## Pre-Investigation Information Needed
- Source VPC ID and CIDR
- Destination VPC ID and CIDR
- Peering connection ID (if known)
- Protocol and port
- Whether using SG references or CIDR-based rules

---

## Investigation Steps

### Step 1: Check Peering Connection Status

```bash
# List all peering connections
aws ec2 describe-vpc-peering-connections \
  --query 'VpcPeeringConnections[].{
    Id:VpcPeeringConnectionId,
    Status:Status.Code,
    Requester:RequesterVpcInfo.{VpcId:VpcId,CIDR:CidrBlock,Region:Region},
    Accepter:AccepterVpcInfo.{VpcId:VpcId,CIDR:CidrBlock,Region:Region}
  }' --output json

# Check specific peering connection
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-xxxxx \
  --query 'VpcPeeringConnections[0].{
    Id:VpcPeeringConnectionId,
    Status:Status.Code,
    StatusMessage:Status.Message,
    RequesterVpc:RequesterVpcInfo.VpcId,
    RequesterCIDR:RequesterVpcInfo.CidrBlock,
    AccepterVpc:AccepterVpcInfo.VpcId,
    AccepterCIDR:AccepterVpcInfo.CidrBlock
  }'
```

**Expected:** Status = `active`

**If `pending-acceptance`:** The accepter VPC owner needs to accept:
```bash
aws ec2 accept-vpc-peering-connection --vpc-peering-connection-id pcx-xxxxx
```

**If `failed`:** Check status message — common reasons:
- CIDR overlap between VPCs
- Peering limit reached
- VPC doesn't exist or wrong account/region

### Step 2: Check Route Tables (BOTH VPCs)

```bash
# Check route table in VPC A (requester)
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-requester-id" \
  --query 'RouteTables[].{Id:RouteTableId,Routes:Routes[?VpcPeeringConnectionId!=`null`].{Dest:DestinationCidrBlock,Peering:VpcPeeringConnectionId,State:State}}'

# Check route table in VPC B (accepter)
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-accepter-id" \
  --query 'RouteTables[].{Id:RouteTableId,Routes:Routes[?VpcPeeringConnectionId!=`null`].{Dest:DestinationCidrBlock,Peering:VpcPeeringConnectionId,State:State}}'
```

**Expected:** Both VPCs have routes pointing to the peer's CIDR via the peering connection.

**If missing:** Add routes:
```bash
# In VPC A: route to VPC B CIDR via peering
aws ec2 create-route \
  --route-table-id rtb-vpc-a \
  --destination-cidr-block <VPC_B_CIDR> \
  --vpc-peering-connection-id pcx-xxxxx

# In VPC B: route to VPC A CIDR via peering
aws ec2 create-route \
  --route-table-id rtb-vpc-b \
  --destination-cidr-block <VPC_A_CIDR> \
  --vpc-peering-connection-id pcx-xxxxx
```

**Important:** Routes must be added to ALL subnet route tables that need peering access, not just the main route table.

### Step 3: Check for CIDR Overlap

```bash
# Get CIDRs of both VPCs
aws ec2 describe-vpcs --vpc-ids vpc-a vpc-b \
  --query 'Vpcs[].{VpcId:VpcId,CIDRs:CidrBlockAssociationSet[].CidrBlock}'
```

**VPC Peering does NOT work if CIDRs overlap.** Even partial overlap will prevent the peering from being created.

### Step 4: Check Security Groups

```bash
# Check SG in VPC A (outbound to VPC B)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-vpc-a" \
  --query 'SecurityGroupRules[?IsEgress==`true`].{Protocol:IpProtocol,Port:ToPort,Dest:CidrIpv4||ReferencedGroupInfo.GroupId}'

# Check SG in VPC B (inbound from VPC A)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-vpc-b" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{Protocol:IpProtocol,Port:ToPort,Source:CidrIpv4||ReferencedGroupInfo.GroupId}'
```

**Key point about SG references with peering:**
- ✅ SG references work across peered VPCs **in the same region**
- ❌ SG references do NOT work for **cross-region** peering — must use CIDR
- The referenced SG must be in the **peer VPC** (format: `sg-xxxxx` with the peer VPC's SG ID)

### Step 5: Check DNS Resolution (Private DNS)

```bash
# Check if DNS resolution is enabled on the peering connection
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-xxxxx \
  --query 'VpcPeeringConnections[0].{
    RequesterDnsEnabled:RequesterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc,
    AccepterDnsEnabled:AccepterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc
  }'
```

**If DNS resolution needed across peering:**
```bash
# Enable DNS resolution (must be done from both sides)
aws ec2 modify-vpc-peering-connection-options \
  --vpc-peering-connection-id pcx-xxxxx \
  --requester-peering-connection-options AllowDnsResolutionFromRemoteVpc=true

aws ec2 modify-vpc-peering-connection-options \
  --vpc-peering-connection-id pcx-xxxxx \
  --accepter-peering-connection-options AllowDnsResolutionFromRemoteVpc=true
```

### Step 6: Check VPC Flow Logs

```bash
# Check for REJECT in source VPC
aws logs start-query \
  --log-group-name /vpc/flow-logs/vpc-a \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, action
    | filter dstAddr like "<VPC_B_CIDR_PREFIX>" and action = "REJECT"
    | sort @timestamp desc
    | limit 20'
```

### Step 7: Check Transitive Routing Limitations

**VPC Peering does NOT support transitive routing:**
```
VPC A ←peering→ VPC B ←peering→ VPC C
VPC A CANNOT reach VPC C through VPC B
```

If you need transitive connectivity, use:
- Transit Gateway (recommended)
- Or create a direct peering between VPC A and VPC C

**Also NOT supported via peering:**
- Edge-to-edge routing (VPC A cannot use VPC B's IGW, NAT GW, or VPN)
- VPC A cannot reach the internet through VPC B's NAT Gateway

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Peering not accepted | Status: pending-acceptance | Accept from the other account/VPC |
| Missing route | Timeout | Add route to peer CIDR via pcx-xxxxx in BOTH VPCs |
| Route in wrong RT | Some subnets work, others don't | Add route to ALL subnet route tables |
| CIDR overlap | Peering creation fails | Cannot peer — use different CIDRs or TGW |
| SG blocking | Connection refused | Add inbound rule for peer VPC CIDR or SG ref |
| Cross-region SG ref | SG ref doesn't work | Use CIDR-based rules for cross-region peering |
| DNS not resolving | Can't resolve private hostnames | Enable DNS resolution on peering connection |
| Transitive routing | Can't reach VPC C via VPC B | Not supported — create direct peering or use TGW |
| Edge routing | Can't use peer's NAT/IGW | Not supported — each VPC needs own internet path |

---

## VPC Peering vs Transit Gateway

| Feature | VPC Peering | Transit Gateway |
|---------|-------------|-----------------|
| Transitive routing | ❌ No | ✅ Yes |
| Centralized inspection | ❌ No | ✅ Yes |
| Max connections | 125 per VPC | 5000 attachments |
| Cross-region | ✅ Yes | ✅ Yes (peering) |
| Bandwidth | No limit (within VPC limits) | 50 Gbps per attachment |
| Cost | Free (data transfer only) | Per attachment + per GB |
| SG references | ✅ Same region | ❌ No (CIDR only) |
| Complexity | Simple (point-to-point) | More complex (hub-and-spoke) |

**Use VPC Peering when:**
- Simple point-to-point connectivity between 2-3 VPCs
- No need for centralized inspection
- Cost-sensitive (no hourly charges)
- Need SG references across VPCs

**Use Transit Gateway when:**
- Many VPCs (>3) need interconnection
- Centralized firewall inspection required
- Hybrid connectivity (DX/VPN)
- Transitive routing needed
