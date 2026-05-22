---
name: aws-networking-investigation
description: End-to-end networking investigation and troubleshooting for
  hub-and-spoke AWS architectures with Transit Gateway, AWS Network Firewall,
  VPC Peering, centralized VPC endpoints, NAT Gateway, and hybrid connectivity
  via Direct Connect and VPN. Use this skill when investigating connectivity
  failures between VPCs (east-west), internet access issues (north-south egress),
  inbound traffic failures (north-south ingress), AWS service access via VPC
  endpoints, Transit Gateway routing problems including blackhole routes,
  VPC Peering connectivity issues, Network Firewall blocking or dropping traffic,
  asymmetric routing causing intermittent failures, security group misconfigurations,
  Direct Connect BGP session issues, VPN tunnel connectivity problems, or when
  analyzing VPC Flow Logs, TGW Flow Logs, or Network Firewall alert and flow logs.
  Covers workload VPC private subnet architectures with centralized inspection.
---

# AWS Networking Investigation Skill

## Architecture Context

This skill is designed for hub-and-spoke architectures with centralized inspection:

- **Workload VPCs** (spoke): Private subnets only, all traffic routed to inspection VPC via TGW
- **Inspection/Egress VPC** (hub): AWS Network Firewall, NAT Gateway, Internet Gateway, VPC Endpoints
- **Ingress VPC**: ALB/NLB for published services
- **Transit Gateway**: Central routing with Spoke RT and Firewall RT
- **VPC Peering**: Optional point-to-point connectivity (no transitive routing)
- **Hybrid Connectivity**: Direct Connect and/or VPN to on-premises

The agent should discover actual VPC CIDRs, resource IDs, and log group names dynamically using AWS API calls during investigation.

---

## Environment Discovery (Always Run First)

Before investigating any issue, discover the environment topology:

```
1. List all VPCs and their CIDRs:
   → aws ec2 describe-vpcs --query 'Vpcs[].{Id:VpcId,CIDR:CidrBlock,Name:Tags[?Key==`Name`].Value|[0]}'

2. List Transit Gateway and all attachments:
   → aws ec2 describe-transit-gateways
   → aws ec2 describe-transit-gateway-attachments --query 'TransitGatewayAttachments[].{Id:TransitGatewayAttachmentId,Resource:ResourceId,Type:ResourceType,State:State}'

3. Identify the Inspection VPC:
   → aws network-firewall list-firewalls (if AWS NFW)
   → aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-type,Values=GatewayLoadBalancer" (if GWLB)
   → The VPC containing the firewall/GWLB is the inspection VPC

4. Identify the Ingress VPC:
   → aws elbv2 describe-load-balancers --query 'LoadBalancers[?Scheme==`internet-facing`]'
   → The VPC with internet-facing ALB/NLB is the ingress VPC

5. Identify hybrid connectivity:
   → aws ec2 describe-vpn-connections (VPN)
   → aws directconnect describe-direct-connect-gateways (DX)
   → aws ec2 describe-transit-gateway-connects (SD-WAN/TGW Connect)

6. Check for VPC Peering:
   → aws ec2 describe-vpc-peering-connections

7. Check KNOWN-EXCEPTIONS.md (if provided):
   → Review known exceptions before flagging findings as issues
```

---

## Architecture Pattern Detection

Before investigating, determine which VPC pattern the environment uses:

```
1. Find Inspection VPC:
   → aws network-firewall list-firewalls (AWS NFW)
   → The VPC containing the firewall is the Inspection VPC

2. Find Egress VPC:
   → aws ec2 describe-nat-gateways
   → aws ec2 describe-internet-gateways
   → The VPC with NAT GW + IGW is the Egress VPC

3. Find Shared Services VPC:
   → aws ec2 describe-vpc-endpoints (look for many interface endpoints)
   → aws route53resolver list-resolver-endpoints
   → The VPC with centralized endpoints + DNS resolvers is Shared Services

4. Determine pattern:
   IF Firewall + NAT + IGW all in SAME VPC → Combined (simplest)
   IF Firewall in one VPC, NAT+IGW in another → Separate Inspection + Egress
   IF Endpoints/DNS in a third VPC → Shared Services VPC exists
```

### Traffic Paths by Pattern

**Pattern A: Combined Inspection + Egress (single VPC)**
```
Workload → TGW → Inspection VPC (Firewall → NAT GW → IGW) → Internet
Workload → TGW → Inspection VPC (Firewall → VPC Endpoints) → AWS Services
```

**Pattern B: Separate Inspection + Egress VPCs**
```
Workload → TGW (Spoke RT → Inspection VPC)
→ Inspection VPC (Firewall inspects)
→ TGW (Firewall RT → Egress VPC)
→ Egress VPC (NAT GW → IGW) → Internet

Return: Internet → IGW → NAT GW → Egress VPC RT (→ TGW)
→ TGW → Inspection VPC (Firewall, return path)
→ TGW → Workload VPC
```

**Pattern C: Separate Inspection + Egress + Shared Services**
```
Internet traffic:
  Workload → TGW → Inspection VPC → TGW → Egress VPC → Internet

AWS service traffic:
  Workload → TGW → Shared Services VPC → VPC Endpoints → AWS Services
  (may or may not pass through Inspection VPC depending on routing)

DNS:
  Workload → TGW → Shared Services VPC → Route 53 Resolver → resolve
```

### Troubleshooting Separate VPC Patterns

**Extra failure points in Pattern B/C:**
- Additional TGW route table entries needed (Firewall RT must route to Egress VPC)
- Egress VPC needs its own TGW attachment + route table association
- Return traffic from Egress VPC must go back through Inspection VPC (symmetric)
- Shared Services VPC needs TGW attachment + routes from workload VPCs

**Common issues with separate VPCs:**
| Issue | Symptom | Fix |
|-------|---------|-----|
| Firewall RT missing route to Egress VPC | Traffic inspected but can't reach internet | Add Egress VPC CIDR → Egress attachment in Firewall RT |
| Egress VPC RT missing return route | Internet works one-way | Add 10.0.0.0/8 → TGW in Egress VPC NAT subnet RT |
| Shared Services not in TGW | Can't reach VPC endpoints | Attach Shared VPC to TGW, add routes |
| Spoke RT sends AWS traffic to Inspection instead of Shared | Slow endpoint access | Add specific routes for Shared VPC CIDR in Spoke RT |
| Asymmetric return from Egress VPC | Intermittent failures | Ensure Egress VPC return goes through Inspection (firewall stateful) |

**How to check TGW routing for multi-VPC patterns:**
```
→ aws ec2 search-transit-gateway-routes --transit-gateway-route-table-id <firewall-rt>
  Look for:
  - Egress VPC CIDR → Egress VPC attachment (for internet-bound traffic after inspection)
  - Shared VPC CIDR → Shared VPC attachment (for endpoint access)
  - Workload CIDRs → Workload VPC attachments (for return traffic)

→ aws ec2 get-transit-gateway-route-table-associations
  Verify:
  - Inspection VPC → associated with Firewall RT
  - Egress VPC → associated with Firewall RT (or its own RT)
  - Shared VPC → associated with Spoke RT or its own RT
  - Workload VPCs → associated with Spoke RT
```

---

## Investigation Methodology

### Step 1: Identify Traffic Flow Type

| Flow Type | Pattern |
|-----------|---------|
| Intra-VPC | Source and destination in same VPC |
| East-West | Between different workload VPCs (via TGW + Firewall) |
| East-West (Peering) | Between peered VPCs (direct, no firewall) |
| North-South Egress | Workload to internet |
| North-South Ingress | Internet to workload (via ALB/NLB) |
| AWS Service | Workload to S3/DynamoDB/SQS/etc |
| Hybrid | Workload to/from on-premises |

### Step 2: Trace Path Hop-by-Hop

**East-West Path (via TGW + Firewall):**
```
Source EC2 → Security Group (outbound) → Subnet Route Table (→ TGW)
→ TGW Spoke RT (→ Inspection VPC) → TGW Subnet RT (→ FW Endpoint)
→ Network Firewall (inspect) → Firewall Subnet RT (→ TGW)
→ TGW Firewall RT (→ Destination VPC) → Subnet RT → Security Group (inbound)
→ Destination EC2
```

**East-West Path (via VPC Peering):**
```
Source EC2 → Security Group (outbound) → Subnet Route Table (→ pcx-xxxxx)
→ VPC Peering → Subnet Route Table (peer VPC) → Security Group (inbound)
→ Destination EC2
```

**North-South Egress Path:**
```
Source EC2 → Security Group (outbound) → Subnet RT (→ TGW)
→ TGW Spoke RT (→ Inspection VPC) → TGW Subnet RT (→ FW Endpoint)
→ Network Firewall (inspect) → Firewall Subnet RT (→ NAT GW)
→ NAT Gateway (SNAT) → Public Subnet RT (→ IGW) → Internet
```

**North-South Ingress Path:**
```
Internet → IGW → ALB (Security Group) → Subnet RT (→ TGW)
→ TGW Spoke RT (→ Inspection VPC) → TGW Subnet RT (→ FW Endpoint)
→ Network Firewall (inspect) → Firewall Subnet RT (→ TGW)
→ TGW Firewall RT (→ Workload VPC) → Subnet RT → Security Group
→ Destination EC2
```

**Hybrid Path (On-Premises via VPN/DX):**
```
On-Premises → DX/VPN → TGW (VPN/DX attachment, Spoke RT)
→ Inspection VPC → Network Firewall → TGW (Firewall RT)
→ Workload VPC → Security Group → EC2
```

### Step 3: Check Each Component

For each hop, verify:
1. **Security Group** — inbound/outbound rules allow the traffic
2. **Route Table** — has correct route for destination CIDR
3. **TGW Route Table** — correct association and routes (no blackholes)
4. **VPC Peering** — status active, routes in both VPCs, no CIDR overlap
5. **Network Firewall** — stateful rules allow the protocol/port
6. **NAT Gateway** — status available, no port exhaustion
7. **VPC Endpoints** — state available, policy allows access, DNS resolves

### Step 4: Check Logs (Correlate All Sources)

**Investigation order for log correlation:**

1. **VPC Flow Logs (source VPC)** — Did traffic leave the source?
   - If REJECT → Security Group or NACL blocking
   - If ACCEPT → Traffic left, check next hop

2. **TGW Flow Logs** — Did traffic reach TGW and get forwarded?
   - If no entry → Route table not pointing to TGW
   - If REJECT → Blackhole route in TGW RT
   - If present → Traffic forwarded, check firewall

3. **Network Firewall Alert Logs** — Did firewall block it?
   - If alert with "blocked" → Firewall rule dropping traffic
   - If no alert → Traffic passed firewall

4. **Network Firewall Flow Logs** — Did traffic pass through firewall?
   - If present with "timeout" → Return path broken (asymmetric routing)
   - If present with "closed" → Connection completed successfully

5. **VPC Flow Logs (destination VPC)** — Did traffic arrive?
   - If ACCEPT → Traffic arrived, check application
   - If no entry → Lost between firewall and destination

6. **CloudTrail** — Was the network configuration recently changed?
   - Check for SecurityGroup changes (AuthorizeSecurityGroupIngress/Egress, Revoke*)
   - Check for Route Table changes (CreateRoute, DeleteRoute, ReplaceRoute)
   - Check for Firewall rule changes (UpdateRuleGroup, UpdateFirewallPolicy)
   - Check for TGW route changes (CreateTransitGatewayRoute, DeleteTransitGatewayRoute)
   - If recent change correlates with issue start time → likely root cause

7. **CloudWatch Network Metrics** — Are there anomalies?
   - NAT Gateway: ErrorPortAllocation, PacketsDropCount, ActiveConnectionCount
   - Transit Gateway: PacketDropCountNoRoute, BytesIn/BytesOut per attachment
   - Network Firewall: DroppedPackets, PassedPackets, StreamExceptionPolicyPackets
   - VPN: TunnelState (1=UP, 0=DOWN), TunnelDataIn/Out
   - ALB/NLB: UnHealthyHostCount, HTTPCode_ELB_5XX, TargetResponseTime
   - Check for ALARM state on any network-related CloudWatch alarms

### Step 5: Verify Return Path

Always check BOTH directions. Common issues:
- Asymmetric routing (appliance mode not enabled on inspection VPC TGW attachment)
- Missing return route in public subnet RT (10.0.0.0/8 → firewall endpoint per AZ)
- Firewall seeing return traffic as new flow (use `drop_strict` not `drop_established`)
- Cross-AZ routing (public subnet RT must be per-AZ with per-AZ firewall endpoints)

---

## Key Rules

- Security Groups are stateful — if outbound is allowed, return is automatic
- Network Firewall is stateful — but needs appliance mode for cross-AZ symmetry
- TGW Appliance Mode MUST be enabled on inspection VPC attachment
- No NACLs in this architecture — Security Groups only
- Cross-VPC SG references DO NOT work across TGW — must use CIDR-based rules
- Cross-VPC SG references DO work across VPC Peering (same region only)
- Public subnet RT needs per-AZ routes to firewall endpoints for return traffic
- Firewall policy should use `drop_strict` (not `drop_established`)
- VPC Peering does NOT support transitive routing or edge-to-edge routing

---

## Direct Connect Gateway Detection & Troubleshooting

### Detect DX Gateway vs Direct VGW Attachment

```
1. Check if DX Gateway exists:
   → aws directconnect describe-direct-connect-gateways
   IF results → DX Gateway pattern (DX GW → TGW or VGW)
   IF empty → Check for VGW with DX VIF attached (legacy pattern)

2. Check DX Gateway associations:
   → aws directconnect describe-direct-connect-gateway-associations
     --direct-connect-gateway-id <dxgw-id>
   Shows: Associated TGW or VGW, allowed prefixes, association state

3. Check DX Gateway attachments:
   → aws directconnect describe-direct-connect-gateway-attachments
     --direct-connect-gateway-id <dxgw-id>
   Shows: VIF attached, attachment state
```

### DX Gateway Investigation Flow

```
Is the issue on-premises ↔ cloud connectivity?
├── NO → Skip DX section
└── YES → Does DX Gateway exist?
    ├── NO → Check VPN tunnels instead
    └── YES → Continue below

Step 1: Check DX Connection physical state
  → aws directconnect describe-connections
    Check: connectionState = "available"
    IF "down" → Physical layer issue (contact colo/provider)

Step 2: Check Virtual Interface status
  → aws directconnect describe-virtual-interfaces
    Check: virtualInterfaceState = "available"
    Check: bgpPeers[].bgpStatus = "up"
    Check: bgpPeers[].bgpPeerState = "established" (private VIF)
    
    IF BGP down → Check ASN, peer IPs, MD5 key, route filters

Step 3: Check DX Gateway → TGW association
  → aws directconnect describe-direct-connect-gateway-associations
    Check: associationState = "associated"
    Check: allowedPrefixesToDirectConnectGateway includes all VPC CIDRs
    
    IF missing prefix → On-prem won't receive routes for that VPC
    Fix: aws directconnect update-direct-connect-gateway-association
      --add-allowed-prefixes-to-direct-connect-gateway cidr=<missing-cidr>

Step 4: Check TGW route table for DX/VPN attachment
  → aws ec2 search-transit-gateway-routes
    Verify: on-prem CIDR has route via DX/VPN attachment (not blackhole)

Step 5: Check CloudWatch DX metrics
  → aws cloudwatch get-metric-statistics
    Namespace: AWS/DX
    Metrics:
      - ConnectionState (1=up, 0=down)
      - ConnectionBpsIngress / ConnectionBpsEgress (throughput)
      - ConnectionPpsIngress / ConnectionPpsEgress (packets)
      - ConnectionErrorCount (CRC errors, etc.)
      - ConnectionLightLevelTx / ConnectionLightLevelRx (optical power)
    
    IF ConnectionState = 0 → Link is down
    IF ConnectionErrorCount > 0 → Physical layer errors
    IF LightLevel dropping → Fiber degradation

Step 6: Check CloudWatch VIF metrics
  → aws cloudwatch get-metric-statistics
    Namespace: AWS/DX
    Dimensions: VirtualInterfaceId=<vif-id>
    Metrics:
      - VirtualInterfaceBpsIngress / VirtualInterfaceBpsEgress
      - VirtualInterfacePpsIngress / VirtualInterfacePpsEgress
    
    IF zero traffic → BGP not advertising routes or traffic not being sent
```

### DX Gateway Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| BGP session down | No connectivity to on-prem | Check ASN, peer IPs, MD5 key |
| Allowed prefixes missing | Partial connectivity (some VPCs unreachable) | Add missing CIDR to DX GW association |
| DX connection down | All on-prem connectivity lost | Check physical layer, contact provider |
| VIF not available | BGP can't establish | Check VLAN tag, VIF state |
| TGW route blackhole | Traffic enters TGW but drops | Check DX/VPN attachment state in TGW RT |
| Asymmetric routing | Intermittent failures | Ensure DX and VPN use same TGW RT |
| Route propagation disabled | TGW not learning DX routes | Enable propagation on TGW RT for DX attachment |

---

## SD-WAN + TGW Connect Troubleshooting

### Detect SD-WAN / TGW Connect

```
1. Check if TGW Connect attachments exist:
   → aws ec2 describe-transit-gateway-connects
   IF results → SD-WAN pattern (appliance in VPC, GRE+BGP to TGW)
   IF empty → Not using TGW Connect (check VPN or DX instead)

2. Check TGW Connect Peers (GRE tunnels + BGP sessions):
   → aws ec2 describe-transit-gateway-connect-peers
     --transit-gateway-attachment-id <connect-attachment-id>
   Shows: peer address, inside CIDR (BGP), GRE address, state
   
   Expected: state = "available"
   IF "failed" or "deleted" → GRE/BGP not established
```

### SD-WAN Investigation Flow (AWS-Side, All Brands)

```
Is the issue branch/site connectivity via SD-WAN?
├── NO → Skip this section
└── YES → Continue

Step 1: Check TGW Connect attachment state
  → aws ec2 describe-transit-gateway-connects
    Check: state = "available"
    Note the transportTransitGatewayAttachmentId (the VPC attachment of SD-WAN VPC)

Step 2: Check TGW Connect Peers (GRE + BGP)
  → aws ec2 describe-transit-gateway-connect-peers
    Check: state = "available"
    Check: bgpConfigurations[].bgpStatus = "up"
    
    IF peer state != available → GRE tunnel down
      → Check appliance EC2 is running
      → Check appliance SG allows GRE (protocol 47) from TGW CIDR
    
    IF bgpStatus != up → BGP session not established
      → Check peer ASN matches appliance config
      → Check inside CIDR (BGP peer IPs) match on both sides

Step 3: Check BGP routes learned from SD-WAN appliance
  → aws ec2 search-transit-gateway-routes
    --transit-gateway-route-table-id <spoke-rt>
    --filters "Name=type,Values=propagated"
  
  Look for branch/site CIDRs (e.g., 172.16.0.0/16, 10.100.0.0/16)
  IF branch CIDRs missing → BGP not advertising from appliance
    → Check appliance BGP config (route-map, prefix-list, network statements)

Step 4: Check SD-WAN appliance EC2 health
  → aws ec2 describe-instance-status --instance-ids <appliance-id>
  → aws cloudwatch get-metric-statistics
    Namespace: AWS/EC2, InstanceId=<appliance-id>
    Metrics: CPUUtilization, NetworkIn, NetworkOut, StatusCheckFailed

Step 5: Check SD-WAN VPC routing
  → aws ec2 describe-route-tables (SD-WAN VPC subnets)
  
  The appliance subnet RT must have:
    - 0.0.0.0/0 → TGW (or specific VPC CIDRs → TGW)
    - Local route for SD-WAN VPC CIDR
  
  The TGW Connect uses a "transport attachment" which is the VPC attachment
  of the SD-WAN VPC. Verify this VPC attachment exists and is associated
  with the correct TGW route table.

Step 6: Check CloudWatch TGW metrics for Connect peer
  → aws cloudwatch get-metric-statistics
    Namespace: AWS/TransitGateway
    Dimensions: TransitGatewayAttachment=<connect-attachment-id>
    Metrics: BytesIn, BytesOut, PacketsIn, PacketsOut
    
    IF zero bytes → GRE tunnel not passing traffic
    IF bytes flowing but branch unreachable → BGP route issue or firewall blocking

Step 7: Check if traffic passes through inspection (if applicable)
  → Same as east-west flow: TGW Spoke RT → Inspection VPC → Firewall → TGW Firewall RT
  → Branch traffic may also be inspected by the centralized firewall
```

### SD-WAN Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| TGW Connect peer down | No branch connectivity | Check GRE config, appliance SG (protocol 47) |
| BGP not established | Peer state available but no routes | Check ASN, peer IPs, inside CIDR |
| BGP not advertising routes | Branch CIDRs missing from TGW RT | Check appliance route-map/prefix-list |
| Transport attachment wrong | Connect can't establish | Verify Connect references correct VPC attachment |
| Appliance overloaded | Intermittent branch drops | Scale out or upgrade instance type |
| Appliance SG blocking GRE | Connect peer fails | Allow protocol 47 (GRE) from TGW CIDR |
| SD-WAN overlay down | Branches can't reach appliance | Check internet/MPLS path to appliance (outside AWS) |
| Route propagation disabled | TGW not learning Connect routes | Enable propagation on TGW RT for Connect attachment |
| Multiple Connect peers | Asymmetric routing | Ensure ECMP or consistent BGP path selection |

---

## Common Root Causes (by frequency)

1. **Security Group** missing inbound/outbound rule (most common)
2. **Network Firewall** rule not matching the traffic pattern
3. **Route table** missing route to TGW/Peering or wrong next hop
4. **TGW route table** blackhole or wrong association
5. **Appliance mode** not enabled (causes intermittent failures)
6. **Cross-VPC SG reference** used instead of CIDR across TGW (doesn't work)
7. **VPC Peering** route missing in one or both VPCs
8. **Public subnet RT** missing return route to firewall endpoint (breaks internet egress)
9. **Firewall default action** using `drop_established` instead of `drop_strict`
10. **VPN VTI routes** not persisted after reboot (on-prem connectivity lost)
11. **DX Gateway** allowed prefixes missing (partial on-prem connectivity)
12. **DX BGP** session down (ASN/peer IP/MD5 mismatch)
