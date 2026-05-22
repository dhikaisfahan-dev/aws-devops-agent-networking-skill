# Runbook: Hybrid Connectivity (On-Premises ↔ Cloud)

## Trigger Conditions
- On-premises servers cannot reach cloud workloads
- Cloud workloads cannot reach on-premises resources
- BGP session flapping
- Direct Connect or VPN tunnel down
- Intermittent connectivity to on-premises

## Pre-Investigation Information Needed
- Source (on-premises or cloud) IP address
- Destination IP address
- Protocol and port
- Direct Connect or VPN connection ID
- BGP ASN numbers (AWS side and customer side)

---

## Investigation Steps

### Step 1: Check Direct Connect Connection Status

```bash
# List all DX connections
aws directconnect describe-connections \
  --query 'connections[].{
    Id:connectionId,
    Name:connectionName,
    State:connectionState,
    Bandwidth:bandwidth,
    Location:location,
    Partner:partnerName
  }' --output table
```

**Expected States:**
- `available` - Connection is up and operational
- `down` - Physical connection is down
- `ordering` - Connection being provisioned
- `deleted` - Connection has been deleted

### Step 2: Check Virtual Interface Status

```bash
# List virtual interfaces
aws directconnect describe-virtual-interfaces \
  --query 'virtualInterfaces[].{
    Id:virtualInterfaceId,
    Name:virtualInterfaceName,
    State:virtualInterfaceState,
    Type:virtualInterfaceType,
    VLAN:vlan,
    ASN:asn,
    AmazonASN:amazonSideAsn,
    BGPPeers:bgpPeers[].{
      PeerIP:customerAddress,
      AmazonIP:amazonAddress,
      BGPStatus:bgpStatus,
      PeerState:bgpPeerState
    }
  }' --output json
```

**Expected:**
- `virtualInterfaceState`: "available"
- `bgpStatus`: "up"
- `bgpPeerState`: "established" (for private VIF) or "available"

### Step 3: Check BGP Route Advertisements

```bash
# Check routes being advertised from AWS to on-premises
aws directconnect describe-virtual-interfaces \
  --virtual-interface-id dxvif-xxxxx \
  --query 'virtualInterfaces[].{
    RouteFilterPrefixes:routeFilterPrefixes,
    CustomerRouterConfig:customerRouterConfig
  }'

# For Transit VIF - check allowed prefixes
aws directconnect describe-direct-connect-gateway-associations \
  --direct-connect-gateway-id dxgw-xxxxx \
  --query 'directConnectGatewayAssociations[].{
    TGW:associatedGateway.id,
    AllowedPrefixes:allowedPrefixesToDirectConnectGateway[].cidr,
    State:associationState
  }'
```

**Expected:** Allowed prefixes include all VPC CIDRs that need on-premises access:
- 10.0.0.0/16, 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16
- Or summarized: 10.0.0.0/8

### Step 4: Check VPN Tunnel Status (if using VPN)

```bash
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-xxxxx \
  --query 'VpnConnections[].{
    Id:VpnConnectionId,
    State:State,
    Type:Type,
    TGW:TransitGatewayId,
    Tunnels:VgwTelemetry[].{
      OutsideIP:OutsideIpAddress,
      Status:status,
      StatusMessage:statusMessage,
      LastChange:lastStatusChange,
      AcceptedRoutes:acceptedRouteCount
    }
  }'
```

**Expected:**
- At least one tunnel with Status: "UP"
- AcceptedRoutes > 0 (if using BGP)

### Step 5: Check TGW Route Tables

```bash
# Check Spoke RT has route for on-premises CIDR
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=192.168.0.0/16"

# This should point to Inspection VPC (for firewall inspection)
# NOT directly to DX/VPN attachment

# Check Firewall RT has route for on-premises
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-firewall \
  --filters "Name=route-search.exact-match,Values=192.168.0.0/16"

# This should point to DX/VPN attachment
```

**Traffic Flow:**
```
Cloud → TGW (Spoke RT: 192.168.0.0/16 → Inspection VPC) → 
Firewall → TGW (Firewall RT: 192.168.0.0/16 → DX/VPN attachment) → 
On-Premises
```

### Step 6: Check Network Firewall Rules

```bash
# Check if firewall allows on-premises traffic
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ ($.event.src_ip = "10.0.*" && $.event.dest_ip = "192.168.*") || ($.event.src_ip = "192.168.*" && $.event.dest_ip = "10.0.*") }' \
  --start-time $(date -u -v-1H +%s000)

# Check on-premises rule group
aws network-firewall describe-rule-group \
  --rule-group-name onprem-rules \
  --type STATEFUL
```

### Step 7: Check DX/VPN Attachment Association

```bash
# Verify DX/VPN attachment is associated with correct TGW RT
aws ec2 describe-transit-gateway-attachments \
  --filters "Name=resource-type,Values=direct-connect-gateway,vpn" \
  --query 'TransitGatewayAttachments[].{
    Id:TransitGatewayAttachmentId,
    ResourceId:ResourceId,
    Type:ResourceType,
    State:State,
    Association:Association.TransitGatewayRouteTableId
  }'
```

**Expected:** DX/VPN attachment associated with SPOKE route table (so on-premises traffic goes through inspection).

### Step 8: Verify On-Premises Routing

Check with on-premises network team:
- Is the on-premises router advertising 192.168.0.0/16 via BGP?
- Is the on-premises router receiving AWS routes (10.0.0.0/8)?
- Are there on-premises firewalls blocking traffic?
- Is the on-premises routing table correct?

```bash
# From on-premises router (example Cisco):
# show ip bgp summary
# show ip bgp neighbors
# show ip route 10.0.0.0 255.0.0.0
```

---

## VPN-Specific Troubleshooting

### Tunnel Down
```bash
# Check tunnel details
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-xxxxx \
  --query 'VpnConnections[].VgwTelemetry[]'
```

**Common causes:**
- IKE phase 1 mismatch (encryption, hash, DH group)
- IKE phase 2 mismatch (encryption, hash, PFS)
- Pre-shared key mismatch
- Customer gateway public IP changed
- NAT-T issues

### No Routes Received
```bash
# Check if routes are propagated
aws ec2 get-transit-gateway-route-table-propagations \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --query 'TransitGatewayRouteTablePropagations[?ResourceType==`vpn`]'
```

---

## Direct Connect Specific Troubleshooting

### DX Connection Down
1. Check physical layer (LOA-CFA, cross-connect)
2. Check with colocation provider
3. Verify port is not disabled on AWS side
4. Check for maintenance events:
```bash
aws directconnect describe-connections \
  --connection-id dxcon-xxxxx
```

### BGP Not Establishing
1. Verify VLAN tag matches
2. Check IP addressing (point-to-point /30 or /31)
3. Verify ASN configuration
4. Check MD5 authentication key
5. Verify BGP timers

### Routes Not Advertised
```bash
# Check allowed prefixes on DX Gateway association
aws directconnect describe-direct-connect-gateway-associations \
  --direct-connect-gateway-id dxgw-xxxxx \
  --query 'directConnectGatewayAssociations[].allowedPrefixesToDirectConnectGateway'
```

**Fix:** Update allowed prefixes:
```bash
aws directconnect update-direct-connect-gateway-association \
  --association-id association-id \
  --add-allowed-prefixes-to-direct-connect-gateway cidr=10.0.0.0/8
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| BGP session down | No connectivity | Check VIF state, BGP config, MD5 key |
| VPN tunnel down | No connectivity | Check IKE config, PSK, CGW IP |
| Missing TGW route | Timeout | Add static route or enable propagation |
| Firewall blocking | Timeout | Add on-premises allow rule |
| Wrong TGW RT association | Traffic bypasses firewall | Re-associate DX/VPN to spoke RT |
| Allowed prefixes missing | Partial connectivity | Update DX GW association prefixes |
| Asymmetric routing | Intermittent drops | Enable appliance mode, check AZ routing |
| On-prem firewall blocking | One-way connectivity | Work with on-prem team to allow AWS CIDRs |

---

## Failover Testing

### DX to VPN Failover
```bash
# Check if VPN is configured as backup
aws ec2 describe-vpn-connections \
  --query 'VpnConnections[].{Id:VpnConnectionId,State:State,TGW:TransitGatewayId}'

# Verify VPN routes have higher MED/lower priority than DX
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=192.168.0.0/16"
# Should show both DX and VPN routes with DX preferred
```
