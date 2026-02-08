#!/usr/bin/env python3
"""Evaluation script for multi-agent incident handler."""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.intent_classifier import classify_intent_sync
from agents.investigator import investigate_sync
from agents.action_agent import execute_action_sync
from agents.policy_engine import apply_policy, build_rca


def load_test_cases(path: str) -> list:
    """Load test cases from JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def evaluate_intent(result: dict, expected: dict) -> dict:
    """Evaluate intent classification result."""
    intent = result.get("intent", "unknown")
    confidence = result.get("confidence", 0.0)
    expected_intent = expected.get("intent")
    
    # Check intent match
    intent_match = intent == expected_intent
    
    # Check confidence thresholds
    min_conf = expected.get("min_confidence", 0.0)
    max_conf = expected.get("max_confidence", 1.0)
    confidence_ok = min_conf <= confidence <= max_conf
    
    return {
        "intent_match": intent_match,
        "confidence_ok": confidence_ok,
        "actual_intent": intent,
        "expected_intent": expected_intent,
        "confidence": confidence,
        "passed": intent_match and confidence_ok
    }


def evaluate_decision(result: dict, expected: dict) -> dict:
    """Evaluate policy decision result."""
    decision = result.get("decision", "unknown")
    expected_decisions = expected.get("decision", [])
    override_expected = expected.get("override_expected", False)
    override_applied = result.get("override_applied", False)
    
    decision_match = decision in expected_decisions
    override_match = override_expected == override_applied
    
    return {
        "decision_match": decision_match,
        "override_match": override_match,
        "actual_decision": decision,
        "expected_decisions": expected_decisions,
        "override_applied": override_applied,
        "passed": decision_match and override_match
    }


def run_single_test(test_case: dict, verbose: bool = False) -> dict:
    """Run a single test case through the agent pipeline."""
    name = test_case.get("name", "unnamed")
    incident = test_case.get("incident", {})
    expected = test_case.get("expected", {})
    
    results = {
        "name": name,
        "description": test_case.get("description", ""),
        "stages": {}
    }
    
    try:
        # Stage 1: Intent Classification
        if verbose:
            print(f"  Running intent classification...")
        intent_result = classify_intent_sync(incident)
        results["stages"]["intent"] = intent_result
        results["intent_evaluation"] = evaluate_intent(intent_result, expected)
        
        # Stage 2: Investigation (mock mode without MCP tools)
        if verbose:
            print(f"  Running investigation (mock)...")
        investigation = investigate_sync(intent_result, incident, mcp_tools=None)
        results["stages"]["investigation"] = investigation
        
        # Stage 3: Action (mock mode)
        if verbose:
            print(f"  Running action execution (mock)...")
        action_result = execute_action_sync(investigation, incident, mcp_tools=None)
        results["stages"]["action"] = action_result
        
        # Stage 4: Policy Decision
        if verbose:
            print(f"  Applying policy...")
        policy_result = apply_policy(intent_result, investigation, action_result)
        results["stages"]["policy"] = policy_result
        results["decision_evaluation"] = evaluate_decision(policy_result, expected)
        
        # Overall result
        results["passed"] = (
            results["intent_evaluation"]["passed"] and
            results["decision_evaluation"]["passed"]
        )
        
    except Exception as e:
        results["error"] = str(e)
        results["passed"] = False
    
    return results


def run_evaluation(test_cases_path: str, verbose: bool = False, output_path: str = None) -> dict:
    """Run full evaluation suite."""
    print(f"\n{'='*60}")
    print("Multi-Agent Incident Handler Evaluation")
    print(f"{'='*60}\n")
    
    test_cases = load_test_cases(test_cases_path)
    print(f"Loaded {len(test_cases)} test cases from {test_cases_path}\n")
    
    results = {
        "total": len(test_cases),
        "passed": 0,
        "failed": 0,
        "intent_accuracy": 0,
        "decision_accuracy": 0,
        "test_results": []
    }
    
    intent_correct = 0
    decision_correct = 0
    
    for i, test_case in enumerate(test_cases, 1):
        name = test_case.get("name", f"test_{i}")
        print(f"[{i}/{len(test_cases)}] {name}")
        
        test_result = run_single_test(test_case, verbose)
        results["test_results"].append(test_result)
        
        # Track results
        if test_result.get("passed"):
            results["passed"] += 1
            status = "✓ PASSED"
        else:
            results["failed"] += 1
            status = "✗ FAILED"
        
        if test_result.get("intent_evaluation", {}).get("passed"):
            intent_correct += 1
        
        if test_result.get("decision_evaluation", {}).get("passed"):
            decision_correct += 1
        
        # Print summary
        intent_eval = test_result.get("intent_evaluation", {})
        decision_eval = test_result.get("decision_evaluation", {})
        
        print(f"  Intent: {intent_eval.get('actual_intent')} "
              f"(expected: {intent_eval.get('expected_intent')}) "
              f"[{'✓' if intent_eval.get('intent_match') else '✗'}]")
        print(f"  Decision: {decision_eval.get('actual_decision')} "
              f"(expected: {decision_eval.get('expected_decisions')}) "
              f"[{'✓' if decision_eval.get('decision_match') else '✗'}]")
        print(f"  Result: {status}\n")
    
    # Calculate accuracies
    results["intent_accuracy"] = round(intent_correct / len(test_cases) * 100, 1)
    results["decision_accuracy"] = round(decision_correct / len(test_cases) * 100, 1)
    
    # Print summary
    print(f"{'='*60}")
    print("EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total Tests:      {results['total']}")
    print(f"Passed:           {results['passed']} ({results['passed']/results['total']*100:.1f}%)")
    print(f"Failed:           {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
    print(f"Intent Accuracy:  {results['intent_accuracy']}%")
    print(f"Decision Accuracy: {results['decision_accuracy']}%")
    print(f"{'='*60}\n")
    
    # Check thresholds
    if results["intent_accuracy"] >= 80:
        print("✓ Intent accuracy meets 80% threshold")
    else:
        print("✗ Intent accuracy below 80% threshold")
    
    if results["decision_accuracy"] >= 70:
        print("✓ Decision accuracy meets 70% threshold")
    else:
        print("✗ Decision accuracy below 70% threshold")
    
    # Save results if output path provided
    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {output_path}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate multi-agent incident handler"
    )
    parser.add_argument(
        "--test-cases", "-t",
        default=str(Path(__file__).parent / "test_cases.json"),
        help="Path to test cases JSON file"
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to save evaluation results JSON"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    results = run_evaluation(
        test_cases_path=args.test_cases,
        verbose=args.verbose,
        output_path=args.output
    )
    
    # Exit with error if tests failed
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
