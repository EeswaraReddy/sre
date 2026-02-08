"""Policy Engine - scores evidence and determines final decision."""
import logging
from typing import Any

from .config import POLICY_OVERRIDES, POLICY_THRESHOLDS

logger = logging.getLogger(__name__)


def calculate_evidence_score(investigation: dict) -> float:
    """Calculate evidence score from investigation findings.
    
    Args:
        investigation: Investigation result with findings
        
    Returns:
        Evidence score between 0.0 and 1.0
    """
    # Start with the investigation's own evidence score if available
    base_score = investigation.get("evidence_score", 0.5)
    
    # Adjust based on findings quality
    findings = investigation.get("findings", [])
    
    if not findings:
        # No findings reduces confidence
        return base_score * 0.5
    
    # Check for successful tool calls
    successful_findings = [
        f for f in findings 
        if f.get("result") and not f.get("result", {}).get("error")
    ]
    
    findings_ratio = len(successful_findings) / len(findings) if findings else 0
    
    # Check for clear root cause
    root_cause = investigation.get("root_cause", "")
    has_clear_cause = len(root_cause) > 20 and "unknown" not in root_cause.lower()
    
    # Calculate adjusted score
    adjusted_score = base_score * 0.5 + findings_ratio * 0.3 + (0.2 if has_clear_cause else 0)
    
    return min(1.0, max(0.0, adjusted_score))


def apply_policy(
    intent_result: dict,
    investigation: dict,
    action_result: dict
) -> dict:
    """Apply policy rules to determine final decision.
    
    Args:
        intent_result: Intent classification result
        investigation: Investigation findings
        action_result: Action execution result
        
    Returns:
        Policy decision with decision, score, and reasoning
    """
    intent = intent_result.get("intent", "unknown")
    intent_confidence = intent_result.get("confidence", 0.0)
    
    # Check for policy overrides first
    if intent in POLICY_OVERRIDES:
        override_decision = POLICY_OVERRIDES[intent]
        logger.info(f"Policy override applied for intent '{intent}': {override_decision}")
        return {
            "decision": override_decision,
            "score": intent_confidence,
            "override_applied": True,
            "override_type": intent,
            "reasoning": f"Policy override: {intent} always results in {override_decision}"
        }
    
    # Calculate combined score
    evidence_score = calculate_evidence_score(investigation)
    action_success = action_result.get("success", False)
    action_taken = action_result.get("action", "none") != "none"
    
    # Weighted scoring
    # - 40% intent confidence
    # - 40% evidence score
    # - 20% action success (if action was taken)
    
    if action_taken:
        combined_score = (
            intent_confidence * 0.4 +
            evidence_score * 0.4 +
            (0.2 if action_success else 0.0)
        )
    else:
        # If no action taken, redistribute weights
        combined_score = (
            intent_confidence * 0.5 +
            evidence_score * 0.5
        )
    
    # Apply thresholds to determine decision
    if combined_score >= POLICY_THRESHOLDS["auto_close"] and action_success:
        decision = "auto_close"
        reasoning = f"High confidence ({combined_score:.2f}) with successful action"
    elif combined_score >= POLICY_THRESHOLDS["auto_retry"] and (action_success or not action_taken):
        if action_taken and action_success:
            decision = "auto_close"
            reasoning = f"Medium confidence ({combined_score:.2f}) with successful retry"
        else:
            decision = "auto_retry"
            reasoning = f"Medium confidence ({combined_score:.2f}), retry may resolve issue"
    elif combined_score >= POLICY_THRESHOLDS["escalate"]:
        decision = "escalate"
        reasoning = f"Low confidence ({combined_score:.2f}), requires expert review"
    else:
        decision = "human_review"
        reasoning = f"Very low confidence ({combined_score:.2f}), manual review required"
    
    # Additional checks that force human review
    if investigation.get("error") or action_result.get("error"):
        if decision in ["auto_close", "auto_retry"]:
            decision = "escalate"
            reasoning = f"Errors occurred during processing: {investigation.get('error') or action_result.get('error')}"
    
    logger.info(f"Policy decision: {decision} (score: {combined_score:.2f})")
    
    return {
        "decision": decision,
        "score": round(combined_score, 3),
        "override_applied": False,
        "reasoning": reasoning,
        "component_scores": {
            "intent_confidence": round(intent_confidence, 3),
            "evidence_score": round(evidence_score, 3),
            "action_success": action_success
        }
    }


def build_rca(
    incident: dict,
    intent_result: dict,
    investigation: dict,
    action_result: dict,
    policy_result: dict
) -> dict:
    """Build Root Cause Analysis document.
    
    Args:
        incident: Original incident
        intent_result: Classification result
        investigation: Investigation findings
        action_result: Action execution result
        policy_result: Policy decision
        
    Returns:
        RCA document for storage
    """
    return {
        "incident": {
            "sys_id": incident.get("sys_id"),
            "short_description": incident.get("short_description"),
            "category": incident.get("category"),
        },
        "classification": {
            "intent": intent_result.get("intent"),
            "confidence": intent_result.get("confidence"),
            "reasoning": intent_result.get("reasoning")
        },
        "investigation": {
            "root_cause": investigation.get("root_cause"),
            "evidence_score": investigation.get("evidence_score"),
            "findings_count": len(investigation.get("findings", [])),
            "key_findings": [
                f.get("summary") for f in investigation.get("findings", [])
            ][:5]
        },
        "remediation": {
            "action_taken": action_result.get("action"),
            "action_success": action_result.get("success"),
            "action_details": action_result.get("details", {})
        },
        "decision": {
            "outcome": policy_result.get("decision"),
            "score": policy_result.get("score"),
            "reasoning": policy_result.get("reasoning"),
            "override_applied": policy_result.get("override_applied", False)
        }
    }
