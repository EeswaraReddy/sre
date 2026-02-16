#!/usr/bin/env python3
"""CDK App entry point for Incident Agent deployment."""
import os
from aws_cdk import App, Environment
from incident_agent_stack import IncidentAgentStack

app = App()

# Get AWS account and region from environment or use defaults
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

env = Environment(account=account, region=region)

IncidentAgentStack(
    app,
    "IncidentAgentStack",
    env=env,
    description="SRE Incident Agent - Automated incident handling with Bedrock"
)

app.synth()
