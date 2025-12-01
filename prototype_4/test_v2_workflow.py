"""
Quick test for V2 Workflow (section_classifier + definition_extract_v2)
"""

import json
from pathlib import Path
from agent import Prototype3Agent


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

    # Run agent
    agent = Prototype3Agent(max_replan_per_task=3)
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
                if log_entry['attempts']:
                    last_attempt = log_entry['attempts'][-1]
                    if not last_attempt['success']:
                        print(f"Error: {last_attempt['error']}")

        return False


if __name__ == "__main__":
    # Test multiple challenging variants
    variants = [
        "test_variant18_missing_titles",  # Missing titles
        "test_variant19_split_definition",  # Definition split across sections
        "test_variant4_text_only_definition",  # Text-only (no table)
    ]

    results = {}
    for variant in variants:
        success = test_variant(variant)
        results[variant] = success

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
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
