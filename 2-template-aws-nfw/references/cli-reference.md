# AWS CLI & API Reference for Network Investigation

## Quick Reference Commands

---

## 1. VPC & Subnet Information

### List all VPCs with CIDR
```bash
aws ec2 describe-vpcs \
  --query 'Vpcs[].{VpcId:VpcId,CidrBlock:CidrBlock,Name:Tags[?Key==`Name`].Value|[0]}' \
  --output table
```

### List subnets in a VPC
```bash
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock,Name:Tags[?Key==`Name`].Value|[0]}' \
  --output table
```

### Get VPC CIDR associations
```bash
aws ec2 describe-vpcs --vpc-ids vpc-xxxxx \
  --query 'Vpcs[].CidrBlockAssociationSet[].{CIDR:CidrBlock,State:CidrBlockState.State}'
```

---

## 2. Security Groups

### Describe security group rules
```bash
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-xxxxx" \
  --query 'SecurityGroupRules[].{Direction:IsEgress,Protocol:IpProtocol,FromPort:FromPort,ToPort:ToPort,CIDR:CidrIpv4,RefSG:ReferencedGroupInfo.GroupId,Description:Description}' \
  --output table
```

### Find security groups for an instance
```bash
aws ec2 describe-instances --instance-ids i-xxxxx \
  --query 'Reservations[].Instances[].{InstanceId:InstanceId,SGs:SecurityGroups[].{Id:GroupId,Name:GroupName}}' \
  --output json
```

### Find security groups for an ENI
```bash
aws ec2 describe-network-interfaces --network-interface-ids eni-xxxxx \
  --query 'NetworkInterfaces[].{ENI:NetworkInterfaceId,SGs:Groups[].{Id:GroupId,Name:GroupName},SubnetId:SubnetId,VpcId:VpcId}'
```

### Search for SG rules allowing specific port
```bash
aws ec2 describe-security-groups \
  --filters "Name=ip-permission.to-port,Values=3306" \
  --query 'SecurityGroups[].{GroupId:GroupId,GroupName:GroupName,Rules:IpPermissions[?ToPort==`3306`]}'
```

### Find all SGs in a VPC
```bash
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --query 'SecurityGroups[].{GroupId:GroupId,GroupName:GroupName,Description:Description}' \
  --output table
```

---

## 3. Route Tables

### Get route table for a subnet
```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-xxxxx" \
  --query 'RouteTables[].{RouteTableId:RouteTableId,Routes:Routes[].{Dest:DestinationCidrBlock,Target:GatewayId||NatGatewayId||TransitGatewayId||NetworkInterfaceId||VpcEndpointId,State:State}}' \
  --output json
```

### List all route tables in a VPC
```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --query 'RouteTables[].{Id:RouteTableId,Name:Tags[?Key==`Name`].Value|[0],Associations:Associations[].SubnetId}' \
  --output json
```

### Check for blackhole routes
```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --query 'RouteTables[].Routes[?State==`blackhole`].{Dest:DestinationCidrBlock,State:State}'
```

---

## 4. Transit Gateway

### Describe TGW
```bash
aws ec2 describe-transit-gateways \
  --query 'TransitGateways[].{Id:TransitGatewayId,State:State,CIDR:Options.TransitGatewayCidrBlocks,ASN:Options.AmazonSideAsn}'
```

### List TGW attachments
```bash
aws ec2 describe-transit-gateway-attachments \
  --filters "Name=transit-gateway-id,Values=tgw-xxxxx" \
  --query 'TransitGatewayAttachments[].{Id:TransitGatewayAttachmentId,ResourceId:ResourceId,Type:ResourceType,State:State}' \
  --output table
```

### List TGW route tables
```bash
aws ec2 describe-transit-gateway-route-tables \
  --filters "Name=transit-gateway-id,Values=tgw-xxxxx" \
  --query 'TransitGatewayRouteTables[].{Id:TransitGatewayRouteTableId,Name:Tags[?Key==`Name`].Value|[0],State:State}' \
  --output table
```

### Search routes in TGW route table
```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-xxxxx \
  --filters "Name=state,Values=active" \
  --query 'Routes[].{CIDR:DestinationCidrBlock,Type:Type,AttachmentId:TransitGatewayAttachments[0].TransitGatewayAttachmentId,ResourceId:TransitGatewayAttachments[0].ResourceId}'
```

### Check for blackhole routes in TGW
```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-xxxxx \
  --filters "Name=state,Values=blackhole"
```

### Get TGW route table associations
```bash
aws ec2 get-transit-gateway-route-table-associations \
  --transit-gateway-route-table-id tgw-rtb-xxxxx \
  --query 'Associations[].{AttachmentId:TransitGatewayAttachmentId,ResourceId:ResourceId,ResourceType:ResourceType,State:State}'
```

### Get TGW route table propagations
```bash
aws ec2 get-transit-gateway-route-table-propagations \
  --transit-gateway-route-table-id tgw-rtb-xxxxx \
  --query 'TransitGatewayRouteTablePropagations[].{AttachmentId:TransitGatewayAttachmentId,ResourceId:ResourceId,State:State}'
```

### Check Appliance Mode
```bash
aws ec2 describe-transit-gateway-vpc-attachments \
  --transit-gateway-attachment-ids tgw-attach-xxxxx \
  --query 'TransitGatewayVpcAttachments[].{Id:TransitGatewayAttachmentId,VpcId:VpcId,ApplianceMode:Options.ApplianceModeSupport,DnsSupport:Options.DnsSupport}'
```

---

## 5. AWS Network Firewall

### List firewalls
```bash
aws network-firewall list-firewalls \
  --query 'Firewalls[].{Name:FirewallName,ARN:FirewallArn}'
```

### Describe firewall
```bash
aws network-firewall describe-firewall \
  --firewall-name <firewall-name> \
  --query '{Status:FirewallStatus.Status,Policy:Firewall.FirewallPolicyArn,Subnets:Firewall.SubnetMappings[].SubnetId,Endpoints:FirewallStatus.SyncStates}'
```

### Get firewall endpoints (for route table configuration)
```bash
aws network-firewall describe-firewall \
  --firewall-name <firewall-name> \
  --query 'FirewallStatus.SyncStates' \
  --output json
```

### Describe firewall policy
```bash
aws network-firewall describe-firewall-policy \
  --firewall-policy-name <policy-name> \
  --query '{StatelessRuleGroups:FirewallPolicy.StatelessRuleGroupReferences,StatefulRuleGroups:FirewallPolicy.StatefulRuleGroupReferences,DefaultActions:FirewallPolicy.StatelessDefaultActions}'
```

### Describe stateful rule group
```bash
aws network-firewall describe-rule-group \
  --rule-group-name east-west-rules \
  --type STATEFUL \
  --query 'RuleGroup.RulesSource'
```

### Describe stateless rule group
```bash
aws network-firewall describe-rule-group \
  --rule-group-name stateless-rules \
  --type STATELESS \
  --query 'RuleGroup.RulesSource.StatelessRulesAndCustomActions'
```

### Check firewall logging configuration
```bash
aws network-firewall describe-logging-configuration \
  --firewall-name <firewall-name>
```

---

## 6. NAT Gateway

### Describe NAT Gateways
```bash
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=vpc-inspection-id" \
  --query 'NatGateways[].{Id:NatGatewayId,State:State,SubnetId:SubnetId,AZ:Tags[?Key==`Name`].Value|[0],PublicIP:NatGatewayAddresses[0].PublicIp,PrivateIP:NatGatewayAddresses[0].PrivateIp}'
```

### Check NAT Gateway metrics
```bash
# Packets dropped
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name PacketsDropCount \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Port allocation errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Active connections
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ActiveConnectionCount \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Maximum
```

---

## 7. VPC Endpoints

### List VPC Endpoints
```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-inspection-id" \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,State:State,Subnets:SubnetIds}' \
  --output table
```

### Check endpoint policy
```bash
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].PolicyDocument' \
  --output json
```

### Check endpoint DNS entries
```bash
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].{DnsEntries:DnsEntries,PrivateDns:PrivateDnsEnabled}'
```

### Check gateway endpoint route tables
```bash
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx \
  --query 'VpcEndpoints[].RouteTableIds'
```

---

## 8. Direct Connect

### Check DX connections
```bash
aws directconnect describe-connections \
  --query 'connections[].{Id:connectionId,Name:connectionName,State:connectionState,Bandwidth:bandwidth,Location:location}'
```

### Check Virtual Interfaces
```bash
aws directconnect describe-virtual-interfaces \
  --query 'virtualInterfaces[].{Id:virtualInterfaceId,Name:virtualInterfaceName,State:virtualInterfaceState,VLAN:vlan,BGPPeers:bgpPeers[].{Status:bgpStatus,PeerState:bgpPeerState}}'
```

### Check BGP routes advertised
```bash
aws directconnect describe-virtual-interfaces \
  --virtual-interface-id dxvif-xxxxx \
  --query 'virtualInterfaces[].{RouteFilterPrefixes:routeFilterPrefixes,BGP:bgpPeers}'
```

---

## 9. VPN

### Check VPN connections
```bash
aws ec2 describe-vpn-connections \
  --query 'VpnConnections[].{Id:VpnConnectionId,State:State,Type:Type,TGW:TransitGatewayId,Tunnels:VgwTelemetry[].{IP:OutsideIpAddress,Status:status,StatusMsg:statusMessage}}'
```

### Check VPN tunnel status
```bash
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-xxxxx \
  --query 'VpnConnections[].VgwTelemetry[].{OutsideIP:OutsideIpAddress,Status:status,StatusMessage:statusMessage,LastChange:lastStatusChange}'
```

---

## 10. SD-WAN / TGW Connect

### List TGW Connect attachments
```bash
aws ec2 describe-transit-gateway-connects \
  --query 'TransitGatewayConnects[].{Id:TransitGatewayAttachmentId,TransportAttachment:TransportTransitGatewayAttachmentId,State:State}'
```

### Check TGW Connect Peers (GRE + BGP)
```bash
aws ec2 describe-transit-gateway-connect-peers \
  --query 'TransitGatewayConnectPeers[].{Id:TransitGatewayConnectPeerId,State:State,InsideCidr:ConnectPeerConfiguration.InsideCidrBlocks,PeerAddress:ConnectPeerConfiguration.PeerAddress,BgpConfigurations:ConnectPeerConfiguration.BgpConfigurations[].{PeerAsn:PeerAsn,Status:BgpStatus}}'
```

### Check BGP routes learned from Connect peers
```bash
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id <spoke-rt> \
  --filters "Name=type,Values=propagated" \
  --query 'Routes[].{CIDR:DestinationCidrBlock,Type:Type,Attachment:TransitGatewayAttachments[0].TransitGatewayAttachmentId}'
```

---

## 11. VPC Peering

### List peering connections
```bash
aws ec2 describe-vpc-peering-connections \
  --query 'VpcPeeringConnections[].{Id:VpcPeeringConnectionId,Status:Status.Code,Requester:RequesterVpcInfo.VpcId,RequesterCIDR:RequesterVpcInfo.CidrBlock,Accepter:AccepterVpcInfo.VpcId,AccepterCIDR:AccepterVpcInfo.CidrBlock}' \
  --output table
```

### Check specific peering connection
```bash
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-xxxxx \
  --query 'VpcPeeringConnections[0].{Status:Status.Code,Message:Status.Message,RequesterDns:RequesterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc,AccepterDns:AccepterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc}'
```

### Check routes for peering in a VPC
```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-xxxxx" \
  --query 'RouteTables[].Routes[?VpcPeeringConnectionId!=`null`].{Dest:DestinationCidrBlock,PeeringId:VpcPeeringConnectionId,State:State}'
```

### Enable DNS resolution across peering
```bash
aws ec2 modify-vpc-peering-connection-options \
  --vpc-peering-connection-id pcx-xxxxx \
  --requester-peering-connection-options AllowDnsResolutionFromRemoteVpc=true
```

---

## 12. VPC Flow Logs

### Query flow logs with CloudWatch Logs Insights
```bash
aws logs start-query \
  --log-group-name /vpc/flow-logs/<your-vpc-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, action
    | filter srcAddr = "<source-ip>" and dstAddr = "<destination-ip>"
    | sort @timestamp desc
    | limit 50'
```

### Get query results
```bash
aws logs get-query-results --query-id "query-id-from-above"
```

### Filter for REJECT actions
```bash
aws logs start-query \
  --log-group-name /vpc/flow-logs/<your-vpc-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, action
    | filter action = "REJECT"
    | stats count(*) as rejectCount by srcAddr, dstAddr, dstPort
    | sort rejectCount desc
    | limit 20'
```

---

## 13. Network Firewall Logs

### Query alert logs
```bash
aws logs start-query \
  --log-group-name /aws/network-firewall/alert \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, event.src_ip, event.dest_ip, event.src_port, event.dest_port, event.proto, event.alert.action, event.alert.signature
    | filter event.src_ip = "<source-ip>"
    | sort @timestamp desc
    | limit 50'
```

### Query flow logs for specific traffic
```bash
aws logs start-query \
  --log-group-name /aws/network-firewall/flow \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, event.src_ip, event.dest_ip, event.proto, event.app_proto
    | filter event.src_ip = "<source-ip>" and event.dest_ip = "<destination-ip>"
    | sort @timestamp desc
    | limit 50'
```

---

## 14. Transit Gateway Flow Logs

### Query TGW flow logs for specific traffic
```bash
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, packets, bytes, flowDirection, tgwId, tgwAttachmentId, tgwSrcVpc, tgwDstVpc, action, logStatus
    | filter srcAddr = "<source-ip>"
    | sort @timestamp desc
    | limit 50'
```

### Find REJECT/DROP in TGW flow logs
```bash
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, tgwSrcVpc, tgwDstVpc, action
    | filter action = "REJECT" or logStatus = "NODATA"
    | sort @timestamp desc
    | limit 20'
```

### Traffic volume per TGW attachment
```bash
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'stats sum(bytes) as totalBytes, count(*) as flowCount by tgwAttachmentId, flowDirection
    | sort totalBytes desc'
```

### Trace traffic between two VPCs via TGW
```bash
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, flowDirection, tgwSrcVpc, tgwDstVpc, tgwAttachmentId, action
    | filter tgwSrcVpc = "vpc-source-id" and tgwDstVpc = "vpc-dest-id"
    | sort @timestamp desc
    | limit 50'
```

### Check TGW blackhole drops (packets with no matching route)
```bash
aws logs start-query \
  --log-group-name /tgw/flow-logs/<your-tgw-log-group> \
  --start-time $(date -u -v-1H +%s) \
  --end-time $(date -u +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, dstPort, tgwAttachmentId, action, logStatus
    | filter logStatus = "NODATA"
    | sort @timestamp desc
    | limit 20'
```

---

## 15. VPC Reachability Analyzer

### Create network insights path
```bash
aws ec2 create-network-insights-path \
  --source eni-source-xxxxx \
  --destination eni-dest-xxxxx \
  --protocol TCP \
  --destination-port 443 \
  --tag-specifications 'ResourceType=network-insights-path,Tags=[{Key=Name,Value=wl1-to-wl2-443}]'
```

### Start analysis
```bash
aws ec2 start-network-insights-analysis \
  --network-insights-path-id nip-xxxxx
```

### Get analysis results
```bash
aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids nia-xxxxx \
  --query 'NetworkInsightsAnalyses[].{Status:Status,Reachable:NetworkPathFound,Explanations:Explanations[].{Component:Component,Explanation:ExplanationCode}}'
```

### Clean up
```bash
aws ec2 delete-network-insights-analysis --network-insights-analysis-ids nia-xxxxx
aws ec2 delete-network-insights-path --network-insights-path-id nip-xxxxx
```

---

## 16. Load Balancer (Ingress VPC)

### Describe ALB
```bash
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?VpcId==`vpc-ingress-id`].{Name:LoadBalancerName,DNS:DNSName,State:State.Code,Type:Type,Scheme:Scheme}'
```

### Check target health
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/tg-name/xxxxx \
  --query 'TargetHealthDescriptions[].{Target:Target.Id,Port:Target.Port,Health:TargetHealth.State,Reason:TargetHealth.Reason}'
```

### Check listener rules
```bash
aws elbv2 describe-rules \
  --listener-arn arn:aws:elasticloadbalancing:region:account:listener/app/alb-name/xxxxx/xxxxx \
  --query 'Rules[].{Priority:Priority,Conditions:Conditions,Actions:Actions[].{Type:Type,TargetGroup:TargetGroupArn}}'
```

---

## 17. CloudTrail - Network Change Investigation

### Find who modified a Security Group
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AuthorizeSecurityGroupIngress \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName,Resources:Resources[0].ResourceName}'
```

### Find who modified a Route Table
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateRoute \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteRoute \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'
```

### Find who modified Network Firewall rules
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateRuleGroup \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateFirewallPolicy \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'
```

### Find who modified Transit Gateway routes
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateTransitGatewayRoute \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteTransitGatewayRoute \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3
```

### Find all network-related changes by a specific user
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=<username> \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[?contains(EventName,`SecurityGroup`) || contains(EventName,`Route`) || contains(EventName,`Firewall`) || contains(EventName,`TransitGateway`)].{Time:EventTime,Event:EventName}'
```

### Find all changes to a specific resource
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=sg-xxxxx \
  --start-time $(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-southeast-3 \
  --query 'Events[].{Time:EventTime,User:Username,Event:EventName}'
```

### Common network-related CloudTrail events to investigate
```
Security Groups:     AuthorizeSecurityGroupIngress, AuthorizeSecurityGroupEgress,
                     RevokeSecurityGroupIngress, RevokeSecurityGroupEgress
Route Tables:        CreateRoute, DeleteRoute, ReplaceRoute, AssociateRouteTable
Transit Gateway:     CreateTransitGatewayRoute, DeleteTransitGatewayRoute,
                     AssociateTransitGatewayRouteTable, DisassociateTransitGatewayRouteTable
Network Firewall:    UpdateRuleGroup, UpdateFirewallPolicy, DeleteRuleGroup
VPC Peering:         CreateVpcPeeringConnection, DeleteVpcPeeringConnection,
                     AcceptVpcPeeringConnection, RejectVpcPeeringConnection
VPN:                 CreateVpnConnection, DeleteVpnConnection
NAT Gateway:         CreateNatGateway, DeleteNatGateway
VPC Endpoints:       CreateVpcEndpoint, DeleteVpcEndpoints, ModifyVpcEndpoint
```

---

## 18. CloudWatch Network Metrics

### NAT Gateway Metrics
```bash
# Port exhaustion (critical - causes connection failures)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ErrorPortAllocation \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Packets dropped
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name PacketsDropCount \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Active connections
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name ActiveConnectionCount \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum

# Bytes throughput
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination \
  --dimensions Name=NatGatewayId,Value=nat-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### Transit Gateway Metrics
```bash
# Packets dropped (no matching route - blackhole)
aws cloudwatch get-metric-statistics \
  --namespace AWS/TransitGateway \
  --metric-name PacketDropCountNoRoute \
  --dimensions Name=TransitGateway,Value=tgw-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Bytes per attachment
aws cloudwatch get-metric-statistics \
  --namespace AWS/TransitGateway \
  --metric-name BytesIn \
  --dimensions Name=TransitGateway,Value=tgw-xxxxx Name=TransitGatewayAttachment,Value=tgw-attach-xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### Network Firewall Metrics
```bash
# Dropped packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name DroppedPackets \
  --dimensions Name=FirewallName,Value=<firewall-name> Name=AvailabilityZone,Value=<availability-zone> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Passed packets
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name PassedPackets \
  --dimensions Name=FirewallName,Value=<firewall-name> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Stream exception (capacity issues)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NetworkFirewall \
  --metric-name StreamExceptionPolicyPackets \
  --dimensions Name=FirewallName,Value=<firewall-name> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### VPN Tunnel Metrics
```bash
# Tunnel state (1=UP, 0=DOWN)
aws cloudwatch get-metric-statistics \
  --namespace AWS/VPN \
  --metric-name TunnelState \
  --dimensions Name=VpnId,Value=vpn-xxxxx Name=TunnelIpAddress,Value=<tunnel-outside-ip> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average

# Tunnel data in/out
aws cloudwatch get-metric-statistics \
  --namespace AWS/VPN \
  --metric-name TunnelDataIn \
  --dimensions Name=VpnId,Value=vpn-xxxxx Name=TunnelIpAddress,Value=<tunnel-outside-ip> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum
```

### ALB/NLB Metrics
```bash
# Unhealthy targets
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name UnHealthyHostCount \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx Name=TargetGroup,Value=targetgroup/my-tg/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Maximum

# 5xx errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_ELB_5XX_Count \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Target response time
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/my-alb/xxxxx \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average,p99
```

### List All Network-Related CloudWatch Alarms
```bash
aws cloudwatch describe-alarms \
  --query 'MetricAlarms[?Namespace==`AWS/NATGateway` || Namespace==`AWS/TransitGateway` || Namespace==`AWS/NetworkFirewall` || Namespace==`AWS/VPN` || Namespace==`AWS/ApplicationELB`].{Name:AlarmName,State:StateValue,Metric:MetricName,Namespace:Namespace}' \
  --output table
```

---

## 19. Useful Compound Commands

### Full path trace (source to destination)
```bash
#!/bin/bash
# Usage: ./trace-path.sh <source-eni> <dest-eni> <port>

SOURCE_ENI=$1
DEST_ENI=$2
PORT=$3

echo "=== Source ENI Details ==="
aws ec2 describe-network-interfaces --network-interface-ids $SOURCE_ENI \
  --query 'NetworkInterfaces[].{VpcId:VpcId,SubnetId:SubnetId,PrivateIp:PrivateIpAddress,SGs:Groups[].GroupId}'

echo "=== Source Security Group Rules ==="
SG_ID=$(aws ec2 describe-network-interfaces --network-interface-ids $SOURCE_ENI \
  --query 'NetworkInterfaces[0].Groups[0].GroupId' --output text)
aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$SG_ID" \
  --query 'SecurityGroupRules[?IsEgress==`true`]'

echo "=== Source Subnet Route Table ==="
SUBNET_ID=$(aws ec2 describe-network-interfaces --network-interface-ids $SOURCE_ENI \
  --query 'NetworkInterfaces[0].SubnetId' --output text)
aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
  --query 'RouteTables[].Routes[]'

echo "=== Destination ENI Details ==="
aws ec2 describe-network-interfaces --network-interface-ids $DEST_ENI \
  --query 'NetworkInterfaces[].{VpcId:VpcId,SubnetId:SubnetId,PrivateIp:PrivateIpAddress,SGs:Groups[].GroupId}'

echo "=== Destination Security Group Rules ==="
DEST_SG=$(aws ec2 describe-network-interfaces --network-interface-ids $DEST_ENI \
  --query 'NetworkInterfaces[0].Groups[0].GroupId' --output text)
aws ec2 describe-security-group-rules --filters "Name=group-id,Values=$DEST_SG" \
  --query 'SecurityGroupRules[?IsEgress==`false` && ToPort==`'$PORT'`]'

echo "=== VPC Reachability Analysis ==="
PATH_ID=$(aws ec2 create-network-insights-path \
  --source $SOURCE_ENI --destination $DEST_ENI \
  --protocol TCP --destination-port $PORT \
  --query 'NetworkInsightsPath.NetworkInsightsPathId' --output text)

ANALYSIS_ID=$(aws ec2 start-network-insights-analysis \
  --network-insights-path-id $PATH_ID \
  --query 'NetworkInsightsAnalysis.NetworkInsightsAnalysisId' --output text)

sleep 30

aws ec2 describe-network-insights-analyses \
  --network-insights-analysis-ids $ANALYSIS_ID \
  --query 'NetworkInsightsAnalyses[].{Reachable:NetworkPathFound,Explanations:Explanations}'

# Cleanup
aws ec2 delete-network-insights-analysis --network-insights-analysis-ids $ANALYSIS_ID
aws ec2 delete-network-insights-path --network-insights-path-id $PATH_ID
```

### Network health check
```bash
#!/bin/bash
echo "=== TGW Status ==="
aws ec2 describe-transit-gateways --query 'TransitGateways[].{Id:TransitGatewayId,State:State}'

echo "=== TGW Attachments ==="
aws ec2 describe-transit-gateway-attachments \
  --query 'TransitGatewayAttachments[].{Id:TransitGatewayAttachmentId,Resource:ResourceId,State:State}'

echo "=== NAT Gateway Status ==="
aws ec2 describe-nat-gateways --filter "Name=state,Values=available,failed" \
  --query 'NatGateways[].{Id:NatGatewayId,State:State,VPC:VpcId}'

echo "=== Network Firewall Status ==="
aws network-firewall list-firewalls --query 'Firewalls[].FirewallName' --output text | while read FW; do
  aws network-firewall describe-firewall --firewall-name $FW \
    --query '{Name:Firewall.FirewallName,Status:FirewallStatus.Status}'
done

echo "=== VPN Tunnel Status ==="
aws ec2 describe-vpn-connections \
  --query 'VpnConnections[].{Id:VpnConnectionId,Tunnels:VgwTelemetry[].{Status:status}}'

echo "=== DX Connection Status ==="
aws directconnect describe-connections \
  --query 'connections[].{Id:connectionId,State:connectionState}'

echo "=== Blackhole Routes (TGW) ==="
for RTB in $(aws ec2 describe-transit-gateway-route-tables --query 'TransitGatewayRouteTables[].TransitGatewayRouteTableId' --output text); do
  BLACKHOLES=$(aws ec2 search-transit-gateway-routes --transit-gateway-route-table-id $RTB --filters "Name=state,Values=blackhole" --query 'Routes[]')
  if [ "$BLACKHOLES" != "[]" ] && [ "$BLACKHOLES" != "" ]; then
    echo "BLACKHOLE in $RTB: $BLACKHOLES"
  fi
done
```
