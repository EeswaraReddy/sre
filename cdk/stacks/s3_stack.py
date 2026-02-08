"""S3 Stack for RCA storage."""
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    CfnOutput,
)
from constructs import Construct


class S3Stack(Stack):
    """Creates S3 bucket for RCA (Root Cause Analysis) storage."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # RCA Storage Bucket
        self.rca_bucket = s3.Bucket(
            self, "RCABucket",
            bucket_name=f"incident-handler-rca-{self.account}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ArchiveOldRCA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=Duration.days(30)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        )
                    ],
                    expiration=Duration.days(365)
                )
            ]
        )

        # Outputs
        CfnOutput(self, "RCABucketName", value=self.rca_bucket.bucket_name)
        CfnOutput(self, "RCABucketArn", value=self.rca_bucket.bucket_arn)
