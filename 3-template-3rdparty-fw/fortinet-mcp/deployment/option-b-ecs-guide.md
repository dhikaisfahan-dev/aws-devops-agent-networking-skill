# Option B: Deploy on ECS Fargate - Full Step-by-Step Guide

Production-grade deployment. From filling in IPs to a running MCP server connected to DevOps Agent.

---

## Overview of Steps

```
Step 1: Fill in Fortinet IPs and API tokens
Step 2: Build Docker images
Step 3: Push images to ECR
Step 4: Deploy CloudFormation (ECS + ALB)
Step 5: Verify MCP servers are running
Step 6: Register MCP in DevOps Agent Space
Step 7: Test
```

---

## Step 1: Fill in Fortinet IPs and API Tokens

### FortiGate (devices.json)

```bash
cd fortinet-mcp/fortigate-mcp
cp devices.json.template devices.json
```

Edit `devices.json` — replace with your real FortiGate IPs and tokens:
```json
{
  "devices": {
    "fw-az-a": {
      "host": "10.100.1.10",
      "api_token": "your-real-fortigate-token-here",
      "port": 443,
      "verify_ssl": false,
      "vdom": "root"
    }
  }
}
```

### FortiManager (.env)

```bash
cd fortinet-mcp/fortimanager-mcp
cp .env.template .env
```

Edit `.env`:
```
FMG_HOST=10.100.1.20
FMG_API_TOKEN=your-real-fortimanager-token-here
FMG_PORT=443
FMG_VERIFY_SSL=false
FMG_ADOM=root
LOG_LEVEL=INFO
```

### FortiAnalyzer (.env)

```bash
cd fortinet-mcp/fortianalyzer-mcp
cp .env.template .env
```

Edit `.env`:
```
FAZ_HOST=10.100.1.30
FAZ_API_TOKEN=your-real-fortianalyzer-token-here
FAZ_PORT=443
FAZ_VERIFY_SSL=false
FAZ_ADOM=root
LOG_LEVEL=INFO
```

---

## Step 2: Build Docker Images

```bash
cd fortinet-mcp/

# Build FortiGate MCP image
docker build -t fortigate-mcp:latest ./fortigate-mcp/

# Build FortiManager MCP image
docker build -t fortimanager-mcp:latest ./fortimanager-mcp/

# Build FortiAnalyzer MCP image
docker build -t fortianalyzer-mcp:latest ./fortianalyzer-mcp/

# Verify images built
docker images | grep mcp
```

---

## Step 3: Push Images to ECR

```bash
# Set your variables
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-southeast-3  # Change to your region

# Login to ECR
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Create ECR repositories
aws ecr create-repository --repository-name fortigate-mcp --region $REGION
aws ecr create-repository --repository-name fortimanager-mcp --region $REGION
aws ecr create-repository --repository-name fortianalyzer-mcp --region $REGION

# Tag images
docker tag fortigate-mcp:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortigate-mcp:latest
docker tag fortimanager-mcp:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortimanager-mcp:latest
docker tag fortianalyzer-mcp:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortianalyzer-mcp:latest

# Push images
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortigate-mcp:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortimanager-mcp:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortianalyzer-mcp:latest
```

---

## Step 4: Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file deployment/option-b-ecs.yaml \
  --stack-name fortinet-mcp \
  --region $REGION \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    VpcId=vpc-xxxxx \
    SubnetIds=subnet-aaaa,subnet-bbbb \
    FazHost=10.100.1.30 \
    FazApiToken=your-faz-token \
    FmgHost=10.100.1.20 \
    FmgApiToken=your-fmg-token \
    FgtConfigJson='{"devices":{"fw-primary":{"host":"10.100.1.10","api_token":"your-fgt-token","port":443,"verify_ssl":false,"vdom":"root"}}}' \
    FazImageUri=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortianalyzer-mcp:latest \
    FmgImageUri=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortimanager-mcp:latest \
    FgtImageUri=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/fortigate-mcp:latest
```

Wait for deployment (~5 minutes):
```bash
aws cloudformation wait stack-create-complete --stack-name fortinet-mcp --region $REGION
```

---

## Step 5: Verify MCP Servers Are Running

```bash
# Get ALB DNS name
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name fortinet-mcp \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`AlbDns`].OutputValue' \
  --output text)

echo "ALB URL: http://$ALB_DNS"

# Check health (from within the VPC or via VPN)
curl http://$ALB_DNS/health

# Check ECS services
aws ecs list-services --cluster fortinet-mcp --region $REGION
aws ecs describe-services --cluster fortinet-mcp --services fortianalyzer-mcp --region $REGION \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

---

## Step 6: Register MCP in DevOps Agent Space

1. Open AWS DevOps Agent console (us-east-1)
2. Select your Agent Space → **Capabilities** tab
3. Find **MCP Servers** → Click **Add MCP Server**

Register each:

| Name | URL |
|------|-----|
| `fortianalyzer` | `http://<ALB_DNS>:80/mcp` |
| `fortimanager` | `http://<ALB_DNS>:80/mcp` |
| `fortigate` | `http://<ALB_DNS>:80/mcp` |

> Note: If using path-based routing, URLs would be:
> - `http://<ALB_DNS>/fortianalyzer/mcp`
> - `http://<ALB_DNS>/fortimanager/mcp`
> - `http://<ALB_DNS>/fortigate/mcp`

4. Verify each shows **Connected**

---

## Step 7: Test

Chat with the DevOps Agent:

```
Check the health of all FortiGate devices
```

```
Search FortiAnalyzer traffic logs for blocked traffic from 10.0.1.229 in the last hour
```

```
List all firewall policies on FortiManager in the root ADOM
```

---

## Troubleshooting

```bash
# Check ECS task logs
aws logs tail /ecs/fortinet-mcp --follow --region $REGION

# Check if tasks are running
aws ecs list-tasks --cluster fortinet-mcp --region $REGION

# Describe a failed task
aws ecs describe-tasks --cluster fortinet-mcp --tasks <task-arn> --region $REGION \
  --query 'tasks[0].{Status:lastStatus,Reason:stoppedReason}'

# Check ALB target health
aws elbv2 describe-target-health --target-group-arn <tg-arn> --region $REGION
```

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Task keeps restarting | Can't reach Fortinet appliance | Check SG allows outbound 443 to Fortinet IP |
| ALB returns 502 | Task not healthy | Check task logs for connection errors |
| DevOps Agent can't connect | ALB not reachable from agent | Use public ALB or PrivateLink |
| "Invalid session" in logs | Wrong API token | Regenerate token on Fortinet appliance |

---

## Delete Stack

```bash
aws cloudformation delete-stack --stack-name fortinet-mcp --region $REGION

# Also delete ECR repos if no longer needed
aws ecr delete-repository --repository-name fortigate-mcp --force --region $REGION
aws ecr delete-repository --repository-name fortimanager-mcp --force --region $REGION
aws ecr delete-repository --repository-name fortianalyzer-mcp --force --region $REGION
```
