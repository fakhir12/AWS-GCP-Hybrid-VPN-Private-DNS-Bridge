import aws_cdk as cdk
from vpn_aws_to_gcp.vpn_aws_to_gcp_stack import AwsCoreStack

synth = cdk.DefaultStackSynthesizer(qualifier="gcp-vpn")
app = cdk.App()



config = {
    "env": "dev",
    "identifier": "gcp-vpn",
    "vpc_cidr": "10.10.0.0/16",
    "aws_asn": 64512,
    "gcp_asn": 65020,
    "gcp_vpn_ip_interface-0": "34.183.45.103", 
    "dns_zone": "vpn.internal",
    "dns_record_name": "test",
    "ssh_key_name": "vpn-ssh-key",
    "gcp_dns_proxy_cidr": "35.199.192.0/19", 
    "gcp_vpc_cidr": "172.16.0.0/24"
}

AwsCoreStack(app, "aws-hybrid-stack", config=config, synthesizer=synth)


app.synth()
