"""
Prototype Agent for Insurance Definition Extraction
"""
import json
from pathlib import Path
from typing import Dict
from replanner import SimpleReplanner
from executor import ToolExecutor
from validator import SimpleValidator


class PrototypeAgent:
    def __init__(self, max_replans: int = 2):
        self.replanner = SimpleReplanner()
        self.executor = ToolExecutor()
        self.validator = SimpleValidator()
        self.max_replans = max_replans

    def run(self, document_path: str, doc_analysis_path: str = None) -> Dict:
        """
        End-to-End 실행
        """
        # 1. Load document
        with open(document_path, encoding="utf-8") as f:
            doc = json.load(f)

        # 2. Load document analysis (location 정보)
        if doc_analysis_path:
            with open(doc_analysis_path, encoding="utf-8") as f:
                doc_analysis = json.load(f)
        else:
            doc_analysis = None

        print(f"\n{'='*70}")
        print(f"📄 Processing: {Path(document_path).name}")
        print(f"{'='*70}\n")

        # 3. Initial Planning (doc_analysis 전달)
        plan = self.replanner.create_initial_plan(doc, doc_analysis)

        # 3. Execution Loop
        replan_count = 0
        result = None

        while replan_count <= self.max_replans:
            print(f"\n{'─'*70}")
            print(f"🚀 Attempt {replan_count + 1}/{self.max_replans + 1}")
            print(f"{'─'*70}")

            # Execute plan
            result = self.executor.execute_plan(doc, plan)

            if result.success:
                # ✅ Tool 실행은 성공했지만, 결과를 검증
                validation = self.validator.validate(result.final_data)

                if validation["is_valid"]:
                    print(f"\n{'='*70}")
                    print(f"✅ SUCCESS on attempt {replan_count + 1}")
                    print(f"{'='*70}\n")

                    # 결과 일부 출력
                    definitions = result.final_data.get("definitions", [])
                    print(f"📊 Total combinations: {len(definitions)}")
                    print(f"\n🔍 First 3 results:")
                    for i, item in enumerate(definitions[:3], 1):
                        print(f"  {i}. {json.dumps(item, ensure_ascii=False)}")

                    return {
                        "success": True,
                        "data": result.final_data,
                        "replan_count": replan_count,
                        "execution_log": result.execution_log,
                        "validation": validation
                    }
                else:
                    # ⚠️ Validation 실패 → Replanning 필요
                    print(f"\n⚠️  Tool succeeded but validation failed:")
                    for error in validation["errors"]:
                        print(f"    - {error}")

                    # Execution log에 validation 에러 추가
                    result.execution_log[-1]["validation_errors"] = validation["errors"]

            # 4. Replanning
            if replan_count < self.max_replans:
                if result.success:
                    print(f"\n🔄 Replanning due to validation failure...\n")
                else:
                    print(f"\n⚠️  Execution failed. Replanning...\n")
                plan = self.replanner.replan(doc, doc_analysis, result.execution_log)
                replan_count += 1
            else:
                print(f"\n{'='*70}")
                print(f"❌ FAILED after {self.max_replans + 1} attempts")
                print(f"{'='*70}\n")
                break

        return {
            "success": False,
            "data": {},
            "replan_count": replan_count,
            "execution_log": result.execution_log if result else []
        }


# 실행 예제
if __name__ == "__main__":
    agent = PrototypeAgent(max_replans=2)

    # 테스트 문서
    doc_path = r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json"
    doc_analysis_path = r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed_plan.json"

    result = agent.run(doc_path, doc_analysis_path)

    # 결과 저장
    output_path = r"c:\Users\NT-165\Desktop\Project\Toy\prototype\results\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Result saved to: {output_path}")
