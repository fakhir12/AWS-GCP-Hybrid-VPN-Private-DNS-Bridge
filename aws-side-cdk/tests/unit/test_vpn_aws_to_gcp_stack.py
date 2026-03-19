import aws_cdk as core
import aws_cdk.assertions as assertions

from vpn_aws_to_gcp.vpn_aws_to_gcp_stack import VpnAwsToGcpStack

# example tests. To run these tests, uncomment this file along with the example
# resource in vpn_aws_to_gcp/vpn_aws_to_gcp_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = VpnAwsToGcpStack(app, "vpn-aws-to-gcp")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
