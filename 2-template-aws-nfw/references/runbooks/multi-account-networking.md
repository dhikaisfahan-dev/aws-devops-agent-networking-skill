# Runbook: Multi-Account Networking (RAM Sharing)

## Trigger Conditions
- Cross-account resource not accessible (TGW, endpoint, PHZ)
- RAM share pending acceptance
- TGW attachment from another account not routing
- VPC endpoint service not reachable cross-account
- Shared subnet not working (VPC sharing via RAM)

---

## Investigation Steps

### Step 1: Check RAM Resource Shares

```bash
# List resource shares (what's being shared)
aws ram get-resource-shares --resource-owner SELF \
  --query 'ResourceShares[].{Name:Name,Status:Status,Principals:associatedPrincipals}'

# List resources in a share
aws ram list-resources --resource-owner SELF \
  --query 'Resources[].{ARN:Arn,Type:Type,Status:Status}'

# Check pending invitations (in the RECEIVING account)
aws ram get-resource-share-invitations \
  --query 'ResourceShareInvitations[].{Id:ResourceShareInvitationArn,ShareName:ResourceShareName,Status:Status}'
```

**If status = `PENDING`:** Receiving account must accept:
```bash
aws ram accept-resource-share-invitation \
  --resource-share-invitation-arn <invitation-arn>
```

### Step 2: TGW Sharing Across Accounts

```bash
# Check TGW is shared via RAM
aws ram list-resources --resource-owner SELF \
  --resource-type ec2:TransitGateway \
  --query 'Resources[].{ARN:Arn,Status:Status}'

# In the receiving account — check if TGW is visible
aws ec2 describe-transit-gateways \
  --query 'TransitGateways[].{Id:TransitGatewayId,OwnerId:OwnerId,State:State}'

# Check cross-account attachment state
aws ec2 describe-transit-gateway-attachments \
  --filters "Name=state,Values=pendingAcceptance,available" \
  --query 'TransitGatewayAttachments[].{Id:TransitGatewayAttachmentId,ResourceOwnerId:ResourceOwnerId,State:State}'
```

**Cross-account TGW attachment flow:**
1. TGW owner shares TGW via RAM
2. Other account accepts RAM invitation
3. Other account creates VPC attachment to shared TGW
4. TGW owner accepts the attachment (if auto-accept disabled)
5. TGW owner adds routes in TGW route table

### Step 3: VPC Endpoint Service Sharing (PrivateLink)

```bash
# Check endpoint service allowed principals
aws ec2 describe-vpc-endpoint-service-permissions \
  --service-id <vpce-svc-id> \
  --query 'AllowedPrincipals[].Principal'

# Check cross-account endpoint connections
aws ec2 describe-vpc-endpoint-connections \
  --filters "Name=service-id,Values=<vpce-svc-id>" \
  --query 'VpcEndpointConnections[].{EndpointId:VpcEndpointId,State:VpcEndpointState,Owner:VpcEndpointOwner}'
```

### Step 4: Subnet Sharing (VPC Sharing via RAM)

```bash
# Check shared subnets
aws ram list-resources --resource-owner SELF \
  --resource-type ec2:Subnet \
  --query 'Resources[].{ARN:Arn,Status:Status}'

# In participant account — check if shared subnets are visible
aws ec2 describe-subnets \
  --filters "Name=owner-id,Values=<owner-account-id>" \
  --query 'Subnets[].{Id:SubnetId,VpcId:VpcId,OwnerId:OwnerId,CIDR:CidrBlock}'
```

**VPC sharing limitations:**
- Participant can launch resources in shared subnets
- Participant CANNOT modify the subnet, route table, or NACL
- Security Groups are per-account (participant uses their own SGs)
- VPC owner controls routing

### Step 5: Route 53 PHZ Sharing via RAM

```bash
# Check PHZ shared via RAM
aws ram list-resources --resource-owner SELF \
  --resource-type route53:HostedZone \
  --query 'Resources[].{ARN:Arn,Status:Status}'

# Or manual sharing (authorization-based):
aws route53 list-vpc-association-authorizations \
  --hosted-zone-id <zone-id> \
  --query 'VPCAssociationAuthorizations[].{VpcId:VPCId,Region:VPCRegion}'
```

### Step 6: Check AWS Organizations Integration

```bash
# If using Organizations — RAM can auto-share within the org
aws ram enable-sharing-with-aws-organization

# Check if sharing within org is enabled
aws ram get-resource-shares --resource-owner SELF \
  --query 'ResourceShares[?FeatureSet==`FULL`].{Name:Name,AllowExternal:AllowExternalPrincipals}'
```

**With Organizations:**
- RAM shares can target the entire org or specific OUs
- No invitation acceptance needed (auto-accepted)
- Simplifies multi-account networking

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| RAM share pending | Resource not visible in other account | Accept the invitation |
| TGW attachment pending acceptance | Cross-account VPC not routing | TGW owner must accept attachment |
| Endpoint service missing principal | Can't create cross-account endpoint | Add account to allowed principals |
| Shared subnet not visible | Can't launch in shared subnet | Accept RAM share, check region |
| PHZ not resolving cross-account | DNS fails in other account | Associate VPC with PHZ (authorization needed) |
| RAM sharing not enabled for org | Must share individually | Run enable-sharing-with-aws-organization |
| Wrong principal in RAM share | Share not reaching target | Use account ID, OU ID, or org ID correctly |

---

## Multi-Account Networking Patterns

```
Pattern 1: Centralized TGW (shared via RAM)
  - Network account owns TGW
  - Shares TGW to all workload accounts via RAM
  - Workload accounts attach their VPCs
  - Network account manages route tables

Pattern 2: Centralized Egress (shared via TGW)
  - Network account owns Inspection + Egress VPCs
  - All accounts route 0.0.0.0/0 through TGW to inspection
  - Single point of egress control

Pattern 3: Shared VPC (subnets shared via RAM)
  - Network account owns VPC + subnets
  - Shares subnets to workload accounts
  - Workload accounts launch resources in shared subnets
  - Network account controls routing + NACLs

Pattern 4: Centralized DNS (PHZ shared via RAM)
  - DNS account owns Private Hosted Zones
  - Shares PHZs to all accounts via RAM
  - All VPCs resolve the same private DNS
```
