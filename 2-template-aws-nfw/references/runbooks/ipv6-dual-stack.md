# Runbook: IPv6 Dual-Stack Troubleshooting

## Trigger Conditions
- IPv6 connectivity fails while IPv4 works
- "Network unreachable" for IPv6 destinations
- DNS returns AAAA records but connection fails
- IPv6-only services unreachable (e.g., some S3 endpoints)
- Egress-only internet gateway issues

---

## Investigation Steps

### Step 1: Check if VPC Has IPv6 CIDR

```bash
aws ec2 describe-vpcs --vpc-ids <vpc-id> \
  --query 'Vpcs[0].{IPv4:CidrBlock,IPv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock}'
```

**If no IPv6 CIDR:** VPC doesn't support IPv6. Must associate one:
```bash
aws ec2 associate-vpc-cidr-block --vpc-id <vpc-id> --amazon-provided-ipv6-cidr-block
```

### Step 2: Check Subnet IPv6 CIDR

```bash
aws ec2 describe-subnets --subnet-ids <subnet-id> \
  --query 'Subnets[0].{IPv4:CidrBlock,IPv6:Ipv6CidrBlockAssociationSet[].Ipv6CidrBlock,AssignIPv6:AssignIpv6AddressOnCreation}'
```

**If no IPv6 CIDR on subnet:** Must associate a /64 from the VPC's /56.

### Step 3: Check Instance Has IPv6 Address

```bash
aws ec2 describe-instances --instance-ids <instance-id> \
  --query 'Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses'
```

**If empty:** Instance doesn't have an IPv6 address assigned.

### Step 4: Check Route Table for IPv6

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query 'RouteTables[0].Routes[?DestinationIpv6CidrBlock!=`null`]'
```

**Expected routes:**
- `::/0 → igw-xxxxx` (public subnet — direct internet)
- `::/0 → eigw-xxxxx` (private subnet — egress-only internet gateway)
- `::/0 → tgw-xxxxx` (if routing IPv6 via TGW)

**Egress-Only Internet Gateway (EIGW):**
- Allows IPv6 outbound to internet
- Blocks IPv6 inbound from internet (like NAT GW for IPv4)
- Required for private subnets that need IPv6 internet access

### Step 5: Check Security Group for IPv6

```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<sg-id>" \
  --query 'SecurityGroupRules[?CidrIpv6!=`null`].{Direction:IsEgress,Protocol:IpProtocol,Port:ToPort,IPv6CIDR:CidrIpv6}'
```

**Common miss:** SG has `0.0.0.0/0` (IPv4) but not `::/0` (IPv6) for outbound.

### Step 6: Check NACL for IPv6

```bash
aws ec2 describe-network-acls \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query 'NetworkAcls[0].Entries[?Ipv6CidrBlock!=`null`]'
```

**NACLs need separate rules for IPv6** — IPv4 rules don't cover IPv6 traffic.

### Step 7: Check Transit Gateway IPv6 Support

```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --transit-gateway-attachment-ids <attachment-id> \
  --query 'TransitGatewayVpcAttachments[0].Options.Ipv6Support'
```

**If `disable`:** TGW attachment won't route IPv6. Enable:
```bash
aws ec2 modify-transit-gateway-vpc-attachment \
  --transit-gateway-attachment-id <id> \
  --options Ipv6Support=enable
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| No IPv6 CIDR on VPC | No IPv6 at all | Associate IPv6 CIDR block |
| No IPv6 on subnet | Instances don't get IPv6 | Associate /64 to subnet |
| Missing ::/0 route | IPv6 internet unreachable | Add route to IGW or EIGW |
| SG only has 0.0.0.0/0 | IPv6 blocked by SG | Add ::/0 to outbound rules |
| NACL missing IPv6 rules | IPv6 blocked by NACL | Add IPv6 allow rules |
| TGW IPv6 disabled | Cross-VPC IPv6 fails | Enable IPv6 on TGW attachment |
| No EIGW for private subnet | Private instances can't reach IPv6 internet | Create Egress-Only IGW |
| DNS resolves AAAA but no IPv6 path | Connection timeout | Fix routing or disable IPv6 DNS (prefer IPv4) |
