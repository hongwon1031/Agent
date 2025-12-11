"""
Prototype 7 Main Entry Point

Dynamic Task Execution System with True Backtracking
"""

import json
import sys
import argparse
from pathlib import Path
from agent import  Prototype7Agent


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

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="Prototype 8 Agent - Dynamic Task Execution")
    parser.add_argument("input_path", type=str, help="Input document path or directory")
    parser.add_argument("--prototype", type=int, choices=[6, 7], default=7,
                        help="Prototype version to use (6=legacy, 7=dynamic) [default: 7]")

    args = parser.parse_args()
    input_path = Path(args.input_path)

    # Select agent

    print("\n🚀 Using Prototype 7: Dynamic Task Execution Agent")
    agent = Prototype7Agent()
    results_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8\new_results")


    results_dir.mkdir(parents=True, exist_ok=True)

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
            # 필요 시 task_results를 포함시킴
            if "task_results" not in result and hasattr(agent, "task_results"):
                result["task_results"] = getattr(agent, "task_results", [])
                result["debug_logs"] = agent.debug_logs  # 필요하다면
            output_path = results_dir / f"{doc_path.stem}_new_result.json"
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

        # 필요하면 task_results를 result에 넣어줌 (이미 포함돼 있으면 생략)
        if "task_results" not in result and hasattr(agent, "task_results"):
            result["task_results"] = getattr(agent, "task_results", [])
            result["debug_logs"] = agent.debug_logs  # 필요하다면
        output_path = results_dir / f"{doc_path.stem}_single_result.json"
        save_result(result, str(output_path))


if __name__ == "__main__":
    main()