"""
only_plan.py가 생성한 execution_plan이
각 문서(document_analysis + raw parsed JSON)에 대해
적절한 툴과 메타데이터를 선택했는지 점검하는 스크립트.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent
RAW_DOC_DIR = BASE_DIR / "data" / "토이프로젝트_데이터" / "파싱결과"
ONLY_DOC_DIR = RAW_DOC_DIR / "only_doc"
ONLY_PLAN_DIR = RAW_DOC_DIR / "only_plan"


def resolve_access_path(root_obj: Any, access_path: str) -> Any:
    """
    access_path 예: "elements[0].paragraphs[0].table.table_elements"
    root_obj는 parsed.json의 0번째 요소(dict)를 넘기는 것을 가정.
    """
    current = root_obj
    for part in access_path.split("."):
        if "[" in part and part.endswith("]"):
            key, index_str = part[:-1].split("[", 1)
            if key:
                current = current[key]
            current = current[int(index_str)]
        else:
            current = current[part]
    return current


def validate_plan_for_document(
    doc_analysis: Dict[str, Any],
    raw_doc: List[Any],
    exec_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """
    하나의 문서에 대한 execution_plan 품질 점검.
    """
    results = {
        "has_definition_step": False,
        "definition_section_match": False,
        "definition_access_resolves": False,
        "has_condition_step": False,
        "condition_section_match": False,
        "has_formula_step_if_needed": False,
        "errors": [],
    }

    plan_steps: List[Dict[str, Any]] = exec_plan.get("plan", [])
    if not plan_steps:
        results["errors"].append("plan 배열이 비어 있음")
        return results

    def_section = doc_analysis["document_analysis"]["definition_section"]
    cond_section = doc_analysis["document_analysis"]["condition_section"]

    def_section_idx = def_section["section_index"]
    cond_section_idx = cond_section["section_index"]

    has_formula_in_doc = bool(cond_section.get("sample_conditions", {}).get("has_formula"))

    # raw_doc는 보통 [ { "doc_title": ..., "elements": [...] } ]
    if isinstance(raw_doc, list) and raw_doc:
        root = raw_doc[0]
    else:
        root = raw_doc

    # Definition step 검사
    for step in plan_steps:
        tool = (step.get("tool") or "").lower()
        if tool.startswith("definition"):
            results["has_definition_step"] = True
            meta = step.get("metadata", {})
            sec_idx = meta.get("section_index")
            if sec_idx == def_section_idx:
                results["definition_section_match"] = True

            access_path = meta.get("access_path")
            if access_path:
                try:
                    resolved = resolve_access_path(root, access_path)
                    if isinstance(resolved, list) and resolved:
                        results["definition_access_resolves"] = True
                    else:
                        results["errors"].append(
                            f"Definition step access_path는 해석되지만 유효한 row 리스트가 아님: {access_path}"
                        )
                except Exception as e:
                    results["errors"].append(
                        f"Definition step access_path 해석 실패 ({access_path}): {e}"
                    )
            break

    if not results["has_definition_step"]:
        results["errors"].append("Definition* 툴을 사용하는 step이 없음")

    # Condition step 검사
    for step in plan_steps:
        tool = (step.get("tool") or "").lower()
        if tool.startswith("condition"):
            results["has_condition_step"] = True
            meta = step.get("metadata", {})
            sec_idx = meta.get("section_index")
            if sec_idx == cond_section_idx:
                results["condition_section_match"] = True
            else:
                results["errors"].append(
                    f"Condition step section_index 불일치: expected {cond_section_idx}, got {sec_idx}"
                )
            break

    if not results["has_condition_step"]:
        results["errors"].append("Condition* 툴을 사용하는 step이 없음")

    # FormulaEvaluator step 검사 (문서에 수식이 있을 때만)
    if has_formula_in_doc:
        has_formula_step = any(
            "formula" in (s.get("tool") or "").lower() for s in plan_steps
        )
        results["has_formula_step_if_needed"] = has_formula_step
        if not has_formula_step:
            results["errors"].append(
                "sample_conditions.has_formula = true 인데 Formula* 툴 step이 없음"
            )
    else:
        # 필요 없으면 true로 간주
        results["has_formula_step_if_needed"] = True

    return results


def main():
    if not ONLY_PLAN_DIR.exists():
        print(f"[WARN] only_plan 디렉터리가 없습니다: {ONLY_PLAN_DIR}")
        return

    exec_files = sorted(ONLY_PLAN_DIR.glob("*_execution_plan.json"))

    print(f"\n{'='*80}")
    print(f"only_plan.py 실행 계획 검증 (총 {len(exec_files)}개 파일)")
    print(f"{'='*80}\n")

    summary = {
        "total": len(exec_files),
        "passed": 0,
        "failed": 0,
        "details": [],
    }

    for exec_file in exec_files:
        base_name = exec_file.stem.replace("_execution_plan", "")
        raw_file = RAW_DOC_DIR / f"{base_name}.json"
        doc_plan_file = ONLY_DOC_DIR / f"{base_name}_plan.json"

        print(f"\n{'-'*80}")
        print(f"[TARGET] {exec_file.name}")

        if not raw_file.exists():
            print(f"[SKIP] 원본 parsed 파일 없음: {raw_file.name}")
            continue
        if not doc_plan_file.exists():
            print(f"[SKIP] only_doc 분석 파일 없음: {doc_plan_file.name}")
            continue

        doc_analysis = json.load(doc_plan_file.open("r", encoding="utf-8"))
        raw_doc = json.load(raw_file.open("r", encoding="utf-8"))
        exec_plan = json.load(exec_file.open("r", encoding="utf-8"))

        results = validate_plan_for_document(doc_analysis, raw_doc, exec_plan)

        print("  - Definition step 존재:", results["has_definition_step"])
        print("  - Definition section 매칭:", results["definition_section_match"])
        print("  - Definition access_path 유효:", results["definition_access_resolves"])
        print("  - Condition step 존재:", results["has_condition_step"])
        print("  - Condition section 매칭:", results["condition_section_match"])
        print("  - Formula step 필요시 존재:", results["has_formula_step_if_needed"])

        if results["errors"]:
            print("  ! Errors:")
            for err in results["errors"]:
                print("    -", err)

        all_passed = (
            results["has_definition_step"]
            and results["definition_section_match"]
            and results["definition_access_resolves"]
            and results["has_condition_step"]
            and results["condition_section_match"]
            and results["has_formula_step_if_needed"]
        )

        if all_passed:
            print("  => ✅ PASS")
            summary["passed"] += 1
        else:
            print("  => ❌ FAIL")
            summary["failed"] += 1

        summary["details"].append(
            {
                "file": exec_file.name,
                "passed": all_passed,
                **results,
            }
        )

    print(f"\n{'='*80}")
    print("종합 결과")
    print(f"{'='*80}")
    print("총 파일:", summary["total"])
    print("PASS   :", summary["passed"])
    print("FAIL   :", summary["failed"])
    if summary["total"]:
        rate = summary["passed"] / summary["total"] * 100
        print(f"Pass 비율: {rate:.1f}%")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

