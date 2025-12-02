"""
Quick test for Prototype 5: Reflection-Based Prompt Tuning System
"""

import json
from pathlib import Path
from agent import Prototype5Agent


def test_variant(variant_name: str):
    """Test a single variant file"""
    input_path = Path(r"c:\Users\NT-165\Desktop\Project\Toy\GT_data\input") / f"{variant_name}.json"

    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return False

    print(f"\n{'='*80}")
    print(f"Testing: {variant_name}")
    print(f"{'='*80}\n")

    # Load document
    with open(input_path, 'r', encoding='utf-8') as f:
        doc = json.load(f)

    # Run agent with reflection (max 6 attempts per task)
    agent = Prototype5Agent(max_replan_per_task=6)
    result = agent.run(doc)

    # Print results
    if result['success']:
        final_data = result.get('final_data', {})
        definitions = final_data.get('definitions', [])
        total_count = final_data.get('total_count', len(definitions))

        print(f"\n{'='*80}")
        print(f"[SUCCESS] Extracted {total_count} definitions")
        print(f"{'='*80}\n")

        # Print first 3 definitions
        for i, defn in enumerate(definitions[:3]):
            print(f"Definition {i+1}: {defn}")

        if len(definitions) > 3:
            print(f"\n... and {len(definitions) - 3} more")

        # Print reflection summary
        print(f"\n--- Reflection Summary ---")
        execution_log = result.get('execution_log', [])
        for log_entry in execution_log:
            task_id = log_entry['task_id']
            attempts = log_entry.get('attempts', [])
            print(f"Task {task_id}: {len(attempts)} attempts")

            # Show if instructions were added
            for i, attempt in enumerate(attempts):
                params = attempt.get('parameters', {})
                if 'instruction' in params and params['instruction']:
                    print(f"  Attempt {i+1}: instruction added")

        return True
    else:
        print(f"\n{'='*80}")
        print(f"[FAIL] {result.get('error')}")
        print(f"{'='*80}\n")

        # Print execution log for debugging
        execution_log = result.get('execution_log', [])
        if execution_log:
            print("\nExecution Log:")
            for log_entry in execution_log:
                print(f"\nTask {log_entry['task_id']}: {log_entry['description']}")
                print(f"Success: {log_entry['final_success']}")

                attempts = log_entry.get('attempts', [])
                for i, attempt in enumerate(attempts):
                    print(f"\n  Attempt {i+1}:")
                    print(f"    Tool: {attempt.get('tool')}")
                    print(f"    Success: {attempt.get('success')}")
                    if not attempt['success']:
                        print(f"    Error: {attempt.get('error')}")

                    # Show validation details
                    validation = attempt.get('validation')
                    if validation:
                        print(f"    Validation: {validation.get('is_valid')}")
                        if not validation.get('is_valid'):
                            errors = validation.get('errors', [])
                            for err in errors:
                                print(f"      - {err}")

        return False


if __name__ == "__main__":
    # Test with challenging variants that require reflection
    variants = [
        "test_variant23_simple_jusuk",  # Simple case with annotations
        "test_variant24_jusuk_1",  # More complex annotations
        "test_variant16_definition_in_middle",  # Definition in middle
    ]

    results = {}
    for variant in variants:
        success = test_variant(variant)
        results[variant] = success

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY - Prototype 5 (Reflection)")
    print("="*80)
    for variant, success in results.items():
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status}: {variant}")
    print("="*80)

    # Overall result
    total = len(results)
    passed = sum(1 for s in results.values() if s)
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*80)
