# Runbook: Internet Ingress (Public → Workload VPC)

## Trigger Conditions
- External users cannot access published services
- ALB/NLB health checks failing
- 502/503/504 errors from load balancer
- Increased latency for public-facing services

## Pre-Investigation Information Needed
- Service URL / DNS name
- ALB/NLB identifier
- Backend target VPC and instance/container details
- Error codes observed
- Timestamp of issue

---

## Investigation Steps

### Step 1: Verify DNS Resolution

```bash
# Check ALB/NLB DNS
aws elbv2 describe-load-balancers \
  --names alb-public-service \
  --query 'LoadBalancers[].{DNS:DNSName,State:State.Code,Type:Type,Scheme:Scheme,VpcId:VpcId}'

# Verify DNS resolves (from client perspective)
dig +short alb-dns-name.region.elb.amazonaws.com
```

### Step 2: Check Load Balancer Status

```bash
# ALB/NLB state
aws elbv2 describe-load-balancers \
  --load-balancer-arns arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/xxxxx \
  --query 'LoadBalancers[].{State:State.Code,AZs:AvailabilityZones[].{Zone:ZoneName,Subnet:SubnetId}}'
```

**Expected:** State = "active"

### Step 3: Check ALB Security Group

```bash
# Get ALB security group
aws elbv2 describe-load-balancers \
  --load-balancer-arns arn:aws:elasticloadbalancing:... \
  --query 'LoadBalancers[].SecurityGroups[]'

# Check inbound rules
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-alb" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{
    Protocol:IpProtocol,
    Port:ToPort,
    Source:CidrIpv4,
    Description:Description
  }'
```

**Expected:** Inbound TCP 443 from 0.0.0.0/0 (public access)

### Step 4: Check Target Group Health

```bash
# List target groups for the ALB
aws elbv2 describe-target-groups \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --query 'TargetGroups[].{Name:TargetGroupName,ARN:TargetGroupArn,Type:TargetType,VpcId:VpcId}'

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/name/xxxxx \
  --query 'TargetHealthDescriptions[].{
    Id:Target.Id,
    Port:Target.Port,
    AZ:Target.AvailabilityZone,
    Health:TargetHealth.State,
    Reason:TargetHealth.Reason,
    Description:TargetHealth.Description
  }'
```

**If unhealthy:** Check reason codes:
- `Target.Timeout` → Health check path not responding
- `Target.FailedHealthChecks` → Backend returning non-200
- `Elb.InitialHealthChecking` → Target recently registered
- `Target.NotRegistered` → Target deregistered
- `Target.NotInUse` → AZ not enabled on LB

### Step 5: Check Ingress VPC Route Table

```bash
# ALB subnet route table
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-alb-ingress" \
  --query 'RouteTables[].Routes[]'
```

**Expected for IP targets in workload VPCs:**
- 10.0.0.0/8 → tgw-xxxxx (route to workload VPCs via TGW)
- 0.0.0.0/0 → igw-xxxxx (internet access)

### Step 6: Check TGW Spoke Route Table (Ingress VPC → Inspection)

```bash
# Verify Ingress VPC is associated with Spoke RT
aws ec2 get-transit-gateway-route-table-associations \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --query 'Associations[?ResourceId==`vpc-ingress`]'

# Check route to workload VPC
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=10.0.0.0/16"
```

### Step 7: Check Network Firewall (Ingress Rules)

```bash
# Check for blocked inbound traffic
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.dest_ip = "BACKEND_IP" }' \
  --start-time $(date -u -v-30M +%s000)

# Check ingress rule group
aws network-firewall describe-rule-group \
  --rule-group-name ingress-rules \
  --type STATEFUL
```

### Step 8: Check TGW Firewall Route Table (→ Workload VPC)

```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-firewall \
  --filters "Name=route-search.exact-match,Values=10.0.0.0/16"
```

**Expected:** 10.0.0.0/16 → VPC WL1 attachment

### Step 9: Check Workload VPC Destination Security Group

```bash
# Backend instance/container SG
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-backend" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{
    Protocol:IpProtocol,
    Port:ToPort,
    Source:CidrIpv4||ReferencedGroupInfo.GroupId
  }'
```

**Expected:** Inbound rule allowing traffic from:
- ALB private IP range (10.200.0.0/16) on application port
- OR specific ALB security group reference (if same VPC)

**Common mistake:** Backend SG only allows ALB SG reference, but ALB is in different VPC (SG references don't work cross-VPC). Must use CIDR.

### Step 10: Verify Return Path

For IP-target cross-VPC routing, return traffic must follow:
```
Backend → SG (outbound) → RT (0.0.0.0/0 → TGW) → 
TGW Spoke RT → Inspection VPC → Firewall → 
TGW Firewall RT (10.200.0.0/16 → Ingress VPC) → 
Ingress VPC → ALB → Client
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| ALB SG missing 443 inbound | Connection refused | Add 0.0.0.0/0:443 to ALB SG |
| Target unhealthy | 502 errors | Fix health check path, check backend app |
| Backend SG uses SG ref cross-VPC | Target timeout | Change to CIDR-based rule (10.200.0.0/16) |
| Missing TGW route in Ingress VPC | Target timeout | Add 10.0.0.0/8 → TGW in Ingress subnet RT |
| Firewall blocking ingress | Target timeout | Add ingress allow rule in firewall |
| Return path broken | Intermittent 504 | Check workload VPC RT has 0.0.0.0/0 → TGW |
| AZ mismatch | Increased latency | Enable cross-zone load balancing |

---

## Health Check Troubleshooting

```bash
# Check health check configuration
aws elbv2 describe-target-groups \
  --target-group-arns arn:aws:elasticloadbalancing:... \
  --query 'TargetGroups[].{
    HealthCheckPath:HealthCheckPath,
    HealthCheckPort:HealthCheckPort,
    HealthCheckProtocol:HealthCheckProtocol,
    HealthyThreshold:HealthyThresholdCount,
    UnhealthyThreshold:UnhealthyThresholdCount,
    Timeout:HealthCheckTimeoutSeconds,
    Interval:HealthCheckIntervalSeconds
  }'
```

**Key considerations for cross-VPC targets:**
- Health check traffic follows same path as data traffic
- Health check must pass through TGW → Firewall → Workload VPC
- Firewall must allow health check traffic
- Backend SG must allow health check from ALB CIDR (not SG ref)
