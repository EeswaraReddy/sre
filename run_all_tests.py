"""Master Test Runner for All Agent Components.

Runs isolated tests for each agent component:
- Intent Classifier
- Investigator
- Action Agent
- Policy Engine
- Full E2E Orchestrator

Generates a comprehensive test report.
"""
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


TEST_SCRIPTS = [
    {
        "name": "Intent Classifier",
        "script": "evaluation/test_intent_classifier.py",
        "description": "Tests incident classification into 13 intent categories"
    },
    {
        "name": "Investigator",
        "script": "evaluation/test_investigator.py",
        "description": "Tests evidence gathering and root cause analysis"
    },
    {
        "name": "Action Agent",
        "script": "evaluation/test_action_agent.py",
        "description": "Tests remediation action execution"
    },
    {
        "name": "Policy Engine",
        "script": "evaluation/test_policy_engine.py",
        "description": "Tests policy decisions and RCA generation"
    },
    {
        "name": "E2E Orchestrator",
        "script": "test_orchestrator.py",
        "description": "Tests full end-to-end orchestration flow"
    },
]


def run_test(test_info):
    """Run a single test script and capture results."""
    print(f"\n{'=' * 100}")
    print(f"Running: {test_info['name']}")
    print(f"Description: {test_info['description']}")
    print(f"{'=' * 100}\n")
    
    script_path = Path(__file__).parent / test_info['script']
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return {
            "name": test_info['name'],
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "name": test_info['name'],
            "success": False,
            "exit_code": -1,
            "error": "Test timed out after 60 seconds"
        }
    except Exception as e:
        return {
            "name": test_info['name'],
            "success": False,
            "exit_code": -1,
            "error": str(e)
        }


def main():
    """Run all tests and generate report."""
    print("=" * 100)
    print("AGENT VALIDATION TEST SUITE")
    print("=" * 100)
    print(f"\nStarting test run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total test suites: {len(TEST_SCRIPTS)}\n")
    
    results = []
    
    for test_info in TEST_SCRIPTS:
        result = run_test(test_info)
        results.append(result)
        
        # Print immediate result
        status = "✓ PASSED" if result['success'] else "✗ FAILED"
        print(f"\n{status}: {result['name']}")
        
        if not result['success']:
            print(f"Exit Code: {result['exit_code']}")
            if 'error' in result:
                print(f"Error: {result['error']}")
            if result.get('stderr'):
                print(f"Stderr: {result['stderr'][:500]}")  # First 500 chars
    
    # Summary Report
    print(f"\n\n{'=' * 100}")
    print("TEST SUITE SUMMARY")
    print(f"{'=' * 100}\n")
    
    total = len(results)
    passed = sum(1 for r in results if r['success'])
    failed = total - passed
    
    print(f"Total Suites: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/total*100):.1f}%\n")
    
    for result in results:
        status_emoji = "✓" if result['success'] else "✗"
        print(f"  {status_emoji} {result['name']:<25} {'PASS' if result['success'] else 'FAIL'}")
    
    # Save detailed report
    report_path = Path(__file__).parent / "test_reports" / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "success_rate": passed/total
            },
            "results": results
        }, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_path}")
    print(f"\n{'=' * 100}\n")
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
