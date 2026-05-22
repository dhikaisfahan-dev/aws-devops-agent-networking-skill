# Runbook: AWS Cloud WAN Troubleshooting

## Trigger Conditions
- Connectivity issues between segments in Cloud WAN
- Attachments not routing traffic
- Service insertion (firewall) not working
- Cross-region connectivity failures
- Route policy not applying correctly
- Segment isolation not working (traffic leaking between segments)

---

## Background: Cloud WAN vs Transit Gateway

| Aspect | Transit Gateway | Cloud WAN |
|--------|----------------|-----------|
| Scope | Single region | Global (multi-region) |
| Routing | Route tables (manual) | Network policy (intent-based) |
| Segmentation | Route table isolation | Segments (policy-driven) |
| Firewall insertion | Appliance mode + routing | Service Insertion feature |
| Management | Per-region TGW | Single global network |

---

## Investigation Steps

### Step 1: Check Global Network Status

```bash
# List global networks
aws networkmanager list-global-networks \
  --query 'GlobalNetworks[].{Id:GlobalNetworkId,State:State,Description:Description}'

# Get core network (Cloud WAN)
aws networkmanager list-core-networks \
  --query 'CoreNetworks[].{Id:CoreNetworkId,State:State,Description:Description}'

# Get core network details
aws networkmanager get-core-network --core-network-id <core-network-id> \
  --query '{State:CoreNetwork.State,Segments:CoreNetwork.Segments,Edges:CoreNetwork.Edges}'
```

### Step 2: Check Attachments

```bash
# List all attachments (VPCs, VPNs, Connect, TGW peering)
aws networkmanager list-attachments \
  --core-network-id <core-network-id> \
  --query 'Attachments[].{Id:AttachmentId,Type:AttachmentType,State:State,Segment:SegmentName,EdgeLocation:EdgeLocation,ResourceArn:ResourceArn}'

# Get specific attachment details
aws networkmanager get-vpc-attachment --attachment-id <attachment-id> \
  --query '{State:VpcAttachment.Attachment.State,Segment:VpcAttachment.Attachment.SegmentName,VpcArn:VpcAttachment.Attachment.ResourceArn,SubnetArns:VpcAttachment.SubnetArns}'
```

**Attachment states:**
- `AVAILABLE` — working correctly
- `CREATING` — still being provisioned
- `FAILED` — check error, recreate
- `PENDING_ATTACHMENT_ACCEPTANCE` — needs acceptance
- `PENDING_NETWORK_UPDATE` — policy change propagating

### Step 3: Check Segments and Routing

```bash
# List segments
aws networkmanager get-core-network --core-network-id <core-network-id> \
  --query 'CoreNetwork.Segments[].{Name:Name,EdgeLocations:EdgeLocations,SharedSegments:SharedSegments}'

# Get route table for a segment in a specific edge location
aws networkmanager get-network-routes \
  --core-network-id <core-network-id> \
  --route-table-identifier '{SegmentName: "<segment-name>", CoreNetworkId: "<core-network-id>", EdgeLocation: "<region>"}' \
  --query 'NetworkRoutes[].{Destination:DestinationCidrBlock,State:State,Type:Type,Attachments:Destinations[].{AttachmentId:TransitGatewayAttachmentId,ResourceId:ResourceId}}'
```

**Check for:**
- Missing routes (destination CIDR not in segment route table)
- Blackhole routes (state != active)
- Wrong segment (attachment in wrong segment)

### Step 4: Check Network Policy

```bash
# Get the current policy document
aws networkmanager get-core-network-policy --core-network-id <core-network-id> \
  --query 'CoreNetworkPolicy.PolicyDocument'

# Check policy versions
aws networkmanager list-core-network-policy-versions --core-network-id <core-network-id> \
  --query 'CoreNetworkPolicyVersions[].{Version:PolicyVersionId,ChangeSetState:ChangeSetState,CreatedAt:CreatedAt}'
```

**Policy defines:**
- Segments (isolation boundaries)
- Segment actions (sharing, route propagation)
- Attachment policies (which VPCs go in which segment)
- Service insertion (firewall routing)

### Step 5: Check Service Insertion (Firewall)

```bash
# If using service insertion for centralized inspection:
# Check the service insertion segment
aws networkmanager get-core-network --core-network-id <core-network-id> \
  --query 'CoreNetwork.Segments[?Name==`inspection`]'

# Check if firewall attachment is in the correct segment
aws networkmanager list-attachments \
  --core-network-id <core-network-id> \
  --attachment-type VPC \
  --query 'Attachments[?SegmentName==`inspection`]'

# Verify send-via / send-to routing in policy
# The policy should have segment-actions with "send-via" for inspection
```

### Step 6: Check Cross-Region Connectivity

```bash
# List edge locations (regions) in the core network
aws networkmanager get-core-network --core-network-id <core-network-id> \
  --query 'CoreNetwork.Edges[].{EdgeLocation:EdgeLocation,Asn:Asn}'

# Check peering between regions
aws networkmanager list-peerings \
  --core-network-id <core-network-id> \
  --query 'Peerings[].{Id:PeeringId,Type:PeeringType,State:State,EdgeLocation:EdgeLocation}'

# Check routes are propagated cross-region
aws networkmanager get-network-routes \
  --core-network-id <core-network-id> \
  --route-table-identifier '{SegmentName: "<segment>", CoreNetworkId: "<id>", EdgeLocation: "<remote-region>"}'
```

### Step 7: Check CloudWatch Metrics

```bash
# Cloud WAN metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkManager \
  --metric-name BytesIn \
  --dimensions Name=CoreNetworkId,Value=<core-network-id> Name=EdgeLocation,Value=<region> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Check for dropped packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkManager \
  --metric-name DroppedPackets \
  --dimensions Name=CoreNetworkId,Value=<core-network-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Attachment in wrong segment | Can't reach resources in other segment | Update attachment policy or move attachment |
| Segment not shared | Cross-segment traffic blocked | Add segment sharing in policy |
| Service insertion misconfigured | Traffic bypasses firewall | Check send-via/send-to in policy |
| Policy change pending | Routes not updated | Wait for PENDING_NETWORK_UPDATE to complete |
| Cross-region route missing | Can't reach remote region | Check edge locations and peering state |
| Attachment FAILED | VPC not connected | Check subnet, VPC CIDR overlap, recreate |
| Route propagation disabled | Segment missing routes | Enable route propagation in segment actions |
| Blackhole route | Traffic drops | Check attachment state, may need recreation |

---

## Cloud WAN vs TGW Decision

```
Using Cloud WAN?
├── Check: aws networkmanager list-core-networks
│   IF results → Cloud WAN architecture
│   IF empty → Traditional TGW architecture (use TGW troubleshooting)
│
└── Cloud WAN investigation:
    ├── Check attachment state (AVAILABLE?)
    ├── Check segment assignment (correct segment?)
    ├── Check segment routes (destination reachable?)
    ├── Check policy (sharing, service insertion)
    └── Check cross-region peering (if multi-region)
```
