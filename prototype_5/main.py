"""
Prototype 3 Main Entry Point (Version 2 - Full Implementation)

완전히 구현된 일반화 Agent 시스템
"""

import json
import sys
from pathlib import Path
from agent import Prototype3Agent


def load_document(doc_path: str):
    """Load JSON document"""
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading document: {e}")
        return None


def save_result(result: dict, output_path: str):
    """Save result to JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nResult saved to: {output_path}")
    except Exception as e:
        print(f"\nError saving result: {e}")


# def main():
#     """Main execution"""
#     if len(sys.argv) < 2:
#         print("Usage: python main_v2.py <document_path> [output_path]")
#         print("\nExample:")
#         print('  python main_v2.py "C:/path/to/document.json"')
#         print('  python main_v2.py "C:/path/to/document.json" "output.json"')
#         sys.exit(1)

#     doc_path = sys.argv[1]

#     # Determine output path
#     # if len(sys.argv) >= 3:
#     #     output_path = sys.argv[2]
#     # else:
#     #     input_file = Path(doc_path)
#     #     output_path = str(input_file.parent / f"{input_file.stem}_prototype3_result.json")

#     output_path = r"C:\Users\NT-165\Desktop\Project\Toy\prototype_3\results\1.json"
#     print(f"\n📄 Input document: {Path(doc_path).name}")
#     print(f"💾 Output path: {output_path}\n")

#     # Load document
#     doc = load_document(doc_path)
#     if doc is None:
#         sys.exit(1)

#     # Create and run agent
#     agent = Prototype3Agent(max_replan_per_task=3)
#     result = agent.run(doc)

#     # Display summary
#     print("\n" + "="*80)
#     print("EXECUTION SUMMARY")
#     print("="*80)
#     print(f"Success: {result['success']}")

#     if result['success']:
#         # Document analysis
#         doc_analysis = result.get('document_analysis', {})
#         print(f"\n📊 Document Analysis:")
#         print(f"  - Structure: {doc_analysis.get('structure_type')}")
#         print(f"  - Sections: {doc_analysis.get('total_sections_estimate')}")

#         # Execution plan
#         plan = result.get('execution_plan', {})
#         tasks = plan.get('tasks', [])
#         print(f"\n📋 Execution Plan:")
#         print(f"  - Total tasks: {len(tasks)}")
#         print(f"  - Difficulty: {plan.get('estimated_difficulty')}")

#         # Final data
#         final_data = result.get('final_data', {})
#         definitions = final_data.get('definitions', [])
#         print(f"\n🎯 Final Result:")
#         print(f"  - Total definitions: {len(definitions)}")

#         if definitions:
#             print(f"\n  Sample definitions (first 3):")
#             for i, defn in enumerate(definitions[:3], 1):
#                 print(f"    {i}. {json.dumps(defn, ensure_ascii=False)}")
#             if len(definitions) > 3:
#                 print(f"    ... and {len(definitions) - 3} more")

#         # Execution log
#         execution_log = result.get('execution_log', [])
#         print(f"\n📝 Execution Log:")
#         for log_entry in execution_log:
#             task_id = log_entry['task_id']
#             desc = log_entry['description']
#             attempts = len(log_entry['attempts'])
#             success = log_entry['final_success']
#             status = "✅" if success else "❌"
#             print(f"  {status} Task {task_id}: {desc} ({attempts} attempts)")

#     else:
#         print(f"\n❌ Error: {result.get('error')}")

#         # Show execution log for debugging
#         execution_log = result.get('execution_log', [])
#         if execution_log:
#             print(f"\n📝 Execution Log:")
#             for log_entry in execution_log:
#                 print(f"  Task {log_entry['task_id']}: {log_entry['description']}")
#                 for attempt in log_entry['attempts']:
#                     print(f"    Attempt {attempt['attempt']}: {attempt['tool']}")
#                     if not attempt['success']:
#                         print(f"      Error: {attempt['error']}")
#                     if attempt.get('validation'):
#                         val = attempt['validation']
#                         print(f"      Validation: {'✅' if val['is_valid'] else '❌'}")
#                         if not val['is_valid']:
#                             for err in val.get('errors', []):
#                                 print(f"        - {err}")

#     # Save result
#     save_result(result, output_path)

#     print("\n" + "="*80)
#     print("Done!")
#     print("="*80)


# if __name__ == "__main__":
#     main()
def main():
    if len(sys.argv) < 2:
        print("Usage: python main_v2.py <document_path_or_dir>")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    # 결과 디렉터리 고정
    results_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_5\results")
    results_dir.mkdir(parents=True, exist_ok=True)

    agent = Prototype3Agent(max_replan_per_task=3)

    if input_path.is_dir():
        # 디렉터리 모드: 모든 .json 처리
        json_files = sorted(input_path.glob("*.json"))
        if not json_files:
            print(f"No .json files found in {input_path}")
            return

        for doc_path in json_files:
            print("\n" + "="*80)
            print(f"Processing: {doc_path.name}")
            print("="*80)

            doc = load_document(str(doc_path))
            if doc is None:
                continue

            result = agent.run(doc)

            output_path = results_dir / f"{doc_path.stem}_prototype5_result.json"
            save_result(result, str(output_path))

        print("\nAll files processed.")
    else:
        # 단일 파일 모드 (기존 동작 유지)
        doc_path = input_path
        print(f"\nInput document: {doc_path.name}")

        doc = load_document(str(doc_path))
        if doc is None:
            sys.exit(1)

        result = agent.run(doc)
        output_path = results_dir / f"{doc_path.stem}_prototype5_result.json"
        save_result(result, str(output_path))

if __name__ == "__main__":
    main()