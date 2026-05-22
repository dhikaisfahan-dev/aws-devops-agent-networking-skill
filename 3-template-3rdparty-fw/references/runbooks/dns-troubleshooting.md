# Runbook: DNS Troubleshooting (Route 53 Resolver, Private Hosted Zones)

## Trigger Conditions
- Application cannot resolve hostnames across VPCs
- Private hosted zone records not resolving
- VPC endpoint DNS not working
- On-premises cannot resolve AWS private DNS
- "Could not resolve host" errors

## Pre-Investigation Information Needed
- Source VPC and instance
- DNS name being resolved
- Expected IP / record type
- Whether using private hosted zones, Route 53 Resolver, or VPC endpoint DNS

---

## Investigation Steps

### Step 1: Test DNS Resolution from the Instance

```bash
# Basic resolution
dig +short hostname.example.com

# Verbose with server info
dig hostname.example.com

# Check which DNS server is being used
cat /etc/resolv.conf

# Test against VPC DNS resolver directly (always at VPC CIDR + 2)
dig @10.0.0.2 hostname.example.com

# Test specific record types
dig A hostname.example.com
dig CNAME hostname.example.com
dig SRV _service._tcp.example.com
```

### Step 2: Check VPC DNS Settings

```bash
# Check if DNS support and hostnames are enabled
aws ec2 describe-vpc-attribute --vpc-id vpc-xxxxx --attribute enableDnsSupport
aws ec2 describe-vpc-attribute --vpc-id vpc-xxxxx --attribute enableDnsHostnames
```

**Expected:** Both should be `true`. If `enableDnsSupport` is false, instances can't use the VPC DNS resolver.

### Step 3: Check Private Hosted Zones

```bash
# List private hosted zones
aws route53 list-hosted-zones \
  --query 'HostedZones[?Config.PrivateZone==`true`].{Id:Id,Name:Name,Comment:Config.Comment}'

# Check which VPCs are associated with a private hosted zone
aws route53 get-hosted-zone --id /hostedzone/ZXXXXX \
  --query '{Name:HostedZone.Name,VPCs:VPCs[].{VpcId:VPCId,Region:VPCRegion}}'

# List records in the zone
aws route53 list-resource-record-sets --hosted-zone-id /hostedzone/ZXXXXX \
  --query 'ResourceRecordSets[].{Name:Name,Type:Type,TTL:TTL,Records:ResourceRecords[].Value}'
```

**Common issue:** Private hosted zone not associated with the VPC where the instance is trying to resolve.

**Fix:**
```bash
aws route53 associate-vpc-with-hosted-zone \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --vpc VPCRegion=ap-southeast-3,VPCId=vpc-xxxxx
```

### Step 4: Check Route 53 Resolver Rules

```bash
# List resolver rules
aws route53resolver list-resolver-rules \
  --query 'ResolverRules[].{Id:Id,Name:Name,DomainName:DomainName,RuleType:RuleType,Status:Status}'

# Check rule associations (which VPCs use this rule)
aws route53resolver list-resolver-rule-associations \
  --query 'ResolverRuleAssociations[].{RuleId:ResolverRuleId,VpcId:VPCId,Name:Name,Status:Status}'
```

**For hybrid DNS (on-premises ↔ AWS):**
```bash
# List resolver endpoints (inbound and outbound)
aws route53resolver list-resolver-endpoints \
  --query 'ResolverEndpoints[].{Id:Id,Name:Name,Direction:Direction,Status:Status,IPs:IpAddressCount}'

# Get endpoint IP addresses
aws route53resolver list-resolver-endpoint-ip-addresses \
  --resolver-endpoint-id rslvr-in-xxxxx \
  --query 'IpAddresses[].{IP:Ip,SubnetId:SubnetId,Status:Status}'
```

### Step 5: Check VPC Endpoint DNS (Interface Endpoints)

```bash
# Check if private DNS is enabled on the endpoint
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[0].{Service:ServiceName,PrivateDns:PrivateDnsEnabled,DnsEntries:DnsEntries[].DnsName}'

# Test resolution of the service endpoint
dig +short sqs.ap-southeast-3.amazonaws.com
```

**If private DNS is enabled:** The service DNS (e.g., `sqs.ap-southeast-3.amazonaws.com`) should resolve to private IPs within the VPC.

**If resolving to public IPs:** Private DNS is not enabled or the endpoint is not in the correct VPC.

### Step 6: Check DNS Resolution Across VPC Peering

```bash
# Check if DNS resolution is enabled on peering
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-xxxxx \
  --query 'VpcPeeringConnections[0].{
    RequesterDns:RequesterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc,
    AccepterDns:AccepterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc
  }'
```

**For private hostnames to resolve across peering:** Both sides must enable DNS resolution.

### Step 7: Check Route 53 Resolver Query Logs

```bash
# List query log configs
aws route53resolver list-resolver-query-log-configs \
  --query 'ResolverQueryLogConfigs[].{Id:Id,Name:Name,Status:Status,DestinationArn:DestinationArn}'

# Query the logs (if sent to CloudWatch)
aws logs start-query \
  --log-group-name /aws/route53resolver/query-logs \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, query_name, query_type, rcode, answers.0.Rdata, srcaddr, vpc_id
    | filter query_name like "example.com"
    | sort @timestamp desc
    | limit 20'
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| DNS support disabled on VPC | All DNS fails | Enable `enableDnsSupport` on VPC |
| Private hosted zone not associated | Can't resolve private records | Associate zone with the VPC |
| VPC endpoint private DNS disabled | Service resolves to public IP | Enable private DNS on endpoint |
| Resolver rule not associated with VPC | Conditional forwarding not working | Associate rule with VPC |
| Resolver endpoint in wrong subnet | On-prem can't reach DNS | Check endpoint subnet has route to on-prem |
| DNS over peering not enabled | Can't resolve peer's private hostnames | Enable DNS resolution on peering connection |
| DHCP options set wrong | Instance using wrong DNS server | Check VPC DHCP options set |
| TTL caching | Old record still resolving | Wait for TTL expiry or flush cache |

---

## DNS Flow in Multi-VPC Architecture

```
Instance DNS query → VPC DNS Resolver (VPC CIDR + 2)
  → Check Private Hosted Zones associated with this VPC
  → Check Route 53 Resolver Rules (conditional forwarding)
  → Check VPC Endpoint Private DNS overrides
  → If no match → Forward to public Route 53 / internet DNS
```

**For on-premises → AWS private DNS:**
```
On-Prem DNS Server → Route 53 Resolver Inbound Endpoint (in AWS VPC)
→ VPC DNS Resolver → Private Hosted Zone → Return answer
```

**For AWS → on-premises DNS:**
```
Instance → VPC DNS Resolver → Route 53 Resolver Rule (forward to on-prem)
→ Route 53 Resolver Outbound Endpoint → On-Prem DNS Server → Return answer
```
