# Runbook: EKS/ECS Networking (Pod-Level, ENI Exhaustion)

## Trigger Conditions
- Pods stuck in Pending state (EKS)
- Tasks failing to launch (ECS awsvpc)
- "Failed to assign an IP address to container" errors
- Application in pod/task can't reach other services
- Intermittent connectivity from containers

---

## Investigation Steps

### Step 1: Check ENI Capacity on Node

```bash
# Get node instance type and current ENI count
aws ec2 describe-instances --instance-ids <node-instance-id> \
  --query 'Reservations[0].Instances[0].{Type:InstanceType,ENIs:NetworkInterfaces[].NetworkInterfaceId}'

# Check max ENIs and IPs per ENI for the instance type
aws ec2 describe-instance-types --instance-types <instance-type> \
  --query 'InstanceTypes[0].NetworkInfo.{MaxENIs:MaximumNetworkInterfaces,IPv4PerENI:Ipv4AddressesPerInterface,MaxPods:MaximumNetworkInterfaces*Ipv4AddressesPerInterface}'

# Count ENIs currently attached
aws ec2 describe-network-interfaces \
  --filters "Name=attachment.instance-id,Values=<node-instance-id>" \
  --query 'NetworkInterfaces | length(@)'
```

**IF ENIs at max:** Node can't allocate more pod IPs → scale out nodes or use prefix delegation.

### Step 2: Check Subnet IP Exhaustion

```bash
# Check available IPs in the subnet
aws ec2 describe-subnets --subnet-ids <node-subnet-id> \
  --query 'Subnets[0].{SubnetId:SubnetId,CIDR:CidrBlock,AvailableIPs:AvailableIpAddressCount,AZ:AvailabilityZone}'
```

**IF AvailableIPs near zero:** No IPs for new pods/tasks. Options:
- Add secondary CIDR to VPC
- Use larger subnets
- Enable prefix delegation (EKS)

### Step 3: Check Security Groups on Pod/Task ENI

```bash
# EKS: Find pod ENIs (description contains "aws-K8S-")
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*aws-K8S-*" "Name=subnet-id,Values=<subnet-id>" \
  --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,IP:PrivateIpAddress,SGs:Groups[].GroupId,Status:Status}'

# ECS awsvpc: Find task ENIs (description contains "ecs-")
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*ecs-*" "Name=subnet-id,Values=<subnet-id>" \
  --query 'NetworkInterfaces[].{Id:NetworkInterfaceId,IP:PrivateIpAddress,SGs:Groups[].GroupId,Status:Status}'

# Check SG rules on the pod/task ENI
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=<pod-sg-id>" \
  --query 'SecurityGroupRules[].{Direction:IsEgress,Protocol:IpProtocol,Port:ToPort,CIDR:CidrIpv4}'
```

### Step 4: Check VPC CNI Plugin (EKS)

```bash
# Check aws-node DaemonSet status
# (via kubectl or checking CloudWatch Container Insights)

# Check WARM_ENI_TARGET and WARM_IP_TARGET
# These control how many spare ENIs/IPs are pre-allocated
# Low values = faster exhaustion under load

# Check ipamd logs for errors
aws logs filter-log-events \
  --log-group-name /aws/eks/<cluster-name>/cluster \
  --filter-pattern "ipamd" \
  --start-time $(date -u -v-1H +%s000) \
  --limit 20
```

### Step 5: Check Routing from Pod to Destination

```bash
# Pods use the node's subnet route table
# Same path as EC2: SG → RT → TGW → Firewall → destination

# Check node subnet route table
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<node-subnet-id>" \
  --query 'RouteTables[0].Routes[]'

# For EKS with custom networking (ENIConfig):
# Pods may be in a DIFFERENT subnet than the node
# Check the ENIConfig subnet's route table instead
```

### Step 6: Check ECS Task Networking (awsvpc mode)

```bash
# Describe task to get ENI info
aws ecs describe-tasks --cluster <cluster> --tasks <task-arn> \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value'

# Check task ENI details
aws ec2 describe-network-interfaces --network-interface-ids <task-eni> \
  --query 'NetworkInterfaces[0].{SubnetId:SubnetId,SGs:Groups[].GroupId,IP:PrivateIpAddress,Status:Status}'
```

---

## Common Issues & Fixes

| Issue | Symptom | Fix |
|-------|---------|-----|
| ENI limit reached | Pods Pending, "insufficient ENI" | Use larger instance type or prefix delegation |
| Subnet IP exhaustion | Pods Pending, "no available IPs" | Add secondary CIDR or use larger subnets |
| Pod SG missing rule | Pod can't reach service | Add inbound/outbound rule to pod SG |
| VPC CNI not running | All pods on node fail | Check aws-node DaemonSet, restart if needed |
| Custom networking misconfigured | Pods in wrong subnet | Check ENIConfig CRD matches subnet/AZ |
| ECS task SG too restrictive | Task can't reach dependencies | Update task SG to allow required traffic |
| Node SG blocks pod traffic | Cross-node pod communication fails | Allow node SG self-reference or pod CIDR |

---

## ENI Limits Quick Reference

| Instance Type | Max ENIs | IPv4/ENI | Max Pod IPs |
|---------------|----------|----------|-------------|
| t3.micro | 2 | 2 | 4 |
| t3.medium | 3 | 6 | 17 |
| m5.large | 3 | 10 | 29 |
| m5.xlarge | 4 | 15 | 58 |
| m5.2xlarge | 4 | 15 | 58 |
| c5.4xlarge | 8 | 30 | 234 |

With prefix delegation (EKS 1.21+): multiply by ~16x
