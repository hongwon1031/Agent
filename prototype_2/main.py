"""
Main entry point for prototype_2 agent.
Processes insurance documents and extracts all definition combinations.

이 프로그램의 진입점입니다. 명령줄 인자로 문서 경로를 받아 처리합니다.

사용법:
    python main.py <document_path> [output_path]

예시:
    python main.py "data/문서.json"
    python main.py "data/문서.json" "결과.json"

동작 흐름:
    1. 문서 로드 (JSON 파일)
    2. MultiStepAgent 생성
    3. Agent 실행 (Plan → Execute → Validate → Replan → Result)
    4. 결과 출력 및 저장
"""

import json
import sys
import os
from pathlib import Path
from agent import MultiStepAgent


def load_document(doc_path: str):
    """
    파싱된 보험 문서 JSON 로드

    Args:
        doc_path (str): 문서 파일 경로

    Returns:
        List[Dict] or None: 로드된 문서 또는 None (실패 시)
    """
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        return doc
    except Exception as e:
        print(f"Error loading document: {e}")
        return None


def save_result(result: dict, output_path: str):
    """Save agent execution result to JSON file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] Result saved to: {output_path}")
    except Exception as e:
        print(f"\nError saving result: {e}")


def main():
    """Main execution function."""

    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python main.py <document_path> [output_path]")
        print("\nExample:")
        print('  python main.py "C:/path/to/document.json"')
        print('  python main.py "C:/path/to/document.json" "output.json"')
        sys.exit(1)

    doc_path = sys.argv[1]

    # Determine output path
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        # Default: same directory as input, with _result suffix
        input_file = Path(doc_path)
        output_path = str(input_file.parent / f"{input_file.stem}_result.json")

    print("="*80)
    print("Prototype 2: Multi-Step Agent with LLM Validator")
    print("="*80)
    print(f"\nInput document: {doc_path}")
    print(f"Output path: {output_path}")

    # Load document
    print("\nLoading document...")
    doc = load_document(doc_path)

    if doc is None:
        print("Failed to load document. Exiting.")
        sys.exit(1)

    print(f"[OK] Document loaded successfully")

    # Create and run agent
    print("\nInitializing agent...")
    agent = MultiStepAgent(max_replan_per_task=3)

    print("Running agent...")
    result = agent.run(doc)

    # Display result summary
    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Success: {result['success']}")

    if result['success']:
        definitions = result['final_data'].get('definitions', [])
        print(f"Total definitions extracted: {len(definitions)}")
        print(f"\nSample definitions (first 3):")
        for i, defn in enumerate(definitions[:3], 1):
            print(f"  {i}. {json.dumps(defn, ensure_ascii=False)}")
        if len(definitions) > 3:
            print(f"  ... and {len(definitions) - 3} more")
    else:
        print(f"Error: {result['error']}")

    print(f"\nTotal tasks in execution log: {len(result['execution_log'])}")

    # Save result
    save_result(result, output_path)

    print("\n" + "="*80)
    print("Done!")
    print("="*80)


if __name__ == "__main__":
    main()
