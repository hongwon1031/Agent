"""
Prototype 3 Test Main - GT 형식 출력

definitions만 깔끔하게 출력하는 테스트용 메인 파일
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


def save_gt_result(definitions: list, total_count: int, output_path: str):
    """Save result in GT format (definitions only)"""
    try:
        gt_result = {
            "definitions": definitions,
            "total_count": total_count
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(gt_result, f, ensure_ascii=False, indent=2)
        print(f"\nGT result saved to: {output_path}")
    except Exception as e:
        print(f"\nError saving GT result: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_main.py <document_path_or_dir>")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    # GT 결과 디렉터리 고정
    gt_results_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_3\gt_results")
    gt_results_dir.mkdir(parents=True, exist_ok=True)

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

            # Extract definitions only
            if result['success']:
                final_data = result.get('final_data', {})
                definitions = final_data.get('definitions', [])
                total_count = final_data.get('total_count', len(definitions))

                output_path = gt_results_dir / f"{doc_path.stem}_gt.json"
                save_gt_result(definitions, total_count, str(output_path))

                # Console summary
                print(f"\n[OK] {len(definitions)} definitions extracted")
            else:
                print(f"\n[FAIL] {result.get('error')}")

        print("\nAll files processed.")
    else:
        # 단일 파일 모드
        doc_path = input_path
        print(f"\nInput document: {doc_path.name}")

        doc = load_document(str(doc_path))
        if doc is None:
            sys.exit(1)

        result = agent.run(doc)

        # Extract definitions only
        if result['success']:
            final_data = result.get('final_data', {})
            definitions = final_data.get('definitions', [])
            total_count = final_data.get('total_count', len(definitions))

            output_path = gt_results_dir / f"{doc_path.stem}_gt.json"
            save_gt_result(definitions, total_count, str(output_path))

            # Console summary
            print(f"\n[OK] {len(definitions)} definitions extracted")
            if definitions:
                print(f"\nSample (first 3):")
                for i, defn in enumerate(definitions[:3], 1):
                    print(f"  {i}. {json.dumps(defn, ensure_ascii=False)}")
                if len(definitions) > 3:
                    print(f"  ... and {len(definitions) - 3} more")
        else:
            print(f"\n[FAIL] {result.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
