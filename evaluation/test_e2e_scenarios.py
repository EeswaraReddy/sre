#!/usr/bin/env python3
"""
End-to-end test scenarios using AgentCore Runtime with Bedrock.

Uses strands Agent() class with native strands agents as tools.
Each specialized agent (intent classifier, investigator, action agent) 
is exposed as a tool that the orchestrator agent can invoke.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strands import Agent, tool

# Try to import BedrockModel, fall back to mock if unavailable
try:
    from strands.models.bedrock import BedrockModel
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False

# Configuration
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"

# Import configuration and policy engine
from agents.config import INTENT_TAXONOMY, POLICY_OVERRIDES, POLICY_THRESHOLDS


# ============================================================
# MOCK RESPONSES FOR TESTING WITHOUT AWS
# ============================================================

MOCK_INTENT_RESPONSES = {
    "dag": {"intent": "dag_failure", "confidence": 0.85, "reasoning": "DAG and EMR failure indicators detected"},
    "emr": {"intent": "emr_failure", "confidence": 0.90, "reasoning": "EMR cluster step failure identified"},
    "access": {"intent": "access_denied", "confidence": 0.92, "reasoning": "Access request pattern detected"},
    "default": {"intent": "unknown", "confidence": 0.50, "reasoning": "Unable to classify with confidence"}
}

MOCK_INVESTIGATION_RESPONSES = {
    "zero_byte": {
        "findings": [
            {"tool": "get_emr_logs", "result": {"status": "FAILED"}, "summary": "EMR step failed - zero byte source"},
            {"tool": "verify_source_data", "result": {"verified": False, "empty_files": 1}, "summary": "Source has zero bytes"}
        ],
        "root_cause": "Source data file has zero bytes. Upstream system did not produce valid data.",
        "evidence_score": 0.95,
        "retry_recommended": False,
        "recommended_action": "Notify upstream team"
    },
    "access_request": {
        "findings": [{"tool": "get_cloudwatch_alarm", "result": {"alarms": []}, "summary": "No alarms - access request"}],
        "root_cause": "This is an access request, not an incident.",
        "evidence_score": 0.85,
        "retry_recommended": False,
        "recommended_action": "Redirect to work reception process"
    },
    "default": {
        "findings": [],
        "root_cause": "Unable to determine root cause",
        "evidence_score": 0.30,
        "retry_recommended": False,
        "recommended_action": "human_review"
    }
}


class MockAgent:
    """Mock agent for testing without AWS credentials."""
    
    def __init__(self, response_type: str = "default"):
        self.response_type = response_type
    
    def __call__(self, prompt: str) -> str:
        return json.dumps(self._get_response(prompt))
    
    def _get_response(self, prompt: str) -> dict:
        prompt_lower = prompt.lower()
        if "classify" in prompt_lower:
            if "dag" in prompt_lower or "emr" in prompt_lower:
                return MOCK_INTENT_RESPONSES["dag"]
            elif "access" in prompt_lower:
                return MOCK_INTENT_RESPONSES["access"]
            return MOCK_INTENT_RESPONSES["default"]
        elif "investigate" in prompt_lower:
            if "zero byte" in prompt_lower or "emr" in prompt_lower:
                return MOCK_INVESTIGATION_RESPONSES["zero_byte"]
            elif "access" in prompt_lower:
                return MOCK_INVESTIGATION_RESPONSES["access_request"]
            return MOCK_INVESTIGATION_RESPONSES["default"]
        elif "remediation" in prompt_lower or "action" in prompt_lower:
            return {"action": "none", "success": True, "details": {"mock": True}, "error": None}
        return {"result": "mock response"}


# ============================================================
# SPECIALIZED AGENTS AS TOOLS
# ============================================================

def create_agent(system_prompt: str, tools: list = None) -> Agent:
    """Create an agent - uses Bedrock if available, otherwise mock."""
    if MOCK_MODE or not BEDROCK_AVAILABLE:
        print("   [MOCK MODE] Using mock agent")
        return MockAgent()
    
    try:
        model = BedrockModel(model_id=MODEL_ID, region_name=AWS_REGION)
        return Agent(model=model, system_prompt=system_prompt, tools=tools or [])
    except Exception as e:
        print(f"   [FALLBACK] Bedrock unavailable ({e}), using mock agent")
        return MockAgent()


# Create specialized agents (lazy initialization)
_intent_classifier_agent = None
_investigator_agent = None
_action_agent = None


def get_intent_classifier():
    global _intent_classifier_agent
    if _intent_classifier_agent is None:
        _intent_classifier_agent = create_agent(
            f"""You are an expert AWS data-lake incident classifier.
Classify incidents into one of: {', '.join(INTENT_TAXONOMY)}

Respond with JSON: {{"intent": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""
        )
    return _intent_classifier_agent


def get_investigator():
    global _investigator_agent
    if _investigator_agent is None:
        _investigator_agent = create_agent(
            """You are an AWS data-lake incident investigator.
Analyze incidents and gather evidence about root causes.

Respond with JSON: {"findings": [...], "root_cause": "...", "evidence_score": 0.0-1.0, "retry_recommended": bool, "recommended_action": "..."}"""
        )
    return _investigator_agent


def get_action_agent():
    global _action_agent  
    if _action_agent is None:
        _action_agent = create_agent(
            """You are an AWS data-lake action executor.
Respond with JSON: {"action": "...", "success": bool, "details": {...}, "error": null}"""
        )
    return _action_agent


# ============================================================
# AGENT TOOLS - Strands Agents as callable tools
# ============================================================

@tool
def classify_incident(incident_description: str, incident_category: str = "") -> dict:
    """
    Classify an incident into an intent category using the Intent Classifier Agent.
    
    Args:
        incident_description: The incident short description and details
        incident_category: Optional category from ServiceNow
        
    Returns:
        Classification result with intent, confidence, and reasoning
    """
    prompt = f"""Classify this incident:

Description: {incident_description}
Category: {incident_category or 'N/A'}

Provide your classification in JSON format."""
    
    try:
        result = get_intent_classifier()(prompt)
        # Parse JSON from response
        response_text = str(result)
        return _extract_json(response_text, default={
            "intent": "unknown",
            "confidence": 0.5,
            "reasoning": response_text[:200]
        })
    except Exception as e:
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reasoning": f"Classification error: {str(e)}",
            "error": str(e)
        }


@tool
def investigate_incident(
    incident_description: str,
    intent: str,
    additional_context: str = ""
) -> dict:
    """
    Investigate an incident using the Investigator Agent.
    Gathers evidence and determines root cause.
    
    Args:
        incident_description: The incident details
        intent: The classified intent from classify_incident
        additional_context: Any additional information (cluster IDs, paths, etc.)
        
    Returns:
        Investigation results with findings, root_cause, and evidence_score
    """
    prompt = f"""Investigate this {intent} incident:

Description: {incident_description}
Context: {additional_context or 'N/A'}

Gather evidence and determine the root cause. Respond in JSON format."""
    
    try:
        result = get_investigator()(prompt)
        response_text = str(result)
        return _extract_json(response_text, default={
            "findings": [],
            "root_cause": "Unable to determine",
            "evidence_score": 0.3,
            "retry_recommended": False,
            "recommended_action": "human_review"
        })
    except Exception as e:
        return {
            "findings": [],
            "root_cause": f"Investigation error: {str(e)}",
            "evidence_score": 0.0,
            "retry_recommended": False,
            "error": str(e)
        }


@tool
def execute_remediation(
    investigation_summary: str,
    recommended_action: str,
    incident_details: str
) -> dict:
    """
    Execute remediation action using the Action Agent.
    
    Args:
        investigation_summary: Summary of the investigation findings
        recommended_action: The recommended action from investigation
        incident_details: Original incident details for context
        
    Returns:
        Action result with action taken, success status, and details
    """
    prompt = f"""Execute remediation for this incident:

Investigation: {investigation_summary}
Recommended Action: {recommended_action}
Incident: {incident_details}

Determine if action should be taken and respond in JSON format."""
    
    try:
        result = get_action_agent()(prompt)
        response_text = str(result)
        return _extract_json(response_text, default={
            "action": "none",
            "success": True,
            "details": {"reason": "Could not determine action"},
            "error": None
        })
    except Exception as e:
        return {
            "action": "none",
            "success": False,
            "details": {},
            "error": str(e)
        }


@tool
def apply_policy_decision(
    intent: str,
    confidence: float,
    evidence_score: float,
    action_success: bool
) -> dict:
    """
    Apply policy rules to determine final decision.
    
    Args:
        intent: The classified intent
        confidence: Intent classification confidence (0.0-1.0)
        evidence_score: Evidence quality from investigation (0.0-1.0)
        action_success: Whether the remediation action succeeded
        
    Returns:
        Policy decision with outcome and reasoning
    """
    # Check for policy overrides
    if intent in POLICY_OVERRIDES:
        return {
            "decision": POLICY_OVERRIDES[intent],
            "score": confidence * evidence_score,
            "reasoning": f"Policy override: {intent} always results in {POLICY_OVERRIDES[intent]}",
            "override_applied": True,
            "override_type": intent
        }
    
    # Calculate combined score
    combined_score = (
        confidence * 0.4 +
        evidence_score * 0.4 +
        (0.2 if action_success else 0.0)
    )
    
    # Determine decision based on thresholds
    if combined_score >= POLICY_THRESHOLDS["auto_close"]:
        decision = "auto_close"
        reasoning = f"High confidence ({combined_score:.2f}), auto-closing"
    elif combined_score >= POLICY_THRESHOLDS["auto_retry"]:
        decision = "auto_retry"
        reasoning = f"Medium confidence ({combined_score:.2f}), attempting retry"
    elif combined_score >= POLICY_THRESHOLDS["escalate"]:
        decision = "escalate"
        reasoning = f"Low confidence ({combined_score:.2f}), escalating"
    else:
        decision = "human_review"
        reasoning = f"Very low confidence ({combined_score:.2f}), requires human review"
    
    return {
        "decision": decision,
        "score": round(combined_score, 3),
        "reasoning": reasoning,
        "override_applied": False
    }


@tool
def build_rca_document(
    incident_id: str,
    incident_description: str,
    classification: dict,
    investigation: dict,
    action: dict,
    policy: dict
) -> dict:
    """
    Build the Root Cause Analysis document.
    
    Args:
        incident_id: ServiceNow incident ID
        incident_description: Original incident description
        classification: Intent classification result
        investigation: Investigation findings
        action: Action execution result
        policy: Policy decision
        
    Returns:
        Complete RCA document
    """
    return {
        "incident": {
            "id": incident_id,
            "description": incident_description
        },
        "classification": {
            "intent": classification.get("intent"),
            "confidence": classification.get("confidence"),
            "reasoning": classification.get("reasoning")
        },
        "investigation": {
            "findings_count": len(investigation.get("findings", [])),
            "root_cause": investigation.get("root_cause"),
            "evidence_score": investigation.get("evidence_score")
        },
        "remediation": {
            "action": action.get("action"),
            "success": action.get("success")
        },
        "decision": {
            "outcome": policy.get("decision"),
            "score": policy.get("score"),
            "reasoning": policy.get("reasoning"),
            "override_applied": policy.get("override_applied", False)
        }
    }


def _extract_json(text: str, default: dict) -> dict:
    """Extract JSON from text response."""
    import re
    try:
        # Try direct parse
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON block in markdown
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find raw JSON object
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return default


# ============================================================
# ORCHESTRATOR AGENT - Uses other agents as tools
# ============================================================

_orchestrator_agent = None

def get_orchestrator_agent():
    """Get the orchestrator agent - uses Bedrock if available, mock fallback."""
    global _orchestrator_agent
    if _orchestrator_agent is not None:
        return _orchestrator_agent
    
    # Tools for the orchestrator
    tools = [
        classify_incident,
        investigate_incident,
        execute_remediation,
        apply_policy_decision,
        build_rca_document
    ]
    
    system_prompt = """You are an AWS data-lake incident handler orchestrator.
You coordinate the end-to-end incident resolution process using specialized tools.

## Workflow
1. Use classify_incident to determine the incident type
2. Use investigate_incident to gather evidence and find root cause  
3. Use execute_remediation if action is needed
4. Use apply_policy_decision to determine the final outcome
5. Use build_rca_document to create the final RCA

Always follow this workflow and return a comprehensive summary."""
    
    if MOCK_MODE or not BEDROCK_AVAILABLE:
        print("   [MOCK MODE] Using mock orchestrator agent")
        _orchestrator_agent = MockOrchestratorAgent(tools)
    else:
        try:
            model = BedrockModel(model_id=MODEL_ID, region_name=AWS_REGION)
            _orchestrator_agent = Agent(model=model, tools=tools, system_prompt=system_prompt)
        except Exception as e:
            print(f"   [FALLBACK] Bedrock unavailable ({e}), using mock orchestrator")
            _orchestrator_agent = MockOrchestratorAgent(tools)
    
    return _orchestrator_agent


class MockOrchestratorAgent:
    """Mock orchestrator that calls tools directly in sequence."""
    
    def __init__(self, tools: list):
        self.tools = {t.__name__: t for t in tools}
    
    def __call__(self, prompt: str) -> str:
        """Execute the full workflow using the tools."""
        results = {}
        
        # Extract incident details from prompt
        prompt_lower = prompt.lower()
        
        # Step 1: Classification
        classification = self.tools['classify_incident'](
            incident_description=prompt[:500],
            incident_category=""
        )
        results['classification'] = classification
        
        # Step 2: Investigation  
        investigation = self.tools['investigate_incident'](
            incident_description=prompt[:500],
            intent=classification.get('intent', 'unknown'),
            additional_context=""
        )
        results['investigation'] = investigation
        
        # Step 3: Remediation
        remediation = self.tools['execute_remediation'](
            investigation_summary=investigation.get('root_cause', ''),
            recommended_action=investigation.get('recommended_action', ''),
            incident_details=prompt[:300]
        )
        results['remediation'] = remediation
        
        # Step 4: Policy Decision
        policy = self.tools['apply_policy_decision'](
            intent=classification.get('intent', 'unknown'),
            confidence=classification.get('confidence', 0.5),
            evidence_score=investigation.get('evidence_score', 0.5),
            action_success=remediation.get('success', False)
        )
        results['policy'] = policy
        
        # Step 5: Build RCA
        # Extract incident_id from prompt if present
        import re
        id_match = re.search(r'Incident ID:\s*(\S+)', prompt)
        incident_id = id_match.group(1) if id_match else "UNKNOWN"
        
        rca = self.tools['build_rca_document'](
            incident_id=incident_id,
            incident_description=prompt[:500],
            classification=classification,
            investigation=investigation,
            action=remediation,
            policy=policy
        )
        results['rca'] = rca
        
        # Format response
        return f"""## Incident Analysis Complete

**Classification**: {classification.get('intent')} (confidence: {classification.get('confidence')})
**Root Cause**: {investigation.get('root_cause')}
**Evidence Score**: {investigation.get('evidence_score')}
**Decision**: {policy.get('decision')} (score: {policy.get('score')})
**Reasoning**: {policy.get('reasoning')}

### RCA Summary
{json.dumps(rca, indent=2)}
"""


# ============================================================
# TEST SCENARIOS
# ============================================================

SCENARIO_1_INCIDENT = {
    "sys_id": "INC0010001",
    "short_description": "DAG 'daily_etl_pipeline' failed - EMR step error, data source issue",
    "description": """
        The daily ETL pipeline DAG failed during execution.
        EMR cluster j-ABCD1234 step 's-5678EFGH' failed with error.
        Logs indicate: ERROR source file s3://data-lake-raw/transactions/dt=2024-01-15/ has zero bytes.
        Downstream processing cannot continue.
    """,
    "category": "Data Pipeline",
    "subcategory": "ETL",
    "priority": "2",
    "additional_info": {
        "dag_id": "daily_etl_pipeline",
        "cluster_id": "j-ABCD1234",
        "step_id": "s-5678EFGH",
        "s3_source_path": "s3://data-lake-raw/transactions/dt=2024-01-15/"
    }
}

SCENARIO_2_INCIDENT = {
    "sys_id": "INC0010002",
    "short_description": "I need access to production table customer_data in Athena",
    "description": """
        Hi Team,
        I need read access to the production table 'customer_data' in database 'prod_analytics'.
        This is for a new dashboard I'm building.
        Please grant me SELECT permissions.
        Thanks!
    """,
    "category": "Access Request",
    "subcategory": "Database",
    "priority": "3",
    "additional_info": {
        "requested_by": "john.doe@company.com",
        "table_name": "customer_data",
        "database": "prod_analytics",
        "access_type": "SELECT"
    }
}


def run_scenario_1():
    """Run Scenario 1: DAG Failed - Source Zero Byte using orchestrator agent."""
    print("\n" + "="*70)
    print("SCENARIO 1: DAG Failed with EMR Jobs - Source Zero Byte")
    print("Using: AgentCore Runtime + Strands Agents as Tools")
    print("="*70)
    
    incident = SCENARIO_1_INCIDENT
    print(f"\n📋 Incident: {incident['short_description']}")
    print(f"   Sys ID: {incident['sys_id']}")
    
    # Build the prompt for the orchestrator
    prompt = f"""Process this ServiceNow incident:

Incident ID: {incident['sys_id']}
Short Description: {incident['short_description']}
Description: {incident['description']}
Category: {incident['category']}
Additional Info: {json.dumps(incident['additional_info'], indent=2)}

Follow the complete incident handling workflow:
1. Classify the incident intent
2. Investigate to find the root cause
3. Determine if remediation action is needed
4. Apply policy rules
5. Build the RCA document

Provide a complete analysis."""
    
    print("\n🤖 Running orchestrator agent with strands Agent tools...")
    
    try:
        result = get_orchestrator_agent()(prompt)
        response_text = str(result)
        
        print(f"\n📊 Agent Response:")
        print("-" * 50)
        # Truncate for display
        print(response_text[:1500] + "..." if len(response_text) > 1500 else response_text)
        print("-" * 50)
        
        # Validation
        print("\n" + "-"*50)
        print("VALIDATION:")
        
        # Check if key terms appear in response (indicates proper flow)
        flow_indicators = [
            ("classification" in response_text.lower() or "classify" in response_text.lower(), "Classification step"),
            ("investigation" in response_text.lower() or "investigate" in response_text.lower(), "Investigation step"),
            ("zero byte" in response_text.lower() or "empty" in response_text.lower(), "Root cause detection"),
            ("decision" in response_text.lower() or "policy" in response_text.lower(), "Policy decision")
        ]
        
        all_pass = True
        for check, name in flow_indicators:
            status = "✅" if check else "❌"
            print(f"   {status} {name}: {check}")
            if not check:
                all_pass = False
        
        print(f"\n{'✅ SCENARIO 1 PASSED' if all_pass else '❌ SCENARIO 1 PARTIAL'}")
        return all_pass, {"response": response_text}
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False, {"error": str(e)}


def run_scenario_2():
    """Run Scenario 2: Access Request using orchestrator agent."""
    print("\n" + "="*70)
    print("SCENARIO 2: Access Request - Should Follow Work Reception Process")
    print("Using: AgentCore Runtime + Strands Agents as Tools")
    print("="*70)
    
    incident = SCENARIO_2_INCIDENT
    print(f"\n📋 Incident: {incident['short_description']}")
    print(f"   Sys ID: {incident['sys_id']}")
    
    prompt = f"""Process this ServiceNow incident:

Incident ID: {incident['sys_id']}
Short Description: {incident['short_description']}
Description: {incident['description']}
Category: {incident['category']}
Additional Info: {json.dumps(incident['additional_info'], indent=2)}

This appears to be an access request. Follow the workflow and apply appropriate policy.

Provide complete analysis and determine how to handle this."""
    
    print("\n🤖 Running orchestrator agent with strands Agent tools...")
    
    try:
        result = get_orchestrator_agent()(prompt)
        response_text = str(result)
        
        print(f"\n📊 Agent Response:")
        print("-" * 50)
        print(response_text[:1500] + "..." if len(response_text) > 1500 else response_text)
        print("-" * 50)
        
        # Validation
        print("\n" + "-"*50)
        print("VALIDATION:")
        
        flow_indicators = [
            ("access" in response_text.lower(), "Access request recognized"),
            ("escalate" in response_text.lower() or "redirect" in response_text.lower(), "Escalation/redirect suggested"),
            ("policy" in response_text.lower(), "Policy referenced")
        ]
        
        all_pass = True
        for check, name in flow_indicators:
            status = "✅" if check else "❌"
            print(f"   {status} {name}: {check}")
            if not check:
                all_pass = False
        
        print(f"\n{'✅ SCENARIO 2 PASSED' if all_pass else '❌ SCENARIO 2 PARTIAL'}")
        return all_pass, {"response": response_text}
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False, {"error": str(e)}


def run_all_scenarios():
    """Run all end-to-end test scenarios."""
    print("\n" + "="*70)
    print("   END-TO-END TEST SCENARIOS")
    print("   AgentCore Runtime + Strands Agents as Tools")
    print("="*70)
    
    results = {}
    
    # Run Scenario 1
    passed_1, details_1 = run_scenario_1()
    results["scenario_1_source_zero_byte"] = {
        "passed": passed_1,
        "details": details_1
    }
    
    # Run Scenario 2
    passed_2, details_2 = run_scenario_2()
    results["scenario_2_access_request"] = {
        "passed": passed_2,
        "details": details_2
    }
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Scenario 1 (DAG Failed - Zero Byte): {'✅ PASSED' if passed_1 else '❌ FAILED'}")
    print(f"Scenario 2 (Access Request):         {'✅ PASSED' if passed_2 else '❌ FAILED'}")
    print(f"\nOverall: {sum([passed_1, passed_2])}/2 scenarios passed")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run end-to-end test scenarios")
    parser.add_argument("--scenario", "-s", type=int, choices=[1, 2], 
                        help="Run specific scenario (1 or 2)")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    if args.scenario == 1:
        passed, details = run_scenario_1()
        results = {"scenario_1": {"passed": passed, "details": details}}
    elif args.scenario == 2:
        passed, details = run_scenario_2()
        results = {"scenario_2": {"passed": passed, "details": details}}
    else:
        results = run_all_scenarios()
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")
