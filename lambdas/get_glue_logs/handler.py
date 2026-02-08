"""Get Glue job run logs."""
import json
import boto3
from datetime import datetime, timedelta
from typing import Any


glue = boto3.client("glue")
logs = boto3.client("logs")


def handler(event: dict, context: Any) -> dict:
    """Retrieve Glue job run logs and execution details.
    
    Args:
        event: Contains job_name (required) and run_id (optional)
    
    Returns:
        Job run details and CloudWatch logs
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        job_name = body.get("job_name")
        run_id = body.get("run_id")
        
        if not job_name:
            return _error_response(400, "job_name is required")
        
        result = {"job_name": job_name, "logs": []}
        
        # Get job info
        job_info = glue.get_job(JobName=job_name)
        job = job_info["Job"]
        result["job_type"] = job.get("Command", {}).get("Name")
        result["glue_version"] = job.get("GlueVersion")
        result["worker_type"] = job.get("WorkerType")
        result["number_of_workers"] = job.get("NumberOfWorkers")
        
        if run_id:
            # Get specific run
            run_info = glue.get_job_run(JobName=job_name, RunId=run_id)
            run = run_info["JobRun"]
            result["run_id"] = run_id
            result["run_status"] = run.get("JobRunState")
            result["error_message"] = run.get("ErrorMessage")
            result["started_on"] = run.get("StartedOn")
            result["completed_on"] = run.get("CompletedOn")
            result["execution_time"] = run.get("ExecutionTime")
            result["dpu_seconds"] = run.get("DPUSeconds")
            
            # Get logs for this run
            result["logs"] = _get_cloudwatch_logs(job_name, run_id)
        else:
            # Get recent runs
            runs_response = glue.get_job_runs(JobName=job_name, MaxResults=10)
            result["recent_runs"] = [
                {
                    "run_id": r["Id"],
                    "status": r.get("JobRunState"),
                    "error": r.get("ErrorMessage"),
                    "started": r.get("StartedOn"),
                    "execution_time": r.get("ExecutionTime")
                }
                for r in runs_response.get("JobRuns", [])
            ]
            
            # If there's a failed run, get its logs
            failed_runs = [r for r in runs_response.get("JobRuns", []) 
                          if r.get("JobRunState") in ["FAILED", "ERROR", "TIMEOUT"]]
            if failed_runs:
                latest_failed = failed_runs[0]
                result["latest_failed_run"] = {
                    "run_id": latest_failed["Id"],
                    "error": latest_failed.get("ErrorMessage"),
                    "logs": _get_cloudwatch_logs(job_name, latest_failed["Id"])
                }
        
        return _success_response(result)
        
    except glue.exceptions.EntityNotFoundException as e:
        return _error_response(404, f"Glue resource not found: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrieving Glue logs: {str(e)}")


def _get_cloudwatch_logs(job_name: str, run_id: str) -> list:
    """Fetch CloudWatch logs for Glue job run."""
    log_entries = []
    
    # Glue logs are in /aws-glue/jobs/logs-v2 or /aws-glue/jobs/output
    log_groups = [
        f"/aws-glue/jobs/logs-v2",
        f"/aws-glue/jobs/output",
        f"/aws-glue/jobs/error"
    ]
    
    for log_group in log_groups:
        try:
            # Check if log group exists
            logs.describe_log_groups(logGroupNamePrefix=log_group)
            
            # Search for streams matching the run
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=run_id[:8],  # Glue uses run_id prefix
                limit=5
            )
            
            for stream in streams.get("logStreams", []):
                events = logs.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream["logStreamName"],
                    limit=100
                )
                
                for event in events.get("events", []):
                    log_entries.append({
                        "timestamp": event["timestamp"],
                        "message": event["message"][:500],
                        "log_group": log_group.split("/")[-1]
                    })
                    
        except Exception:
            continue
    
    # Sort by timestamp
    log_entries.sort(key=lambda x: x.get("timestamp", 0))
    return log_entries[-100:]  # Last 100 entries


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
