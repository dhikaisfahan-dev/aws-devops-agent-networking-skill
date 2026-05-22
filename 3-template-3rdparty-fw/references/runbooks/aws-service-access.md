# Runbook: AWS Service Access (S3, DynamoDB, SQS, etc.)

## Trigger Conditions
- Application cannot access S3 buckets
- DynamoDB operations timing out
- SQS/SNS/KMS/SSM calls failing
- "Could not connect to the endpoint URL" errors
- Access denied on AWS service calls

## Pre-Investigation Information Needed
- Source instance/container details
- AWS service being accessed
- Error message (timeout vs access denied)
- Whether using VPC endpoint or internet path

---

## Investigation Steps

### Step 1: Identify the AWS Service and Access Method

```bash
# List VPC endpoints in inspection VPC
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-inspection" \
  --query 'VpcEndpoints[].{
    Id:VpcEndpointId,
    Service:ServiceName,
    Type:VpcEndpointType,
    State:State
  }' --output table
```

**Determine access method:**
- **Gateway Endpoint** (S3, DynamoDB): Routes via prefix list in route table
- **Interface Endpoint** (SQS, SNS, KMS, etc.): Routes via DNS to ENI in VPC
- **No Endpoint**: Routes via NAT Gateway to public internet

### Step 2: For Gateway Endpoints (S3, DynamoDB)

```bash
# Check gateway endpoint exists
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-inspection" "Name=service-name,Values=com.amazonaws.REGION.s3" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,State:State,RouteTables:RouteTableIds}'

# Verify route table has prefix list entry
aws ec2 describe-route-tables \
  --route-table-ids rtb-firewall-subnet \
  --query 'RouteTables[].Routes[?DestinationPrefixListId!=`null`].{
    PrefixList:DestinationPrefixListId,
    Target:GatewayId||VpcEndpointId
  }'

# Check prefix list contents
aws ec2 describe-managed-prefix-lists \
  --query 'PrefixLists[?PrefixListName==`com.amazonaws.REGION.s3`].{Id:PrefixListId,Name:PrefixListName}'

aws ec2 get-managed-prefix-list-entries \
  --prefix-list-id pl-xxxxx
```

**Expected:** Route table in firewall subnet has prefix list route → vpce-gateway

**If Missing:** Associate gateway endpoint with route table:
```bash
aws ec2 modify-vpc-endpoint \
  --vpc-endpoint-id vpce-xxxxx \
  --add-route-table-ids rtb-firewall-subnet
```

### Step 3: For Interface Endpoints (SQS, SNS, KMS, etc.)

```bash
# Check interface endpoint exists and is available
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-inspection" "Name=service-name,Values=com.amazonaws.REGION.sqs" \
  --query 'VpcEndpoints[].{
    Id:VpcEndpointId,
    State:State,
    Subnets:SubnetIds,
    SGs:Groups[].GroupId,
    PrivateDNS:PrivateDnsEnabled,
    DNS:DnsEntries[0].DnsName
  }'

# Check DNS resolution
# From within the VPC, the service DNS should resolve to private IP
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].DnsEntries[]'
```

**Check Security Group on Interface Endpoint:**
```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-vpce" \
  --query 'SecurityGroupRules[?IsEgress==`false`].{
    Protocol:IpProtocol,
    Port:ToPort,
    Source:CidrIpv4
  }'
```

**Expected:** Inbound TCP 443 from 10.0.0.0/8 (all workload VPCs)

### Step 4: Check VPC Endpoint Policy

```bash
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].PolicyDocument' \
  --output json
```

**Expected:** Policy allows the required actions. Full access policy:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "*",
      "Resource": "*"
    }
  ]
}
```

**Restrictive policy example (S3):**
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ]
    }
  ]
}
```

### Step 5: Check Network Firewall Rules

Traffic to AWS services still passes through the firewall before reaching the endpoint.

```bash
# Check if firewall is blocking AWS service traffic
aws logs filter-log-events \
  --log-group-name /aws/network-firewall/alert \
  --filter-pattern '{ $.event.src_ip = "SOURCE_IP" && $.event.dest_port = 443 }' \
  --start-time $(date -u -v-30M +%s000)
```

**If blocked:** Add rule to allow traffic to AWS service endpoints:
```
pass tcp 10.0.0.0/8 any -> $AWS_SERVICE_CIDRS 443 (msg:"Allow AWS service access"; sid:2000001;)
```

Or use domain-based rules:
```
pass tls 10.0.0.0/8 any -> any 443 (tls.sni; content:".amazonaws.com"; endswith; msg:"Allow AWS services"; sid:2000002;)
```

### Step 6: Check Source Path (Workload VPC → Inspection VPC)

```bash
# Source SG outbound (port 443)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-source" \
  --query 'SecurityGroupRules[?IsEgress==`true` && ToPort==`443`]'

# Source subnet RT → TGW
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-source" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`]'

# TGW Spoke RT → Inspection VPC
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-spoke \
  --filters "Name=route-search.exact-match,Values=0.0.0.0/0"
```

### Step 7: Check IAM Permissions (Access Denied)

If the error is "Access Denied" rather than timeout:

```bash
# Check instance role
aws ec2 describe-instances --instance-ids i-xxxxx \
  --query 'Reservations[].Instances[].IamInstanceProfile.Arn'

# Check role policies
aws iam list-attached-role-policies --role-name ROLE_NAME
aws iam list-role-policies --role-name ROLE_NAME

# Check specific policy
aws iam get-role-policy --role-name ROLE_NAME --policy-name POLICY_NAME
```

**Note:** Both IAM policy AND VPC endpoint policy must allow the action.

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Gateway endpoint not in RT | S3 timeout | Associate endpoint with firewall subnet RT |
| Interface endpoint SG blocking | Service timeout | Add inbound 443 from 10.0.0.0/8 |
| Private DNS not enabled | DNS resolves to public IP | Enable private DNS on interface endpoint |
| Endpoint policy too restrictive | Access denied | Update endpoint policy |
| Firewall blocking 443 to AWS | Service timeout | Add allow rule for AWS service domains |
| IAM policy missing | Access denied | Update IAM role policy |
| Endpoint in wrong AZ | Intermittent timeout | Create endpoint in all used AZs |

---

## Service-Specific Notes

### S3 (Gateway Endpoint)
- Uses prefix list in route table (not DNS)
- No security group needed
- Endpoint policy controls access
- Free (no data processing charges)

### DynamoDB (Gateway Endpoint)
- Same as S3 - prefix list based
- Free

### SQS/SNS/KMS/SSM/ECR (Interface Endpoints)
- DNS-based routing
- Requires security group (allow 443 inbound)
- Private DNS must be enabled for transparent access
- Charges per hour + per GB processed

### ECR (Special Case)
- Requires BOTH `ecr.api` and `ecr.dkr` interface endpoints
- Also requires S3 gateway endpoint (for image layers)
- Docker pull needs all three endpoints working
