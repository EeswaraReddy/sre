"""Lambda handler for orchestrating incident resolution."""
import json
import logging
import os

from agents import orchestrate_incident
from servicenow import ServiceNowClient
from storage import RCAStorage

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Lambda handler for orchestrating incident resolution.
    
    Triggered by the poller Lambda for each new incident.
    
    Args:
        event: Event containing incident data
        context: Lambda context
        
    Returns:
        Response with orchestration result
    """
    logger.info("Starting incident orchestration")
    
    try:
        # Extract incident from event
        incident = event.get("incident", {})
        sys_id = incident.get("sys_id", "unknown")
        incident_number = incident.get("number", "unknown")
        
        logger.info(f"Processing incident: {incident_number} ({sys_id})")
        
        # Get MCP Gateway endpoint from environment
        gateway_endpoint = os.environ.get("MCP_GATEWAY_ENDPOINT", "")
        
        # TODO: Load MCP tools from gateway
        # For now, run without tools (will use mock mode)
        mcp_tools = []
        
        # Run orchestrator
        logger.info("Running orchestrator agent")
        result = orchestrate_incident(incident, mcp_tools=mcp_tools)
        
        logger.info(f"Orchestration complete: {result.get('decision', {}).get('outcome')}")
        
        # Store RCA to S3
        bucket_name = os.environ.get("RCA_BUCKET", "incident-rca-bucket")
        storage = RCAStorage(bucket_name=bucket_name)
        
        try:
            s3_uri = storage.store_rca(sys_id, result)
            logger.info(f"RCA stored: {s3_uri}")
        except Exception as e:
            logger.error(f"Failed to store RCA: {str(e)}")
        
        # Update ServiceNow incident based on decision
        snow_client = ServiceNowClient()
        decision = result.get("decision", {})
        outcome = decision.get("outcome", "human_review")
        
        # Build work notes
        classification = result.get("classification", {})
        investigation = result.get("investigation", {})
        
        work_notes = f"""Automated Analysis Complete:

Intent: {classification.get('intent', 'unknown')}
Confidence: {classification.get('confidence', 0.0)}

Root Cause: {investigation.get('root_cause', 'Unable to determine')}

Decision: {outcome}
Reasoning: {decision.get('reasoning', 'N/A')}

Full RCA available at: {s3_uri if 's3_uri' in locals() else 'N/A'}
"""
        
        # Update incident based on outcome
        if outcome == "auto_close":
            logger.info("Auto-closing incident")
            snow_client.close_incident(
                sys_id=sys_id,
                resolution_code="Solved (Permanently)",
                resolution_notes=work_notes
            )
        elif outcome == "auto_retry":
            logger.info("Adding retry notes to incident")
            snow_client.add_work_notes(sys_id, work_notes + "\nAction: Automated retry initiated")
        else:
            # escalate or human_review
            logger.info("Adding analysis notes for human review")
            snow_client.add_work_notes(sys_id, work_notes + "\nRequires human review")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "incident_id": sys_id,
                "incident_number": incident_number,
                "outcome": outcome,
                "rca_stored": 's3_uri' in locals()
            })
        }
        
    except Exception as e:
        logger.error(f"Orchestration failed: {str(e)}", exc_info=True)
        
        # Try to update incident with error
        try:
            sys_id = event.get("incident", {}).get("sys_id")
            if sys_id:
                snow_client = ServiceNowClient()
                snow_client.add_work_notes(
                    sys_id,
                    f"Automated processing failed: {str(e)}\nRequires manual investigation"
                )
        except:
            pass
        
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
