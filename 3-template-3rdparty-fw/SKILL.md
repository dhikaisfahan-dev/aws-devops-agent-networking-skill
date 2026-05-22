---
name: aws-networking-investigation-3rdparty-fw
description: End-to-end networking investigation and troubleshooting for
  hub-and-spoke AWS architectures with Transit Gateway, 3rd party firewall
  appliances (Fortinet FortiGate, Palo Alto VM-Series) behind Gateway Load
  Balancer (GWLB), VPC Peering, centralized VPC endpoints, NAT Gateway, and
  hybrid connectivity via Direct Connect and VPN. Use this skill when
  investigating connectivity failures between VPCs (east-west), internet access
  issues (north-south egress), inbound traffic failures (north-south ingress),
  GWLB endpoint routing issues, firewall appliance health problems, firewall
  policy blocking traffic, Transit Gateway routing problems including blackhole
  routes, VPC Peering connectivity issues, asymmetric routing causing
  intermittent failures, security group misconfigurations, Direct Connect BGP
  session issues, VPN tunnel connectivity problems, or when analyzing VPC Flow
  Logs, TGW Flow Logs, FortiAnalyzer logs, or CloudTrail for network changes.
  Covers workload VPC private subnet architectures with centralized inspection
  via GWLB and 3rd party firewall appliances. Integrates with FortiAnalyzer MCP
  for log analysis, FortiManager MCP for policy inspection, and FortiGate MCP
  for direct appliance management.
---

# AWS Networking Investigation Skill (3rd Party Firewall + GWLB)

## Architecture Context

This skill is designed for hub-and-spoke architectures with centralized inspection using 3rd party firewall appliances behind AWS Gateway Load Balancer:

- **Workload VPCs** (spoke): Private subnets only, all traffic routed to inspection VPC via TGW
- **Inspection/Egress VPC** (hub): GWLB + Firewall appliances (EC2), NAT Gateway, IGW, VPC Endpoints
- **Ingress VPC**: ALB/NLB for published services
- **Transit Gateway**: Central routing with Spoke RT and Firewall RT
- **Gateway Load Balancer (GWLB)**: Distributes traffic to firewall appliance fleet
- **VPC Peering**: Optional point-to-point connectivity (no transitive routing)
- **Hybrid Connectivity**: Direct Connect and/or VPN to on-premises

The agent discovers actual VPC CIDRs, resource IDs, and log group names dynamically using AWS API calls.

---

## Environment Discovery (Always Run First)

Before investigating any issue, discover the environment topology:

```
1. List all VPCs and their CIDRs:
   → call_aws: aws ec2 describe-vpcs --query 'Vpcs[].{Id:VpcId,CIDR:CidrBlock,Name:Tags[?Key==`Name`].Value|[0]}'

2. List Transit Gateway and all attachments:
   → call_aws: aws ec2 describe-transit-gateways
   → call_aws: aws ec2 describe-transit-gateway-attachments

3. Identify the Inspection VPC:
   → call_aws: aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-type,Values=GatewayLoadBalancer"
   → The VPC containing the GWLB endpoints is the inspection VPC

4. Identify the Ingress VPC:
   → call_aws: aws elbv2 describe-load-balancers --query 'LoadBalancers[?Scheme==`internet-facing`]'

5. Identify hybrid connectivity:
   → call_aws: aws ec2 describe-vpn-connections (VPN)
   → call_aws: aws directconnect describe-direct-connect-gateways (DX)
   → call_aws: aws ec2 describe-transit-gateway-connects (SD-WAN)

6. Check for VPC Peering:
   → call_aws: aws ec2 describe-vpc-peering-connections

7. Check GWLB target health (firewall appliances):
   → call_aws: aws elbv2 describe-target-health

8. Check KNOWN-EXCEPTIONS.md (if provided):
   → Review known exceptions before flagging findings as issues
```

---

## Architecture Pattern Detection

Before investigating, determine which VPC pattern the environment uses:

```
1. Find Inspection VPC:
   → call_aws: aws ec2 describe-vpc-endpoints --filters "Name=vpc-endpoint-type,Values=GatewayLoadBalancer"
   → The VPC containing GWLB endpoints is the Inspection VPC

2. Find Egress VPC:
   → call_aws: aws ec2 describe-nat-gateways
   → call_aws: aws ec2 describe-internet-gateways
   → The VPC with NAT GW + IGW is the Egress VPC

3. Find Shared Services VPC:
   → call_aws: aws ec2 describe-vpc-endpoints (look for many interface endpoints)
   → call_aws: aws route53resolver list-resolver-endpoints
   → The VPC with centralized endpoints + DNS resolvers is Shared Services

4. Determine pattern:
   IF GWLB + NAT + IGW all in SAME VPC → Combined (simplest)
   IF GWLB in one VPC, NAT+IGW in another → Separate Inspection + Egress
   IF Endpoints/DNS in a third VPC → Shared Services VPC exists
```

### Traffic Paths by Pattern

**Pattern A: Combined Inspection + Egress (single VPC)**
```
Workload → TGW → Inspection VPC (GWLB → Firewall → NAT GW → IGW) → Internet
```

**Pattern B: Separate Inspection + Egress VPCs**
```
Workload → TGW (Spoke RT → Inspection VPC)
→ Inspection VPC (GWLB → Firewall Appliance → GWLB)
→ TGW (Firewall RT → Egress VPC)
→ Egress VPC (NAT GW → IGW) → Internet
```

**Pattern C: Separate Inspection + Egress + Shared Services**
```
Internet traffic:
  Workload → TGW → Inspection VPC (GWLB+FW) → TGW → Egress VPC → Internet

AWS service traffic:
  Workload → TGW → Shared Services VPC → VPC Endpoints → AWS Services

DNS:
  Workload → TGW → Shared Services VPC → Route 53 Resolver
```

### Troubleshooting Separate VPC Patterns

**Extra failure points in Pattern B/C:**
- Additional TGW route table entries (Firewall RT → Egress VPC)
- Egress VPC needs TGW attachment + correct RT association
- Return traffic must go back through Inspection VPC (symmetric)
- Shared Services VPC needs TGW attachment + routes

**Common issues:**
| Issue | Symptom | Fix |
|-------|---------|-----|
| Firewall RT missing Egress VPC route | Inspected but can't reach internet | Add Egress CIDR → Egress attachment in Firewall RT |
| Egress VPC missing return route | One-way internet | Add 10.0.0.0/8 → TGW in Egress NAT subnet RT |
| Shared Services not in TGW | Can't reach endpoints | Attach Shared VPC to TGW |
| Asymmetric return from Egress | Intermittent failures | Return must go through Inspection (stateful) |

---

## Available MCP Tools

### AWS API MCP (Infrastructure Layer)
- `call_aws` — Execute any AWS CLI command (EC2, VPC, TGW, GWLB, CloudWatch, Flow Logs)
- `suggest_aws_commands` — Get CLI command suggestions for a task

### FortiAnalyzer MCP (Log & Alert Layer)
- `search_traffic_logs` — Search firewall traffic logs by source/dest IP, port, action
- `search_security_logs` — Search IPS/AV/web filter logs
- `get_alerts` — Get security alerts (blocked traffic, threats)
- `search_event_logs` — Search system event logs (VPN, HA, admin actions)
- `get_log_stats` — Log statistics (volume, top talkers)
- `get_top_sources` / `get_top_destinations` — FortiView analytics
- `get_top_threats` — Top detected threats
- `get_incidents` — List security incidents
- `list_devices` — List managed devices and their status
- `get_system_status` — FortiAnalyzer system info

### FortiManager MCP (Policy Layer)
- `health_check` — Check if FortiManager is online
- `get_system_status` — FortiManager system info and version
- `list_adoms` — List Administrative Domains
- `list_devices` — List managed FortiGate devices with connection status
- `get_device_status` — Get specific device detail
- `list_policy_packages` — List policy packages in an ADOM
- `get_firewall_policies` — Get all policies in a package (src, dst, service, action)
- `get_firewall_policy_detail` — Get single policy detail by ID
- `list_address_objects` — List address objects (subnets, FQDNs)
- `list_service_objects` — List service objects (TCP/UDP ports)

### FortiGate MCP (Direct Appliance Layer)
- `list_devices` — List all registered FortiGate devices
- `health_check` — Check if firewall is online/healthy
- `get_system_status` — Firmware, hostname, serial, uptime
- `list_firewall_policies` — List all policies on the device
- `get_firewall_policy` — Get policy detail by ID with resolved objects
- `list_address_objects` — List address objects
- `list_service_objects` — List service objects
- `get_routing_table` — Get active routing table
- `list_interfaces` — List interfaces and status
- `list_static_routes` — List configured routes
- `get_ha_status` — HA cluster status

---

## Investigation Methodology (Tool Orchestration)

### Phase 1: AWS Infrastructure Check (ALWAYS START HERE)

```
Goal: Determine if the issue is at the AWS networking layer or firewall layer.

1.1 Check source Security Group (outbound)
    → call_aws: aws ec2 describe-security-group-rules --filters Name=group-id,Values=<sg-id>

1.2 Check source subnet Route Table
    → call_aws: aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=<subnet-id>
    Expected: 0.0.0.0/0 → tgw-xxxxx

1.3 Check TGW Route Tables
    → call_aws: aws ec2 search-transit-gateway-routes --transit-gateway-route-table-id <spoke-rt>
    Check for: blackhole routes, missing routes

1.4 Check TGW Subnet Route Table in Inspection VPC
    → call_aws: aws ec2 describe-route-tables --route-table-ids <tgw-subnet-rt>
    Expected: 0.0.0.0/0 → vpce-gwlb-xxxxx (GWLB endpoint)

1.5 Check GWLB Target Group Health
    → call_aws: aws elbv2 describe-target-health --target-group-arn <tg-arn>
    
    IF all targets HEALTHY → Go to Phase 2 (traffic reaches firewall, check logs)
    IF targets UNHEALTHY → Go to Phase 3 (firewall appliance is down)
```

### Phase 2: Firewall Log Analysis (Traffic Reaches Firewall)

```
Goal: Determine if the firewall is blocking the traffic and which rule.

2.1 Query FortiAnalyzer for the specific traffic
    → FortiAnalyzer MCP: search_traffic_logs
      Filters: src_ip=<source>, dst_ip=<destination>, dst_port=<port>
      Time range: last 1 hour
    
    IF logs show action=DENY/BLOCK → Traffic is blocked by firewall rule
       → Note the policy ID and rule name from the log
       → Go to Phase 4 (identify the blocking rule)
    
    IF logs show action=ACCEPT → Traffic passed firewall
       → Issue is AFTER the firewall (check return path, destination SG)
       → Go back to AWS: check destination VPC routing and SG
    
    IF NO logs found → Traffic never reached the firewall
       → Issue is BEFORE the firewall (AWS routing problem)
       → Go back to Phase 1, check more carefully

2.2 Check FortiAnalyzer alerts
    → FortiAnalyzer MCP: get_alerts
      Filter by source/destination IP
    
    IF alert exists → Shows threat detection (IPS/AV blocked)
       → Get alert details for signature/rule info

2.3 Check FortiAnalyzer device list (is firewall reporting?)
    → FortiAnalyzer MCP: list_devices
    
    IF device shows offline/unreachable → Firewall connectivity issue to FAZ
```

### Phase 3: Firewall Appliance Down

```
Goal: Determine why the firewall appliance is unhealthy.

3.1 Check EC2 instance status
    → call_aws: aws ec2 describe-instance-status --instance-ids <appliance-instance-id>
    
    IF instance stopped/terminated → Appliance is down
       → Check Auto Scaling Group for replacement
       → call_aws: aws autoscaling describe-auto-scaling-groups

3.2 Check FortiGate directly (if reachable)
    → FortiGate MCP: health_check
    → FortiGate MCP: get_device_status
    
    IF connection refused → Appliance OS is down or network issue
    IF responds → Appliance is up but GWLB health check failing
       → Check health check port/protocol configuration

3.3 Check FortiManager for device status
    → FortiManager MCP: execute
      Code: fortimanager.request('get', [{url: '/dvmdb/device'}])
    
    Shows: device connection status, last seen, firmware version

3.4 Check GWLB cross-zone load balancing
    → call_aws: aws elbv2 describe-load-balancer-attributes --load-balancer-arn <gwlb-arn>
    
    IF cross-zone disabled AND unhealthy target is in one AZ only
       → Traffic to that AZ is blackholed
       → Recommendation: Enable cross-zone load balancing

3.5 Check CloudWatch GWLB metrics
    → call_aws: aws cloudwatch get-metric-statistics
      Namespace: AWS/GatewayELB
      Metrics: UnHealthyHostCount, HealthyHostCount, ProcessedBytes
```

### Phase 4: Identify Blocking Firewall Rule

```
Goal: Find the exact rule that's blocking traffic and recommend a fix.

4.1 Get policy details from FortiManager
    → FortiManager MCP: get_firewall_policy_detail
      Parameters: package=<pkg-name>, policy_id=<id>, adom=root
    
    Shows: source/destination addresses, services, action, schedule

4.2 OR get policy from FortiGate directly
    → FortiGate MCP: get_firewall_policy
      Parameters: policy_id=<id>, device=<device-name>
    
    Shows: resolved address objects, service objects, action

4.3 Check address objects referenced in the policy
    → FortiManager MCP: list_address_objects
      Parameters: adom=root
    
    OR
    → FortiGate MCP: list_address_objects
      Parameters: device=<device-name>

4.4 Determine root cause:
    - Source IP not in the source address object → Add to address group
    - Destination IP not in the destination address object → Add to address group
    - Port/service not in the service object → Add service
    - Policy action is DENY → Need new ALLOW policy above it
    - Policy is disabled → Enable it
    - Schedule restricts time → Check if within allowed hours

4.5 Provide recommendation:
    "Traffic from <src> to <dst>:<port> is blocked by policy ID <X> named '<name>'.
     The policy denies traffic because <reason>.
     Recommendation: <specific fix>.
     Escalate to firewall team to implement the change."
```

### Phase 5: Return Path Verification

```
Goal: Verify the return traffic path is symmetric.

5.1 Check Appliance Mode on TGW attachment
    → call_aws: aws ec2 describe-transit-gateway-vpc-attachments
      Check: Options.ApplianceModeSupport = enable
    
    IF disabled → Causes intermittent failures (asymmetric routing)
       → Recommendation: Enable appliance mode

5.2 Check public subnet RT (for internet egress return)
    → call_aws: aws ec2 describe-route-tables --route-table-ids <public-rt>
    Expected: 10.0.0.0/8 → vpce-gwlb-xxxxx (per AZ)

5.3 Check GWLB endpoint routing is per-AZ
    → Verify AZ-A public subnet RT → AZ-A GWLB endpoint
    → Verify AZ-B public subnet RT → AZ-B GWLB endpoint
```

### Phase 6: CloudTrail & CloudWatch Correlation

```
Goal: Check if a recent change caused the issue.

6.1 Check CloudTrail for recent network changes
    → call_aws: aws cloudtrail lookup-events
      EventNames: AuthorizeSecurityGroupIngress, CreateRoute, DeleteRoute,
                  ModifyTransitGatewayVpcAttachment, UpdateRuleGroup

6.2 Check CloudWatch for anomalies
    → call_aws: aws cloudwatch get-metric-statistics
      - AWS/GatewayELB: UnHealthyHostCount, ProcessedBytes
      - AWS/TransitGateway: PacketDropCountNoRoute
      - AWS/NATGateway: ErrorPortAllocation
      - AWS/VPN: TunnelState

6.3 Correlate timeline:
    - When did the issue start? (from user report)
    - Any CloudTrail changes at that time?
    - Any metric anomalies at that time?
    - If change correlates → That's the root cause
```

---

## Detecting Offline/Degraded Firewalls

### Quick Health Check Sequence

```
1. AWS Level:
   → call_aws: aws elbv2 describe-target-health (GWLB targets)
   → Result: Shows healthy/unhealthy per target

3. FortiManager Level:
   → FortiManager MCP: list_devices
   → Result: Shows connection_status per device (up/down/unknown)

3. FortiAnalyzer Level:
   → FortiAnalyzer MCP: list_devices
   → Result: Shows last log received timestamp per device
   → If no logs in >5 minutes → Device may be offline

4. FortiGate Direct:
   → FortiGate MCP: health_check
   → Result: Immediate connectivity test to each registered device
```

### Offline Firewall Decision Tree

```
GWLB target unhealthy?
├── YES → EC2 instance running?
│   ├── NO → Instance stopped/terminated → Check ASG, launch new
│   └── YES → FortiGate responding?
│       ├── NO → OS crashed or network issue → Reboot instance
│       └── YES → Health check misconfigured
│           → Check GWLB health check port matches FortiGate listener
│
└── NO (all healthy) → Traffic still failing?
    ├── Check FortiAnalyzer logs → Rule blocking?
    │   ├── YES → Identify rule (Phase 4)
    │   └── NO → Check if FAZ receiving logs
    │       ├── NO → FAZ connectivity issue (not firewall issue)
    │       └── YES → Traffic not reaching firewall (AWS routing issue)
    └── Check FortiManager device status
        → Shows firmware version, HA status, resource usage
```

---

## Traffic Flow Paths

**East-West (via TGW + GWLB + Firewall):**
```
Source EC2 → SG → Subnet RT (→ TGW) → TGW Spoke RT (→ Inspection VPC)
→ TGW Subnet RT (→ GWLB Endpoint) → GWLB → Firewall Appliance (inspect)
→ GWLB → Firewall Subnet RT (→ TGW) → TGW Firewall RT (→ Dest VPC)
→ Subnet RT → SG → Destination EC2
```

**North-South Egress:**
```
Source EC2 → SG → Subnet RT (→ TGW) → TGW Spoke RT (→ Inspection VPC)
→ TGW Subnet RT (→ GWLB Endpoint) → GWLB → Firewall (inspect)
→ GWLB → Firewall Subnet RT (→ NAT GW) → NAT GW → Public Subnet RT (→ IGW) → Internet
```

**North-South Ingress:**
```
Internet → IGW → ALB (SG) → Subnet RT (→ TGW) → TGW Spoke RT (→ Inspection VPC)
→ TGW Subnet RT (→ GWLB Endpoint) → GWLB → Firewall (inspect)
→ GWLB → Firewall Subnet RT (→ TGW) → TGW Firewall RT (→ Workload VPC)
→ Subnet RT → SG → Destination EC2
```

---

## Key Rules

- TGW Appliance Mode MUST be enabled on inspection VPC attachment
- GWLB uses GENEVE encapsulation (port 6081) — firewall must support it
- GWLB cross-zone should be enabled for HA
- Public subnet RT must be per-AZ with per-AZ GWLB endpoints for return traffic
- Cross-VPC SG references DO NOT work across TGW — use CIDR
- Agent can query FortiAnalyzer/FortiManager/FortiGate via MCP for firewall-level investigation
- Agent CANNOT modify firewall rules — always recommend and escalate
- If FortiAnalyzer shows no logs for a flow, traffic never reached the firewall (AWS issue)
- If FortiAnalyzer shows ACCEPT but destination unreachable, issue is return path

## Common Root Causes (by frequency)

1. **Security Group** missing inbound/outbound rule
2. **Firewall policy blocking** — identified via FortiAnalyzer logs + FortiManager policy lookup
3. **GWLB target unhealthy** — firewall appliance down or health check failing
4. **Route table** missing route to TGW or GWLB endpoint
5. **TGW route table** blackhole or wrong association
6. **Appliance mode** not enabled (causes intermittent failures)
7. **GWLB cross-zone disabled** — one AZ has no healthy targets
8. **GENEVE tunnel misconfigured** on appliance — traffic enters but doesn't return
9. **Public subnet RT** missing return route to GWLB endpoint (per AZ)
10. **Recent change** — CloudTrail shows SG/RT/policy modification correlating with issue start

---

## Direct Connect Gateway Detection & Troubleshooting

### Detect DX Gateway vs Direct VGW Attachment

```
1. Check if DX Gateway exists:
   → call_aws: aws directconnect describe-direct-connect-gateways
   IF results → DX Gateway pattern (DX GW → TGW or VGW)
   IF empty → Check for VGW with DX VIF attached (legacy pattern)

2. Check DX Gateway associations:
   → call_aws: aws directconnect describe-direct-connect-gateway-associations
     --direct-connect-gateway-id <dxgw-id>
   Shows: Associated TGW or VGW, allowed prefixes, association state

3. Check DX Gateway attachments:
   → call_aws: aws directconnect describe-direct-connect-gateway-attachments
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
  → call_aws: aws directconnect describe-connections
    Check: connectionState = "available"
    IF "down" → Physical layer issue (contact colo/provider)

Step 2: Check Virtual Interface status
  → call_aws: aws directconnect describe-virtual-interfaces
    Check: virtualInterfaceState = "available"
    Check: bgpPeers[].bgpStatus = "up"
    
    IF BGP down → Check ASN, peer IPs, MD5 key, route filters

Step 3: Check DX Gateway → TGW association
  → call_aws: aws directconnect describe-direct-connect-gateway-associations
    Check: associationState = "associated"
    Check: allowedPrefixesToDirectConnectGateway includes all VPC CIDRs
    
    IF missing prefix → On-prem won't receive routes for that VPC

Step 4: Check CloudWatch DX metrics
  → call_aws: aws cloudwatch get-metric-statistics
    Namespace: AWS/DX
    Metrics:
      - ConnectionState (1=up, 0=down)
      - ConnectionBpsIngress / ConnectionBpsEgress
      - ConnectionErrorCount (CRC errors)
      - ConnectionLightLevelTx / ConnectionLightLevelRx (optical)
    
    IF ConnectionState = 0 → Link is down
    IF ConnectionErrorCount > 0 → Physical layer errors

Step 5: Check CloudWatch VIF metrics
  → call_aws: aws cloudwatch get-metric-statistics
    Namespace: AWS/DX, Dimensions: VirtualInterfaceId=<vif-id>
    Metrics: VirtualInterfaceBpsIngress/Egress, VirtualInterfacePpsIngress/Egress
    
    IF zero traffic → BGP not advertising or traffic not being sent
```

### DX Gateway Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| BGP session down | No on-prem connectivity | Check ASN, peer IPs, MD5 key |
| Allowed prefixes missing | Partial connectivity | Add CIDR to DX GW association |
| DX connection down | All on-prem lost | Physical layer, contact provider |
| VIF not available | BGP can't establish | Check VLAN tag, VIF state |
| TGW route blackhole | Traffic drops at TGW | Check DX attachment in TGW RT |
| Route propagation disabled | TGW not learning DX routes | Enable propagation |

---

## SD-WAN + TGW Connect Troubleshooting

### Detect SD-WAN / TGW Connect

```
1. Check if TGW Connect attachments exist:
   → call_aws: aws ec2 describe-transit-gateway-connects
   IF results → SD-WAN pattern (appliance in VPC, GRE+BGP to TGW)
   IF empty → Not using TGW Connect (check VPN or DX instead)

2. Check TGW Connect Peers:
   → call_aws: aws ec2 describe-transit-gateway-connect-peers
   Shows: peer address, inside CIDR (BGP), GRE address, state
```

### SD-WAN Investigation Flow (AWS-Side, All Brands)

```
Step 1: Check TGW Connect attachment state
  → call_aws: aws ec2 describe-transit-gateway-connects
    Check: state = "available"
    Note: transportTransitGatewayAttachmentId (VPC attachment of SD-WAN VPC)

Step 2: Check TGW Connect Peers (GRE + BGP)
  → call_aws: aws ec2 describe-transit-gateway-connect-peers
    Check: state = "available", bgpConfigurations[].bgpStatus = "up"
    
    IF peer state != available → GRE tunnel down
    IF bgpStatus != up → BGP not established

Step 3: Check BGP routes learned
  → call_aws: aws ec2 search-transit-gateway-routes
    --filters "Name=type,Values=propagated"
  Look for branch CIDRs. IF missing → BGP not advertising

Step 4: Check SD-WAN appliance EC2 health
  → call_aws: aws ec2 describe-instance-status
  → call_aws: aws cloudwatch get-metric-statistics (CPU, Network, StatusCheck)

Step 5: Check SD-WAN VPC routing
  → Appliance subnet RT must have routes to TGW
  → Transport attachment (VPC attachment) must be correct

Step 6: CloudWatch TGW Connect metrics
  → call_aws: aws cloudwatch get-metric-statistics
    Namespace: AWS/TransitGateway
    Dimensions: TransitGatewayAttachment=<connect-attachment-id>
    IF zero bytes → GRE tunnel not passing traffic
```

### Fortinet SD-WAN (with MCP Tools)

```
IF FortiManager MCP available:
  → FortiManager MCP: list_devices
    Shows: SD-WAN appliance connection status
  
  → FortiManager MCP: get_firewall_policies
    Parameters: package=<sdwan-pkg>, adom=root
    Shows: SD-WAN policies and routing rules

IF FortiGate MCP available:
  → FortiGate MCP: get_system_status
    Shows: SD-WAN appliance overall health
  
  → FortiGate MCP: list_interfaces
    Shows: SD-WAN overlay interfaces (UP/DOWN per tunnel)
    Look for: interfaces named sdwan*, vpn*, or overlay*
  
  → FortiGate MCP: get_routing_table
    Shows: Routes to branch sites via SD-WAN interfaces
    Verify: Branch CIDRs have next-hop via SD-WAN interface

IF FortiAnalyzer MCP available:
  → FortiAnalyzer MCP: search_traffic_logs
    Filter: srcintf or dstintf contains "sdwan" or "overlay"
    Shows: Traffic flowing through SD-WAN links
  
  → FortiAnalyzer MCP: get_alerts
    Shows: SD-WAN related alerts (link failover, SLA violation)
```

### Other SD-WAN Brands (Cisco, Palo Alto, VMware VeloCloud, Aruba)

```
Agent CANNOT query these appliances via MCP (no MCP server available).
AWS-side investigation only:

1. Check TGW Connect peer state → call_aws
2. Check BGP routes propagated → call_aws
3. Check appliance EC2 health → call_aws (CloudWatch)
4. Check VPC Flow Logs on appliance ENI → call_aws (CloudWatch Logs)
5. Check appliance Security Group allows GRE (protocol 47) → call_aws

IF all AWS-side checks pass but branches still unreachable:
  → Issue is inside the SD-WAN appliance or overlay network
  → Escalate to SD-WAN team with:
    - TGW Connect peer state (available/up)
    - BGP routes being advertised
    - Appliance EC2 metrics (healthy)
    - VPC Flow Logs showing traffic reaching appliance
    - Timestamp of issue start
```

### SD-WAN Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| TGW Connect peer down | No branch connectivity | Check GRE config, SG allows protocol 47 |
| BGP not established | Peer available but no routes | Check ASN, peer IPs, inside CIDR |
| BGP not advertising | Branch CIDRs missing from TGW | Check appliance route-map/prefix-list |
| Transport attachment wrong | Connect can't establish | Verify correct VPC attachment referenced |
| Appliance overloaded | Intermittent branch drops | Scale out or upgrade instance |
| SG blocking GRE | Connect peer fails | Allow protocol 47 from TGW CIDR |
| SD-WAN overlay down | Branches can't reach appliance | Outside AWS — check internet/MPLS path |
| SD-WAN SLA violation | Traffic shifted to backup | Check link quality (FortiAnalyzer alerts) |
| Multiple Connect peers | Asymmetric routing | Ensure ECMP or consistent BGP path |
| Route propagation disabled | TGW not learning routes | Enable propagation for Connect attachment |

### SD-WAN Decision Tree

```
Branch/site connectivity issue?
├── NO → Skip
└── YES → How connected?
    ├── VPN → VPN troubleshooting section
    ├── Direct Connect → DX Gateway section
    └── SD-WAN + TGW Connect → This section
        │
        ├── AWS checks (all brands):
        │   ├── TGW Connect peer state
        │   ├── BGP routes learned
        │   ├── Appliance EC2 health
        │   └── CloudWatch metrics
        │
        └── Appliance-level (brand-specific):
            ├── Fortinet → FortiManager/FortiGate/FortiAnalyzer MCP
            │   ├── SD-WAN member status
            │   ├── SLA probe results
            │   ├── Overlay interface status
            │   └── SD-WAN failover alerts
            ├── Cisco/Palo Alto/VMware/Aruba → AWS-only, escalate
            └── Unknown → AWS-only, escalate
```

---

## GWLB Instance (Firewall Appliance) CloudWatch Monitoring

### GWLB-Level Metrics

```
Check GWLB health and throughput:
→ call_aws: aws cloudwatch get-metric-statistics
  Namespace: AWS/GatewayELB
  Dimensions: LoadBalancer=<gwlb-id>

Key Metrics:
  - HealthyHostCount → Number of healthy firewall appliances
  - UnHealthyHostCount → Number of unhealthy appliances (CRITICAL if > 0)
  - ProcessedBytes → Total traffic through GWLB
  - NewFlowCount → New connections per period
  - ActiveFlowCount → Concurrent connections
  - ConsumedLCUs → Load balancer capacity units consumed

Decision:
  IF UnHealthyHostCount > 0 → Check per-instance metrics below
  IF ProcessedBytes dropping to 0 → No traffic reaching GWLB (routing issue)
  IF ActiveFlowCount spike → Possible DDoS or connection table exhaustion
  IF ConsumedLCUs near limit → Scale out appliance fleet
```

### Per-Appliance EC2 Instance Metrics

```
Check individual firewall appliance health:
→ call_aws: aws cloudwatch get-metric-statistics
  Namespace: AWS/EC2
  Dimensions: InstanceId=<appliance-instance-id>

Key Metrics:
  - CPUUtilization → IF > 80% → Appliance overloaded, scale out
  - NetworkIn / NetworkOut → Traffic volume per appliance
  - NetworkPacketsIn / NetworkPacketsOut → Packet rate
    IF PacketsIn high but PacketsOut low → Appliance dropping/buffering
  - StatusCheckFailed_Instance → IF 1 → OS/software issue, reboot
  - StatusCheckFailed_System → IF 1 → Hardware issue, stop+start (new host)

Enhanced Networking (ENA) Metrics:
  → call_aws: aws ec2 describe-instance-types --instance-types <type>
    Check: NetworkInfo.EnaSupport, NetworkInfo.MaximumNetworkInterfaces
  
  → CloudWatch: AWS/EC2
    - EnaAllowanceExceeded → IF > 0 → Instance type bandwidth limit hit
      → Recommendation: Upgrade to larger instance type
    - ConnTrackAllowanceExceeded → IF > 0 → Connection tracking table full
      → Recommendation: Upgrade instance or reduce concurrent connections
```

### Appliance Health Decision Tree

```
GWLB target unhealthy?
│
├── Check EC2 StatusCheckFailed_System
│   └── IF 1 → Hardware failure → Stop + Start instance (moves to new host)
│
├── Check EC2 StatusCheckFailed_Instance  
│   └── IF 1 → OS crash → Reboot instance
│
├── Check EC2 CPUUtilization
│   └── IF > 90% → Overloaded → Scale out ASG or upgrade instance type
│
├── Check EnaAllowanceExceeded
│   └── IF > 0 → Network bandwidth limit → Upgrade instance type
│
├── Check NetworkPacketsIn vs NetworkPacketsOut
│   └── IF In >> Out → Appliance processing issue (GENEVE tunnel or FW engine)
│
└── All EC2 metrics normal but GWLB unhealthy?
    → Health check misconfiguration
    → Check: GWLB health check port matches FortiGate/Palo Alto listener port
    → Check: Security group on appliance allows health check from GWLB subnet
```

### Correlating GWLB + Appliance Metrics with Traffic Issues

```
Investigation sequence:
1. call_aws: aws cloudwatch get-metric-statistics (GWLB UnHealthyHostCount)
   → Tells you IF appliances are down

2. call_aws: aws cloudwatch get-metric-statistics (GWLB ProcessedBytes)
   → Tells you IF traffic is flowing through GWLB

3. call_aws: aws cloudwatch get-metric-statistics (EC2 CPUUtilization per appliance)
   → Tells you IF appliances are overloaded

4. call_aws: aws cloudwatch get-metric-statistics (EC2 NetworkPacketsIn/Out per appliance)
   → Tells you IF appliances are processing or dropping

5. FortiGate MCP: health_check (if available)
   → Tells you IF the firewall application layer is responding

6. FortiAnalyzer MCP: list_devices (if available)
   → Tells you IF the firewall is sending logs (last seen timestamp)

Timeline correlation:
  - When did UnHealthyHostCount increase? → That's when the issue started
  - Did CPUUtilization spike before that? → Overload caused the failure
  - Did ProcessedBytes spike? → Traffic surge overwhelmed the appliance
  - CloudTrail: Was the ASG modified? Instance terminated? SG changed?
```

---

## Fallback: FortiGate MCP Only (No FortiManager / No FortiAnalyzer)

For environments with only FortiGate appliances (no centralized management or logging):

### What You Lose Without FortiManager/FortiAnalyzer

| Capability | With FAZ+FMG | FortiGate Only |
|---|---|---|
| Centralized log search | ✅ FAZ: search_traffic_logs | ❌ No historical logs via MCP |
| Alert/incident management | ✅ FAZ: get_alerts | ❌ Not available |
| Policy search across all devices | ✅ FMG: search + execute | ⚠️ Must query each FortiGate individually |
| Device fleet status | ✅ FMG: device list | ⚠️ Must health_check each device |
| PCAP downloads | ✅ FAZ: get_pcap_file | ❌ Not available |

### Investigation Flow (FortiGate MCP Only)

```
Phase 1: AWS Infrastructure Check (same as before)
  → call_aws: Check SG, RT, TGW, GWLB target health

Phase 2: Firewall Check (FortiGate MCP directly)

  2.1 Check if firewall is online
      → FortiGate MCP: health_check
      → FortiGate MCP: get_device_status
      
      IF offline → EC2 issue (check instance status via AWS)
      IF online → Continue

  2.2 Check firewall policies (find which rule applies)
      → FortiGate MCP: list_firewall_policies
        Parameters: device=<device-name>, vdom=root
      
      Look for policies matching:
        - srcaddr contains source IP/subnet
        - dstaddr contains destination IP/subnet
        - service contains the port/protocol
        - action = deny

  2.3 Get policy detail with resolved objects
      → FortiGate MCP: get_firewall_policy_detail
        Parameters: device=<device-name>, policy_id=<id>
      
      Shows: actual IP ranges, port numbers, schedule, action

  2.4 Check address objects
      → FortiGate MCP: list_address_objects
        Parameters: device=<device-name>
      
      Verify source/destination IPs are in the correct address objects

  2.5 Check routing on the firewall
      → FortiGate MCP: get_routing_table
        Parameters: device=<device-name>
      
      Verify firewall has routes for source and destination networks

  2.6 Check interfaces
      → FortiGate MCP: list_interfaces
      → FortiGate MCP: get_interface_status
      
      Verify interfaces are UP and have correct IP/zone assignment
```

### Limitations Without FortiAnalyzer

Without FortiAnalyzer, the agent CANNOT:
- Search historical traffic logs (no "show me blocked traffic in the last hour")
- Confirm if traffic actually reached the firewall (must infer from VPC Flow Logs)
- Download PCAPs for deep packet analysis
- View alert/threat details

**Workaround:** Use AWS VPC Flow Logs to infer:
```
1. Check VPC Flow Log on firewall appliance ENI (source VPC side)
   → call_aws: aws logs start-query (filter by appliance ENI)
   
   IF traffic shows ACCEPT on appliance ENI → Traffic reached the firewall
   IF no traffic on appliance ENI → Traffic never reached (routing issue)

2. Check VPC Flow Log on firewall appliance ENI (destination VPC side)
   → If ACCEPT on source side but nothing on dest side → Firewall dropped it
   → Then check policies via FortiGate MCP
```

### Multi-Device Environments (FortiGate Only, No FortiManager)

When managing multiple FortiGate devices without FortiManager:

```
1. Register all devices in FortiGate MCP config:
   {
     "devices": {
       "fw-az-a": {"host": "10.100.0.33", "api_token": "..."},
       "fw-az-b": {"host": "10.100.0.49", "api_token": "..."}
     }
   }

2. Health check all devices:
   → FortiGate MCP: health_check (checks all registered devices)

3. Query policies on the correct device:
   - Determine which AZ the traffic flows through (from TGW/GWLB routing)
   - Query that specific device's policies
   → FortiGate MCP: list_firewall_policies (device=fw-az-a)

4. Compare policies across devices (should be identical):
   → FortiGate MCP: list_firewall_policies (device=fw-az-a)
   → FortiGate MCP: list_firewall_policies (device=fw-az-b)
   → If different → Policy sync issue (common without FortiManager)
```

### Decision: Which MCP Tools Are Available?

The agent should auto-detect available tools at the start of investigation:

```
1. Try FortiAnalyzer MCP tools available?
   → If YES: Use full investigation flow (Phase 1-6)
   → If NO: Continue to step 2

2. Try FortiManager MCP tools available?
   → If YES: Use FMG for policy lookup + device status
   → If NO: Continue to step 3

3. FortiGate MCP tools available?
   → If YES: Use FortiGate-only flow (direct appliance queries)
   → If NO: Can only investigate at AWS level, escalate firewall checks to team

Summary:
- FAZ + FMG + FGT = Full autonomous investigation
- FMG + FGT (no FAZ) = Policy check OK, no log search
- FGT only = Direct device check, no centralized view
- None = AWS-only investigation, escalate all firewall checks
```
