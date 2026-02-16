"""S3 storage for RCA documents."""
import json
import logging
from datetime import datetime
from typing import Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class RCAStorage:
    """Storage handler for RCA documents in S3."""
    
    def __init__(self, bucket_name: str, prefix: str = "rca"):
        """Initialize RCA storage.
        
        Args:
            bucket_name: S3 bucket name
            prefix: S3 key prefix for RCA documents
        """
        self.bucket_name = bucket_name
        self.prefix = prefix
        self.s3_client = boto3.client('s3')
        logger.info(f"RCA Storage initialized: s3://{bucket_name}/{prefix}")
    
    def store_rca(self, incident_id: str, rca: Dict) -> str:
        """Store RCA document to S3.
        
        Args:
            incident_id: Incident ID (e.g., INC001)
            rca: RCA document dictionary
            
        Returns:
            S3 URI of the stored document
        """
        try:
            # Generate S3 key with date partitioning
            timestamp = datetime.utcnow()
            date_path = timestamp.strftime("%Y/%m/%d")
            key = f"{self.prefix}/{date_path}/{incident_id}_rca.json"
            
            # Add storage metadata
            rca["_metadata"] = {
                "stored_at": timestamp.isoformat(),
                "s3_bucket": self.bucket_name,
                "s3_key": key
            }
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(rca, indent=2, default=str),
                ContentType="application/json",
                ServerSideEncryption="AES256"
            )
            
            s3_uri = f"s3://{self.bucket_name}/{key}"
            logger.info(f"Stored RCA for {incident_id}: {s3_uri}")
            return s3_uri
            
        except ClientError as e:
            logger.error(f"Failed to store RCA for {incident_id}: {str(e)}")
            raise
    
    def retrieve_rca(self, incident_id: str, date: str = None) -> Dict:
        """Retrieve RCA document from S3.
        
        Args:
            incident_id: Incident ID
            date: Date in YYYY/MM/DD format (default: today)
            
        Returns:
            RCA document dictionary
        """
        try:
            if not date:
                date = datetime.utcnow().strftime("%Y/%m/%d")
            
            key = f"{self.prefix}/{date}/{incident_id}_rca.json"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            rca = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Retrieved RCA for {incident_id}")
            return rca
            
        except ClientError as e:
            logger.error(f"Failed to retrieve RCA for {incident_id}: {str(e)}")
            raise
    
    def list_rcas(self, date: str = None, limit: int = 100) -> list:
        """List RCA documents for a specific date.
        
        Args:
            date: Date in YYYY/MM/DD format (default: today)
            limit: Maximum number of documents to return
            
        Returns:
            List of S3 keys
        """
        try:
            if not date:
                date = datetime.utcnow().strftime("%Y/%m/%d")
            
            prefix = f"{self.prefix}/{date}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=limit
            )
            
            keys = [obj['Key'] for obj in response.get('Contents', [])]
            logger.info(f"Found {len(keys)} RCAs for {date}")
            return keys
            
        except ClientError as e:
            logger.error(f"Failed to list RCAs: {str(e)}")
            return []


# Example usage
if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    
    bucket = os.environ.get("RCA_BUCKET", "incident-rca-bucket")
    storage = RCAStorage(bucket_name=bucket)
    
    # Example RCA document
    sample_rca = {
        "incident": {"sys_id": "INC001"},
        "classification": {"intent": "glue_etl_failure"},
        "decision": {"outcome": "auto_close"}
    }
    
    # Store RCA
    uri = storage.store_rca("INC001", sample_rca)
    print(f"Stored: {uri}")
    
    # Retrieve RCA
    retrieved = storage.retrieve_rca("INC001")
    print(f"Retrieved: {json.dumps(retrieved, indent=2, default=str)}")
