"""Test Intent Classifier Agent in isolation."""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.intent_classifier import classify_intent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Test incidents for intent classification
TEST_INCIDENTS = [
    {
        "name": "DAG Failure",
        "incident": {
            "sys_id": "TEST001",
            "short_description": "CloudWatch alarm: dagstatus failure for dlr_grp in MWAA",
            "category": "Data Pipeline"
        },
        "expected_intent": "dag_failure"
    },
    {
        "name": "Glue Job Failure",
        "incident": {
            "sys_id": "TEST002",
            "short_description": "Job SPENDING_POTS has failed - Glue ETL failure",
            "category": "Data Pipeline"
        },
        "expected_intent": "glue_etl_failure"
    },
    {
        "name": "EMR Failure",
        "incident": {
            "sys_id": "TEST003",
            "short_description": "EMR cluster j-123456 step s-789 failed with error",
            "category": "Data Pipeline"
        },
        "expected_intent": "emr_failure"
    },
    {
        "name": "Athena Failure",
        "incident": {
            "sys_id": "TEST004",
            "short_description": "Athena query execution failed in workgroup",
            "category": "Data Query"
        },
        "expected_intent": "athena_failure"
    },
    {
        "name": "Data Missing",
        "incident": {
            "sys_id": "TEST005",
            "short_description": "Data is not available in DLR location",
            "category": "Data Quality"
        },
        "expected_intent": "data_missing"
    },
    {
        "name": "Access Denied",
        "incident": {
            "sys_id": "TEST006",
            "short_description": "User requesting access to S3 bucket prod-data-lake",
            "category": "Security"
        },
        "expected_intent": "access_denied"
    },
    {
        "name": "Source Zero Data",
        "incident": {
            "sys_id": "TEST007",
            "short_description": "Source system has zero records for date 2024-01-15",
            "category": "Data Quality"
        },
        "expected_intent": "source_zero_data"
    },
]


async def test_intent_classifier():
    """Test intent classifier with various incident types."""
    print("=" * 100)
    print("INTENT CLASSIFIER AGENT TEST")
    print("=" * 100)
    
    results = []
    
    for test_case in TEST_INCIDENTS:
        print(f"\n{'=' * 100}")
        print(f"TEST: {test_case['name']}")
        print(f"{'=' * 100}")
        print(f"Incident: {test_case['incident']['short_description']}")
        print(f"Expected Intent: {test_case['expected_intent']}")
        
        try:
            # Call intent classifier
            result = await classify_intent(test_case['incident'])
            
            print(f"\n{'—' * 50}")
            print("RESULT:")
            print(f"{'—' * 50}")
            print(json.dumps(result, indent=2))
            
            # Validate result
            success = (
                result.get("intent") == test_case['expected_intent'] or
                result.get("confidence", 0.0) >= 0.5
            )
            
            results.append({
                "test_name": test_case['name'],
                "success": success,
                "classified_as": result.get("intent"),
                "expected": test_case['expected_intent'],
                "confidence": result.get("confidence", 0.0),
                "reasoning": result.get("reasoning", "")
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
        classified = result.get("classified_as", "unknown")
        expected = result.get("expected", "unknown")
        confidence = result.get("confidence", 0.0)
        
        if result.get("success", False):
            print(f"  {status} - {result['test_name']}")
            print(f"          Intent: {classified} (confidence: {confidence:.2f})")
        else:
            print(f"  {status} - {result['test_name']}")
            print(f"          Expected: {expected}, Got: {classified}")
            if "error" in result:
                print(f"          Error: {result['error']}")
    
    print(f"\n{'=' * 100}\n")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(test_intent_classifier())
    
    # Exit with error if any tests failed
    sys.exit(0 if all(r.get("success", False) for r in results) else 1)
