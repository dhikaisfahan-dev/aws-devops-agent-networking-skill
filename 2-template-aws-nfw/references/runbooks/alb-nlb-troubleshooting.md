# Runbook: ALB/NLB Cross-Zone Troubleshooting

## Trigger Conditions
- Load balancer health checks failing
- 502/503/504 errors from ALB
- Targets showing unhealthy in one AZ but healthy in another
- Intermittent connectivity to backend targets
- Cross-VPC target registration issues
- Increased latency for specific targets

## Pre-Investigation Information Needed
- Load balancer ARN or name
- Target group ARN
- Target type (instance, IP, Lambda)
- Which targets are unhealthy
- Error codes observed (502, 503, 504)

---

## Investigation Steps

### Step 1: Check Load Balancer Status

```bash
# Describe ALB/NLB
aws elbv2 describe-load-balancers \
  --names my-alb-name \
  --query 'LoadBalancers[0].{
    ARN:LoadBalancerArn,
    DNS:DNSName,
    State:State.Code,
    Type:Type,
    Scheme:Scheme,
    VpcId:VpcId,
    AZs:AvailabilityZones[].{Zone:ZoneName,Subnet:SubnetId}
  }'
```

**Expected:** State = `active`, AZs show all expected zones.

### Step 2: Check Target Group Health

```bash
# List target groups for the LB
aws elbv2 describe-target-groups \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --query 'TargetGroups[].{
    Name:TargetGroupName,
    ARN:TargetGroupArn,
    Type:TargetType,
    Protocol:Protocol,
    Port:Port,
    VpcId:VpcId,
    HealthCheck:{Path:HealthCheckPath,Port:HealthCheckPort,Protocol:HealthCheckProtocol,Interval:HealthCheckIntervalSeconds,Timeout:HealthCheckTimeoutSeconds,Healthy:HealthyThresholdCount,Unhealthy:UnhealthyThresholdCount}
  }'

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query 'TargetHealthDescriptions[].{
    Target:Target.Id,
    Port:Target.Port,
    AZ:Target.AvailabilityZone,
    Health:TargetHealth.State,
    Reason:TargetHealth.Reason,
    Description:TargetHealth.Description
  }' --output table
```

**Health states:**
- `healthy` — Target is passing health checks
- `unhealthy` — Target is failing health checks
- `initial` — Target recently registered, health check in progress
- `draining` — Target is deregistering
- `unavailable` — Health checks disabled or LB not active

**Reason codes:**
- `Target.Timeout` — Health check timed out (target not responding)
- `Target.FailedHealthChecks` — Target returned non-2xx response
- `Target.NotRegistered` — Target was deregistered
- `Target.NotInUse` — Target is in an AZ not enabled on the LB
- `Elb.InternalError` — LB internal error

### Step 3: Check Cross-Zone Load Balancing

```bash
# Check if cross-zone is enabled
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --query 'Attributes[?Key==`load_balancing.cross_zone.enabled`].Value'

# For target group level cross-zone setting
aws elbv2 describe-target-group-attributes \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query 'Attributes[?Key==`load_balancing.cross_zone.enabled`].Value'
```

**If cross-zone is disabled:**
- Traffic only goes to targets in the same AZ as the LB node that received the request
- If all targets in one AZ are unhealthy, requests to that AZ's LB node will fail (503)
- Enable cross-zone to distribute across all healthy targets regardless of AZ

**Fix:**
```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --attributes Key=load_balancing.cross_zone.enabled,Value=true
```

### Step 4: Check Security Groups (ALB)

```bash
# ALB security group
aws elbv2 describe-load-balancers \
  --load-balancer-arns arn:aws:elasticloadbalancing:... \
  --query 'LoadBalancers[0].SecurityGroups'

# Check ALB SG allows inbound from clients
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-alb" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{Protocol:IpProtocol,Port:ToPort,Source:CidrIpv4}'

# Check ALB SG allows outbound to targets
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-alb" \
  --query 'SecurityGroupRules[?IsEgress==`true`].{Protocol:IpProtocol,Port:ToPort,Dest:CidrIpv4}'
```

**For cross-VPC IP targets:** ALB SG outbound must allow traffic to the target VPC CIDR on the target port.

### Step 5: Check Target Security Group

```bash
# Target instance/ENI security group
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-target" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{Protocol:IpProtocol,Port:ToPort,Source:CidrIpv4||ReferencedGroupInfo.GroupId}'
```

**Critical for cross-VPC targets:**
- ❌ SG reference to ALB SG does NOT work (different VPC)
- ✅ Must use CIDR of the ALB's VPC/subnet (e.g., `10.200.0.0/16`)

### Step 6: Check Routing for Cross-VPC Targets (IP type)

When ALB targets are IP addresses in a different VPC:

```bash
# Check ALB subnet route table has route to target VPC
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-alb" \
  --query 'RouteTables[0].Routes[].{Dest:DestinationCidrBlock,Target:TransitGatewayId||VpcPeeringConnectionId||GatewayId}'
```

**Expected:** Route to target VPC CIDR via TGW or VPC Peering.

**Health check path for cross-VPC targets:**
```
ALB → ALB Subnet RT (target CIDR → TGW) → TGW → [Firewall if inspection] → Target VPC → Target SG → Target
```

The health check follows the SAME path as data traffic. If the path is broken, health checks fail.

### Step 7: Check Listener Rules

```bash
# List listeners
aws elbv2 describe-listeners \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --query 'Listeners[].{ARN:ListenerArn,Port:Port,Protocol:Protocol}'

# Check rules for a listener
aws elbv2 describe-rules \
  --listener-arn arn:aws:elasticloadbalancing:... \
  --query 'Rules[].{Priority:Priority,Conditions:Conditions[].{Field:Field,Values:Values},Actions:Actions[].{Type:Type,TargetGroup:TargetGroupArn}}'
```

### Step 8: Check ALB Access Logs and CloudWatch Metrics

```bash
# Check 5xx errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_ELB_5XX_Count \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Check target response time
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average,p99

# Check healthy/unhealthy host count
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name UnHealthyHostCount \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx Name=TargetGroup,Value=targetgroup/my-tg/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum
```

### Step 9: NLB-Specific Checks

```bash
# NLB does NOT have security groups (traffic passes through)
# Check target SG allows traffic from NLB subnet CIDR or client IP (preserve client IP)

# Check if client IP preservation is enabled
aws elbv2 describe-target-group-attributes \
  --target-group-arn arn:aws:elasticloadbalancing:... \
  --query 'Attributes[?Key==`preserve_client_ip.enabled`].Value'
```

**NLB with client IP preservation:**
- Target SG must allow traffic from the **client's IP** (not NLB IP)
- For internet-facing NLB: target SG needs `0.0.0.0/0` on the target port

**NLB without client IP preservation:**
- Target SG must allow traffic from the **NLB's subnet CIDR**

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Cross-zone disabled | 503 when one AZ has no healthy targets | Enable cross-zone load balancing |
| Target SG uses ALB SG ref cross-VPC | Health check timeout | Change to CIDR-based rule |
| Missing route to target VPC | Health check timeout | Add route to target CIDR via TGW/Peering |
| Health check path wrong | Targets unhealthy | Fix health check path (e.g., `/health`) |
| Health check port mismatch | Targets unhealthy | Align health check port with app port |
| Firewall blocking health checks | Targets unhealthy | Add firewall rule for ALB→target traffic |
| Target in disabled AZ | Target.NotInUse | Enable the AZ on the load balancer |
| NLB client IP + restrictive SG | Intermittent failures | Allow client CIDR or disable preservation |
| ALB idle timeout | 504 errors | Increase idle timeout or fix slow backend |
| Target deregistration delay | Connections dropping | Increase deregistration delay |

---

## Error Code Reference

| Error | Meaning | Investigation |
|-------|---------|---------------|
| **502** | Bad Gateway — target sent invalid response | Check target application logs, verify target is running |
| **503** | Service Unavailable — no healthy targets | Check target health, cross-zone settings |
| **504** | Gateway Timeout — target didn't respond in time | Check target response time, network path, firewall |
| **460** | Client closed connection before LB could respond | Client timeout too short, or LB processing too slow |
| **561** | Unauthorized — ALB couldn't authenticate with IdP | Check ALB authentication action configuration |

---

## Cross-VPC Target Architecture

```
Internet → ALB (Ingress VPC, 10.200.0.0/16)
  → ALB Subnet RT: 10.0.0.0/8 → TGW
  → TGW Spoke RT → Inspection VPC
  → Network Firewall (must allow ALB→target traffic)
  → TGW Firewall RT → Workload VPC
  → Target SG (must allow from 10.200.0.0/16, NOT ALB SG ref)
  → Target EC2/Container

Health checks follow the SAME path.
If any hop is broken, targets show unhealthy.
```
