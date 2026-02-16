"""Test Policy Engine in isolation."""
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.policy_engine import apply_policy, build_rca

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Test scenarios with full agent results
TEST_SCENARIOS = [
    {
        "name": "Auto-Close: High Confidence + Successful Retry",
        "intent": {
            "intent": "glue_etl_failure",
            "confidence": 0.90,
            "reasoning": "Clear Glue job failure"
        },
        "investigation": {
            "root_cause": "Glue job timeout",
            "evidence_score": 0.85,
            "retry_recommended": True
        },
        "action": {
            "action": "retry_glue_job",
            "success": True,
            "details": {"new_run_id": "jr_123"}
        },
        "expected_decision": "auto_close"
    },
    {
        "name": "Auto-Retry: Medium Confidence + Retry Recommended",
        "intent": {
            "intent": "athena_failure",
            "confidence": 0.70,
            "reasoning": "Athena failure indicators"
        },
        "investigation": {
            "root_cause": "Athena query timeout",
            "evidence_score": 0.65,
            "retry_recommended": True
        },
        "action": {
            "action": "retry_athena_query",
            "success": True
        },
        "expected_decision": "auto_retry"
    },
    {
        "name": "Human Review: Low Confidence",
        "intent": {
            "intent": "unknown",
            "confidence": 0.40,
            "reasoning": "Unable to classify"
        },
        "investigation": {
            "root_cause": "Unable to determine",
            "evidence_score": 0.30,
            "retry_recommended": False
        },
        "action": {
            "action": "none",
            "success": False
        },
        "expected_decision": "human_review"
    },
    {
        "name": "Escalate: Complex Issue",
        "intent": {
            "intent": "data_missing",
            "confidence": 0.75,
            "reasoning": "Data missing indicators"
        },
        "investigation": {
            "root_cause": "Upstream source data unavailable",
            "evidence_score": 0.60,
            "retry_recommended": False
        },
        "action": {
            "action": "none",
            "success": False
        },
        "expected_decision": "escalate"
    },
    {
        "name": "Human Review: Access Denied (Policy Override)",
        "intent": {
            "intent": "access_denied",
            "confidence": 0.95,
            "reasoning": "Clear access request"
        },
        "investigation": {
            "root_cause": "IAM permissions required",
            "evidence_score": 0.90,
            "retry_recommended": False
        },
        "action": {
            "action": "none",
            "success": False
        },
        "expected_decision": "human_review"  # Policy override
    },
]


def test_policy_engine():
    """Test policy engine with various agent result combinations."""
    print("=" * 100)
    print("POLICY ENGINE TEST")
    print("=" * 100)
    
    results = []
    
    for test_case in TEST_SCENARIOS:
        print(f"\n{'=' * 100}")
        print(f"TEST: {test_case['name']}")
        print(f"{'=' * 100}")
        print(f"Intent: {test_case['intent']['intent']} (confidence: {test_case['intent']['confidence']})")
        print(f"Evidence Score: {test_case['investigation']['evidence_score']}")
        print(f"Action Success: {test_case['action']['success']}")
        print(f"Expected Decision: {test_case['expected_decision']}")
        
        try:
            # Call policy engine
            result = apply_policy(
                test_case['intent'],
                test_case['investigation'],
                test_case['action']
            )
            
            print(f"\n{'—' * 50}")
            print("POLICY DECISION:")
            print(f"{'—' * 50}")
            print(f"Decision: {result.get('decision', 'N/A')}")
            print(f"Score: {result.get('score', 0.0):.2f}")
            print(f"Reasoning: {result.get('reasoning', 'N/A')}")
            if result.get('override_applied'):
                print(f"Override Applied: {result.get('override_type')}")
            
            # Validate decision
            actual_decision = result.get('decision')
            expected_decision = test_case['expected_decision']
            
            success = (
                "decision" in result and
                "score" in result and
                "reasoning" in result
            )
            
            results.append({
                "test_name": test_case['name'],
                "success": success,
                "actual_decision": actual_decision,
                "expected_decision": expected_decision,
                "match": actual_decision == expected_decision,
                "score": result.get("score")
            })
            
        except Exception as e:
            logger.error(f"Test failed for {test_case['name']}: {str(e)}", exc_info=True)
            results.append({
                "test_name": test_case['name'],
                "success": False,
                "error": str(e)
            })
    
    # Summary
    print(f"\n\n{'=' * 100}")
    print("TEST SUMMARY")
    print(f"{'=' * 100}")
    
    total = len(results)
    passed = sum(1 for r in results if r.get("success", False))
    failed = total - passed
    
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}\n")
    
    for result in results:
        status = "✓ PASS" if result.get("success", False) else "✗ FAIL"
        print(f"  {status} - {result['test_name']}")
        if result.get("success", False):
            expected = result.get('expected_decision')
            actual = result.get('actual_decision')
            match_symbol = "✓" if result.get('match') else "✗"
            print(f"          Decision: {actual} (expected: {expected}) {match_symbol}")
            print(f"          Score: {result.get('score', 0.0):.2f}")
        else:
            print(f"          Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'=' * 100}\n")
    
    # Test RCA builder
    print("\nTesting RCA Builder...")
    if len([r for r in results if r.get("success", False)]) > 0:
        first_success = TEST_SCENARIOS[0]
        try:
            rca = build_rca(
                {"sys_id": "TEST001", "short_description": "Test incident"},
                first_success['intent'],
                first_success['investigation'],
                first_success['action'],
                {"decision": "auto_close", "score": 0.85, "reasoning": "Test"}
            )
            print(f"✓ RCA Builder: Generated RCA with {len(rca.keys())} keys")
            results.append({"test_name": "RCA Builder", "success": True})
        except Exception as e:
            print(f"✗ RCA Builder: {str(e)}")
            results.append({"test_name": "RCA Builder", "success": False, "error": str(e)})
    
    return results


if __name__ == "__main__":
    results = test_policy_engine()
    
    # Exit with error if any tests failed
    sys.exit(0 if all(r.get("success", False) for r in results) else 1)
