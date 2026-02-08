"""Retry Athena query."""
import json
import boto3
import time
from typing import Any


athena = boto3.client("athena")


def handler(event: dict, context: Any) -> dict:
    """Re-execute an Athena query.
    
    Args:
        event: Contains query_execution_id (required) OR query + workgroup
    
    Returns:
        New query execution details
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        query_execution_id = body.get("query_execution_id")
        query = body.get("query")
        workgroup = body.get("workgroup", "primary")
        database = body.get("database")
        catalog = body.get("catalog")
        
        result = {"action": "retry_athena_query"}
        
        # Either get query from previous execution or use provided query
        if query_execution_id:
            # Get original query details
            try:
                execution_response = athena.get_query_execution(
                    QueryExecutionId=query_execution_id
                )
                execution = execution_response["QueryExecution"]
                
                result["original_query_id"] = query_execution_id
                result["original_state"] = execution["Status"].get("State")
                
                # Check if query actually failed
                if execution["Status"].get("State") not in ["FAILED", "CANCELLED"]:
                    return _error_response(400, 
                        f"Query is in {execution['Status'].get('State')} state, retry not applicable")
                
                query = execution.get("Query")
                workgroup = execution.get("WorkGroup", workgroup)
                
                query_context = execution.get("QueryExecutionContext", {})
                database = database or query_context.get("Database")
                catalog = catalog or query_context.get("Catalog")
                
                result_config = execution.get("ResultConfiguration", {})
                output_location = result_config.get("OutputLocation")
                
            except athena.exceptions.InvalidRequestException:
                return _error_response(404, f"Query execution {query_execution_id} not found")
        
        if not query:
            return _error_response(400, "Either query_execution_id or query is required")
        
        result["query"] = query[:200] + "..." if len(query) > 200 else query
        
        # Build execution params
        exec_params = {
            "QueryString": query,
            "WorkGroup": workgroup
        }
        
        # Add query context if provided
        query_context = {}
        if database:
            query_context["Database"] = database
        if catalog:
            query_context["Catalog"] = catalog
        if query_context:
            exec_params["QueryExecutionContext"] = query_context
        
        # If we have output location from original, use it
        if query_execution_id and "output_location" in dir() and output_location:
            exec_params["ResultConfiguration"] = {"OutputLocation": output_location}
        
        # Start new query execution
        start_response = athena.start_query_execution(**exec_params)
        new_query_id = start_response["QueryExecutionId"]
        
        result["new_query_id"] = new_query_id
        result["workgroup"] = workgroup
        
        # Wait briefly and check status
        time.sleep(2)
        try:
            new_execution = athena.get_query_execution(QueryExecutionId=new_query_id)
            new_state = new_execution["QueryExecution"]["Status"]["State"]
            result["new_query_state"] = new_state
            result["success"] = new_state not in ["FAILED", "CANCELLED"]
        except Exception:
            result["new_query_state"] = "QUEUED"
            result["success"] = True
        
        return _success_response(result)
        
    except athena.exceptions.InvalidRequestException as e:
        return _error_response(400, f"Invalid request: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrying Athena query: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
