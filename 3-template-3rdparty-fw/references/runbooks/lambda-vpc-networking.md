# Runbook: Lambda VPC Networking

## Trigger Conditions
- Lambda function timeout when accessing VPC resources
- Lambda "Task timed out" with VPC configuration
- Lambda ENI creation failures
- Lambda cold start taking too long (VPC-attached)
- Lambda can't reach internet despite VPC config
- "ENILimitReachedException" errors

---

## Investigation Steps

### Step 1: Check Lambda VPC Configuration

```bash
# Get Lambda function VPC config
aws lambda get-function-configuration --function-name <function-name> \
  --query '{VpcConfig:VpcConfig,Timeout:Timeout,MemorySize:MemorySize}'

# Shows: VpcId, SubnetIds, SecurityGroupIds
# If VpcConfig is empty → Lambda is NOT in a VPC (uses public internet)
```

### Step 2: Check Lambda Security Group

```bash
# Get the SG attached to the Lambda function
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<lambda-sg-id>" \
  --query 'SecurityGroupRules[].{Direction:IsEgress,Protocol:IpProtocol,Port:ToPort,CIDR:CidrIpv4}'
```

**Lambda SG must allow:**
- Outbound to the destination (e.g., RDS on port 3306, other VPC on port 443)
- Inbound is NOT needed (Lambda initiates connections, SG is stateful)

### Step 3: Check Subnet Route Table

```bash
# Lambda uses the route table of its configured subnets
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<lambda-subnet-id>" \
  --query 'RouteTables[0].Routes[]'
```

**For Lambda to reach internet:**
- Subnet must have `0.0.0.0/0 → NAT Gateway` (NOT IGW directly)
- Lambda in a public subnet with IGW does NOT get internet access
- Lambda ALWAYS needs NAT GW for internet (even in public subnet)

**For Lambda to reach other VPCs:**
- Subnet must have route to TGW or VPC Peering

### Step 4: Check ENI Capacity in Lambda Subnets

```bash
# Count ENIs in Lambda's subnets
aws ec2 describe-network-interfaces \
  --filters "Name=subnet-id,Values=<lambda-subnet-id>" "Name=description,Values=*lambda*" \
  --query 'NetworkInterfaces | length(@)'

# Check available IPs in subnet
aws ec2 describe-subnets --subnet-ids <lambda-subnet-id> \
  --query 'Subnets[0].{CIDR:CidrBlock,AvailableIPs:AvailableIpAddressCount}'
```

**If AvailableIPs is low:** Lambda can't create new ENIs → functions fail to start.

**Note:** Since 2019, Lambda uses Hyperplane ENIs (shared across functions in same SG+subnet). One ENI supports many concurrent executions. But subnet IP exhaustion still matters.

### Step 5: Check Lambda Execution Role Permissions

```bash
# Lambda needs ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces,
# ec2:DeleteNetworkInterface to work in a VPC
aws iam list-attached-role-policies --role-name <lambda-execution-role>
aws iam get-role-policy --role-name <lambda-execution-role> --policy-name <policy>

# Or check if AWSLambdaVPCAccessExecutionRole is attached
```

**Required permissions for VPC Lambda:**
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:CreateNetworkInterface",
    "ec2:DescribeNetworkInterfaces",
    "ec2:DeleteNetworkInterface",
    "ec2:AssignPrivateIpAddresses",
    "ec2:UnassignPrivateIpAddresses"
  ],
  "Resource": "*"
}
```

### Step 6: Check if Lambda Can Reach Its Target

```bash
# If Lambda targets RDS:
aws rds describe-db-instances --db-instance-identifier <rds-id> \
  --query 'DBInstances[0].{Endpoint:Endpoint.Address,Port:Endpoint.Port,VpcId:DBSubnetGroup.VpcId,SGs:VpcSecurityGroups[].VpcSecurityGroupId}'

# Check RDS SG allows inbound from Lambda SG
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<rds-sg-id>" \
  --query 'SecurityGroupRules[?IsEgress==`false`]'
```

### Step 7: Check CloudWatch Metrics

```bash
# Lambda duration (if near timeout → network issue)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda --metric-name Duration \
  --dimensions Name=FunctionName,Value=<function-name> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average,Maximum

# Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda --metric-name Errors \
  --dimensions Name=FunctionName,Value=<function-name> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Lambda SG missing outbound rule | Timeout connecting to target | Add outbound rule for target port |
| No NAT GW in Lambda subnet | Can't reach internet | Add NAT GW + route 0.0.0.0/0 → NAT |
| Lambda in public subnet expects internet | Timeout to internet | Move to private subnet with NAT GW |
| Subnet IP exhaustion | ENI creation fails | Use larger subnet or fewer concurrent executions |
| Missing VPC permissions on role | Function fails to start | Attach AWSLambdaVPCAccessExecutionRole |
| Target SG doesn't allow Lambda SG | Timeout to target | Add inbound rule from Lambda SG |
| Lambda timeout too short | "Task timed out" | Increase timeout (VPC cold start adds 1-2s) |
| Wrong subnet (no route to target) | Timeout | Put Lambda in subnet with route to target |

---

## Lambda VPC Networking Key Facts

- Lambda in VPC uses Hyperplane ENIs (shared, not 1 per invocation)
- Lambda ALWAYS needs NAT GW for internet (even in public subnet)
- Cold start adds ~1-2 seconds for VPC attachment (much improved since 2019)
- Use multiple subnets across AZs for HA
- Lambda SG only needs OUTBOUND rules (it initiates connections)
- Use VPC endpoints to avoid NAT GW for AWS service calls (S3, DynamoDB, SQS)
