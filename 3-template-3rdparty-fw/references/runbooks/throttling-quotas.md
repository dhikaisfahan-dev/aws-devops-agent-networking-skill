# Runbook: Throttling & Service Quotas

## Trigger Conditions
- NAT Gateway port exhaustion (connections failing)
- TGW bandwidth limit reached
- VPC endpoint throughput degradation
- "Rate exceeded" or throttling errors
- Intermittent connectivity under high load
- ENI limits reached

---

## Investigation Steps

### Step 1: NAT Gateway Limits

```bash
# Check port allocation errors (CRITICAL — means connections are failing)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=<nat-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Check active connections (limit: 55,000 simultaneous per destination)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name ActiveConnectionCount \
  --dimensions Name=NatGatewayId,Value=<nat-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum

# Check packets dropped
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name PacketsDropCount \
  --dimensions Name=NatGatewayId,Value=<nat-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

**NAT Gateway limits:**
| Limit | Value |
|-------|-------|
| Bandwidth | 100 Gbps (bursts to 100 Gbps) |
| Packets per second | 10 million |
| Connections per second (to same destination) | 55,000 |
| Total simultaneous connections | 1,000,000 |

**Fix for port exhaustion:** Add more NAT Gateways or reduce connections to same destination.

### Step 2: Transit Gateway Limits

```bash
# Check TGW packet drops (no route)
aws cloudwatch get-metric-statistics \
  --namespace AWS/TransitGateway --metric-name PacketDropCountNoRoute \
  --dimensions Name=TransitGateway,Value=<tgw-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Check bytes per attachment (is one attachment saturated?)
aws cloudwatch get-metric-statistics \
  --namespace AWS/TransitGateway --metric-name BytesIn \
  --dimensions Name=TransitGateway,Value=<tgw-id> Name=TransitGatewayAttachment,Value=<attachment-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

**TGW limits:**
| Limit | Value |
|-------|-------|
| Bandwidth per VPC attachment | 50 Gbps (burst) |
| Bandwidth per VPN attachment | 1.25 Gbps per tunnel |
| Bandwidth per DX attachment | DX link speed |
| Bandwidth per Connect peer | 5 Gbps (max 4 peers = 20 Gbps) |
| Routes per route table | 10,000 |
| Attachments per TGW | 5,000 |

### Step 3: VPC Endpoint Limits

```bash
# Interface endpoints: check bandwidth
# No direct CloudWatch metric — infer from VPC Flow Logs
aws logs start-query \
  --log-group-name <flow-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'stats sum(bytes) as totalBytes by dstAddr
    | filter dstAddr like "10.100."
    | sort totalBytes desc
    | limit 10'
```

**VPC Endpoint limits:**
| Limit | Value |
|-------|-------|
| Interface endpoint bandwidth | ~10 Gbps per ENI (scales with AZs) |
| Gateway endpoint (S3/DynamoDB) | No bandwidth limit |
| Connections per endpoint ENI | Based on instance type of caller |

### Step 4: Security Group Limits

```bash
# Check SG rule count
aws ec2 describe-security-groups --group-ids <sg-id> \
  --query '{Inbound:IpPermissions|length(@),Outbound:IpPermissionsEgress|length(@)}'
```

**SG limits:**
| Limit | Default | Max |
|-------|---------|-----|
| Rules per SG (inbound + outbound) | 60 | 1000 (request increase) |
| SGs per ENI | 5 | 16 |
| Rules evaluated per ENI | 300 (5 SGs × 60 rules) | — |

### Step 5: Check Service Quotas

```bash
# Check current quotas for EC2/VPC
aws service-quotas list-service-quotas --service-code vpc \
  --query 'Quotas[?UsageMetric!=`null`].{Name:QuotaName,Value:Value,Usage:UsageMetric}'

# Check specific quota usage
aws service-quotas get-service-quota --service-code vpc --quota-code L-F678F1CE \
  --query '{Name:Quota.QuotaName,Limit:Quota.Value}'
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| NAT GW port exhaustion | ErrorPortAllocation > 0 | Add more NAT GWs or reduce connections |
| NAT GW bandwidth | Packets dropped | Use multiple NAT GWs across AZs |
| TGW attachment saturated | Slow cross-VPC traffic | Check if single attachment exceeds 50 Gbps |
| VPN tunnel limit | 1.25 Gbps max | Use ECMP with multiple tunnels |
| SG rule limit reached | Can't add more rules | Consolidate rules or request increase |
| ENI limit per instance | Can't attach more SGs/IPs | Use larger instance type |
| VPC endpoint throttled | Slow AWS service access | Add endpoint in more AZs |
