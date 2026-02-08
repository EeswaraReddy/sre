"""Update ServiceNow ticket with RCA."""
import json
import boto3
import os
import requests
from datetime import datetime
from typing import Any


secrets = boto3.client("secretsmanager")
s3 = boto3.client("s3")

RCA_BUCKET = os.environ.get("RCA_BUCKET")
RCA_PREFIX = os.environ.get("RCA_PREFIX", "rca/")
SERVICENOW_SECRET_ARN = os.environ.get("SERVICENOW_SECRET_ARN")


def handler(event: dict, context: Any) -> dict:
    """Update ServiceNow incident ticket and store RCA in S3.
    
    Args:
        event: Contains sys_id (required), status, rca, resolution_notes
    
    Returns:
        Update confirmation and RCA S3 location
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        
        sys_id = body.get("sys_id")
        status = body.get("status")  # e.g., "resolved", "in_progress", "on_hold"
        rca = body.get("rca", {})
        resolution_notes = body.get("resolution_notes", "")
        work_notes = body.get("work_notes", "")
        assigned_to = body.get("assigned_to")
        
        if not sys_id:
            return _error_response(400, "sys_id is required")
        
        result = {
            "sys_id": sys_id,
            "action": "update_servicenow_ticket"
        }
        
        # Store RCA in S3
        if rca:
            rca_result = _store_rca(sys_id, rca)
            result["rca_storage"] = rca_result
        
        # Get ServiceNow credentials
        if SERVICENOW_SECRET_ARN:
            credentials = _get_servicenow_credentials()
            if not credentials:
                result["servicenow_update"] = {
                    "success": False,
                    "error": "Failed to retrieve ServiceNow credentials"
                }
                return _success_response(result)
            
            # Update ServiceNow ticket
            sn_result = _update_servicenow(
                credentials, 
                sys_id, 
                status, 
                resolution_notes, 
                work_notes,
                assigned_to,
                result.get("rca_storage", {}).get("s3_uri")
            )
            result["servicenow_update"] = sn_result
        else:
            result["servicenow_update"] = {
                "success": False,
                "skipped": True,
                "reason": "SERVICENOW_SECRET_ARN not configured"
            }
        
        result["success"] = (
            result.get("rca_storage", {}).get("success", True) and
            result.get("servicenow_update", {}).get("success", True)
        )
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error updating ticket: {str(e)}")


def _store_rca(sys_id: str, rca: dict) -> dict:
    """Store RCA document in S3."""
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        key = f"{RCA_PREFIX}{sys_id}/{timestamp}_rca.json"
        
        # Add metadata
        rca_doc = {
            "incident_id": sys_id,
            "generated_at": datetime.utcnow().isoformat(),
            **rca
        }
        
        s3.put_object(
            Bucket=RCA_BUCKET,
            Key=key,
            Body=json.dumps(rca_doc, indent=2, default=str),
            ContentType="application/json",
            Metadata={
                "incident-id": sys_id,
                "generated-by": "incident-handler-agent"
            }
        )
        
        return {
            "success": True,
            "bucket": RCA_BUCKET,
            "key": key,
            "s3_uri": f"s3://{RCA_BUCKET}/{key}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def _get_servicenow_credentials() -> dict:
    """Retrieve ServiceNow OAuth credentials from Secrets Manager."""
    try:
        response = secrets.get_secret_value(SecretId=SERVICENOW_SECRET_ARN)
        secret = json.loads(response["SecretString"])
        return secret
    except Exception:
        return None


def _update_servicenow(credentials: dict, sys_id: str, status: str,
                       resolution_notes: str, work_notes: str,
                       assigned_to: str, rca_s3_uri: str) -> dict:
    """Update ServiceNow incident via REST API with OAuth."""
    try:
        instance_url = credentials.get("instance_url")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not all([instance_url, client_id, client_secret]):
            return {"success": False, "error": "Missing ServiceNow credentials"}
        
        # Get OAuth token
        token_response = requests.post(
            f"{instance_url}/oauth_token.do",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret
            },
            timeout=10
        )
        
        if token_response.status_code != 200:
            return {"success": False, "error": f"OAuth failed: {token_response.status_code}"}
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        # Build update payload
        update_data = {}
        
        if status:
            # Map status to ServiceNow state values
            status_map = {
                "resolved": "6",       # Resolved
                "closed": "7",         # Closed
                "in_progress": "2",    # In Progress
                "on_hold": "3",        # On Hold
                "escalated": "2",      # In Progress (with assignment change)
            }
            if status in status_map:
                update_data["state"] = status_map[status]
        
        if resolution_notes:
            update_data["close_notes"] = resolution_notes
        
        if work_notes:
            # Append RCA S3 location to work notes
            full_notes = work_notes
            if rca_s3_uri:
                full_notes += f"\n\n[Automated] RCA stored at: {rca_s3_uri}"
            update_data["work_notes"] = full_notes
        elif rca_s3_uri:
            update_data["work_notes"] = f"[Automated] RCA stored at: {rca_s3_uri}"
        
        if assigned_to:
            update_data["assigned_to"] = assigned_to
        
        if not update_data:
            return {"success": True, "skipped": True, "reason": "No updates to apply"}
        
        # Update incident
        update_response = requests.patch(
            f"{instance_url}/api/now/table/incident/{sys_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json=update_data,
            timeout=15
        )
        
        if update_response.status_code in [200, 204]:
            return {
                "success": True,
                "status_code": update_response.status_code,
                "fields_updated": list(update_data.keys())
            }
        else:
            return {
                "success": False,
                "status_code": update_response.status_code,
                "error": update_response.text[:500]
            }
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "ServiceNow request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"ServiceNow request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
