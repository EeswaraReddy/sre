"""Orchestrator Agent - coordinates the multi-agent incident handling workflow."""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

from strands import Agent
from strands.models import BedrockModel

from .config import MODEL_ID
from .prompts import ORCHESTRATOR_PROMPT
from .intent_classifier import classify_intent
from .investigator import investigate
from .action_agent import execute_action
from .policy_engine import apply_policy, build_rca

logger = logging.getLogger(__name__)

# Create BedrockModel instance
bedrock_model = BedrockModel(model_id=MODEL_ID)


class OrchestratorAgent:
    """Orchestrator that coordinates the multi-agent incident handling workflow."""
    
    def __init__(self, mcp_tools: Optional[List] = None):
        """Initialize the orchestrator.
        
        Args:
            mcp_tools: Optional list of MCP tools from Gateway
        """
        self.mcp_tools = mcp_tools or []
        logger.info("Orchestrator initialized with BedrockModel")
    
    def evaluate_classification(self, classification: Dict) -> Dict:
        """Evaluate classification confidence before proceeding.
        
        Args:
            classification: Classification result
            
        Returns:
            Evaluation with approval to proceed
        """
        confidence = classification.get("confidence", 0.0)
        intent = classification.get("intent", "unknown")
        
        # Evaluation criteria
        if confidence >= 0.7:
            return {
                "approved": True,
                "confidence_level": "high",
                "reasoning": f"High confidence ({confidence}) classification as {intent}"
            }
        elif confidence >= 0.4:
            return {
                "approved": True,
                "confidence_level": "medium",
                "reasoning": f"Medium confidence ({confidence}) classification, proceeding with caution"
            }
        else:
            return {
                "approved": True,  # Still proceed but mark for review
                "confidence_level": "low",
                "reasoning": f"Low confidence ({confidence}) classification, will require human review"
            }
    
    def evaluate_investigation(self, investigation: Dict) -> Dict:
        """Evaluate investigation results before taking action.
        
        Args:
            investigation: Investigation findings
            
        Returns:
            Evaluation with approval for action
        """
        evidence_score = investigation.get("evidence_score", 0.0)
        retry_recommended = investigation.get("retry_recommended", False)
        
        # Evaluation criteria
        if evidence_score >= 0.6 and retry_recommended:
            return {
                "approved": True,
                "action_approved": True,
                "reasoning": f"Strong evidence ({evidence_score}), safe to proceed with action"
            }
        elif evidence_score >= 0.4:
            return {
                "approved": True,
                "action_approved": retry_recommended,
                "reasoning": f"Moderate evidence ({evidence_score}), proceed based on recommendation"
            }
        else:
            return {
                "approved": True,
                "action_approved": False,
                "reasoning": f"Weak evidence ({evidence_score}), skip automated action"
            }
    
    def orchestrate(self, incident: Dict) -> Dict:
        """Orchestrate the complete incident handling workflow with evaluation gates.
        
        Workflow:
        1. Classify incident
        2. Evaluate classification
        3. Investigate based on classification  
        4. Evaluate investigation
        5. Execute action if approved
        6. Apply policy decision
        7. Build RCA
        
        Args:
            incident: Incident data from ServiceNow
            
        Returns:
            Complete RCA with classification, investigation, action, and decision
        """
        sys_id = incident.get("sys_id", "unknown")
        start_time = datetime.utcnow()
        
        logger.info(f"=== Starting orchestration for incident: {sys_id} ===")
        
        try:
            # Step 1: Classify incident
            logger.info("Step 1: Classifying incident")
            classification = classify_intent(incident)
            logger.info(f"Classification: {classification.get('intent')} (confidence: {classification.get('confidence')})")
            
            # Step 2: Evaluate classification
            logger.info("Step 2: Evaluating classification")
            classification_eval = self.evaluate_classification(classification)
            logger.info(f"Classification evaluation: {classification_eval.get('confidence_level')} confidence")
            
            if not classification_eval.get("approved"):
                logger.warning("Classification not approved, aborting orchestration")
                return self._build_abort_response(sys_id, start_time, "classification_rejected", classification_eval)
            
            # Step 3: Investigate based on classification
            logger.info("Step 3: Investigating incident")
            investigation = investigate(classification, incident, self.mcp_tools)
            logger.info(f"Investigation: {investigation.get('root_cause')}")
            
            # Step 4: Evaluate investigation
            logger.info("Step 4: Evaluating investigation")
            investigation_eval = self.evaluate_investigation(investigation)
            logger.info(f"Investigation evaluation: action_approved={investigation_eval.get('action_approved')}")
            
            # Step 5: Execute action if approved
            action = {"action": "none", "success": True, "details": {}, "error": None}
            
            if investigation_eval.get("action_approved"):
                logger.info("Step 5: Executing remediation action")
                action = execute_action(investigation, incident, self.mcp_tools)
                logger.info(f"Action: {action.get('action')} (success: {action.get('success')})")
            else:
                logger.info("Step 5: Skipping action (not approved by evaluation)")
                action["details"]["reason"] = "Action not approved by evaluation"
            
            # Step 6: Apply policy decision
            logger.info("Step 6: Making policy decision")
            decision = apply_policy(classification, investigation, action)
            logger.info(f"Decision: {decision.get('decision')} (score: {decision.get('score')})")
            
            # Step 7: Build complete RCA
            rca = build_rca(incident, classification, investigation, action, decision)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"=== Orchestration complete for {sys_id} in {duration:.2f}s ===")
            
            # Add metadata and evaluation results
            rca["timestamp"] = start_time.isoformat()
            rca["duration_seconds"] = duration
            rca["status"] = "success"
            rca["evaluation"] = {
                "classification": classification_eval,
                "investigation": investigation_eval
            }
            
            return rca
            
        except Exception as e:
            logger.error(f"Orchestration failed for {sys_id}: {str(e)}", exc_info=True)
            return {
                "incident": {"sys_id": sys_id},
                "timestamp": start_time.isoformat(),
                "status": "error",
                "error": str(e),
                "decision": {
                    "outcome": "human_review",
                    "score": 0.0,
                    "reasoning": f"Orchestration error: {str(e)}"
                }
            }
    
    def _build_abort_response(self, sys_id: str, start_time: datetime, reason: str, details: Dict) -> Dict:
        """Build response when orchestration is aborted."""
        return {
            "incident": {"sys_id": sys_id},
            "timestamp": start_time.isoformat(),
            "status": "aborted",
            "abort_reason": reason,
            "abort_details": details,
            "decision": {
                "outcome": "human_review",
                "score": 0.0,
                "reasoning": f"Orchestration aborted: {reason}"
            }
        }


def create_orchestrator(mcp_tools: Optional[List] = None) -> OrchestratorAgent:
    """Factory function to create an orchestrator agent.
    
    Args:
        mcp_tools: Optional list of MCP tools from Gateway
        
    Returns:
        Configured OrchestratorAgent instance
    """
    return OrchestratorAgent(mcp_tools=mcp_tools)


def orchestrate_incident(
    incident: Dict,
    mcp_tools: Optional[List] = None
) -> Dict:
    """Convenience function to orchestrate incident handling.
    
    Args:
        incident: Incident data from ServiceNow
        mcp_tools: Optional list of MCP tools from Gateway
        
    Returns:
        Complete RCA with all agent results
    """
    orchestrator = create_orchestrator(mcp_tools)
    return orchestrator.orchestrate(incident)


if __name__ == "__main__":
    # Test orchestrator with sample incidents
    
    test_incidents = [
        {
            "sys_id": "TEST001",
            "short_description": "dagstatus failure Alarm for dlr_grp ... MWAA",
            "category": "Data Pipeline",
            "subcategory": "Airflow"
        },
        {
            "sys_id": "TEST002",
            "short_description": "Job SPENDING_POTS... has failed Glue ETL failure",
            "category": "Data Pipeline",
            "subcategory": "ETL"
        }
    ]
    
    for incident in test_incidents:
        print(f"\n{'=' * 80}")
        print(f"Testing: {incident['short_description']}")
        print(f"{'=' * 80}")
        result = orchestrate_incident(incident)
        print(json.dumps(result, indent=2, default=str))
