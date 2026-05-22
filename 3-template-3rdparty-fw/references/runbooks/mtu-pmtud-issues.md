# Runbook: MTU / Path MTU Discovery (PMTUD) Issues

## Trigger Conditions
- Small packets work (ping with default size) but large transfers fail
- SSH connects but SCP/SFTP hangs
- HTTP headers work but body download stalls
- TLS handshake completes but data transfer fails
- VPN traffic works for small payloads, fails for large
- "Message too long" errors

---

## Background: MTU Values in AWS

| Path Segment | MTU | Notes |
|---|---|---|
| Within VPC (same AZ) | 9001 (jumbo) | Default for most instance types |
| Within VPC (cross-AZ) | 9001 (jumbo) | Same VPC, different AZ |
| Transit Gateway | 8500 | TGW reduces MTU |
| VPC Peering (same region) | 9001 | Supports jumbo |
| VPC Peering (cross-region) | 1500 | No jumbo cross-region |
| VPN (IPsec) | 1500 | IPsec overhead reduces effective MTU |
| Direct Connect | 9001 or 1500 | Depends on VIF jumbo frame setting |
| Internet (via NAT GW/IGW) | 1500 | Internet standard |
| GWLB (GENEVE encap) | 8500 - ~50 overhead | GENEVE adds headers |
| GWLB (GENEVE encap) | 8500 - ~50 overhead | 3rd party firewall via GWLB |

---

## Investigation Steps

### Step 1: Confirm MTU Issue (Large Packets Fail)

```bash
# From the source instance, test with Don't Fragment bit set:

# Test 1500 MTU (internet standard)
ping -M do -s 1472 <destination>   # 1472 + 28 (IP+ICMP header) = 1500

# Test jumbo (9001)
ping -M do -s 8972 <destination>   # 8972 + 28 = 9000

# Test TGW MTU (8500)
ping -M do -s 8472 <destination>   # 8472 + 28 = 8500

# Find exact MTU by binary search
# If 1472 works but 8472 doesn't, try 4000, then narrow down
```

**IF small ping works but large fails → MTU mismatch confirmed.**

### Step 2: Identify Where MTU Drops

```bash
# Check instance MTU setting
ip link show ens5   # Look for "mtu XXXX"

# Check path to determine expected MTU:
# - Same VPC only? → 9001 should work
# - Crosses TGW? → Max 8500
# - Crosses VPN? → Max 1500
# - Goes to internet? → Max 1500
# - Crosses GWLB + 3rd party firewall? → Max ~8450 (GENEVE overhead)
# - Crosses GWLB? → Max ~8450
```

### Step 3: Check if ICMP Type 3 Code 4 is Allowed

PMTUD relies on receiving "Fragmentation Needed" ICMP messages. If these are blocked, the source never learns to reduce packet size.

```bash
# Check Security Groups allow ICMP Type 3 (Destination Unreachable)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<sg-id>" \
  --query 'SecurityGroupRules[?IpProtocol==`icmp`].{Direction:IsEgress,FromPort:FromPort,ToPort:ToPort,CIDR:CidrIpv4}'

# ICMP Type 3 = FromPort 3, ToPort -1 (all codes)
# Must be allowed INBOUND on the source instance SG
```

**IF ICMP Type 3 not allowed inbound:** PMTUD is broken. Fix:
```bash
aws ec2 authorize-security-group-ingress --group-id <sg-id> \
  --ip-permissions IpProtocol=icmp,FromPort=3,ToPort=-1,IpRanges='[{CidrIp=0.0.0.0/0,Description="PMTUD - Fragmentation Needed"}]'
```

### Step 4: Check GWLB / 3rd Party Firewall Impact

```bash
# 3rd party firewall may block ICMP Type 3 responses
# Check via FortiGate MCP (if available):
# → FortiGate MCP: list_firewall_policies
#   Look for policies that allow/deny ICMP

# Or check GWLB health (if firewall is dropping due to MTU):
aws elbv2 describe-target-health \
  --target-group-arn <gwlb-target-group-arn>

# GWLB adds GENEVE encapsulation (~50 bytes)
# Effective MTU through GWLB = 8500 - 50 = ~8450
# If appliance doesn't handle GENEVE MTU properly, large packets drop
```

### Step 5: Check VPN/DX MTU Settings

```bash
# VPN always uses 1500 MTU (IPsec overhead further reduces to ~1400 effective)
# Check if instance MTU is set too high for VPN path

# Direct Connect: check if jumbo frames enabled on VIF
aws directconnect describe-virtual-interfaces \
  --virtual-interface-id dxvif-xxxxx \
  --query 'virtualInterfaces[0].{Mtu:mtu,JumboFrameCapable:jumboFrameCapable}'
```

### Step 6: Fix MTU on Instance

```bash
# Set MTU to match the lowest point in the path
# For paths crossing TGW:
sudo ip link set dev ens5 mtu 8500

# For paths crossing VPN or internet:
sudo ip link set dev ens5 mtu 1500

# For paths crossing GWLB + 3rd party firewall:
sudo ip link set dev ens5 mtu 1500

# Make persistent (Amazon Linux 2023):
echo 'MTU=1500' >> /etc/sysconfig/network-scripts/ifcfg-ens5
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Instance MTU 9001, path crosses TGW | Large packets dropped silently | Set MTU to 8500 or enable PMTUD (allow ICMP 3) |
| Instance MTU 9001, path crosses VPN | VPN transfers hang | Set MTU to 1400 on VPN-facing instances |
| SG blocks ICMP Type 3 | PMTUD broken, large packets fail | Allow ICMP Type 3 inbound on all SGs |
| 3rd party firewall blocks ICMP | PMTUD broken | Add ICMP PASS rule in firewall |
| Cross-region peering with jumbo | Large packets fail cross-region | Set MTU to 1500 for cross-region traffic |
| GWLB GENEVE overhead | Packets just over 8450 fail | Set appliance MTU to account for GENEVE |
| DX without jumbo frames | Large packets fail over DX | Enable jumbo on VIF or set MTU to 1500 |

---

## Decision Tree

```
Large transfers failing but small packets work?
├── Path crosses VPN? → Set MTU to 1400
├── Path crosses internet/NAT GW? → Set MTU to 1500
├── Path crosses GWLB + firewall? → Set MTU to 8450 (or 1500 if unsure)
├── Path crosses TGW only? → Set MTU to 8500
├── Path is intra-VPC only? → Should work at 9001, check SG for ICMP 3
└── Not sure? → Set MTU to 1500 (safe for all paths) + allow ICMP Type 3
```
