#!/usr/bin/env python3
"""CDK App for Multi-Agent Incident Handler Infrastructure."""
import aws_cdk as cdk
from stacks.s3_stack import S3Stack
from stacks.lambda_stack import LambdaStack
from stacks.cognito_stack import CognitoStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1"
)

# S3 Stack for RCA storage
s3_stack = S3Stack(app, "IncidentHandlerS3Stack", env=env)

# Cognito Stack for Gateway auth
cognito_stack = CognitoStack(app, "IncidentHandlerCognitoStack", env=env)

# Lambda Stack for all tools
lambda_stack = LambdaStack(
    app, "IncidentHandlerLambdaStack",
    rca_bucket=s3_stack.rca_bucket,
    env=env
)
lambda_stack.add_dependency(s3_stack)

# Monitoring Stack for agent observability
monitoring_stack = MonitoringStack(
    app, "IncidentHandlerMonitoringStack",
    lambda_functions=lambda_stack.functions,
    env=env
)
monitoring_stack.add_dependency(lambda_stack)

app.synth()
