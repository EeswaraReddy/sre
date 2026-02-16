"""Main Orchestrator - BedrockAgentCoreApp handler entrypoint."""
import json
import logging
import os
import boto3
from datetime import datetime
from typing import Any

# Configure logging
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Import agent components
from .intent_classifier import classify_intent
from .investigator import investigate
from .action_agent import execute_action
from .policy_engine import apply_policy, build_rca
from .schemas import validate_output
from .config import RCA_BUCKET, RCA_PREFIX, METRICS_NAMESPACE

# Initialize AWS clients
s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")


# BedrockAgentCoreApp decorator setup
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    app = BedrockAgentCoreApp()
except ImportError:
    try:
        # Fallback: try strands-agents package
        from strands.agent.bedrock import BedrockAgentCoreApp
        app = BedrockAgentCoreApp()
    except ImportError:
        # Fallback for local testing without AgentCore SDK
        logger.warning("BedrockAgentCoreApp not available, using mock decorator for local testing")
        class MockApp:
            def handler(self, func):
                return func
        app = MockApp()


def emit_metric(metric_name: str, value: float = 1.0, dimensions: dict = None, unit: str = "Count"):
    """Emit a CloudWatch metric."""
    try:
        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.utcnow()
        }
        if dimensions:
            metric_data["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]
        
        cloudwatch.put_metric_data(
            Namespace=METRICS_NAMESPACE,
            MetricData=[metric_data]
        )
    except Exception as e:
        logger.warning(f"Failed to emit metric {metric_name}: {e}")


def store_rca_to_s3(sys_id: str, rca: dict) -> str:
    """Store RCA document to S3.
    
    Args:
        sys_id: Incident sys_id
        rca: RCA document
        
    Returns:
        S3 URI of stored RCA
    """
    if not RCA_BUCKET:
        logger.warning("RCA_BUCKET not configured, skipping S3 storage")
        return ""
    
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        key = f"{RCA_PREFIX}{sys_id}/{timestamp}_rca.json"
        
        s3.put_object(
            Bucket=RCA_BUCKET,
            Key=key,
            Body=json.dumps(rca, indent=2, default=str),
            ContentType="application/json",
            Metadata={
                "incident-id": sys_id,
                "generated-by": "incident-handler-orchestrator",
                "decision": rca.get("decision", {}).get("outcome", "unknown")
            }
        )
        
        s3_uri = f"s3://{RCA_BUCKET}/{key}"
        logger.info(f"RCA stored at {s3_uri}")
        return s3_uri
        
    except Exception as e:
        logger.error(f"Failed to store RCA: {e}")
        return ""


@app.handler
async def handler(event: dict, context: dict) -> dict:
    """Main orchestrator handler for Bedrock AgentCore Runtime.
    
    This is the entrypoint for the multi-agent incident handler.
    It orchestrates the flow through:
    1. Intent classification
    2. Investigation
    3. Action execution
    4. Policy decision
    5. RCA storage and ServiceNow update
    
    Args:
        event: Contains incident payload from ServiceNow
        context: AgentCore runtime context
        
    Returns:
        Final decision and RCA
    """
    start_time = datetime.utcnow()
    
    # Extract incident from event
    incident = event.get("incident", event)
    sys_id = incident.get("sys_id", "unknown")
    
    logger.info(f"Processing incident {sys_id}: {incident.get('short_description', 'N/A')}")
    emit_metric("Invocations", dimensions={"Agent": "Orchestrator"})
    
    result = {
        "incident_id": sys_id,
        "timestamp": start_time.isoformat(),
        "stages": {}
    }
    
    try:
        # ============ STAGE 1: INTENT CLASSIFICATION ============
        logger.info("Stage 1: Intent Classification")
        emit_metric("Invocations", dimensions={"Agent": "IntentClassifier"})
        
        intent_result = await classify_intent(incident)
        result["stages"]["intent"] = intent_result
        
        # Validate intent output
        is_valid, error = validate_output(intent_result, "intent")
        if not is_valid:
            logger.warning(f"Intent validation failed: {error}")
            emit_metric("Failure", dimensions={"Schema": "intent"})
            return _human_review_response(sys_id, f"Intent validation failed: {error}", result)
        
        emit_metric("Classification", dimensions={"Intent": intent_result.get("intent", "unknown")})
        emit_metric("Confidence", value=intent_result.get("confidence", 0.0), unit="None")
        
        # Check for low confidence
        if intent_result.get("confidence", 0.0) < 0.3:
            emit_metric("LowConfidence", dimensions={"Intent": intent_result.get("intent", "unknown")})
        
        # ============ STAGE 2: INVESTIGATION ============
        logger.info("Stage 2: Investigation")
        emit_metric("Invocations", dimensions={"Agent": "Investigator"})
        
        # Get MCP tools from context (provided by AgentCore Gateway)
        mcp_tools = context.get("mcp_tools", [])
        
        investigation = await investigate(intent_result, incident, mcp_tools)
        result["stages"]["investigation"] = investigation
        
        # Validate investigation output
        is_valid, error = validate_output(investigation, "investigation")
        if not is_valid:
            logger.warning(f"Investigation validation failed: {error}")
            emit_metric("Failure", dimensions={"Schema": "investigation"})
            return _human_review_response(sys_id, f"Investigation validation failed: {error}", result)
        
        # ============ STAGE 3: ACTION EXECUTION ============
        logger.info("Stage 3: Action Execution")
        emit_metric("Invocations", dimensions={"Agent": "ActionAgent"})
        
        action_result = await execute_action(investigation, incident, mcp_tools)
        result["stages"]["action"] = action_result
        
        # Validate action output
        is_valid, error = validate_output(action_result, "action")
        if not is_valid:
            logger.warning(f"Action validation failed: {error}")
            emit_metric("Failure", dimensions={"Schema": "action"})
            return _human_review_response(sys_id, f"Action validation failed: {error}", result)
        
        # ============ STAGE 4: POLICY DECISION ============
        logger.info("Stage 4: Policy Decision")
        
        policy_result = apply_policy(intent_result, investigation, action_result)
        result["stages"]["policy"] = policy_result
        
        # Emit policy metrics
        emit_metric("Decision", dimensions={"Outcome": policy_result.get("decision", "unknown")})
        if policy_result.get("override_applied"):
            emit_metric("Override", dimensions={"Type": policy_result.get("override_type", "unknown")})
        
        # ============ STAGE 5: BUILD AND STORE RCA ============
        logger.info("Stage 5: RCA Storage")
        
        rca = build_rca(incident, intent_result, investigation, action_result, policy_result)
        rca["processing_time_ms"] = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        rca_uri = store_rca_to_s3(sys_id, rca)
        result["rca_uri"] = rca_uri
        
        # ============ STAGE 6: UPDATE SERVICENOW (if credentials available) ============
        servicenow_creds = event.get("servicenow_credentials") or context.get("servicenow_credentials")
        
        if servicenow_creds and mcp_tools:
            logger.info("Stage 6: ServiceNow Update")
            # Find the update_servicenow_ticket tool
            sn_tool = next((t for t in mcp_tools if "servicenow" in t.__name__.lower()), None)
            if sn_tool:
                try:
                    sn_update = await sn_tool({
                        "sys_id": sys_id,
                        "status": _decision_to_status(policy_result.get("decision")),
                        "rca": rca,
                        "work_notes": f"Automated analysis complete. Decision: {policy_result.get('decision')}"
                    })
                    result["servicenow_update"] = sn_update
                except Exception as e:
                    logger.error(f"ServiceNow update failed: {e}")
                    result["servicenow_update"] = {"success": False, "error": str(e)}
        
        # ============ BUILD FINAL RESPONSE ============
        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        emit_metric("Latency", value=processing_time, dimensions={"Agent": "Orchestrator"}, unit="Milliseconds")
        
        final_response = {
            "incident_id": sys_id,
            "intent": intent_result.get("intent"),
            "confidence": intent_result.get("confidence"),
            "decision": policy_result.get("decision"),
            "score": policy_result.get("score"),
            "reasoning": policy_result.get("reasoning"),
            "rca_uri": rca_uri,
            "actions_taken": [action_result] if action_result.get("action") != "none" else [],
            "processing_time_ms": processing_time
        }
        
        # Validate final output
        is_valid, error = validate_output(final_response, "orchestrator")
        if not is_valid:
            logger.warning(f"Orchestrator output validation failed: {error}")
            emit_metric("Failure", dimensions={"Schema": "orchestrator"})
            final_response["validation_warning"] = error
        
        logger.info(f"Incident {sys_id} processed. Decision: {final_response['decision']}")
        return final_response
        
    except Exception as e:
        logger.error(f"Orchestrator error for {sys_id}: {str(e)}", exc_info=True)
        emit_metric("Error", dimensions={"Agent": "Orchestrator"})
        
        return {
            "incident_id": sys_id,
            "intent": result.get("stages", {}).get("intent", {}).get("intent", "unknown"),
            "confidence": 0.0,
            "decision": "human_review",
            "score": 0.0,
            "reasoning": f"Processing error: {str(e)}",
            "error": str(e),
            "partial_results": result
        }


def _human_review_response(sys_id: str, reason: str, partial_results: dict) -> dict:
    """Build a human review response for validation failures."""
    return {
        "incident_id": sys_id,
        "intent": partial_results.get("stages", {}).get("intent", {}).get("intent", "unknown"),
        "confidence": 0.0,
        "decision": "human_review",
        "score": 0.0,
        "reasoning": reason,
        "partial_results": partial_results
    }


def _decision_to_status(decision: str) -> str:
    """Map policy decision to ServiceNow status."""
    mapping = {
        "auto_close": "resolved",
        "auto_retry": "in_progress",
        "escalate": "escalated",
        "human_review": "on_hold"
    }
    return mapping.get(decision, "in_progress")


# Synchronous wrapper for testing
def handler_sync(event: dict, context: dict = None) -> dict:
    """Synchronous handler for local testing."""
    import asyncio
    return asyncio.run(handler(event, context or {}))


if __name__ == "__main__":
    # Test with sample incident
    sample_incident = {
        "incident": {
            "sys_id": "TEST123",
            "short_description": "Glue job 'etl-daily-load' failed with OutOfMemory error",
            "category": "Data Pipeline",
            "subcategory": "ETL"
        }
    }
    
    result = handler_sync(sample_incident)
    print(json.dumps(result, indent=2, default=str))
