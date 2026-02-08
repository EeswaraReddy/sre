"""Retry Glue job."""
import json
import boto3
import time
from typing import Any


glue = boto3.client("glue")


def handler(event: dict, context: Any) -> dict:
    """Retry a failed Glue job.
    
    Args:
        event: Contains job_name (required), run_id (optional - to copy args from failed run)
    
    Returns:
        New job run details
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        job_name = body.get("job_name")
        run_id = body.get("run_id")
        override_args = body.get("arguments", {})
        
        if not job_name:
            return _error_response(400, "job_name is required")
        
        result = {
            "job_name": job_name,
            "action": "retry_glue_job"
        }
        
        # Get job info
        try:
            job_info = glue.get_job(JobName=job_name)
        except glue.exceptions.EntityNotFoundException:
            return _error_response(404, f"Job {job_name} not found")
        
        job = job_info["Job"]
        default_args = job.get("DefaultArguments", {})
        
        # If run_id provided, get arguments from that run
        run_args = {}
        if run_id:
            try:
                run_info = glue.get_job_run(JobName=job_name, RunId=run_id)
                run = run_info["JobRun"]
                result["original_run_id"] = run_id
                result["original_run_state"] = run.get("JobRunState")
                result["original_error"] = run.get("ErrorMessage")
                
                # Check if the run actually failed
                if run.get("JobRunState") not in ["FAILED", "ERROR", "TIMEOUT", "STOPPED"]:
                    return _error_response(400, 
                        f"Run {run_id} is in {run.get('JobRunState')} state, retry not applicable")
                
                run_args = run.get("Arguments", {})
            except glue.exceptions.EntityNotFoundException:
                # Run not found, proceed with default args
                pass
        
        # Merge arguments: default < run < override
        final_args = {**default_args, **run_args, **override_args}
        
        # Start new job run
        start_params = {"JobName": job_name}
        if final_args:
            start_params["Arguments"] = final_args
        
        start_response = glue.start_job_run(**start_params)
        new_run_id = start_response["JobRunId"]
        
        result["new_run_id"] = new_run_id
        result["success"] = True
        result["arguments_used"] = final_args
        
        # Wait briefly and check initial status
        time.sleep(2)
        try:
            new_run_info = glue.get_job_run(JobName=job_name, RunId=new_run_id)
            result["new_run_state"] = new_run_info["JobRun"].get("JobRunState")
        except Exception:
            result["new_run_state"] = "STARTING"
        
        return _success_response(result)
        
    except glue.exceptions.ConcurrentRunsExceededException:
        return _error_response(429, "Maximum concurrent runs exceeded for this job")
    except Exception as e:
        return _error_response(500, f"Error retrying Glue job: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
