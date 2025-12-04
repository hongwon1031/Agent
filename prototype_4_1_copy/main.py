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

def main():
    if len(sys.argv) < 2:
        print("Usage: python main_v2.py <document_path_or_dir>")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    # 결과 디렉터리 고정
    results_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_4_1_copy\results")
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

            output_path = results_dir / f"{doc_path.stem}_prototype4_1_copy_result.json"
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
        output_path = results_dir / f"{doc_path.stem}_prototype4_1_copy_result.json"
        save_result(result, str(output_path))

if __name__ == "__main__":
    main()