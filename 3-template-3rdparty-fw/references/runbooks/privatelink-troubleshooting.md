# Runbook: PrivateLink (Cross-Account VPC Endpoints)

## Trigger Conditions
- Can't reach a service exposed via PrivateLink from another account
- VPC endpoint stuck in "pendingAcceptance" state
- DNS not resolving for PrivateLink service
- Connection timeout to PrivateLink endpoint
- "Access denied" when connecting to endpoint service

---

## Investigation Steps

### Step 1: Check VPC Endpoint Service (Provider Side)

```bash
# List endpoint services you own
aws ec2 describe-vpc-endpoint-service-configurations \
  --query 'ServiceConfigurations[].{Id:ServiceId,Name:ServiceName,State:ServiceState,Type:ServiceType,AcceptanceRequired:AcceptanceRequired,NLB:NetworkLoadBalancerArns}'

# Check allowed principals (who can create endpoints to this service)
aws ec2 describe-vpc-endpoint-service-permissions \
  --service-id vpce-svc-xxxxx \
  --query 'AllowedPrincipals[].Principal'
```

**IF consumer account not in allowed principals:**
```bash
aws ec2 modify-vpc-endpoint-service-permissions \
  --service-id vpce-svc-xxxxx \
  --add-allowed-principals "arn:aws:iam::<consumer-account-id>:root"
```

### Step 2: Check VPC Endpoint (Consumer Side)

```bash
# List endpoints in consumer VPC
aws ec2 describe-vpc-endpoints \
  --filters "Name=service-name,Values=<service-name>" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,State:State,ServiceName:ServiceName,VpcId:VpcId,Subnets:SubnetIds,SGs:Groups[].GroupId,DNS:DnsEntries[0].DnsName,PrivateDns:PrivateDnsEnabled}'
```

**Expected:** State = `available`

**If `pendingAcceptance`:** Provider must accept the connection:
```bash
# On provider side:
aws ec2 accept-vpc-endpoint-connections \
  --service-id vpce-svc-xxxxx \
  --vpc-endpoint-ids vpce-consumer-xxxxx
```

**If `rejected` or `failed`:** Check allowed principals and recreate.

### Step 3: Check Endpoint Connections (Provider Side)

```bash
aws ec2 describe-vpc-endpoint-connections \
  --filters "Name=service-id,Values=vpce-svc-xxxxx" \
  --query 'VpcEndpointConnections[].{EndpointId:VpcEndpointId,State:VpcEndpointState,Owner:VpcEndpointOwner,CreationTime:CreationTimestamp}'
```

### Step 4: Check DNS Resolution (Consumer Side)

```bash
# If private DNS enabled: service domain resolves to endpoint private IP
dig +short <service-domain-name>
# Should return private IP (10.x.x.x) not public

# If private DNS NOT enabled: must use endpoint-specific DNS
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[0].DnsEntries[].DnsName'
# Use the regional DNS name: vpce-xxxxx.svc.region.vpce.amazonaws.com
```

**Private DNS requirements:**
- VPC must have `enableDnsSupport` = true
- VPC must have `enableDnsHostnames` = true
- Only ONE endpoint per service can have private DNS enabled per VPC

### Step 5: Check Security Groups

```bash
# Consumer endpoint SG (must allow outbound to service port)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<endpoint-sg>" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{Protocol:IpProtocol,Port:ToPort,Source:CidrIpv4}'

# The endpoint SG must allow INBOUND from the consumer VPC CIDR on the service port
# Example: If service runs on port 443:
# Inbound: TCP 443 from 10.0.0.0/16 (consumer VPC CIDR)
```

**Provider side (NLB):**
- NLB doesn't have a security group
- But the NLB targets (EC2/containers) have SGs
- Target SG must allow traffic from the NLB subnet CIDR or the endpoint private IPs

### Step 6: Check AZ Alignment

```bash
# PrivateLink endpoints must be in the SAME AZ as the NLB targets
# Check which AZs the endpoint is in:
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[0].{Subnets:SubnetIds,AZs:AvailabilityZones}'

# Check which AZs the NLB has targets in:
aws elbv2 describe-target-health --target-group-arn <tg-arn> \
  --query 'TargetHealthDescriptions[].Target.AvailabilityZone'
```

**IF endpoint is in AZ-A but NLB targets only in AZ-B:** Cross-zone must be enabled on NLB, or add endpoint subnet in AZ-B.

### Step 7: Check Endpoint Policy (if restrictive)

```bash
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[0].PolicyDocument'
```

Default policy allows all. If custom policy exists, verify it allows the required actions.

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Endpoint pending acceptance | Can't connect | Provider: accept-vpc-endpoint-connections |
| Consumer not in allowed principals | Endpoint creation fails | Provider: add consumer account to permissions |
| Private DNS not enabled | DNS resolves to public IP | Enable private DNS on endpoint |
| Endpoint SG blocking | Connection timeout | Add inbound rule for consumer CIDR on service port |
| AZ mismatch | Intermittent failures | Add endpoint subnet in same AZ as NLB targets |
| Endpoint policy restrictive | Access denied | Update endpoint policy to allow required actions |
| DNS support disabled on VPC | DNS doesn't resolve | Enable enableDnsSupport on VPC |
| Multiple endpoints same service | DNS conflict | Only one can have private DNS enabled |

---

## PrivateLink Architecture

```
Consumer Account                          Provider Account
┌─────────────────────┐                  ┌─────────────────────┐
│ Consumer VPC         │                  │ Provider VPC         │
│                      │                  │                      │
│ App → Endpoint SG    │                  │  NLB → Target SG     │
│      → VPC Endpoint ─┼── PrivateLink ──┼→ NLB → EC2/Container│
│        (vpce-xxx)    │                  │  (vpce-svc-xxx)     │
│                      │                  │                      │
│ DNS: service.com     │                  │                      │
│ → resolves to        │                  │                      │
│   endpoint private IP│                  │                      │
└─────────────────────┘                  └─────────────────────┘

Traffic stays on AWS private network — never touches internet.
```
