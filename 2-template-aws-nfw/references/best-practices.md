# Best Practices for AWS Networking Troubleshooting

## Guiding Principles

### 1. Always Work from Source to Destination
Never jump to conclusions. Trace the packet path hop-by-hop from source to destination. Each hop is a potential failure point.

### 2. Verify Both Directions
In stateful architectures (like AWS Network Firewall), the return path matters. Always verify:
- Forward path: Source → Destination
- Return path: Destination → Source

### 3. Check the Simplest Things First
Most networking issues are caused by:
1. Security Group rules (80% of cases)
2. Route table entries (15% of cases)
3. Everything else (5% of cases)

---

## Best Practice Recommendations

### Security Group Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  SECURITY GROUP DESIGN PRINCIPLES                                │
│                                                                  │
│  ✅ DO:                                                          │
│  • Use SG references instead of CIDR when possible              │
│  • Create purpose-specific SGs (web-sg, app-sg, db-sg)         │
│  • Document each rule with description field                    │
│  • Use least-privilege (specific ports, not 0-65535)            │
│  • Review SGs quarterly for stale rules                         │
│                                                                  │
│  ❌ DON'T:                                                       │
│  • Use 0.0.0.0/0 for inbound rules (except ALB/NLB)           │
│  • Open all ports between tiers                                 │
│  • Share SGs across unrelated workloads                         │
│  • Forget outbound rules (they matter for troubleshooting)      │
│  • Exceed 60 rules per SG (performance impact)                  │
└─────────────────────────────────────────────────────────────────┘
```

**Recommended SG Structure for Workload VPCs:**

| Security Group | Inbound | Outbound |
|---------------|---------|----------|
| web-tier-sg | 443 from ALB-SG | 443 to app-tier-sg |
| app-tier-sg | 443 from web-tier-sg | 3306 to db-tier-sg, 443 to 0.0.0.0/0 |
| db-tier-sg | 3306 from app-tier-sg | Deny all (stateful return allowed) |

---

### Route Table Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  ROUTE TABLE DESIGN PRINCIPLES                                   │
│                                                                  │
│  ✅ DO:                                                          │
│  • Use most specific routes (longest prefix match wins)         │
│  • Keep route tables simple and consistent across AZs           │
│  • Use 0.0.0.0/0 → TGW as default in workload VPCs            │
│  • Document route table purpose with tags                       │
│  • Verify AZ-specific routing for firewall endpoints            │
│                                                                  │
│  ❌ DON'T:                                                       │
│  • Mix public and private routes in same route table            │
│  • Forget to update RT when adding new VPCs                     │
│  • Use overlapping CIDRs across VPCs                            │
│  • Point routes to resources in different AZ (latency/cost)     │
│  • Forget return routes in inspection VPC                       │
└─────────────────────────────────────────────────────────────────┘
```

**Critical Route Table Patterns:**

```
Workload VPC Subnet RT:
  10.x.0.0/16 → local          (intra-VPC)
  0.0.0.0/0   → tgw-xxxxx     (everything else to TGW)

Inspection VPC - TGW Subnet RT (per AZ):
  10.100.0.0/22 → local        (intra-VPC)
  0.0.0.0/0     → vpce-fw-az-a (to firewall endpoint in SAME AZ)

Inspection VPC - Firewall Subnet RT (per AZ):
  10.100.0.0/22 → local        (intra-VPC)
  10.0.0.0/8    → tgw-xxxxx   (return to workload VPCs)
  0.0.0.0/0     → nat-gw-az-a (internet via NAT in SAME AZ)

Inspection VPC - Public Subnet RT:
  10.100.0.0/22 → local        (intra-VPC)
  10.0.0.0/8    → vpce-fw-az-a (return traffic through firewall)
  0.0.0.0/0     → igw-xxxxx   (internet)
```

---

### Transit Gateway Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  TRANSIT GATEWAY DESIGN PRINCIPLES                               │
│                                                                  │
│  ✅ DO:                                                          │
│  • Enable Appliance Mode for inspection VPC attachment          │
│  • Use separate route tables (spoke vs firewall)                │
│  • Use static routes for deterministic routing                  │
│  • Enable route table association/propagation carefully         │
│  • Monitor TGW metrics (BytesIn, BytesOut, PacketDropCount)     │
│                                                                  │
│  ❌ DON'T:                                                       │
│  • Use default route table for all attachments                  │
│  • Enable propagation on spoke RT (use static routes)           │
│  • Forget to add routes for new VPCs in firewall RT             │
│  • Disable appliance mode (causes asymmetric routing)           │
│  • Exceed TGW bandwidth limits without monitoring               │
└─────────────────────────────────────────────────────────────────┘
```

**Critical TGW Configuration:**
```bash
# MUST enable appliance mode for inspection VPC
aws ec2 modify-transit-gateway-vpc-attachment \
  --transit-gateway-attachment-id tgw-attach-inspection \
  --options ApplianceModeSupport=enable

# Verify appliance mode is enabled
aws ec2 describe-transit-gateway-vpc-attachments \
  --transit-gateway-attachment-ids tgw-attach-inspection \
  --query 'TransitGatewayVpcAttachments[].Options.ApplianceModeSupport'
```

---

### AWS Network Firewall Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  NETWORK FIREWALL DESIGN PRINCIPLES                              │
│                                                                  │
│  ✅ DO:                                                          │
│  • Deploy firewall endpoints in every AZ used by workloads      │
│  • Use strict rule ordering (not default action order)          │
│  • Enable all logging (alert, flow, TLS)                        │
│  • Use domain allowlists for egress filtering                   │
│  • Separate rule groups by function (east-west, north-south)    │
│  • Test rules in alert-only mode before enforcing               │
│                                                                  │
│  ❌ DON'T:                                                       │
│  • Deploy firewall in only one AZ                               │
│  • Use overly broad rules (allow all TCP)                       │
│  • Forget to handle ICMP for path MTU discovery                 │
│  • Ignore firewall capacity limits                              │
│  • Mix stateless and stateful without understanding order       │
│  • Forget return traffic rules in stateful groups               │
└─────────────────────────────────────────────────────────────────┘
```

**Recommended Firewall Rule Structure:**
```
Stateless Rules (processed first):
  Priority 1: Pass established/related TCP (optimization)
  Priority 2: Drop known bad IPs (threat intel)
  Priority 99: Forward everything else to stateful engine

Stateful Rules (strict order):
  Priority 1: Drop rules (known bad patterns)
  Priority 2: East-West allow rules (inter-VPC)
  Priority 3: North-South allow rules (internet egress)
  Priority 4: On-premises allow rules
  Priority 5: AWS service allow rules
  Default: DROP ALL
```

---

### VPC Endpoint Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  VPC ENDPOINT DESIGN PRINCIPLES                                  │
│                                                                  │
│  ✅ DO:                                                          │
│  • Centralize endpoints in inspection/shared services VPC       │
│  • Enable private DNS for interface endpoints                   │
│  • Use endpoint policies to restrict access                     │
│  • Deploy interface endpoints in multiple AZs                   │
│  • Use gateway endpoints for S3 and DynamoDB (free)             │
│                                                                  │
│  ❌ DON'T:                                                       │
│  • Create duplicate endpoints in every VPC                      │
│  • Use overly permissive endpoint policies                      │
│  • Forget to add gateway endpoint to route tables               │
│  • Ignore DNS resolution requirements                           │
│  • Skip SG configuration on interface endpoints                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### Monitoring & Observability Best Practices

```
┌─────────────────────────────────────────────────────────────────┐
│  MONITORING STRATEGY                                             │
│                                                                  │
│  MUST HAVE:                                                      │
│  • VPC Flow Logs (all VPCs, reject-only minimum)                │
│  • Network Firewall Logs (alert + flow)                         │
│  • TGW Flow Logs                                                │
│  • CloudWatch Alarms on:                                        │
│    - NAT Gateway ErrorPortAllocation                            │
│    - NAT Gateway PacketsDropCount                               │
│    - TGW PacketDropCountNoRoute                                 │
│    - Network Firewall DroppedPackets                            │
│    - DX ConnectionState                                         │
│    - VPN TunnelState                                            │
│                                                                  │
│  NICE TO HAVE:                                                   │
│  • VPC Flow Logs (all traffic, not just reject)                 │
│  • Network Manager for topology visualization                   │
│  • Traffic Mirroring for deep packet inspection                 │
│  • Reachability Analyzer scheduled checks                       │
└─────────────────────────────────────────────────────────────────┘
```

**CloudWatch Alarm Examples:**
```bash
# NAT Gateway Port Exhaustion Alert
aws cloudwatch put-metric-alarm \
  --alarm-name "NAT-GW-Port-Exhaustion" \
  --metric-name ErrorPortAllocation \
  --namespace AWS/NATGateway \
  --statistic Sum \
  --period 300 \
  --threshold 100 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:region:account:network-alerts

# TGW Packet Drop Alert
aws cloudwatch put-metric-alarm \
  --alarm-name "TGW-Packet-Drop" \
  --metric-name PacketDropCountNoRoute \
  --namespace AWS/TransitGateway \
  --statistic Sum \
  --period 300 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=TransitGateway,Value=tgw-xxxxx \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:region:account:network-alerts
```

---

### Troubleshooting Efficiency Tips

#### Tip 1: Use VPC Reachability Analyzer First
Before manual investigation, run Reachability Analyzer. It automatically checks:
- Route tables
- Security groups
- NACLs (if any)
- Transit Gateway routes
- VPC peering routes

#### Tip 2: Check AZ Alignment
Many issues stem from cross-AZ misalignment:
- Firewall endpoint in AZ-A but traffic entering from AZ-B
- NAT Gateway in AZ-A but workload in AZ-B (cross-AZ charges + potential issues)
- TGW attachment ENI in different AZ than firewall endpoint

#### Tip 3: Enable VPC Flow Logs with Traffic Mirroring
For intermittent issues, enable full VPC Flow Logs temporarily:
```bash
aws ec2 create-flow-log \
  --resource-type VPC \
  --resource-ids vpc-xxxxx \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs \
  --log-group-name /vpc/flow-logs/debug \
  --max-aggregation-interval 60
```

#### Tip 4: Network Firewall Log Correlation
Always correlate:
1. Source VPC Flow Log (traffic leaving)
2. Network Firewall Alert Log (traffic being inspected)
3. Destination VPC Flow Log (traffic arriving)

If traffic appears in #1 but not #3, check #2 for DROP actions.

#### Tip 5: Check TGW Attachment Appliance Mode
The #1 cause of intermittent failures in inspection architectures:
```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --transit-gateway-attachment-ids tgw-attach-xxxxx \
  --query 'TransitGatewayVpcAttachments[].Options'
```
If `ApplianceModeSupport` is `disable`, this is likely your issue.

---

## Escalation Matrix

| Severity | Condition | Action |
|----------|-----------|--------|
| P1 - Critical | Complete connectivity loss, production down | Immediate investigation, engage AWS Support (Business/Enterprise) |
| P2 - High | Partial connectivity loss, degraded performance | Investigate within 30 min, consider rollback |
| P3 - Medium | Intermittent issues, non-production | Investigate within 4 hours |
| P4 - Low | Optimization opportunity, non-urgent | Schedule for next maintenance window |

---

## Pre-Change Checklist

Before making any network changes:

- [ ] Document current state (route tables, SGs, firewall rules)
- [ ] Identify blast radius (which VPCs/workloads affected)
- [ ] Test in non-production first
- [ ] Have rollback plan ready
- [ ] Notify affected teams
- [ ] Schedule during maintenance window (for production)
- [ ] Verify monitoring is active
- [ ] Test connectivity after change (both directions)
