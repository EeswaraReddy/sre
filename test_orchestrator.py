"""Test the orchestrator agent with sample incidents based on the issue types."""
import json
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import orchestrate_incident

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_orchestrator():
    """Test orchestrator with different issue types."""
    
    # Sample incidents based on the image issue types
    test_incidents = [
        {
            "name": "MWAA DAG Failure",
            "incident": {
                "sys_id": "INC001",
                "short_description": "dagstatus failure Alarm for dlr_grp ... MWAA",
                "description": "CloudWatch alarm triggered for MWAA DAG status failure in dlr_grp",
                "category": "Data Pipeline",
                "subcategory": "Airflow",
                "additional_info": {
                    "alarm_name": "dagstatus-failure-dlr_grp",
                    "service": "MWAA"
                }
            }
        },
        {
            "name": "Glue Job Failure",
            "incident": {
                "sys_id": "INC002",
                "short_description": "Job SPENDING_POTS... has failed Glue ETL failure",
                "description": "Glue ETL job SPENDING_POTS has failed with error",
                "category": "Data Pipeline",
                "subcategory": "ETL",
                "additional_info": {
                    "job_name": "SPENDING_POTS",
                    "service": "Glue",
                    "error_type": "JobFailure"
                }
            }
        },
        {
            "name": "Athena Failure",
            "incident": {
                "sys_id": "INC003",
                "short_description": "Athena AWS failure Service: Athena",
                "description": "Athena query execution failed",
                "category": "Data Query",
                "subcategory": "Athena",
                "additional_info": {
                    "service": "Athena",
                    "alert_group": "cdlspprodafwgrp"
                }
            }
        },
        {
            "name": "Data Missing",
            "incident": {
                "sys_id": "INC004",
                "short_description": "Data is not available..., Data missing in DLR",
                "description": "Expected data not found in DLR location",
                "category": "Data Quality",
                "subcategory": "Missing Data",
                "additional_info": {
                    "location": "DLR",
                    "expected_files": ["daily_load.parquet"]
                }
            }
        },
        {
            "name": "Historical Data Missing",
            "incident": {
                "sys_id": "INC005",
                "short_description": "Data missing ... historical load",
                "description": "Historical data missing across multiple dates",
                "category": "Data Quality",
                "subcategory": "Historical Data",
                "additional_info": {
                    "missing_dates": ["2024-01-01", "2024-01-02", "2024-01-03"]
                }
            }
        }
    ]
    
    print("=" * 100)
    print("ORCHESTRATOR AGENT TEST")
    print("=" * 100)
    
    results = []
    
    for test_case in test_incidents:
        print(f"\n{'=' * 100}")
        print(f"TEST: {test_case['name']}")
        print(f"{'=' * 100}")
        print(f"\nIncident: {test_case['incident']['short_description']}")
        print(f"Sys ID: {test_case['incident']['sys_id']}")
        
        try:
            logger.info(f"Running orchestrator for {test_case['name']}")
            result = orchestrate_incident(test_case['incident'])
            
            print(f"\n{'=' * 50}")
            print("ORCHESTRATION RESULT")
            print(f"{'=' * 50}")
            print(json.dumps(result, indent=2, default=str))
            
            results.append({
                "test_name": test_case['name'],
                "sys_id": test_case['incident']['sys_id'],
                "success": "error" not in result or result.get("error") is None,
                "result": result
            })
            
        except Exception as e:
            logger.error(f"Test failed for {test_case['name']}: {str(e)}", exc_info=True)
            results.append({
                "test_name": test_case['name'],
                "sys_id": test_case['incident']['sys_id'],
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
        print(f"  {status} - {result['test_name']} ({result['sys_id']})")
        if not result.get("success", False):
            print(f"    Error: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'=' * 100}\n")
    
    return results


if __name__ == "__main__":
    test_orchestrator()
