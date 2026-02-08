"""Intent Classifier Agent - classifies incidents using the intent taxonomy."""
import json
import logging
from typing import Any

from strands import Agent

from .config import MODEL_ID, INTENT_TAXONOMY
from .schemas import parse_agent_response, validate_output

logger = logging.getLogger(__name__)


def _get_intent_description(intent: str) -> str:
    """Get description for each intent category."""
    descriptions = {
        "dag_failure": "Airflow DAG execution failed or errored",
        "dag_alarm": "CloudWatch alarm triggered for DAG metrics",
        "mwaa_failure": "MWAA environment or Airflow service failure",
        "glue_etl_failure": "AWS Glue ETL job failure or error",
        "athena_failure": "Athena query execution failure",
        "emr_failure": "EMR cluster or step failure",
        "kafka_events_failed": "Kafka event processing or consumer failure",
        "data_missing": "Expected data not found in target location",
        "source_zero_data": "Source data exists but contains zero records",
        "data_not_available": "Data source not accessible or unreachable",
        "batch_auto_recovery_failed": "Automated batch recovery process failed",
        "access_denied": "Permission or IAM access denied errors",
        "unknown": "Cannot determine specific category"
    }
    return descriptions.get(intent, "Unknown category")


# System prompt for intent classification
INTENT_SYSTEM_PROMPT = f"""You are an expert AWS data-lake incident classifier. Your role is to analyze incident descriptions from ServiceNow and classify them into one of the predefined intent categories.

## Intent Taxonomy

{chr(10).join(f'- **{intent}**: ' + _get_intent_description(intent) for intent in INTENT_TAXONOMY)}

## Instructions

1. Analyze the incident short description and any additional context provided.
2. Identify keywords, error patterns, and indicators that match the intent taxonomy.
3. Assign the most appropriate intent category.
4. Provide a confidence score between 0.0 and 1.0 based on how well the incident matches the category.
5. Include brief reasoning for your classification.

## Response Format

You MUST respond with a valid JSON object in this exact format:

```json
{{
    "intent": "<intent_category>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation of classification>"
}}
```

## Confidence Guidelines

- **0.9-1.0**: Clear, unambiguous match with specific error codes or service names
- **0.7-0.9**: Strong match with good keyword indicators
- **0.5-0.7**: Moderate match, some ambiguity present
- **0.3-0.5**: Weak match, multiple possible categories
- **0.0-0.3**: Very uncertain, defaulting to best guess
"""


def create_intent_classifier() -> Agent:
    """Create the intent classifier agent."""
    return Agent(
        model=MODEL_ID,
        system_prompt=INTENT_SYSTEM_PROMPT,
    )


async def classify_intent(incident: dict) -> dict:
    """Classify an incident into an intent category.
    
    Args:
        incident: Incident data containing short_description and other fields
        
    Returns:
        Classification result with intent, confidence, and reasoning
    """
    agent = create_intent_classifier()
    
    # Build classification prompt
    short_description = incident.get("short_description", "")
    description = incident.get("description", "")
    category = incident.get("category", "")
    subcategory = incident.get("subcategory", "")
    
    prompt = f"""Classify the following incident:

**Short Description**: {short_description}

**Description**: {description[:500] if description else 'N/A'}

**Category**: {category or 'N/A'}
**Subcategory**: {subcategory or 'N/A'}

Analyze this incident and provide your classification in JSON format."""

    try:
        # Run the agent
        result = agent(prompt)
        response_text = str(result)
        
        # Parse and validate response
        parsed, is_valid, error = parse_agent_response(response_text, "intent")
        
        if not is_valid:
            logger.warning(f"Intent classification validation failed: {error}")
            # Return fallback response
            return {
                "intent": "unknown",
                "confidence": 0.1,
                "reasoning": f"Classification failed validation: {error}",
                "validation_error": error
            }
        
        # Ensure intent is in taxonomy
        if parsed.get("intent") not in INTENT_TAXONOMY:
            logger.warning(f"Unknown intent: {parsed.get('intent')}, defaulting to 'unknown'")
            parsed["intent"] = "unknown"
            parsed["confidence"] = min(parsed.get("confidence", 0.5), 0.5)
        
        logger.info(f"Classified incident as '{parsed['intent']}' with confidence {parsed['confidence']}")
        return parsed
        
    except Exception as e:
        logger.error(f"Intent classification error: {str(e)}")
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reasoning": f"Classification error: {str(e)}",
            "error": str(e)
        }


def classify_intent_sync(incident: dict) -> dict:
    """Synchronous wrapper for classify_intent."""
    import asyncio
    return asyncio.run(classify_intent(incident))
