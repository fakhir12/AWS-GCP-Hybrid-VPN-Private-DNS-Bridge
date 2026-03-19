# AWS-GCP Hybrid VPN & Private DNS Bridge

This project establishes a **secure, encrypted bridge** between an AWS VPC and a GCP VPC, enabling seamless communication between resources in both clouds.

----

## Key Features

- **Encrypted VPN Tunnel:** Site-to-Site HA VPN using IPsec (IKEv2).  
- **Dynamic Routing:** BGP automatically exchanges routes between AWS and GCP.  
- **Unified DNS Resolution:**  
  - GCP resolves AWS hostnames (`test.vpn.internal`)  
  - AWS resolves GCP hostnames (`vm.gcp.internal`)  
- **Infrastructure as Code (IaC):**  
  - **AWS:** Managed via CDK (Python)  
  - **GCP:** Managed via Deployment Manager (Jinja templates)  

---

## Infrastructure Reference

| Parameter                   | AWS Side        | GCP Side         |
|------------------------------|----------------|----------------|
| VPC CIDR                     | 10.10.0.0/16   | 172.16.0.0/24  |
| BGP ASN                      | 64512          | 65020          |
| Private DNS Zone             | vpn.internal.  | gcp.internal.  |
| GCP VPN Public IP (Interface 0) | –             | 35.238.206.203 |
| AWS VPN Remote IP (Tunnel 1) | 34.192.128.185 | –              |
| BGP Peer IPs (Tunnel 1)      | 169.254.74.85  | 169.254.74.86  |

**Notes:**  
- Only **one tunnel** is configured.  
- BGP peer IPs and VPN PSK must be obtained from AWS VPN configuration.  
- GCP VPN Public IP (interface 0) is required for AWS CDK configuration.

---

## Deployment Workflow

Deployment must follow this **strict sequence**:

### Phase 1: Deploy GCP Foundation

1. Navigate to your GCP project folder.  
2. Deploy the core network and VPN gateway:

```bash
gcloud deployment-manager deployments create gcp-core --config gcp_core_config.yaml
````

3. Copy the **GCP VPN Public IP (interface 0)** from the GCP Console.

---

### Phase 2: Deploy AWS Hybrid Stack

1. Open AWS **app.py** for the CDK stack.
2. Insert the GCP VPN Public IP:

```python
"gcp_vpn_ip_interface-0": "<GCP_PUBLIC_IP>"
```

3. Deploy the AWS stack:

```bash
cdk deploy aws-hybrid-stack
```

4. Note the **AWS DNS Resolver IPs** from the output:

```text
aws-hybrid-stack.ResolverIP1 = 10.10.2.253
aws-hybrid-stack.ResolverIP2 = 10.10.3.192
```

5. Download the **AWS VPN configuration file** (contains PSK and BGP info).

---

### Phase 3: Configure and Deploy GCP VPN & DNS

1. Open `gcp_vpn_config.yaml`.
2. Configure AWS DNS Resolver IPs and VPN details:

```yaml
aws_dns_ip_1: "10.10.2.253"
aws_dns_ip_2: "10.10.3.192"
aws_vpn_ip: "<AWS_VPN_IP>"
shared_secret: "<AWS_PSK>"
gcp_bgp_ip: "<GCP_BGP_IP>"
aws_bgp_ip: "<AWS_BGP_IP>"
aws_asn: 64512
```

3. Deploy GCP VPN and DNS:

```bash
gcloud deployment-manager deployments create gcp-vpn --config gcp_vpn_config.yaml
```

**Notes:**

* Only **Tunnel 1** is used.
* GCP IP Interface 0 is used for AWS CDK configuration.
* Ensure traffic selectors match to avoid routing issues.

---

## Tools Reference

### AWS CDK

* `cdk bootstrap aws://387867038403/us-east-1 --qualifier gcp-vpn` 
* `cdk synth` – Preview CloudFormation template
* `cdk deploy aws-hybrid-stack` – Deploy or update stack
* `cdk destroy` – Tear down stack

### GCP Deployment Manager

* **imports:** Load Jinja templates
* **properties:** Customize variables (IPs, regions, names)
* Deploy:

```bash
gcloud deployment-manager deployments create <deployment-name> --config <config-file>
```

* Update:

```bash
gcloud deployment-manager deployments update <deployment-name> --config <config-file>
```

## Important Notes

* IKEv2 must match on both sides.
* PSK must match exactly, including special characters.
* Only **one VPN tunnel** is active.
* Use **GCP IP Interface 0** for AWS configuration.
