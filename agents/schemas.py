"""JSON Schema validation for agent outputs."""
import json
from typing import Any
import logging

logger = logging.getLogger(__name__)

# Schema definitions
SCHEMAS = {
    "intent": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"}
        },
        "required": ["intent", "confidence"]
    },
    "investigation": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string"},
                        "result": {"type": "object"},
                        "summary": {"type": "string"}
                    }
                }
            },
            "root_cause": {"type": "string"},
            "evidence_score": {"type": "number", "minimum": 0, "maximum": 1},
            "retry_recommended": {"type": "boolean"},
            "recommended_action": {"type": "string"}
        },
        "required": ["findings", "root_cause", "evidence_score"]
    },
    "action": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "success": {"type": "boolean"},
            "details": {"type": "object"},
            "error": {"type": "string"}
        },
        "required": ["action", "success"]
    },
    "orchestrator": {
        "type": "object",
        "properties": {
            "incident_id": {"type": "string"},
            "intent": {"type": "string"},
            "confidence": {"type": "number"},
            "decision": {
                "type": "string",
                "enum": ["auto_close", "auto_retry", "escalate", "human_review"]
            },
            "score": {"type": "number"},
            "rca": {"type": "object"},
            "actions_taken": {
                "type": "array",
                "items": {"type": "object"}
            }
        },
        "required": ["incident_id", "intent", "decision"]
    }
}


def validate_output(data: Any, schema_name: str) -> tuple[bool, str]:
    """Validate data against a named schema.
    
    Args:
        data: The data to validate
        schema_name: Name of the schema to validate against
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if schema_name not in SCHEMAS:
        return False, f"Unknown schema: {schema_name}"
    
    schema = SCHEMAS[schema_name]
    
    try:
        # Try to use jsonschema if available
        import jsonschema
        jsonschema.validate(data, schema)
        return True, ""
    except ImportError:
        # Fallback to basic validation
        return _basic_validate(data, schema, schema_name)
    except jsonschema.ValidationError as e:
        error_msg = f"Schema validation failed for {schema_name}: {e.message}"
        logger.warning(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Validation error for {schema_name}: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def _basic_validate(data: Any, schema: dict, schema_name: str) -> tuple[bool, str]:
    """Basic schema validation without jsonschema library."""
    if not isinstance(data, dict):
        return False, f"{schema_name}: Expected object, got {type(data).__name__}"
    
    # Check required fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            return False, f"{schema_name}: Missing required field '{field}'"
    
    # Basic type checks for properties
    properties = schema.get("properties", {})
    for field, field_schema in properties.items():
        if field not in data:
            continue
            
        value = data[field]
        expected_type = field_schema.get("type")
        
        if expected_type == "string" and not isinstance(value, str):
            return False, f"{schema_name}.{field}: Expected string"
        elif expected_type == "number" and not isinstance(value, (int, float)):
            return False, f"{schema_name}.{field}: Expected number"
        elif expected_type == "boolean" and not isinstance(value, bool):
            return False, f"{schema_name}.{field}: Expected boolean"
        elif expected_type == "array" and not isinstance(value, list):
            return False, f"{schema_name}.{field}: Expected array"
        elif expected_type == "object" and not isinstance(value, dict):
            return False, f"{schema_name}.{field}: Expected object"
        
        # Check enum values
        if "enum" in field_schema and value not in field_schema["enum"]:
            return False, f"{schema_name}.{field}: Value must be one of {field_schema['enum']}"
        
        # Check number ranges
        if expected_type == "number":
            if "minimum" in field_schema and value < field_schema["minimum"]:
                return False, f"{schema_name}.{field}: Value must be >= {field_schema['minimum']}"
            if "maximum" in field_schema and value > field_schema["maximum"]:
                return False, f"{schema_name}.{field}: Value must be <= {field_schema['maximum']}"
    
    return True, ""


def parse_agent_response(response: str, schema_name: str) -> tuple[dict, bool, str]:
    """Parse agent response and validate against schema.
    
    Args:
        response: Raw agent response string
        schema_name: Schema to validate against
        
    Returns:
        Tuple of (parsed_data, is_valid, error_message)
    """
    # Try to extract JSON from response
    try:
        # Look for JSON in code blocks
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            json_str = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            json_str = response[start:end].strip()
        elif "{" in response:
            # Try to find JSON object
            start = response.find("{")
            end = response.rfind("}") + 1
            json_str = response[start:end]
        else:
            return {}, False, "No JSON found in response"
        
        data = json.loads(json_str)
        is_valid, error = validate_output(data, schema_name)
        return data, is_valid, error
        
    except json.JSONDecodeError as e:
        return {}, False, f"JSON parse error: {str(e)}"
    except Exception as e:
        return {}, False, f"Parse error: {str(e)}"
