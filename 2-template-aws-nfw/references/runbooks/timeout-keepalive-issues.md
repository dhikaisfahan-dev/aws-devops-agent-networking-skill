# Runbook: Timeout & Keepalive Issues

## Trigger Conditions
- Connections drop after being idle for a period
- "Connection reset by peer" after inactivity
- Long-running connections (WebSocket, database) randomly disconnect
- ALB returning 504 for slow backends
- VPN tunnel flapping (idle timeout)
- NAT GW dropping idle connections

---

## Key Timeout Values in AWS

| Component | Idle Timeout | Configurable? |
|-----------|---|---|
| ALB | 60 seconds (default) | ✅ Yes (1-4000s) |
| NLB | 350 seconds | ❌ No |
| NAT Gateway | 350 seconds (TCP) | ❌ No |
| NAT Gateway | 300 seconds (UDP) | ❌ No |
| VPN tunnel | DPD timeout (30s default) | ✅ Yes |
| Security Group (connection tracking) | 5 days (established TCP) | ❌ No |
| Network Firewall | 30 minutes (TCP idle) | ✅ Yes (in rule) |
| TGW | No timeout (stateless) | — |

---

## Investigation Steps

### Step 1: Identify the Timeout Source

```
Connection drops after ~60 seconds idle?  → ALB idle timeout
Connection drops after ~350 seconds idle? → NAT GW or NLB timeout
Connection drops after ~30 minutes idle?  → Network Firewall session timeout
Connection drops randomly?                → TCP keepalive mismatch
```

### Step 2: ALB Idle Timeout (504 errors)

```bash
# Check current ALB idle timeout
aws elbv2 describe-load-balancer-attributes \
  --load-balancer-arn <alb-arn> \
  --query 'Attributes[?Key==`idle_timeout.timeout_seconds`].Value'

# Check 504 errors (gateway timeout)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name HTTPCode_ELB_504_Count \
  --dimensions Name=LoadBalancer,Value=<alb-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Fix: increase idle timeout
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn <alb-arn> \
  --attributes Key=idle_timeout.timeout_seconds,Value=300
```

**Important:** Backend application keepalive must be LONGER than ALB idle timeout. Otherwise ALB sends request to a closed connection → 502.

### Step 3: NAT Gateway Idle Timeout

```bash
# NAT GW drops TCP connections idle > 350 seconds
# Check for idle connection drops
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name IdleTimeoutCount \
  --dimensions Name=NatGatewayId,Value=<nat-id> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

**Fix:** Application must send TCP keepalive packets before 350 seconds:
```bash
# On Linux instances:
sysctl -w net.ipv4.tcp_keepalive_time=200
sysctl -w net.ipv4.tcp_keepalive_intvl=30
sysctl -w net.ipv4.tcp_keepalive_probes=5
```

### Step 4: Network Firewall Session Timeout

```bash
# Network Firewall drops tracked sessions after idle timeout
# Default: 30 minutes for TCP
# Check firewall flow logs for "timeout" reason
aws logs start-query \
  --log-group-name <fw-flow-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, event.src_ip, event.dest_ip, event.netflow.reason
    | filter event.netflow.reason = "timeout"
    | sort @timestamp desc
    | limit 20'
```

### Step 5: VPN Tunnel Keepalive

```bash
# Check VPN tunnel status (flapping = going UP/DOWN)
aws ec2 describe-vpn-connections --vpn-connection-ids <vpn-id> \
  --query 'VpnConnections[0].VgwTelemetry[].{IP:OutsideIpAddress,Status:status,LastChange:lastStatusChange}'

# Check DPD (Dead Peer Detection) settings
aws ec2 describe-vpn-connections --vpn-connection-ids <vpn-id> \
  --query 'VpnConnections[0].Options.TunnelOptions[].DpdTimeoutSeconds'
```

**If tunnel flaps due to idle:** Send periodic traffic or adjust DPD timeout.

### Step 6: TCP Keepalive Mismatch

```
Common mismatch pattern:
- Application sends keepalive every 7200s (Linux default: 2 hours)
- NAT GW drops connection after 350s idle
- Result: Connection silently dies, next request fails

Fix: Set application keepalive < 350s (for NAT GW path)
     Set application keepalive < ALB idle timeout (for ALB path)
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| ALB idle timeout too short | 504 for slow requests | Increase ALB timeout |
| Backend keepalive < ALB timeout | 502 errors | Set backend keepalive > ALB timeout |
| NAT GW drops idle connections | Long-running connections die | Set TCP keepalive < 350s |
| Firewall session timeout | Connections drop after 30 min | Adjust FW timeout or send keepalive |
| VPN DPD timeout | Tunnel flaps when idle | Adjust DPD or send periodic traffic |
| WebSocket through ALB | Disconnects after 60s | Increase ALB idle timeout to 3600s |
| Database connection pool | Stale connections | Set pool validation interval < NAT timeout |
