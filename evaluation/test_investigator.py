"""Test Investigator Agent in isolation."""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.investigator import investigate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Test scenarios with classified intents
TEST_SCENARIOS = [
    {
        "name": "Glue Job Failure Investigation",
        "intent_result": {
            "intent": "glue_etl_failure",
            "confidence": 0.85,
            "reasoning": "Clear Glue ETL failure indicators"
        },
        "incident": {
            "sys_id": "TEST001",
            "short_description": "Job SPENDING_POTS has failed",
            "additional_info": {
                "job_name": "SPENDING_POTS",
                "error": "OutOfMemory"
            }
        }
    },
    {
        "name": "EMR Step Failure Investigation",
        "intent_result": {
            "intent": "emr_failure",
            "confidence": 0.90,
            "reasoning": "EMR step failure detected"
        },
        "incident": {
            "sys_id": "TEST002",
            "short_description": "EMR cluster step failed",
            "additional_info": {
                "cluster_id": "j-ABCD1234",
                "step_id": "s-XYZ789"
            }
        }
    },
    {
        "name": "Data Missing Investigation",
        "intent_result": {
            "intent": "data_missing",
            "confidence": 0.80,
            "reasoning": "Expected data not found"
        },
        "incident": {
            "sys_id": "TEST003",
            "short_description": "Data not available in DLR",
            "additional_info": {
                "location": "s3://prod-data-lake/daily/2024-01-15/",
                "expected_files": ["data.parquet"]
            }
        }
    },
]


async def test_investigator():
    """Test investigator agent with various incident types."""
    print("=" * 100)
    print("INVESTIGATOR AGENT TEST")
    print("=" * 100)
    print("\nNote: Running with MOCK tools (no AWS credentials required)\n")
    
    results = []
    
    for test_case in TEST_SCENARIOS:
        print(f"\n{'=' * 100}")
        print(f"TEST: {test_case['name']}")
        print(f"{'=' * 100}")
        print(f"Intent: {test_case['intent_result']['intent']}")
        print(f"Incident: {test_case['incident']['short_description']}")
        
        try:
            # Call investigator (with empty mcp_tools - will use mock mode)
            result = await investigate(
                test_case['intent_result'],
                test_case['incident'],
                mcp_tools=[]  # Mock mode
            )
            
            print(f"\n{'—' * 50}")
            print("INVESTIGATION RESULT:")
            print(f"{'—' * 50}")
            print(f"Root Cause: {result.get('root_cause', 'N/A')}")
            print(f"Evidence Score: {result.get('evidence_score', 0.0)}")
            print(f"Retry Recommended: {result.get('retry_recommended', False)}")
            print(f"Recommended Action: {result.get('recommended_action', 'none')}")
            print(f"\nFindings: {len(result.get('findings', []))} tool(s) executed")
            
            # Validate result structure
            success = (
                "root_cause" in result and
                "evidence_score" in result and
                "findings" in result
            )
            
            results.append({
                "test_name": test_case['name'],
                "success": success,
                "root_cause": result.get("root_cause"),
                "evidence_score": result.get("evidence_score"),
                "retry_recommended": result.get("retry_recommended")
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
            print(f"          Evidence Score: {result.get('evidence_score', 0.0):.2f}")
            print(f"          Retry: {result.get('retry_recommended', False)}")
        else:
            print(f"          Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'=' * 100}\n")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(test_investigator())
    
    # Exit with error if any tests failed
    sys.exit(0 if all(r.get("success", False) for r in results) else 1)
