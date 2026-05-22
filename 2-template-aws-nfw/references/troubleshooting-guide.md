# Networking Troubleshooting Guide

## Step-by-Step Troubleshooting Methodology

### The 7-Layer Investigation Framework

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 7: APPLICATION                                            │
│  Check: DNS resolution, application logs, health checks          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 6: LOAD BALANCER                                          │
│  Check: Target health, listener rules, SG on ALB/NLB            │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 5: SECURITY GROUP                                         │
│  Check: Inbound/outbound rules, SG references, port/protocol    │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4: ROUTE TABLE                                            │
│  Check: Subnet associations, route entries, blackholes           │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: TRANSIT GATEWAY                                        │
│  Check: Attachments, route tables, associations, propagations    │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: NETWORK FIREWALL                                       │
│  Check: Firewall policy, rule groups, stateful rules, logs       │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: INFRASTRUCTURE                                         │
│  Check: ENI status, AZ alignment, endpoint health, DX/VPN state  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting Decision Tree

```
START: Connectivity Issue Reported
│
├─── Is it within the SAME VPC?
│    │
│    ├── YES → Check Security Groups (inbound + outbound)
│    │         → Check if instances are in same/different subnets
│    │         → Check route table has local route
│    │         → Check ENI status
│    │
│    └── NO → Continue below
│
├─── Is it INTER-VPC (East-West)?
│    │
│    ├── YES → Follow East-West Troubleshooting Path
│    │    │
│    │    ├── Step 1: Check Source SG outbound
│    │    ├── Step 2: Check Source subnet route table (→ TGW)
│    │    ├── Step 3: Check TGW Spoke RT (→ Inspection VPC)
│    │    ├── Step 4: Check TGW subnet RT in Inspection VPC (→ FW endpoint)
│    │    ├── Step 5: Check Network Firewall rules & logs
│    │    ├── Step 6: Check Firewall subnet RT (→ TGW)
│    │    ├── Step 7: Check TGW Firewall RT (→ Destination VPC)
│    │    ├── Step 8: Check Destination subnet RT
│    │    └── Step 9: Check Destination SG inbound
│    │
│    └── NO → Continue below
│
├─── Is it to INTERNET (North-South Egress)?
│    │
│    ├── YES → Follow North-South Egress Path
│    │    │
│    │    ├── Step 1: Check Source SG outbound (port 443/80)
│    │    ├── Step 2: Check Source subnet RT (→ TGW)
│    │    ├── Step 3: Check TGW Spoke RT (0.0.0.0/0 → Inspection VPC)
│    │    ├── Step 4: Check TGW subnet RT (→ FW endpoint)
│    │    ├── Step 5: Check Network Firewall (domain allowlist)
│    │    ├── Step 6: Check Firewall subnet RT (0.0.0.0/0 → NAT GW)
│    │    ├── Step 7: Check NAT Gateway status & EIP
│    │    ├── Step 8: Check Public subnet RT (0.0.0.0/0 → IGW)
│    │    └── Step 9: Check IGW attachment
│    │
│    └── NO → Continue below
│
├─── Is it from INTERNET (North-South Ingress)?
│    │
│    ├── YES → Follow Ingress Path
│    │    │
│    │    ├── Step 1: Check DNS resolution to ALB/NLB
│    │    ├── Step 2: Check IGW in Ingress VPC
│    │    ├── Step 3: Check ALB/NLB Security Group (inbound 443/80)
│    │    ├── Step 4: Check ALB/NLB target health
│    │    ├── Step 5: Check Ingress VPC subnet RT (→ TGW)
│    │    ├── Step 6: Check TGW Spoke RT (→ Inspection VPC)
│    │    ├── Step 7: Check Network Firewall rules
│    │    ├── Step 8: Check TGW Firewall RT (→ Workload VPC)
│    │    ├── Step 9: Check Workload VPC subnet RT
│    │    └── Step 10: Check Destination SG inbound
│    │
│    └── NO → Continue below
│
├─── Is it to AWS SERVICE (S3, DynamoDB, SQS)?
│    │
│    ├── YES → Follow AWS Service Path
│    │    │
│    │    ├── Step 1: Check Source SG outbound (port 443)
│    │    ├── Step 2: Check Source subnet RT (→ TGW)
│    │    ├── Step 3: Check TGW routing to Inspection VPC
│    │    ├── Step 4: Check Network Firewall rules
│    │    ├── Step 5: Check VPC Endpoint exists and is active
│    │    ├── Step 6: Check VPC Endpoint policy
│    │    ├── Step 7: Check DNS resolution (private DNS enabled?)
│    │    └── Step 8: Check IAM permissions on endpoint
│    │
│    └── NO → Continue below
│
└─── Is it to ON-PREMISES?
     │
     ├── YES → Follow Hybrid Path
     │    │
     │    ├── Step 1: Check Source SG outbound
     │    ├── Step 2: Check Source subnet RT (→ TGW)
     │    ├── Step 3: Check TGW Spoke RT (→ Inspection VPC)
     │    ├── Step 4: Check Network Firewall rules
     │    ├── Step 5: Check TGW Firewall RT (192.168.0.0/16 → DX/VPN)
     │    ├── Step 6: Check DX Virtual Interface / VPN Tunnel status
     │    ├── Step 7: Check BGP route advertisements
     │    └── Step 8: Check on-premises firewall/routing
     │
     └── NO → Escalate - Unknown traffic pattern
```

---

## Common Issues & Resolution

### Issue 1: Inter-VPC Communication Failure

**Symptoms:**
- Timeout connecting from VPC WL1 to VPC WL2
- No response on specific ports

**Investigation Steps:**

```bash
# Step 1: Verify Security Groups
aws ec2 describe-security-groups --group-ids sg-source-id \
  --query 'SecurityGroups[].IpPermissionsEgress[]'

aws ec2 describe-security-groups --group-ids sg-dest-id \
  --query 'SecurityGroups[].IpPermissions[]'

# Step 2: Check Route Tables
aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=subnet-source" \
  --query 'RouteTables[].Routes[]'

# Step 3: Check TGW Route Tables
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke-id \
  --filters "Name=route-search.exact-match,Values=10.1.0.0/16"

# Step 4: Check Network Firewall Logs
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.src_ip = "10.0.1.10" }'

# Step 5: Use VPC Reachability Analyzer
aws ec2 create-network-insights-path \
  --source eni-source-id \
  --destination eni-dest-id \
  --protocol TCP \
  --destination-port 443

aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-xxxxx
```

**Common Root Causes:**
| Root Cause | Fix |
|-----------|-----|
| Security Group missing rule | Add inbound rule for source CIDR/SG on required port |
| Route table missing TGW route | Add 0.0.0.0/0 → TGW or specific CIDR → TGW |
| TGW route table blackhole | Check VPC attachment state, re-associate |
| Network Firewall blocking | Add/modify stateful rule to allow traffic |
| Asymmetric routing | Ensure both AZs have consistent FW endpoint routing |

---

### Issue 2: Internet Access Failure (Egress)

**Symptoms:**
- Cannot reach external APIs
- DNS resolution works but connection times out
- curl/wget hangs

**Investigation Steps:**

```bash
# Step 1: Verify NAT Gateway status
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=vpc-inspection-id" \
  --query 'NatGateways[].{Id:NatGatewayId,State:State,AZ:SubnetId}'

# Step 2: Check NAT Gateway has Elastic IP
aws ec2 describe-nat-gateways \
  --nat-gateway-ids nat-xxxxx \
  --query 'NatGateways[].NatGatewayAddresses[]'

# Step 3: Check Network Firewall domain allowlist
aws network-firewall describe-rule-group \
  --rule-group-arn arn:aws:network-firewall:region:account:stateful-rulegroup/domain-allowlist

# Step 4: Check Public Subnet Route Table
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-public-id" \
  --query 'RouteTables[].Routes[]'

# Step 5: Check IGW attachment
aws ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=vpc-inspection-id"

# Step 6: Check CloudWatch metrics for NAT GW
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T01:00:00Z \
  --period 300 \
  --statistics Sum
```

**Common Root Causes:**
| Root Cause | Fix |
|-----------|-----|
| NAT Gateway in wrong AZ | Ensure NAT GW exists in same AZ as firewall endpoint |
| Firewall blocking domain | Add domain to allowlist in stateful rule group |
| Missing route to NAT GW | Add 0.0.0.0/0 → NAT GW in firewall subnet RT |
| NAT GW port exhaustion | Add additional NAT GW or reduce connections |
| IGW not attached | Attach IGW to inspection VPC |

---

### Issue 3: Network Firewall Dropping Traffic

**Symptoms:**
- VPC Flow Logs show traffic leaving source
- Traffic never arrives at destination
- Firewall alert logs show DROP action

**Investigation Steps:**

```bash
# Step 1: Check Firewall Alert Logs
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.event_type = "alert" }' \
  --start-time $(date -d '1 hour ago' +%s000)

# Step 2: Check Firewall Flow Logs
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/flow \
  --filter-pattern '{ $.event.src_ip = "10.0.1.10" && $.event.dest_ip = "10.1.1.20" }'

# Step 3: List all rule groups in policy
aws network-firewall describe-firewall-policy \
  --firewall-policy-arn arn:aws:network-firewall:region:account:firewall-policy/policy-name

# Step 4: Check specific stateful rule group
aws network-firewall describe-rule-group \
  --rule-group-arn arn:aws:network-firewall:region:account:stateful-rulegroup/east-west-rules

# Step 5: Check rule evaluation order
aws network-firewall describe-firewall-policy \
  --firewall-policy-arn arn:aws:network-firewall:region:account:firewall-policy/policy-name \
  --query 'FirewallPolicy.StatefulRuleGroupReferences[].{Priority:Priority,ARN:ResourceArn}'
```

**Common Root Causes:**
| Root Cause | Fix |
|-----------|-----|
| No matching allow rule | Add stateful rule for the traffic pattern |
| Rule priority ordering | Adjust priority (lower number = evaluated first) |
| Default action is DROP | Add explicit allow rule before default drop |
| Stateless rule forwarding | Ensure stateless rules forward to stateful engine |
| Wrong protocol in rule | Verify TCP vs UDP vs ICMP in rule definition |

---

### Issue 4: Transit Gateway Routing Issues

**Symptoms:**
- Traffic reaches TGW but doesn't arrive at destination
- Blackhole routes in TGW route table
- Asymmetric routing causing connection resets

**Investigation Steps:**

```bash
# Step 1: Check TGW attachment state
aws ec2 describe-transit-gateway-attachments \
  --filters "Name=transit-gateway-id,Values=tgw-xxxxx" \
  --query 'TransitGatewayAttachments[].{VPC:ResourceId,State:State,Association:Association}'

# Step 2: Check Spoke Route Table
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=state,Values=active,blackhole"

# Step 3: Check Firewall Route Table
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-firewall \
  --filters "Name=state,Values=active,blackhole"

# Step 4: Verify associations
aws ec2 get-transit-gateway-route-table-associations \
  --transit-gateway-route-table-id tgw-rtb-spoke

aws ec2 get-transit-gateway-route-table-associations \
  --transit-gateway-route-table-id tgw-rtb-firewall

# Step 5: Check for blackhole routes
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=state,Values=blackhole"
```

**Common Root Causes:**
| Root Cause | Fix |
|-----------|-----|
| VPC attachment in wrong RT | Re-associate attachment to correct TGW RT |
| Blackhole route | Check if VPC attachment is deleted/failed, recreate |
| Missing static route | Add static route for destination CIDR |
| Propagation disabled | Enable route propagation from attachment |
| Appliance mode not enabled | Enable appliance mode on inspection VPC attachment |

---

### Issue 5: VPC Endpoint Connectivity Issues

**Symptoms:**
- Cannot reach S3, DynamoDB, or other AWS services
- DNS resolution fails for service endpoints
- Access denied errors

**Investigation Steps:**

```bash
# Step 1: Check VPC Endpoint status
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-inspection-id" \
  --query 'VpcEndpoints[].{Service:ServiceName,State:State,Type:VpcEndpointType}'

# Step 2: Check endpoint policy
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].PolicyDocument'

# Step 3: For Gateway Endpoints - check route table
aws ec2 describe-route-tables \
  --filters "Name=route.gateway-id,Values=vpce-xxxxx"

# Step 4: For Interface Endpoints - check DNS
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].{DNS:DnsEntries,PrivateDns:PrivateDnsEnabled}'

# Step 5: Check Security Group on Interface Endpoint
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].Groups[]'
```

**Common Root Causes:**
| Root Cause | Fix |
|-----------|-----|
| Endpoint not in correct subnet | Create endpoint in correct AZ/subnet |
| Private DNS not enabled | Enable private DNS on interface endpoint |
| Endpoint policy too restrictive | Update endpoint policy to allow required actions |
| Gateway endpoint not in RT | Associate gateway endpoint with correct route tables |
| SG on interface endpoint blocking | Add inbound rule for port 443 from VPC CIDR |

---

### Issue 6: Direct Connect / VPN Issues

**Symptoms:**
- Cannot reach on-premises resources
- BGP session down
- Intermittent connectivity

**Investigation Steps:**

```bash
# Step 1: Check DX Connection status
aws directconnect describe-connections \
  --query 'connections[].{Id:connectionId,State:connectionState,Bandwidth:bandwidth}'

# Step 2: Check Virtual Interface status
aws directconnect describe-virtual-interfaces \
  --query 'virtualInterfaces[].{Id:virtualInterfaceId,State:virtualInterfaceState,BGP:bgpPeers}'

# Step 3: Check BGP peer status
aws directconnect describe-virtual-interfaces \
  --virtual-interface-id dxvif-xxxxx \
  --query 'virtualInterfaces[].bgpPeers[].{Status:bgpStatus,State:bgpPeerState}'

# Step 4: Check VPN tunnel status
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-xxxxx \
  --query 'VpnConnections[].VgwTelemetry[].{Status:status,StatusMessage:statusMessage}'

# Step 5: Check TGW route for on-premises CIDR
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-firewall \
  --filters "Name=route-search.exact-match,Values=192.168.0.0/16"
```

---

### Issue 7: Asymmetric Routing in Inspection VPC

**Symptoms:**
- Connections work in one direction but not the other
- TCP RST packets
- Stateful firewall dropping return traffic

**Root Cause Explanation:**
```
PROBLEM: Traffic enters via AZ-A firewall endpoint but returns via AZ-B
         Stateful firewall in AZ-B has no session state → DROPS return traffic

CORRECT SETUP:
- Enable "Appliance Mode" on TGW attachment for Inspection VPC
- This ensures symmetric routing through same AZ firewall endpoint
```

**Fix:**
```bash
# Enable Appliance Mode on Inspection VPC TGW Attachment
aws ec2 modify-transit-gateway-vpc-attachment \
  --transit-gateway-attachment-id tgw-attach-inspection-vpc \
  --options ApplianceModeSupport=enable
```

---

## Diagnostic Commands Quick Reference

### Security Group Analysis
```bash
# Check all SG rules for an instance
aws ec2 describe-instances --instance-ids i-xxxxx \
  --query 'Reservations[].Instances[].SecurityGroups[]'

# Check specific SG rules
aws ec2 describe-security-groups --group-ids sg-xxxxx

# Find SGs allowing specific port
aws ec2 describe-security-groups \
  --filters "Name=ip-permission.to-port,Values=443"
```

### Route Table Analysis
```bash
# Get route table for a subnet
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-xxxxx"

# Check for specific route
aws ec2 describe-route-tables --route-table-ids rtb-xxxxx \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]'
```

### VPC Flow Logs Analysis
```bash
# Query flow logs for specific traffic
aws logs filter-log-events \
  --log-group-name vpc-flow-logs \
  --filter-pattern '[version, account, eni, srcaddr="10.0.1.10", dstaddr="10.1.1.20", srcport, dstport="443", protocol="6", packets, bytes, start, end, action, log_status]'

# Check for REJECT entries
aws logs filter-log-events \
  --log-group-name vpc-flow-logs \
  --filter-pattern 'REJECT'
```

### Network Firewall Logs
```bash
# Alert logs (blocked traffic)
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.alert.action = "blocked" }'

# Flow logs (all traffic through firewall)
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/flow \
  --start-time $(date -d '30 minutes ago' +%s000)
```

### Transit Gateway Flow Logs
```bash
# Query TGW flow logs for specific source
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, flowDirection, tgwSrcVpc, tgwDstVpc, tgwAttachmentId, action
    | filter srcAddr = "SOURCE_IP"
    | sort @timestamp desc
    | limit 50'

# Find rejected/dropped traffic at TGW level
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, tgwAttachmentId, action
    | filter action = "REJECT"
    | sort @timestamp desc
    | limit 20'

# Traffic between specific VPCs
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, flowDirection, action
    | filter tgwSrcVpc = "vpc-xxxxx" and tgwDstVpc = "vpc-yyyyy"
    | sort @timestamp desc
    | limit 50'
```

### CloudTrail - Network Change Audit
```bash
# Who changed security groups in the last 24 hours?
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AuthorizeSecurityGroupIngress \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'

# Who modified route tables?
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateRoute \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'

# Who modified firewall rules?
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateRuleGroup \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'

# All changes to a specific resource (e.g., security group)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=sg-xxxxx \
  --start-time $(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ) \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'
```

### CloudWatch Network Metrics (Quick Checks)
```bash
# NAT Gateway port exhaustion
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# TGW packet drops (blackhole routes)
aws cloudwatch get-metric-statistics \
  --namespace AWS/TransitGateway --metric-name PacketDropCountNoRoute \
  --dimensions Name=TransitGateway,Value=tgw-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Network Firewall dropped packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall --metric-name DroppedPackets \
  --dimensions Name=FirewallName,Value=my-firewall \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# VPN tunnel state (1=UP, 0=DOWN)
aws cloudwatch get-metric-statistics \
  --namespace AWS/VPN --metric-name TunnelState \
  --dimensions Name=VpnId,Value=vpn-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average

# ALB unhealthy targets
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name UnHealthyHostCount \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx Name=TargetGroup,Value=targetgroup/my-tg/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum

# List all ALARM state network alarms
aws cloudwatch describe-alarms --state-value ALARM \
  --query 'MetricAlarms[?Namespace==`AWS/NATGateway` || Namespace==`AWS/TransitGateway` || Namespace==`AWS/NetworkFirewall` || Namespace==`AWS/VPN` || Namespace==`AWS/ApplicationELB`].{Name:AlarmName,Metric:MetricName,State:StateValue}'
```

### VPC Reachability Analyzer
```bash
# Create path and analyze
aws ec2 create-network-insights-path \
  --source eni-source \
  --destination eni-dest \
  --protocol TCP \
  --destination-port 443

aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-xxxxx

# Get analysis results
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-xxxxx
```
