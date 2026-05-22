# Runbook: GWLB + 3rd Party Firewall Investigation

## Trigger Conditions
- Traffic passing through inspection VPC but not arriving at destination
- GWLB target group showing unhealthy targets
- Firewall appliance EC2 instance down or impaired
- Intermittent connectivity (possible GENEVE tunnel issue)
- All east-west or north-south traffic failing simultaneously

---

## Investigation Steps

### Step 1: Check GWLB Status

```bash
aws elbv2 describe-load-balancers --type gateway \
  --query 'LoadBalancers[].{Name:LoadBalancerName,ARN:LoadBalancerArn,State:State.Code,AZs:AvailabilityZones[].ZoneName}'
```

**Expected:** State = `active`

### Step 2: Check GWLB Target Group Health

```bash
# List target groups
aws elbv2 describe-target-groups \
  --load-balancer-arn <gwlb-arn> \
  --query 'TargetGroups[].{Name:TargetGroupName,ARN:TargetGroupArn,HealthCheck:{Protocol:HealthCheckProtocol,Port:HealthCheckPort,Path:HealthCheckPath}}'

# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <tg-arn> \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,AZ:Target.AvailabilityZone,Health:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}'
```

**If unhealthy:**
- `Target.Timeout` → Appliance not responding to health checks
- `Target.FailedHealthChecks` → Appliance responding but with errors
- `Elb.InternalError` → GWLB issue

### Step 3: Check Firewall Appliance EC2 Status

```bash
# Get appliance instance IDs from target group
aws elbv2 describe-target-health --target-group-arn <tg-arn> \
  --query 'TargetHealthDescriptions[].Target.Id' --output text

# Check instance status
aws ec2 describe-instance-status --instance-ids <instance-ids> \
  --query 'InstanceStatuses[].{Id:InstanceId,State:InstanceState.Name,System:SystemStatus.Status,Instance:InstanceStatus.Status}'

# Check instance details
aws ec2 describe-instances --instance-ids <instance-ids> \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone,LaunchTime:LaunchTime}'
```

### Step 4: Check GWLB Endpoint Routing

```bash
# Find GWLB endpoints
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-endpoint-type,Values=GatewayLoadBalancer" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,State:State,VPC:VpcId,Subnets:SubnetIds}'

# Check TGW subnet route table points to GWLB endpoint
aws ec2 describe-route-tables --route-table-ids <tgw-subnet-rt> \
  --query 'RouteTables[0].Routes[]'
# Expected: 0.0.0.0/0 → vpce-gwlb-xxxxx
```

### Step 5: Check GWLB Cross-Zone Load Balancing

```bash
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <gwlb-arn> \
  --query 'Attributes[?Key==`load_balancing.cross_zone.enabled`].Value'
```

**If disabled and one AZ has no healthy targets:** Traffic to that AZ is blackholed. Enable cross-zone:
```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn <gwlb-arn> \
  --attributes Key=load_balancing.cross_zone.enabled,Value=true
```

### Step 6: Check GWLB CloudWatch Metrics

```bash
# Healthy vs unhealthy targets
aws cloudwatch get-metric-statistics \
  --namespace AWS/GatewayELB --metric-name UnHealthyHostCount \
  --dimensions Name=LoadBalancer,Value=<gwlb-id> Name=TargetGroup,Value=<tg-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum

# Traffic flowing through
aws cloudwatch get-metric-statistics \
  --namespace AWS/GatewayELB --metric-name ProcessedBytes \
  --dimensions Name=LoadBalancer,Value=<gwlb-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# New flows (connections per second)
aws cloudwatch get-metric-statistics \
  --namespace AWS/GatewayELB --metric-name NewFlowCount \
  --dimensions Name=LoadBalancer,Value=<gwlb-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### Step 7: Check Appliance Security Group

```bash
# Firewall appliance SG must allow:
# - All traffic from GWLB (or GWLB subnet CIDR)
# - GENEVE port 6081 from GWLB
# - Health check port from GWLB

aws ec2 describe-security-groups --group-ids <appliance-sg> \
  --query 'SecurityGroups[0].{Ingress:IpPermissions,Egress:IpPermissionsEgress}'
```

**Required inbound rules on appliance SG:**
- UDP 6081 (GENEVE) from GWLB subnet CIDR
- Health check port (TCP 80/443 or custom) from GWLB subnet CIDR

### Step 8: Escalate to Firewall Team (if needed)

If traffic reaches the GWLB, targets are healthy, but traffic doesn't arrive at destination:

**The issue is inside the firewall appliance.** The agent cannot investigate further via AWS API.

Provide the firewall team with:
- Source IP and destination IP
- Protocol and port
- Timestamp of failure
- Confirmation that traffic IS reaching the appliance (VPC Flow Logs show ACCEPT on appliance ENI)

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Appliance down | GWLB target unhealthy | Restart appliance EC2 or check ASG |
| Health check failing | Target unhealthy but EC2 running | Fix health check port/path on appliance |
| Cross-zone disabled | One AZ traffic blackholed | Enable cross-zone on GWLB |
| GENEVE misconfigured | Traffic enters but doesn't return | Check appliance GENEVE tunnel config |
| SG blocking GENEVE | Target unhealthy | Allow UDP 6081 from GWLB subnet |
| Route missing GWLB endpoint | Traffic bypasses firewall | Add 0.0.0.0/0 → vpce-gwlb in TGW subnet RT |
| Firewall policy blocking | Traffic reaches appliance but drops | Escalate to firewall team |
| Appliance capacity | Intermittent drops under load | Scale out ASG or upgrade instance type |
| Appliance mode disabled | Intermittent failures | Enable on inspection VPC TGW attachment |
