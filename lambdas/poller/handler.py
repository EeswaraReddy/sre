"""Lambda handler for polling ServiceNow incidents."""
import json
import logging
import os

from servicenow import ServiceNowClient

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Lambda handler for polling ServiceNow for new incidents.
    
    Triggered by EventBridge on a schedule (e.g., every 5 minutes).
    
    Args:
        event: EventBridge event
        context: Lambda context
        
    Returns:
        Response with processed incidents count
    """
    logger.info("Starting ServiceNow incident polling")
    
    # Get configuration from environment
    assignment_group = os.environ.get("ASSIGNMENT_GROUP", "Data Lake Platform Team")
    orchestrator_lambda = os.environ.get("ORCHESTRATOR_LAMBDA", "incident-orchestrator")
    poll_limit = int(os.environ.get("POLL_LIMIT", "10"))
    minutes_back = int(os.environ.get("MINUTES_BACK", "10"))
    
    try:
        # Initialize ServiceNow client
        snow_client = ServiceNowClient()
        
        # Fetch new incidents
        incidents = snow_client.get_new_incidents(
            assignment_group=assignment_group,
            limit=poll_limit,
            minutes_back=minutes_back
        )
        
        if not incidents:
            logger.info("No new incidents found")
            return {
                "statusCode": 200,
                "body": json.dumps({"incidents_found": 0})
            }
        
        logger.info(f"Found {len(incidents)} new incidents")
        
        # Invoke orchestrator for each incident
        import boto3
        lambda_client = boto3.client('lambda')
        
        processed = 0
        for incident in incidents:
            try:
                # Mark incident as "In Progress"
                snow_client.update_incident(
                    sys_id=incident['sys_id'],
                    state=2,  # In Progress
                    work_notes="Incident being processed by automated agent"
                )
                
                # Invoke orchestrator Lambda asynchronously
                lambda_client.invoke(
                    FunctionName=orchestrator_lambda,
                    InvocationType='Event',  # Async
                    Payload=json.dumps({
                        "incident": incident
                    })
                )
                
                processed += 1
                logger.info(f"Triggered processing for incident: {incident['number']}")
                
            except Exception as e:
                logger.error(f"Failed to process incident {incident['number']}: {str(e)}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "incidents_found": len(incidents),
                "incidents_processed": processed
            })
        }
        
    except Exception as e:
        logger.error(f"Polling error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
