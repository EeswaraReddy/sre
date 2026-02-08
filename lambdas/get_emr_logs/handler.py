"""Get EMR cluster and step logs."""
import json
import boto3
from datetime import datetime, timedelta
from typing import Any


emr = boto3.client("elasticmapreduce")
logs = boto3.client("logs")
s3 = boto3.client("s3")


def handler(event: dict, context: Any) -> dict:
    """Retrieve EMR logs for a cluster or specific step.
    
    Args:
        event: Contains cluster_id (required) and step_id (optional)
    
    Returns:
        Logs and metadata for the specified EMR resource
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        cluster_id = body.get("cluster_id")
        step_id = body.get("step_id")
        
        if not cluster_id:
            return _error_response(400, "cluster_id is required")
        
        result = {"cluster_id": cluster_id, "logs": []}
        
        # Get cluster info
        cluster_info = emr.describe_cluster(ClusterId=cluster_id)
        cluster = cluster_info["Cluster"]
        result["cluster_name"] = cluster.get("Name")
        result["cluster_status"] = cluster["Status"]["State"]
        result["log_uri"] = cluster.get("LogUri")
        
        # Get step info if step_id provided
        if step_id:
            step_info = emr.describe_step(ClusterId=cluster_id, StepId=step_id)
            step = step_info["Step"]
            result["step_name"] = step.get("Name")
            result["step_status"] = step["Status"]["State"]
            result["step_failure_reason"] = step["Status"].get("FailureDetails", {}).get("Reason")
            
            # Get step logs from S3 if log_uri exists
            if cluster.get("LogUri"):
                log_uri = cluster["LogUri"]
                result["logs"] = _get_s3_logs(log_uri, cluster_id, step_id)
        else:
            # List recent steps
            steps_response = emr.list_steps(ClusterId=cluster_id)
            result["recent_steps"] = [
                {
                    "step_id": s["Id"],
                    "name": s["Name"],
                    "status": s["Status"]["State"],
                    "created": s["Status"]["Timeline"].get("CreationDateTime", "").isoformat()
                    if s["Status"]["Timeline"].get("CreationDateTime") else None
                }
                for s in steps_response.get("Steps", [])[:10]
            ]
        
        # Try to get CloudWatch logs
        cw_logs = _get_cloudwatch_logs(cluster_id, step_id)
        if cw_logs:
            result["cloudwatch_logs"] = cw_logs
        
        return _success_response(result)
        
    except emr.exceptions.InvalidRequestException as e:
        return _error_response(404, f"EMR resource not found: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrieving EMR logs: {str(e)}")


def _get_s3_logs(log_uri: str, cluster_id: str, step_id: str) -> list:
    """Fetch logs from S3."""
    logs_content = []
    try:
        # Parse S3 URI
        if log_uri.startswith("s3://"):
            parts = log_uri[5:].split("/", 1)
            bucket = parts[0]
            prefix = parts[1] if len(parts) > 1 else ""
        else:
            return logs_content
        
        # Construct step log path
        step_log_prefix = f"{prefix}{cluster_id}/steps/{step_id}/"
        
        response = s3.list_objects_v2(Bucket=bucket, Prefix=step_log_prefix, MaxKeys=10)
        
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith((".gz", ".log", ".txt", "stderr", "stdout")):
                try:
                    log_obj = s3.get_object(Bucket=bucket, Key=key)
                    content = log_obj["Body"].read()
                    
                    # Handle gzip
                    if key.endswith(".gz"):
                        import gzip
                        content = gzip.decompress(content)
                    
                    # Limit content size
                    content_str = content.decode("utf-8", errors="ignore")[:10000]
                    logs_content.append({
                        "file": key.split("/")[-1],
                        "content": content_str
                    })
                except Exception:
                    continue
                    
    except Exception:
        pass
    
    return logs_content


def _get_cloudwatch_logs(cluster_id: str, step_id: str = None) -> list:
    """Fetch CloudWatch logs for EMR."""
    log_entries = []
    try:
        log_group = f"/aws/emr/{cluster_id}"
        
        # Check if log group exists
        try:
            logs.describe_log_groups(logGroupNamePrefix=log_group)
        except Exception:
            return log_entries
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=6)
        
        response = logs.filter_log_events(
            logGroupName=log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            limit=50
        )
        
        for event in response.get("events", []):
            log_entries.append({
                "timestamp": event["timestamp"],
                "message": event["message"][:500]
            })
            
    except Exception:
        pass
    
    return log_entries


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
