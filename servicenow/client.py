"""ServiceNow API integration for incident management."""
import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import boto3
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class ServiceNowClient:
    """Client for ServiceNow API operations."""
    
    def __init__(self, secret_name: str = "servicenow/credentials"):
        """Initialize ServiceNow client with credentials from Secrets Manager.
        
        Args:
            secret_name: Name of the secret in AWS Secrets Manager
        """
        self.credentials = self._get_credentials(secret_name)
        self.instance = self.credentials["servicenow_instance"]
        self.username = self.credentials["servicenow_username"]
        self.password = self.credentials["servicenow_password"]
        self.base_url = f"https://{self.instance}/api/now"
        self.auth = HTTPBasicAuth(self.username, self.password)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        logger.info(f"ServiceNow client initialized for instance: {self.instance}")
    
    def _get_credentials(self, secret_name: str) -> Dict:
        """Retrieve ServiceNow credentials from AWS Secrets Manager.
        
        Args:
            secret_name: Name of the secret
            
        Returns:
            Dictionary with credentials
        """
        try:
            secrets_client = boto3.client('secretsmanager')
            response = secrets_client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"Failed to retrieve secrets: {str(e)}")
            # Fallback to environment variables for local testing
            return {
                "servicenow_instance": os.environ.get("SERVICENOW_INSTANCE", ""),
                "servicenow_username": os.environ.get("SERVICENOW_USERNAME", ""),
                "servicenow_password": os.environ.get("SERVICENOW_PASSWORD", "")
            }
    
    def get_new_incidents(
        self,
        assignment_group: str,
        limit: int = 10,
        minutes_back: int = 10
    ) -> List[Dict]:
        """Fetch new incidents from ServiceNow.
        
        Args:
            assignment_group: Assignment group name to filter
            limit: Maximum number of incidents to fetch
            minutes_back: Look back this many minutes for new incidents
            
        Returns:
            List of incident dictionaries
        """
        try:
            # Calculate timestamp for filtering
            time_threshold = datetime.utcnow() - timedelta(minutes=minutes_back)
            time_str = time_threshold.strftime("%Y-%m-%d %H:%M:%S")
            
            # Build query
            # state=1 (New) OR state=2 (In Progress)
            # sys_created_on > time_threshold
            # assignment_group = specified group
            query = (
                f"assignment_group.name={assignment_group}"
                f"^stateIN1,2"
                f"^sys_created_on>{time_str}"
                f"^ORDERBYDESCsys_created_on"
            )
            
            params = {
                "sysparm_query": query,
                "sysparm_limit": limit,
                "sysparm_fields": "sys_id,number,short_description,description,state,priority,category,subcategory,assignment_group,assigned_to,sys_created_on"
            }
            
            url = f"{self.base_url}/table/incident"
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            incidents = result.get("result", [])
            
            logger.info(f"Retrieved {len(incidents)} new incidents from ServiceNow")
            return incidents
            
        except Exception as e:
            logger.error(f"Failed to fetch incidents: {str(e)}")
            return []
    
    def update_incident(
        self,
        sys_id: str,
        work_notes: Optional[str] = None,
        state: Optional[int] = None,
        resolution_code: Optional[str] = None,
        resolution_notes: Optional[str] = None
    ) -> bool:
        """Update a ServiceNow incident.
        
        Args:
            sys_id: Incident sys_id
            work_notes: Work notes to add
            state: New state (3=In Progress, 6=Resolved, 7=Closed)
            resolution_code: Resolution code
            resolution_notes: Resolution notes
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_data = {}
            
            if work_notes:
                update_data["work_notes"] = work_notes
            if state:
                update_data["state"] = state
            if resolution_code:
                update_data["close_code"] = resolution_code
            if resolution_notes:
                update_data["close_notes"] = resolution_notes
            
            if not update_data:
                logger.warning("No update data provided")
                return False
            
            url = f"{self.base_url}/table/incident/{sys_id}"
            response = requests.patch(
                url,
                auth=self.auth,
                headers=self.headers,
                json=update_data,
                timeout=30
            )
            response.raise_for_status()
            
            logger.info(f"Updated incident {sys_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update incident {sys_id}: {str(e)}")
            return False
    
    def close_incident(
        self,
        sys_id: str,
        resolution_code: str,
        resolution_notes: str
    ) -> bool:
        """Close a ServiceNow incident.
        
        Args:
            sys_id: Incident sys_id
            resolution_code: Resolution code (e.g., "Solved (Permanently)")
            resolution_notes: Resolution notes
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_incident(
            sys_id=sys_id,
            state=6,  # Resolved
            resolution_code=resolution_code,
            resolution_notes=resolution_notes
        )
    
    def add_work_notes(self, sys_id: str, notes: str) -> bool:
        """Add work notes to an incident.
        
        Args:
            sys_id: Incident sys_id
            notes: Work notes to add
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_incident(sys_id=sys_id, work_notes=notes)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Initialize client
    client = ServiceNowClient()
    
    # Fetch new incidents
    incidents = client.get_new_incidents(
        assignment_group="Data Lake Platform Team",
        limit=5
    )
    
    print(f"\nFound {len(incidents)} incidents:")
    for inc in incidents:
        print(f"  - {inc['number']}: {inc['short_description']}")
