"""Get MWAA/Airflow task logs."""
import json
import boto3
from datetime import datetime, timedelta
from typing import Any


mwaa = boto3.client("mwaa")
logs = boto3.client("logs")


def handler(event: dict, context: Any) -> dict:
    """Retrieve MWAA/Airflow logs for DAG runs and tasks.
    
    Args:
        event: Contains environment_name (required), dag_id, execution_date, task_id
    
    Returns:
        DAG/task execution logs
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        environment_name = body.get("environment_name")
        dag_id = body.get("dag_id")
        execution_date = body.get("execution_date")
        task_id = body.get("task_id")
        
        if not environment_name:
            return _error_response(400, "environment_name is required")
        
        result = {"environment_name": environment_name, "logs": []}
        
        # Get environment info
        env_info = mwaa.get_environment(Name=environment_name)
        env = env_info["Environment"]
        result["status"] = env.get("Status")
        result["airflow_version"] = env.get("AirflowVersion")
        result["webserver_url"] = env.get("WebserverUrl")
        result["logging_config"] = env.get("LoggingConfiguration", {})
        
        # Get log group names from environment config
        log_config = env.get("LoggingConfiguration", {})
        
        log_groups = []
        if dag_id and task_id:
            # Task-specific logs
            if log_config.get("TaskLogs", {}).get("Enabled"):
                log_groups.append(f"airflow-{environment_name}-Task")
        elif dag_id:
            # DAG processor logs
            if log_config.get("DagProcessingLogs", {}).get("Enabled"):
                log_groups.append(f"airflow-{environment_name}-DAGProcessing")
        else:
            # General scheduler and worker logs
            if log_config.get("SchedulerLogs", {}).get("Enabled"):
                log_groups.append(f"airflow-{environment_name}-Scheduler")
            if log_config.get("WorkerLogs", {}).get("Enabled"):
                log_groups.append(f"airflow-{environment_name}-Worker")
            if log_config.get("WebserverLogs", {}).get("Enabled"):
                log_groups.append(f"airflow-{environment_name}-WebServer")
        
        # Fetch logs from each log group
        all_logs = []
        for log_group in log_groups:
            group_logs = _get_cloudwatch_logs(log_group, dag_id, task_id, execution_date)
            all_logs.extend(group_logs)
        
        # Sort by timestamp
        all_logs.sort(key=lambda x: x.get("timestamp", 0))
        result["logs"] = all_logs[-200:]  # Last 200 entries
        
        # Add search metadata
        if dag_id:
            result["searched_dag"] = dag_id
        if task_id:
            result["searched_task"] = task_id
        if execution_date:
            result["searched_execution_date"] = execution_date
        
        return _success_response(result)
        
    except mwaa.exceptions.ResourceNotFoundException as e:
        return _error_response(404, f"MWAA environment not found: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrieving MWAA logs: {str(e)}")


def _get_cloudwatch_logs(log_group: str, dag_id: str = None, 
                         task_id: str = None, execution_date: str = None) -> list:
    """Fetch CloudWatch logs with optional filtering."""
    log_entries = []
    
    try:
        # Build filter pattern
        filter_patterns = []
        if dag_id:
            filter_patterns.append(dag_id)
        if task_id:
            filter_patterns.append(task_id)
        if execution_date:
            filter_patterns.append(execution_date)
        
        filter_pattern = " ".join(f'"{p}"' for p in filter_patterns) if filter_patterns else None
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)
        
        params = {
            "logGroupName": log_group,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": 100
        }
        
        if filter_pattern:
            params["filterPattern"] = filter_pattern
        
        response = logs.filter_log_events(**params)
        
        for event in response.get("events", []):
            log_entries.append({
                "timestamp": event["timestamp"],
                "message": event["message"][:1000],
                "log_group": log_group.split("-")[-1]  # Task, Worker, Scheduler, etc.
            })
            
    except logs.exceptions.ResourceNotFoundException:
        pass
    except Exception:
        pass
    
    return log_entries


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
