"""Test Action Agent in isolation."""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.action_agent import execute_action

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Test scenarios with investigation results
TEST_SCENARIOS = [
    {
        "name": "Glue Job Retry Action",
        "investigation": {
            "root_cause": "Glue job exceeded timeout",
            "evidence_score": 0.75,
            "retry_recommended": True,
            "recommended_action": "retry_glue_job",
            "findings": [
                {
                    "tool": "get_glue_logs",
                    "result": {"job_name": "SPENDING_POTS", "status": "TIMEOUT"}
                }
            ]
        },
        "incident": {
            "sys_id": "TEST001",
            "short_description": "Job SPENDING_POTS has failed",
            "additional_info": {"job_name": "SPENDING_POTS"}
        }
    },
    {
        "name": "No Action Needed",
        "investigation": {
            "root_cause": "Data not yet available from source",
            "evidence_score": 0.60,
            "retry_recommended": False,
            "recommended_action": "none",
            "findings": []
        },
        "incident": {
            "sys_id": "TEST002",
            "short_description": "Data missing in DLR"
        }
    },
    {
        "name": "Athena Query Retry",
        "investigation": {
            "root_cause": "Athena query timeout",
            "evidence_score": 0.80,
            "retry_recommended": True,
            "recommended_action": "retry_athena_query",
            "findings": [
                {
                    "tool": "get_athena_query",
                    "result": {"execution_id": "abc-123", "status": "FAILED"}
                }
            ]
        },
        "incident": {
            "sys_id": "TEST003",
            "short_description": "Athena query failed",
            "additional_info": {"query_execution_id": "abc-123"}
        }
    },
]


async def test_action_agent():
    """Test action agent with various investigation result scenarios."""
    print("=" * 100)
    print("ACTION AGENT TEST")
    print("=" * 100)
    print("\nNote: Running with MOCK tools (no AWS credentials required)\n")
    
    results = []
    
    for test_case in TEST_SCENARIOS:
        print(f"\n{'=' * 100}")
        print(f"TEST: {test_case['name']}")
        print(f"{'=' * 100}")
        print(f"Recommended Action: {test_case['investigation']['recommended_action']}")
        print(f"Retry Recommended: {test_case['investigation']['retry_recommended']}")
        
        try:
            # Call action agent (with empty mcp_tools - will use mock mode)
            result = await execute_action(
                test_case['investigation'],
                test_case['incident'],
                mcp_tools=[]  # Mock mode
            )
            
            print(f"\n{'—' * 50}")
            print("ACTION RESULT:")
            print(f"{'—' * 50}")
            print(f"Action: {result.get('action', 'none')}")
            print(f"Success: {result.get('success', False)}")
            if result.get('details'):
                print(f"Details: {json.dumps(result.get('details'), indent=2)}")
            
            # Validate result structure
            success = (
                "action" in result and
                "success" in result
            )
            
            results.append({
                "test_name": test_case['name'],
                "success": success,
                "action": result.get("action"),
                "action_success": result.get("success")
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
    print(f"Failed: {failed}")
    
    for result in results:
        status = "✓ PASS" if result.get("success", False) else "✗ FAIL"
        print(f"  {status} - {result['test_name']}")
        if result.get("success", False):
            print(f"          Action: {result.get('action', 'none')}")
            print(f"          Success: {result.get('action_success', False)}")
        else:
            print(f"          Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'=' * 100}\n")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(test_action_agent())
    
    # Exit with error if any tests failed
    sys.exit(0 if all(r.get("success", False) for r in results) else 1)
