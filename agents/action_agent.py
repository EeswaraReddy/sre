"""Action Agent - executes retry and validation actions."""
import json
import logging
from typing import Any

from strands import Agent

from .config import MODEL_ID
from .schemas import parse_agent_response

logger = logging.getLogger(__name__)

# System prompt for action execution
ACTION_SYSTEM_PROMPT = """You are an AWS data-lake action executor. Your role is to execute remediation actions based on investigation findings.

## Your Objectives

1. Evaluate if an action should be taken based on investigation results.
2. Execute the appropriate retry or validation action.
3. Monitor the result and report success or failure.

## Available Actions

### Retry Actions
- `retry_emr`: Retry a failed EMR step
- `retry_glue_job`: Restart a Glue job
- `retry_airflow_dag`: Trigger a DAG re-run
- `retry_athena_query`: Re-execute an Athena query
- `retry_kafka`: Retry Kafka event processing

### Validation Actions
- `verify_source_data`: Re-verify data availability

## Action Guidelines

1. Only execute actions if the investigation recommends it.
2. Use specific resource IDs from the investigation findings.
3. For retries, ensure the original failure was transient (not a code bug).
4. Do NOT retry if the error indicates a permanent failure (permissions, code bugs).

## Response Format

After action execution, provide results in this JSON format:

```json
{
    "action": "<action_taken or 'none'>",
    "success": <true/false>,
    "details": {
        "resource_id": "<resource that was acted upon>",
        "new_execution_id": "<new job/step ID if applicable>",
        "status": "<current status of retry>"
    },
    "error": "<error message if failed, null otherwise>"
}
```
"""


def create_action_agent(tools: list) -> Agent:
    """Create the action agent with retry tools."""
    return Agent(
        model=MODEL_ID,
        system_prompt=ACTION_SYSTEM_PROMPT,
        tools=tools,
    )


async def execute_action(
    investigation: dict,
    incident: dict,
    mcp_tools: list = None
) -> dict:
    """Execute remediation actions based on investigation.
    
    Args:
        investigation: Investigation findings including recommended action
        incident: Original incident data
        mcp_tools: List of MCP tools from Gateway
        
    Returns:
        Action execution result
    """
    retry_recommended = investigation.get("retry_recommended", False)
    recommended_action = investigation.get("recommended_action", "")
    root_cause = investigation.get("root_cause", "")
    
    # Check if action should be taken
    if not retry_recommended:
        logger.info("No action recommended by investigation")
        return {
            "action": "none",
            "success": True,
            "details": {"reason": "No action recommended"},
            "error": None
        }
    
    # Check for permanent failure indicators
    permanent_failure_indicators = [
        "permission denied", "access denied", "authorization",
        "syntax error", "compilation error", "code bug",
        "schema mismatch", "invalid configuration"
    ]
    
    if any(indicator in root_cause.lower() for indicator in permanent_failure_indicators):
        logger.info(f"Permanent failure detected, skipping action: {root_cause}")
        return {
            "action": "none",
            "success": True,
            "details": {
                "reason": "Permanent failure detected, action would not help",
                "root_cause": root_cause
            },
            "error": None
        }
    
    # Build action prompt
    prompt = f"""Execute the recommended action for this incident:

**Root Cause**: {root_cause}

**Recommended Action**: {recommended_action}

**Investigation Findings**:
{json.dumps(investigation.get('findings', []), indent=2)[:2000]}

**Incident Info**:
- Sys ID: {incident.get('sys_id', 'N/A')}
- Description: {incident.get('short_description', 'N/A')}

Execute the appropriate action tool with the correct parameters based on the investigation findings. If the findings include specific resource IDs (cluster_id, job_name, etc.), use those.
"""

    try:
        if not mcp_tools:
            logger.warning("No MCP tools provided, using mock action")
            return _mock_action(recommended_action, investigation)
        
        agent = create_action_agent(mcp_tools)
        result = agent(prompt)
        response_text = str(result)
        
        # Parse action result
        parsed, is_valid, error = parse_agent_response(response_text, "action")
        
        if not is_valid:
            logger.warning(f"Action validation failed: {error}")
            return {
                "action": "validation_failed",
                "success": False,
                "details": {},
                "error": error
            }
        
        logger.info(f"Action executed: {parsed.get('action')}, success: {parsed.get('success')}")
        return parsed
        
    except Exception as e:
        logger.error(f"Action execution error: {str(e)}")
        return {
            "action": "error",
            "success": False,
            "details": {},
            "error": str(e)
        }


def _mock_action(recommended_action: str, investigation: dict) -> dict:
    """Mock action execution for testing."""
    action_map = {
        "retry_emr": {
            "action": "retry_emr",
            "success": True,
            "details": {
                "resource_id": "j-MOCKCLUSTER",
                "new_execution_id": "s-MOCKNEWSTEP",
                "status": "PENDING"
            },
            "error": None
        },
        "retry_glue_job": {
            "action": "retry_glue_job",
            "success": True,
            "details": {
                "resource_id": "mock-glue-job",
                "new_execution_id": "jr_mock123",
                "status": "RUNNING"
            },
            "error": None
        },
        "retry_airflow_dag": {
            "action": "retry_airflow_dag",
            "success": True,
            "details": {
                "resource_id": "mock_dag",
                "new_execution_id": "manual__2024-01-15T00:00:00+00:00",
                "status": "queued"
            },
            "error": None
        }
    }
    
    # Try to match recommended action
    for action_key, mock_result in action_map.items():
        if action_key in recommended_action.lower():
            return mock_result
    
    return {
        "action": "none",
        "success": True,
        "details": {"reason": "No matching action found in mock mode"},
        "error": None
    }


def execute_action_sync(investigation: dict, incident: dict, mcp_tools: list = None) -> dict:
    """Synchronous wrapper for execute_action."""
    import asyncio
    return asyncio.run(execute_action(investigation, incident, mcp_tools))
