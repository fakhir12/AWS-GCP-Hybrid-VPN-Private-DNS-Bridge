from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_route53 as route53,
    aws_route53resolver as resolver,
    CfnOutput,
    Tags,
    Fn,
    custom_resources as cr,
)
from constructs import Construct

class AwsCoreStack(Stack):

    def __init__(self, scope: Construct, id: str, config: dict, **kwargs):
        super().__init__(scope, id, **kwargs)

        name_prefix = f"{config['env']}-{config['identifier']}"
        
       
        
        # 1. VPC Setup
        vpc = ec2.Vpc(
            self, f"{name_prefix}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(config["vpc_cidr"]),
            max_azs=2,
            nat_gateways=0, 
            subnet_configuration=[]
        )
        Tags.of(vpc).add("Name", f"{name_prefix}-vpc")

        # 2. Route Tables & Subnets
        public_rt = ec2.CfnRouteTable(self, "PublicRT", vpc_id=vpc.vpc_id,
            tags=[{"key": "Name", "value": f"{name_prefix}-public-rt"}])
        private_rt = ec2.CfnRouteTable(self, "PrivateRT", vpc_id=vpc.vpc_id,
            tags=[{"key": "Name", "value": f"{name_prefix}-private-rt"}])

        my_public_subnets = []
        my_private_subnets = []

        for i, az in enumerate(vpc.availability_zones):
            pub_snet = ec2.CfnSubnet(self, f"PublicSubnet{i}",
                vpc_id=vpc.vpc_id, availability_zone=az,
                cidr_block=f"10.10.{i}.0/24", map_public_ip_on_launch=True,
                tags=[{"key": "Name", "value": f"{name_prefix}-public-subnet-{i}"}])
            ec2.CfnSubnetRouteTableAssociation(self, f"PublicAssoc{i}",
                route_table_id=public_rt.ref, subnet_id=pub_snet.ref)
            my_public_subnets.append(pub_snet)

            priv_snet = ec2.CfnSubnet(self, f"PrivateSubnet{i}",
                vpc_id=vpc.vpc_id, availability_zone=az,
                cidr_block=f"10.10.{i+2}.0/24",
                tags=[{"key": "Name", "value": f"{name_prefix}-private-subnet-{i}"}])
            ec2.CfnSubnetRouteTableAssociation(self, f"PrivateAssoc{i}",
                route_table_id=private_rt.ref, subnet_id=priv_snet.ref)
            my_private_subnets.append(priv_snet)

        # 3. Internet & NAT Gateway
        igw = ec2.CfnInternetGateway(self, "IGW", tags=[{"key": "Name", "value": f"{name_prefix}-igw"}])
        ec2.CfnVPCGatewayAttachment(self, "IGWAttach", vpc_id=vpc.vpc_id, internet_gateway_id=igw.ref)
        ec2.CfnRoute(self, "PublicDefaultRoute", route_table_id=public_rt.ref, destination_cidr_block="0.0.0.0/0", gateway_id=igw.ref)

        eip = ec2.CfnEIP(self, "NatEIP", tags=[{"key": "Name", "value": f"{name_prefix}-nat-eip"}])
        nat_gw = ec2.CfnNatGateway(self, "NatGateway", allocation_id=eip.attr_allocation_id, 
                                   subnet_id=my_public_subnets[0].ref, tags=[{"key": "Name", "value": f"{name_prefix}-nat-gw"}])
        ec2.CfnRoute(self, "PrivateRouteToNat", route_table_id=private_rt.ref, destination_cidr_block="0.0.0.0/0", nat_gateway_id=nat_gw.ref)

        # 4. VPN Infrastructure
        vgw = ec2.CfnVPNGateway(self, "vgw", type="ipsec.1", amazon_side_asn=config["aws_asn"],
                                tags=[{"key": "Name", "value": f"{name_prefix}-vgw"}])
        ec2.CfnVPCGatewayAttachment(self, "vgw-attach", vpc_id=vpc.vpc_id, vpn_gateway_id=vgw.ref)

        cgw = ec2.CfnCustomerGateway(self, "customer-gateway", bgp_asn=config["gcp_asn"],
                                     ip_address=config["gcp_vpn_ip_interface-0"], type="ipsec.1",
                                     tags=[{"key": "Name", "value": f"{name_prefix}-cgw"}])

        vpn_conn = ec2.CfnVPNConnection(self, "vpn-connection", customer_gateway_id=cgw.ref,
                                        vpn_gateway_id=vgw.ref, type="ipsec.1", static_routes_only=False,
                                        tags=[{"key": "Name", "value": f"{name_prefix}-vpn-connection"}])

        ec2.CfnVPNGatewayRoutePropagation(self, "Propagate-Private", route_table_ids=[private_rt.ref], vpn_gateway_id=vgw.ref)

        # 5. Security Groups
        resolver_sg = ec2.SecurityGroup(self, "ResolverSG", vpc=vpc, allow_all_outbound=True,
                                        description="Allow DNS traffic from GCP and Local VPC",
                                        security_group_name=f"{name_prefix}-resolver-sg")
        resolver_sg.add_ingress_rule(ec2.Peer.ipv4(config["gcp_dns_proxy_cidr"]), ec2.Port.udp(53))
        resolver_sg.add_ingress_rule(ec2.Peer.ipv4(config["vpc_cidr"]), ec2.Port.all_udp())

        instance_sg = ec2.SecurityGroup(self, "InstanceSG", vpc=vpc, allow_all_outbound=True,
                                        description="Allow ICMP and SSH", security_group_name=f"{name_prefix}-instance-sg")
        instance_sg.add_ingress_rule(ec2.Peer.ipv4(config["gcp_vpc_cidr"]), ec2.Port.icmp_ping())
        instance_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22))

        # 6. Instance & DNS
        private_subnet_0_ref = ec2.Subnet.from_subnet_attributes(self, "PriSub0", subnet_id=my_private_subnets[0].ref,
                                                                 availability_zone=vpc.availability_zones[0])
        instance = ec2.Instance(self, "instance", instance_name=f"{name_prefix}-test-instance",
                                instance_type=ec2.InstanceType("t3.micro"), security_group=instance_sg,
                                machine_image=ec2.MachineImage.latest_amazon_linux2(), vpc=vpc,
                                vpc_subnets=ec2.SubnetSelection(subnets=[private_subnet_0_ref]), key_name=config["ssh_key_name"])

        zone = route53.PrivateHostedZone(self, "private-zone", zone_name=config["dns_zone"], vpc=vpc)
        route53.ARecord(self, "instance-record", zone=zone, record_name=config["dns_record_name"],
                        target=route53.RecordTarget.from_ip_addresses(instance.instance_private_ip))

        # 7. Inbound & Outbound Resolvers
        inbound_resolver = resolver.CfnResolverEndpoint(self, "inbound-endpoint", direction="INBOUND",
                                                         security_group_ids=[resolver_sg.security_group_id],
                                                         ip_addresses=[resolver.CfnResolverEndpoint.IpAddressRequestProperty(subnet_id=my_private_subnets[0].ref),
                                                                       resolver.CfnResolverEndpoint.IpAddressRequestProperty(subnet_id=my_private_subnets[1].ref)],
                                                         name=f"{name_prefix}-inbound-resolver")

        outbound_resolver = resolver.CfnResolverEndpoint(self, "outbound-endpoint", direction="OUTBOUND",
                                                          security_group_ids=[resolver_sg.security_group_id],
                                                          ip_addresses=[resolver.CfnResolverEndpoint.IpAddressRequestProperty(subnet_id=my_private_subnets[0].ref),
                                                                        resolver.CfnResolverEndpoint.IpAddressRequestProperty(subnet_id=my_private_subnets[1].ref)],
                                                          name=f"{name_prefix}-outbound-resolver")

        # Forward queries for GCP to the GCP Inbound IP
        gcp_rule = resolver.CfnResolverRule(self, "GcpForwardingRule", domain_name="gcp.internal.",
                                            rule_type="FORWARD", resolver_endpoint_id=outbound_resolver.attr_resolver_endpoint_id,
                                            target_ips=[resolver.CfnResolverRule.TargetAddressProperty(ip="172.16.0.3")])
        resolver.CfnResolverRuleAssociation(self, "GcpRuleAssoc", resolver_rule_id=gcp_rule.attr_resolver_rule_id, vpc_id=vpc.vpc_id)

        # 8. Custom Resource for IPs
        get_ips = cr.AwsCustomResource(self, "GetResolverIPs",
            on_update=cr.AwsSdkCall(service="Route53Resolver", action="listResolverEndpointIpAddresses",
                                    parameters={"ResolverEndpointId": inbound_resolver.ref},
                                    physical_resource_id=cr.PhysicalResourceId.of(inbound_resolver.ref)),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE))

        CfnOutput(self, "ResolverIP1", value=get_ips.get_response_field("IpAddresses.0.Ip"))
        CfnOutput(self, "ResolverIP2", value=get_ips.get_response_field("IpAddresses.1.Ip"))