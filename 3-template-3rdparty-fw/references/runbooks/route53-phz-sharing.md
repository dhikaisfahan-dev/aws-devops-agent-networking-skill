# Runbook: Route 53 Private Hosted Zone + PHZ Sharing Across Accounts

## Trigger Conditions
- DNS resolution fails for private hostnames in another VPC/account
- Private hosted zone records not resolving from shared VPC
- "NXDOMAIN" for records that exist in the private zone
- DNS works in one VPC but not another for the same domain
- Cross-account DNS resolution not working after PHZ sharing

---

## Investigation Steps

### Step 1: Identify the Private Hosted Zone

```bash
# List all private hosted zones
aws route53 list-hosted-zones \
  --query 'HostedZones[?Config.PrivateZone==`true`].{Id:Id,Name:Name,Records:ResourceRecordSetCount}'

# Get zone details and associated VPCs
aws route53 get-hosted-zone --id /hostedzone/ZXXXXX \
  --query '{Name:HostedZone.Name,VPCs:VPCs[].{VpcId:VPCId,Region:VPCRegion}}'
```

**Check:** Is the VPC where DNS fails listed in the VPCs array?
- IF YES → Zone is associated, issue is elsewhere
- IF NO → Zone not associated with that VPC → Step 2

### Step 2: Associate PHZ with the VPC (Same Account)

```bash
# If PHZ and VPC are in the SAME account:
aws route53 associate-vpc-with-hosted-zone \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --vpc VPCRegion=ap-southeast-3,VPCId=vpc-xxxxx
```

### Step 3: Cross-Account PHZ Sharing

If the PHZ is in Account A but the VPC is in Account B:

```bash
# Step 3.1: In Account A (PHZ owner) — authorize the association
aws route53 create-vpc-association-authorization \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --vpc VPCRegion=ap-southeast-3,VPCId=vpc-in-account-b

# Step 3.2: In Account B (VPC owner) — associate the VPC
aws route53 associate-vpc-with-hosted-zone \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --vpc VPCRegion=ap-southeast-3,VPCId=vpc-in-account-b

# Step 3.3: In Account A — delete the authorization (cleanup, optional)
aws route53 delete-vpc-association-authorization \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --vpc VPCRegion=ap-southeast-3,VPCId=vpc-in-account-b
```

### Step 4: Check VPC DNS Settings

```bash
# Both settings MUST be true for PHZ resolution to work
aws ec2 describe-vpc-attribute --vpc-id vpc-xxxxx --attribute enableDnsSupport
# Expected: {"Value": true}

aws ec2 describe-vpc-attribute --vpc-id vpc-xxxxx --attribute enableDnsHostnames
# Expected: {"Value": true}
```

**IF either is false:** PHZ resolution won't work in that VPC.
```bash
aws ec2 modify-vpc-attribute --vpc-id vpc-xxxxx --enable-dns-support '{"Value":true}'
aws ec2 modify-vpc-attribute --vpc-id vpc-xxxxx --enable-dns-hostnames '{"Value":true}'
```

### Step 5: Check for Conflicting Zones or Resolver Rules

```bash
# Check if a Resolver Rule exists for the same domain
aws route53resolver list-resolver-rules \
  --query 'ResolverRules[].{Id:Id,Domain:DomainName,Type:RuleType,Status:Status}'

# Check rule associations
aws route53resolver list-resolver-rule-associations \
  --query 'ResolverRuleAssociations[?VPCId==`vpc-xxxxx`].{RuleId:ResolverRuleId,Name:Name,Status:Status}'
```

**Priority order:**
1. Resolver Rules (FORWARD type) → highest priority, overrides PHZ
2. Private Hosted Zones → second priority
3. VPC DNS (public resolution) → lowest priority

**IF a Resolver Rule exists for the same domain:** It takes precedence over the PHZ. Either remove the rule or ensure it forwards to the correct DNS server.

### Step 6: Check for Overlapping PHZs

```bash
# Multiple PHZs with the same or overlapping domain names?
aws route53 list-hosted-zones \
  --query 'HostedZones[?Config.PrivateZone==`true`].{Id:Id,Name:Name}' | grep "example.com"

# If multiple zones exist for same domain:
# - Most specific zone wins (app.example.com > example.com)
# - If same domain, the zone associated with the VPC wins
# - If both associated, behavior is undefined — remove one
```

### Step 7: Verify the Record Exists

```bash
# List records in the zone
aws route53 list-resource-record-sets \
  --hosted-zone-id /hostedzone/ZXXXXX \
  --query 'ResourceRecordSets[?Name==`myapp.example.com.`].{Name:Name,Type:Type,TTL:TTL,Records:ResourceRecords[].Value}'
```

**Note:** Domain names in Route 53 end with a dot (e.g., `myapp.example.com.`)

### Step 8: Test DNS Resolution

```bash
# From an instance in the VPC:
dig myapp.example.com
dig +short myapp.example.com

# Check which DNS server is being used
cat /etc/resolv.conf
# Should show VPC DNS resolver (VPC CIDR base + 2, e.g., 10.0.0.2)

# Force query against VPC resolver
dig @10.0.0.2 myapp.example.com
```

### Step 9: Check Route 53 Resolver Query Logs (if enabled)

```bash
# Find query log config
aws route53resolver list-resolver-query-log-configs \
  --query 'ResolverQueryLogConfigs[].{Id:Id,Name:Name,Status:Status,Destination:DestinationArn}'

# Query the logs
aws logs start-query \
  --log-group-name <resolver-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, query_name, query_type, rcode, answers.0.Rdata, vpc_id
    | filter query_name like "example.com"
    | sort @timestamp desc
    | limit 20'
```

**rcode values:**
- `NOERROR` → Resolution succeeded
- `NXDOMAIN` → Domain doesn't exist (zone not associated or record missing)
- `SERVFAIL` → DNS server error (Resolver endpoint issue)

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| PHZ not associated with VPC | NXDOMAIN | Associate zone with VPC |
| Cross-account auth missing | Can't associate | Create authorization in PHZ account first |
| enableDnsSupport = false | All private DNS fails | Enable on VPC |
| enableDnsHostnames = false | Hostname resolution fails | Enable on VPC |
| Resolver Rule overrides PHZ | Wrong IP returned | Remove conflicting rule or adjust priority |
| Overlapping PHZ domains | Inconsistent resolution | Remove duplicate zone |
| Record doesn't exist | NXDOMAIN for specific name | Add the record to the zone |
| TTL caching | Old record still resolving | Wait for TTL expiry |
| Wrong region in association | Zone not visible | Re-associate with correct region |

---

## PHZ Sharing Architecture

```
Account A (PHZ Owner)                    Account B (Consumer)
┌─────────────────────────┐             ┌─────────────────────────┐
│                          │             │                          │
│  Private Hosted Zone     │             │  VPC-B                   │
│  example.internal        │             │                          │
│                          │             │  EC2 → dig app.example   │
│  Records:                │             │         .internal        │
│  - app.example.internal  │  Associated │         ↓                │
│    → 10.0.1.50          ├─────────────┤  VPC DNS Resolver        │
│  - db.example.internal   │   with      │         ↓                │
│    → 10.1.2.100         │   VPC-B     │  Resolves to 10.0.1.50  │
│                          │             │                          │
│  VPCs: [VPC-A, VPC-B]   │             │                          │
└─────────────────────────┘             └─────────────────────────┘

Steps to share:
1. Account A: create-vpc-association-authorization (for VPC-B)
2. Account B: associate-vpc-with-hosted-zone (VPC-B with zone)
3. Account A: delete-vpc-association-authorization (cleanup)
```

---

## Using AWS RAM for PHZ Sharing (Alternative)

```bash
# Share PHZ via Resource Access Manager (simpler for Organizations)
aws ram create-resource-share \
  --name "shared-dns-zone" \
  --resource-arns "arn:aws:route53:::hostedzone/ZXXXXX" \
  --principals "<consumer-account-id>"

# Consumer still needs to associate VPC after accepting the share
```

**RAM vs Manual Authorization:**
- RAM: Better for Organizations, automatic acceptance possible
- Manual: Works for any account, more explicit control
