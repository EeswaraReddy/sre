"""Retry EMR step."""
import json
import boto3
import time
from typing import Any


emr = boto3.client("elasticmapreduce")


def handler(event: dict, context: Any) -> dict:
    """Retry a failed EMR step.
    
    Args:
        event: Contains cluster_id (required), step_id (required to get step config)
    
    Returns:
        New step execution details
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        cluster_id = body.get("cluster_id")
        step_id = body.get("step_id")
        
        if not cluster_id or not step_id:
            return _error_response(400, "cluster_id and step_id are required")
        
        result = {
            "cluster_id": cluster_id,
            "original_step_id": step_id,
            "action": "retry_emr_step"
        }
        
        # Get cluster status first
        cluster_info = emr.describe_cluster(ClusterId=cluster_id)
        cluster_state = cluster_info["Cluster"]["Status"]["State"]
        
        if cluster_state not in ["WAITING", "RUNNING"]:
            return _error_response(400, f"Cluster is in {cluster_state} state, cannot add steps")
        
        # Get original step configuration
        step_info = emr.describe_step(ClusterId=cluster_id, StepId=step_id)
        original_step = step_info["Step"]
        
        # Check if step actually failed
        original_state = original_step["Status"]["State"]
        if original_state not in ["FAILED", "CANCELLED", "INTERRUPTED"]:
            return _error_response(400, f"Step is in {original_state} state, retry not applicable")
        
        result["original_step_name"] = original_step.get("Name")
        result["original_step_state"] = original_state
        result["original_failure_reason"] = original_step["Status"].get("FailureDetails", {}).get("Reason")
        
        # Reconstruct step configuration
        config = original_step.get("Config", {})
        hadoop_jar_step = {
            "Jar": config.get("Jar"),
            "Args": config.get("Args", []),
            "MainClass": config.get("MainClass"),
        }
        # Remove None values
        hadoop_jar_step = {k: v for k, v in hadoop_jar_step.items() if v is not None}
        
        step_config = {
            "Name": f"{original_step.get('Name', 'RetryStep')}_retry_{int(time.time())}",
            "ActionOnFailure": original_step.get("ActionOnFailure", "CONTINUE"),
            "HadoopJarStep": hadoop_jar_step
        }
        
        # Add the new step
        add_response = emr.add_job_flow_steps(
            JobFlowId=cluster_id,
            Steps=[step_config]
        )
        
        new_step_id = add_response["StepIds"][0]
        result["new_step_id"] = new_step_id
        result["success"] = True
        
        # Wait briefly and check initial status
        time.sleep(2)
        new_step_info = emr.describe_step(ClusterId=cluster_id, StepId=new_step_id)
        result["new_step_state"] = new_step_info["Step"]["Status"]["State"]
        
        return _success_response(result)
        
    except emr.exceptions.InvalidRequestException as e:
        return _error_response(400, f"Invalid request: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrying EMR step: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
