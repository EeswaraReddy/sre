"""Retry Airflow DAG via MWAA CLI."""
import json
import boto3
import base64
import requests
from typing import Any


mwaa = boto3.client("mwaa")


def handler(event: dict, context: Any) -> dict:
    """Trigger a DAG run in MWAA.
    
    Args:
        event: Contains environment_name (required), dag_id (required), 
               execution_date (optional), conf (optional - DAG run config)
    
    Returns:
        DAG trigger result
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        environment_name = body.get("environment_name")
        dag_id = body.get("dag_id")
        execution_date = body.get("execution_date")
        conf = body.get("conf", {})
        
        if not environment_name or not dag_id:
            return _error_response(400, "environment_name and dag_id are required")
        
        result = {
            "environment_name": environment_name,
            "dag_id": dag_id,
            "action": "retry_airflow_dag"
        }
        
        # Get environment info
        try:
            env_info = mwaa.get_environment(Name=environment_name)
            env = env_info["Environment"]
            
            if env.get("Status") != "AVAILABLE":
                return _error_response(400, f"Environment is in {env.get('Status')} state")
            
            webserver_url = env.get("WebserverUrl")
            result["webserver_url"] = webserver_url
            
        except mwaa.exceptions.ResourceNotFoundException:
            return _error_response(404, f"Environment {environment_name} not found")
        
        # Create CLI token
        token_response = mwaa.create_cli_token(Name=environment_name)
        cli_token = token_response["CliToken"]
        web_server_hostname = token_response["WebServerHostname"]
        
        # Build Airflow CLI command to trigger DAG
        if execution_date:
            # Clear and re-run specific execution
            cli_command = f"dags trigger {dag_id} --exec-date {execution_date}"
        else:
            # Trigger new run
            cli_command = f"dags trigger {dag_id}"
        
        if conf:
            conf_json = json.dumps(conf)
            cli_command += f" --conf '{conf_json}'"
        
        result["cli_command"] = cli_command
        
        # Execute CLI command via MWAA REST API
        try:
            response = requests.post(
                f"https://{web_server_hostname}/aws_mwaa/cli",
                headers={
                    "Authorization": f"Bearer {cli_token}",
                    "Content-Type": "text/plain"
                },
                data=cli_command,
                timeout=30
            )
            
            # Decode response
            if response.status_code == 200:
                response_data = response.json()
                
                # stdout is base64 encoded
                stdout = base64.b64decode(response_data.get("stdout", "")).decode("utf-8")
                stderr = base64.b64decode(response_data.get("stderr", "")).decode("utf-8")
                
                result["cli_stdout"] = stdout
                result["cli_stderr"] = stderr if stderr else None
                
                # Check for success indicators
                if "Created" in stdout or "Triggered" in stdout or "queued" in stdout.lower():
                    result["success"] = True
                    # Try to extract run_id from output
                    if "run_id" in stdout:
                        # Parse run_id from output like "Created <DagRun ... run_id=xxx>"
                        import re
                        match = re.search(r"run_id[=:]?\s*([^\s,>]+)", stdout)
                        if match:
                            result["run_id"] = match.group(1)
                else:
                    result["success"] = False
                    result["error"] = stderr or stdout
            else:
                result["success"] = False
                result["error"] = f"CLI request failed with status {response.status_code}"
                result["response_body"] = response.text[:500]
                
        except requests.exceptions.Timeout:
            result["success"] = False
            result["error"] = "CLI request timed out"
        except requests.exceptions.RequestException as e:
            result["success"] = False
            result["error"] = f"CLI request failed: {str(e)}"
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error triggering Airflow DAG: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
