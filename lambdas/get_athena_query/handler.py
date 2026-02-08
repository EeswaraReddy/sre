"""Get Athena query execution details."""
import json
import boto3
from typing import Any


athena = boto3.client("athena")


def handler(event: dict, context: Any) -> dict:
    """Retrieve Athena query execution details.
    
    Args:
        event: Contains query_execution_id (required)
    
    Returns:
        Query execution details including status, statistics, and results preview
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        query_execution_id = body.get("query_execution_id")
        
        if not query_execution_id:
            return _error_response(400, "query_execution_id is required")
        
        result = {"query_execution_id": query_execution_id}
        
        # Get query execution details
        execution_response = athena.get_query_execution(
            QueryExecutionId=query_execution_id
        )
        execution = execution_response["QueryExecution"]
        
        # Basic info
        result["query"] = execution.get("Query", "")[:1000]  # Truncate long queries
        result["state"] = execution["Status"].get("State")
        result["state_change_reason"] = execution["Status"].get("StateChangeReason")
        result["submission_time"] = execution["Status"].get("SubmissionDateTime")
        result["completion_time"] = execution["Status"].get("CompletionDateTime")
        
        # Query context
        context_info = execution.get("QueryExecutionContext", {})
        result["database"] = context_info.get("Database")
        result["catalog"] = context_info.get("Catalog")
        result["workgroup"] = execution.get("WorkGroup")
        
        # Statistics
        stats = execution.get("Statistics", {})
        result["statistics"] = {
            "engine_execution_time_ms": stats.get("EngineExecutionTimeInMillis"),
            "data_scanned_bytes": stats.get("DataScannedInBytes"),
            "total_execution_time_ms": stats.get("TotalExecutionTimeInMillis"),
            "query_queue_time_ms": stats.get("QueryQueueTimeInMillis"),
            "service_processing_time_ms": stats.get("ServiceProcessingTimeInMillis"),
            "result_reuse": stats.get("ResultReuseInformation", {}).get("ReusedPreviousResult", False)
        }
        
        # Result configuration
        result_config = execution.get("ResultConfiguration", {})
        result["output_location"] = result_config.get("OutputLocation")
        
        # If query succeeded, get a sample of results
        if result["state"] == "SUCCEEDED":
            try:
                results_response = athena.get_query_results(
                    QueryExecutionId=query_execution_id,
                    MaxResults=10
                )
                
                columns = []
                rows = []
                
                result_set = results_response.get("ResultSet", {})
                
                # Get column info
                for col in result_set.get("ResultSetMetadata", {}).get("ColumnInfo", []):
                    columns.append({
                        "name": col.get("Name"),
                        "type": col.get("Type")
                    })
                
                # Get row data (skip header)
                for i, row in enumerate(result_set.get("Rows", [])):
                    if i == 0:  # Skip header row
                        continue
                    row_data = [d.get("VarCharValue", "") for d in row.get("Data", [])]
                    rows.append(row_data)
                
                result["result_preview"] = {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows)
                }
                
            except Exception as e:
                result["result_preview_error"] = str(e)
        
        # If query failed, provide error details
        if result["state"] == "FAILED":
            result["error_category"] = execution["Status"].get("AthenaError", {}).get("ErrorCategory")
            result["error_type"] = execution["Status"].get("AthenaError", {}).get("ErrorType")
            result["error_message"] = execution["Status"].get("AthenaError", {}).get("ErrorMessage")
        
        return _success_response(result)
        
    except athena.exceptions.InvalidRequestException as e:
        return _error_response(404, f"Query execution not found: {str(e)}")
    except Exception as e:
        return _error_response(500, f"Error retrieving Athena query: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message})}
