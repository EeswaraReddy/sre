"""Cognito Stack for AgentCore Gateway authentication."""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_cognito as cognito,
    CfnOutput,
)
from constructs import Construct


class CognitoStack(Stack):
    """Creates Cognito User Pool and Client for JWT authentication."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # User Pool
        self.user_pool = cognito.UserPool(
            self, "AgentCoreUserPool",
            user_pool_name="incident-handler-agents",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # App Client for machine-to-machine auth
        self.app_client = self.user_pool.add_client(
            "AgentCoreAppClient",
            user_pool_client_name="incident-handler-service",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(
                admin_user_password=True,
                custom=True,
                user_srp=True,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    client_credentials=True,
                ),
                scopes=[cognito.OAuthScope.custom("agents/invoke")],
            ),
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
        )

        # Resource Server for custom scopes
        self.resource_server = self.user_pool.add_resource_server(
            "AgentCoreResourceServer",
            identifier="agents",
            scopes=[
                cognito.ResourceServerScope(
                    scope_name="invoke",
                    scope_description="Invoke agent tools"
                )
            ]
        )

        # Domain for hosted UI (optional but useful for OAuth flows)
        self.domain = self.user_pool.add_domain(
            "AgentCoreDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"incident-handler-{self.account}"
            )
        )

        # Outputs
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolArn", value=self.user_pool.user_pool_arn)
        CfnOutput(self, "AppClientId", value=self.app_client.user_pool_client_id)
        CfnOutput(self, "DomainUrl", value=self.domain.base_url())
