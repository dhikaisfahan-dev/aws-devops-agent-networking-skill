# Runbook: AWS Global Accelerator Troubleshooting

## Trigger Conditions
- Global Accelerator endpoint not reachable
- High latency despite using Global Accelerator
- Health checks failing on endpoint groups
- Traffic not routing to the nearest edge location
- Failover not working between regions

---

## Investigation Steps

### Step 1: Check Accelerator Status

```bash
# List accelerators
aws globalaccelerator list-accelerators \
  --query 'Accelerators[].{Name:Name,Status:Status,Enabled:Enabled,DnsName:DnsName,IpSets:IpSets[0].IpAddresses}'

# Get specific accelerator
aws globalaccelerator describe-accelerator --accelerator-arn <arn> \
  --query '{Status:Accelerator.Status,Enabled:Accelerator.Enabled,DNS:Accelerator.DnsName}'
```

**Expected:** Status = `DEPLOYED`, Enabled = `true`

### Step 2: Check Listeners

```bash
aws globalaccelerator list-listeners --accelerator-arn <accelerator-arn> \
  --query 'Listeners[].{ARN:ListenerArn,Protocol:Protocol,Ports:PortRanges}'
```

### Step 3: Check Endpoint Groups

```bash
aws globalaccelerator list-endpoint-groups --listener-arn <listener-arn> \
  --query 'EndpointGroups[].{Region:EndpointGroupRegion,HealthCheck:{Path:HealthCheckPath,Port:HealthCheckPort,Protocol:HealthCheckProtocol},TrafficDialPercentage:TrafficDialPercentage}'
```

### Step 4: Check Endpoint Health

```bash
aws globalaccelerator describe-endpoint-group --endpoint-group-arn <endpoint-group-arn> \
  --query 'EndpointGroup.EndpointDescriptions[].{EndpointId:EndpointId,Health:HealthState,Reason:HealthReason,Weight:Weight}'
```

**Health states:**
- `HEALTHY` — Endpoint passing health checks
- `UNHEALTHY` — Endpoint failing health checks
- `INITIAL` — Health check in progress

### Step 5: Check Client IP Preservation

```bash
aws globalaccelerator describe-endpoint-group --endpoint-group-arn <arn> \
  --query 'EndpointGroup.EndpointDescriptions[].{Id:EndpointId,ClientIPPreservation:ClientIPPreservationEnabled}'
```

**With client IP preservation:**
- Target SG must allow traffic from client IPs (not GA IPs)
- Only works with ALB and EC2 endpoints

**Without client IP preservation:**
- Target SG must allow traffic from Global Accelerator IP ranges

### Step 6: Check Security Group for GA Traffic

```bash
# If client IP preservation is OFF:
# SG must allow from Global Accelerator IP ranges
# Get GA IP ranges from AWS IP ranges JSON:
curl -s https://ip-ranges.amazonaws.com/ip-ranges.json | \
  python3 -c "import json,sys; data=json.load(sys.stdin); [print(p['ip_prefix']) for p in data['prefixes'] if p['service']=='GLOBALACCELERATOR']"
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Accelerator disabled | Not reachable | Enable the accelerator |
| Endpoint unhealthy | Traffic not reaching backend | Fix health check (path, port, SG) |
| Traffic dial at 0% | No traffic to region | Set traffic dial > 0 |
| SG blocking GA traffic | Connection timeout | Allow GA IP ranges or enable client IP preservation |
| Health check wrong port | Endpoint shows unhealthy | Match health check port to application port |
| DNS not resolving GA | Can't connect | Use the GA DNS name or static IPs |
| Failover not working | Traffic stays in unhealthy region | Check endpoint health + traffic dial settings |
