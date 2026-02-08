"""Investigator Agent - gathers evidence using MCP Gateway tools."""
import json
import logging
from typing import Any, Callable

from strands import Agent, tool

from .config import MODEL_ID, INTENT_TOOL_MAPPING, GATEWAY_ENDPOINT
from .schemas import parse_agent_response

logger = logging.getLogger(__name__)

# System prompt for investigation
INVESTIGATION_SYSTEM_PROMPT = """You are an expert AWS data-lake incident investigator. Your role is to gather evidence about incidents using the available diagnostic tools.

## Your Objectives

1. Based on the incident classification, use appropriate tools to gather evidence.
2. Look for error messages, stack traces, and failure indicators.
3. Check data availability and job execution status.
4. Identify the root cause of the issue.
5. Determine if a retry action would be appropriate.

## Available Tools

You have access to log retrieval and data verification tools via the MCP Gateway. Use the `x-amz-bedrock-agentcore-search` header for semantic tool discovery.

### Log Tools
- `get_emr_logs`: Retrieve EMR cluster/step logs
- `get_glue_logs`: Retrieve Glue job run logs
- `get_mwaa_logs`: Retrieve MWAA/Airflow logs
- `get_cloudwatch_alarm`: Get CloudWatch alarm details
- `get_athena_query`: Get Athena query execution details
- `get_s3_logs`: Get S3 access logs

### Data Tools
- `verify_source_data`: Check data availability and validity

## Investigation Strategy

1. Start with the most relevant tool based on the incident intent.
2. Look for error patterns and failure reasons.
3. If data-related, verify source data availability.
4. Gather enough evidence to determine root cause.

## Response Format

After investigation, provide your findings in this JSON format:

```json
{
    "findings": [
        {
            "tool": "<tool_name>",
            "result": {},
            "summary": "<key finding from this tool>"
        }
    ],
    "root_cause": "<identified root cause>",
    "evidence_score": <0.0-1.0>,
    "retry_recommended": <true/false>,
    "recommended_action": "<specific action if retry is recommended>"
}
```

## Evidence Score Guidelines

- **0.8-1.0**: Clear root cause identified with strong evidence
- **0.6-0.8**: Likely root cause with supporting evidence
- **0.4-0.6**: Possible root cause, some uncertainty
- **0.2-0.4**: Weak evidence, multiple possibilities
- **0.0-0.2**: Unable to determine root cause
"""


def create_investigator(tools: list) -> Agent:
    """Create the investigator agent with MCP tools."""
    return Agent(
        model=MODEL_ID,
        system_prompt=INVESTIGATION_SYSTEM_PROMPT,
        tools=tools,
    )


async def investigate(
    intent_result: dict,
    incident: dict,
    mcp_tools: list = None
) -> dict:
    """Investigate an incident based on its classification.
    
    Args:
        intent_result: Result from intent classification
        incident: Original incident data
        mcp_tools: List of MCP tools from Gateway (or mock tools for testing)
        
    Returns:
        Investigation findings with root cause and evidence
    """
    intent = intent_result.get("intent", "unknown")
    confidence = intent_result.get("confidence", 0.0)
    
    # Get recommended tools for this intent
    recommended_tools = INTENT_TOOL_MAPPING.get(intent, [])
    
    # Build investigation prompt with context
    prompt = f"""Investigate the following incident:

**Incident Details**:
- Short Description: {incident.get('short_description', 'N/A')}
- Category: {incident.get('category', 'N/A')}
- Sys ID: {incident.get('sys_id', 'N/A')}

**Classification**:
- Intent: {intent}
- Confidence: {confidence}
- Reasoning: {intent_result.get('reasoning', 'N/A')}

**Recommended Tools**: {', '.join(recommended_tools) if recommended_tools else 'Use semantic search to find appropriate tools'}

**Additional Context from Incident**:
{json.dumps(incident.get('additional_info', {}), indent=2)[:1000]}

Please investigate this incident using the available tools. Start with the recommended tools and gather evidence to identify the root cause. If the incident mentions specific resource IDs (cluster IDs, job names, etc.), use those in your tool calls.
"""

    try:
        # If no MCP tools provided, use mock investigation
        if not mcp_tools:
            logger.warning("No MCP tools provided, using mock investigation")
            return _mock_investigation(intent, incident)
        
        agent = create_investigator(mcp_tools)
        result = agent(prompt)
        response_text = str(result)
        
        # Parse investigation result
        parsed, is_valid, error = parse_agent_response(response_text, "investigation")
        
        if not is_valid:
            logger.warning(f"Investigation validation failed: {error}")
            return {
                "findings": [],
                "root_cause": f"Investigation incomplete: {error}",
                "evidence_score": 0.2,
                "retry_recommended": False,
                "validation_error": error
            }
        
        logger.info(f"Investigation complete. Root cause: {parsed.get('root_cause', 'Unknown')}")
        return parsed
        
    except Exception as e:
        logger.error(f"Investigation error: {str(e)}")
        return {
            "findings": [],
            "root_cause": f"Investigation error: {str(e)}",
            "evidence_score": 0.0,
            "retry_recommended": False,
            "error": str(e)
        }


def _mock_investigation(intent: str, incident: dict) -> dict:
    """Mock investigation for testing without MCP tools."""
    mock_findings = {
        "emr_failure": {
            "findings": [
                {
                    "tool": "get_emr_logs",
                    "result": {"mock": True},
                    "summary": "EMR step failed with OutOfMemoryError"
                }
            ],
            "root_cause": "EMR step exceeded memory allocation",
            "evidence_score": 0.7,
            "retry_recommended": True,
            "recommended_action": "retry_emr with same step configuration"
        },
        "glue_etl_failure": {
            "findings": [
                {
                    "tool": "get_glue_logs",
                    "result": {"mock": True},
                    "summary": "Glue job failed with timeout"
                }
            ],
            "root_cause": "Glue job exceeded timeout threshold",
            "evidence_score": 0.75,
            "retry_recommended": True,
            "recommended_action": "retry_glue_job"
        },
        "data_missing": {
            "findings": [
                {
                    "tool": "verify_source_data",
                    "result": {"mock": True, "verified": False},
                    "summary": "Source data not found at expected path"
                }
            ],
            "root_cause": "Upstream data pipeline did not produce output",
            "evidence_score": 0.8,
            "retry_recommended": False,
            "recommended_action": "Investigate upstream pipeline"
        }
    }
    
    return mock_findings.get(intent, {
        "findings": [],
        "root_cause": "Unable to determine - mock mode",
        "evidence_score": 0.3,
        "retry_recommended": False,
        "recommended_action": ""
    })


def investigate_sync(intent_result: dict, incident: dict, mcp_tools: list = None) -> dict:
    """Synchronous wrapper for investigate."""
    import asyncio
    return asyncio.run(investigate(intent_result, incident, mcp_tools))
