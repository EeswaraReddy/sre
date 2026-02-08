"""Retry Kafka event processing."""
import json
import boto3
from typing import Any


kafka = boto3.client("kafka")
lambda_client = boto3.client("lambda")


def handler(event: dict, context: Any) -> dict:
    """Retry failed Kafka event processing.
    
    Args:
        event: Contains cluster_arn OR bootstrap_brokers, topic, 
               consumer_function (Lambda function name that processes events)
    
    Returns:
        Retry status and details
    """
    try:
        body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
        cluster_arn = body.get("cluster_arn")
        consumer_function = body.get("consumer_function")
        topic = body.get("topic")
        failed_records = body.get("failed_records", [])
        
        if not consumer_function:
            return _error_response(400, "consumer_function is required")
        
        result = {
            "consumer_function": consumer_function,
            "action": "retry_kafka"
        }
        
        # Get cluster info if ARN provided
        if cluster_arn:
            try:
                cluster_info = kafka.describe_cluster_v2(ClusterArn=cluster_arn)
                cluster = cluster_info.get("ClusterInfo", {})
                result["cluster_name"] = cluster.get("ClusterName")
                result["cluster_state"] = cluster.get("State")
                
                if cluster.get("State") != "ACTIVE":
                    return _error_response(400, f"Cluster is in {cluster.get('State')} state")
                
                # Get bootstrap brokers
                brokers_response = kafka.get_bootstrap_brokers(ClusterArn=cluster_arn)
                result["bootstrap_brokers"] = brokers_response.get("BootstrapBrokerStringSaslIam") or \
                                              brokers_response.get("BootstrapBrokerString")
                                              
            except kafka.exceptions.NotFoundException:
                return _error_response(404, f"Cluster not found: {cluster_arn}")
        
        # Check if consumer Lambda exists and get its event source mappings
        try:
            # Get function info
            func_info = lambda_client.get_function(FunctionName=consumer_function)
            result["function_state"] = func_info["Configuration"].get("State")
            
            # List event source mappings
            esm_response = lambda_client.list_event_source_mappings(
                FunctionName=consumer_function
            )
            
            kafka_mappings = [
                m for m in esm_response.get("EventSourceMappings", [])
                if "kafka" in m.get("EventSourceArn", "").lower() or 
                   m.get("SelfManagedEventSource")
            ]
            
            result["event_source_mappings"] = [
                {
                    "uuid": m["UUID"],
                    "state": m["State"],
                    "event_source": m.get("EventSourceArn") or "self-managed",
                    "topics": m.get("Topics", [])
                }
                for m in kafka_mappings
            ]
            
        except lambda_client.exceptions.ResourceNotFoundException:
            return _error_response(404, f"Function not found: {consumer_function}")
        
        # Option 1: If specific failed records provided, invoke Lambda directly
        if failed_records:
            result["retry_method"] = "direct_invocation"
            result["records_to_retry"] = len(failed_records)
            
            # Build Kafka event structure
            kafka_event = {
                "eventSource": "aws:kafka",
                "records": {}
            }
            
            # Group records by topic-partition
            for record in failed_records[:100]:  # Limit to 100 records
                topic_partition = f"{record.get('topic', topic)}-{record.get('partition', 0)}"
                if topic_partition not in kafka_event["records"]:
                    kafka_event["records"][topic_partition] = []
                kafka_event["records"][topic_partition].append({
                    "topic": record.get("topic", topic),
                    "partition": record.get("partition", 0),
                    "offset": record.get("offset", 0),
                    "timestamp": record.get("timestamp"),
                    "key": record.get("key"),
                    "value": record.get("value")
                })
            
            # Invoke Lambda asynchronously
            try:
                invoke_response = lambda_client.invoke(
                    FunctionName=consumer_function,
                    InvocationType="Event",  # Async
                    Payload=json.dumps(kafka_event)
                )
                
                result["invocation_status"] = invoke_response["StatusCode"]
                result["success"] = invoke_response["StatusCode"] == 202
                
            except Exception as e:
                result["success"] = False
                result["error"] = f"Failed to invoke function: {str(e)}"
        
        # Option 2: Check and potentially re-enable disabled event source mappings
        else:
            result["retry_method"] = "event_source_check"
            
            disabled_mappings = [m for m in kafka_mappings if m["State"] != "Enabled"]
            
            if disabled_mappings:
                result["disabled_mappings_found"] = len(disabled_mappings)
                result["recommendation"] = "Event source mappings are disabled. Enable them to resume processing."
                result["success"] = False
            else:
                result["message"] = "All event source mappings are enabled. Processing should continue automatically."
                result["success"] = True
        
        return _success_response(result)
        
    except Exception as e:
        return _error_response(500, f"Error with Kafka retry: {str(e)}")


def _success_response(data: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(data, default=str)}


def _error_response(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message, "success": False})}
