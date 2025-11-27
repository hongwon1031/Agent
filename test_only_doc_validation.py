"""
only_doc.py 출력 검증 스크립트
Document Analyzer가 구조를 제대로 파악했는지 확인
"""
import json
from pathlib import Path
from typing import Dict, Any


def validate_definition_section(doc_analysis: Dict, raw_doc: list) -> Dict[str, Any]:
    """Definition section 검증"""
    results = {
        "section_index_correct": False,
        "location_correct": False,
        "hierarchy_depth_correct": False,
        "hierarchy_values_exist": False,
        "errors": []
    }

    def_section = doc_analysis["document_analysis"]["definition_section"]
    section_idx = def_section["section_index"]

    try:
        # 1. section_index 검증
        actual_section = raw_doc[0]["elements"][section_idx]
        title_lower = actual_section["title"].lower()
        if any(keyword in title_lower for keyword in ["명칭", "보험종목", "정의"]):
            results["section_index_correct"] = True
        else:
            results["errors"].append(f"Section index {section_idx}의 제목이 정의 섹션이 아님: {actual_section['title']}")

        # 2. primary_table_index 검증
        primary_table_idx = def_section["location"]["primary_table_index"]
        table_para = actual_section["paragraphs"][primary_table_idx]
        if table_para["type"] == "table":
            results["location_correct"] = True
        else:
            results["errors"].append(f"Primary table index {primary_table_idx}가 table이 아님: {table_para['type']}")

        # 3. 계층 깊이 검증
        hierarchy_depth = def_section["sample_data"]["hierarchy_depth"]
        table_elements = table_para["table"]["table_elements"]
        if table_elements:
            actual_columns = len(table_elements[0].keys())
            if hierarchy_depth <= actual_columns:
                results["hierarchy_depth_correct"] = True
            else:
                results["errors"].append(f"계층 깊이 {hierarchy_depth}가 실제 컬럼 수 {actual_columns}보다 큼")

        # 4. 계층 values 검증
        all_values_exist = True
        for level in def_section["sample_data"]["계층구조"]:
            column_name = level["column_name"]
            declared_values = level["values"]

            # 실제 데이터에서 해당 컬럼의 모든 고유값 추출
            actual_values = set()
            for row in table_elements:
                if column_name in row:
                    val = row[column_name]
                    if val:  # None이나 빈 문자열 제외
                        # 원본 값을 추가
                        actual_values.add(val.strip())

                        # 줄바꿈 제거한 버전도 추가 (Document Analyzer가 정규화할 수 있음)
                        # 예: "경증이상치매보장특약\n(무배당, 해약환급금 미지급형)" → "경증이상치매보장특약(무배당, 해약환급금 미지급형)"
                        normalized = val.replace('\n', '').strip()
                        actual_values.add(normalized)

                        # 줄바꿈/슬래시로 구분된 값들도 개별적으로 추가
                        # 예: "간편심사(315)형\n/간편심사(335)형" → ["간편심사(315)형", "간편심사(335)형"]
                        if '\n/' in val or '\n' in val or '/' in val:
                            # 줄바꿈과 슬래시로 분리
                            parts = val.replace('\n/', '/').replace('\n', '/').split('/')
                            for part in parts:
                                cleaned = part.strip()
                                if cleaned:
                                    actual_values.add(cleaned)

            # 선언된 값이 실제로 존재하는지 확인
            for val in declared_values:
                if val not in actual_values:
                    results["errors"].append(f"Level {level['level']}, 컬럼 {column_name}: 값 '{val}'이 실제 데이터에 없음")
                    all_values_exist = False

        results["hierarchy_values_exist"] = all_values_exist

    except Exception as e:
        results["errors"].append(f"검증 중 오류: {str(e)}")

    return results


def validate_condition_section(doc_analysis: Dict, raw_doc: list) -> Dict[str, Any]:
    """Condition section 검증"""
    results = {
        "section_index_correct": False,
        "paragraph_map_correct": False,
        "subtitle_mapping_correct": False,
        "errors": []
    }

    cond_section = doc_analysis["document_analysis"]["condition_section"]
    section_idx = cond_section["section_index"]

    try:
        # 1. section_index 검증
        actual_section = raw_doc[0]["elements"][section_idx]
        title_lower = actual_section["title"].lower()
        if any(keyword in title_lower for keyword in ["가입", "보험기간", "납입기간", "조건"]):
            results["section_index_correct"] = True
        else:
            results["errors"].append(f"Section index {section_idx}의 제목이 조건 섹션이 아님: {actual_section['title']}")

        # 2. paragraph_map 검증
        paragraph_map = cond_section["location"]["paragraph_map"]
        actual_paragraphs = actual_section["paragraphs"]

        if len(paragraph_map) == len(actual_paragraphs):
            results["paragraph_map_correct"] = True
        else:
            results["errors"].append(f"Paragraph map 길이 {len(paragraph_map)} != 실제 paragraphs 길이 {len(actual_paragraphs)}")

        # 3. subtitle_mapping 검증
        if "condition_hierarchy" in cond_section and "subtitle_mapping" in cond_section["condition_hierarchy"]:
            subtitle_mapping = cond_section["condition_hierarchy"]["subtitle_mapping"]
            all_mappings_correct = True

            for mapping in subtitle_mapping:
                subtitle_idx = mapping["paragraph_index"]
                table_idx = mapping["table_index"]

                # subtitle_idx가 실제로 title인지 확인
                if subtitle_idx < len(actual_paragraphs):
                    subtitle_para = actual_paragraphs[subtitle_idx]
                    if subtitle_para["type"] != "title":
                        results["errors"].append(f"Subtitle index {subtitle_idx}가 title이 아님: {subtitle_para['type']}")
                        all_mappings_correct = False

                # table_idx가 실제로 table인지 확인
                if table_idx < len(actual_paragraphs):
                    table_para = actual_paragraphs[table_idx]
                    if table_para["type"] != "table":
                        results["errors"].append(f"Table index {table_idx}가 table이 아님: {table_para['type']}")
                        all_mappings_correct = False

            results["subtitle_mapping_correct"] = all_mappings_correct

    except Exception as e:
        results["errors"].append(f"검증 중 오류: {str(e)}")

    return results


def main():
    """모든 only_doc 출력 검증"""
    only_doc_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc")
    raw_doc_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과")

    if not only_doc_dir.exists():
        print(f"❌ only_doc 디렉토리가 존재하지 않습니다: {only_doc_dir}")
        return

    plan_files = list(only_doc_dir.glob("*_plan.json"))

    print(f"\n{'='*80}")
    print(f"only_doc.py 출력 검증 시작 (총 {len(plan_files)}개 파일)")
    print(f"{'='*80}\n")

    total_results = {
        "total": len(plan_files),
        "passed": 0,
        "failed": 0,
        "details": []
    }

    for plan_file in plan_files:
        # 원본 파일명 추출
        base_name = plan_file.stem.replace("_parsed_plan", "_parsed")
        raw_file = raw_doc_dir / f"{base_name}.json"

        if not raw_file.exists():
            print(f"⚠️  원본 파일 없음: {raw_file.name}")
            continue

        print(f"\n{'─'*80}")
        print(f"📄 {plan_file.name}")
        print(f"{'─'*80}")

        # JSON 로드
        doc_analysis = json.load(plan_file.open("r", encoding="utf-8"))
        raw_doc = json.load(raw_file.open("r", encoding="utf-8"))

        # Definition section 검증
        def_results = validate_definition_section(doc_analysis, raw_doc)
        print("\n[Definition Section]")
        print(f"  ✅ Section index: {def_results['section_index_correct']}")
        print(f"  ✅ Location: {def_results['location_correct']}")
        print(f"  ✅ Hierarchy depth: {def_results['hierarchy_depth_correct']}")
        print(f"  ✅ Hierarchy values: {def_results['hierarchy_values_exist']}")

        # Condition section 검증
        cond_results = validate_condition_section(doc_analysis, raw_doc)
        print("\n[Condition Section]")
        print(f"  ✅ Section index: {cond_results['section_index_correct']}")
        print(f"  ✅ Paragraph map: {cond_results['paragraph_map_correct']}")
        print(f"  ✅ Subtitle mapping: {cond_results['subtitle_mapping_correct']}")

        # 에러 출력
        all_errors = def_results["errors"] + cond_results["errors"]
        if all_errors:
            print("\n⚠️  Errors:")
            for err in all_errors:
                print(f"     - {err}")

        # 결과 집계
        all_passed = (
            def_results["section_index_correct"] and
            def_results["location_correct"] and
            def_results["hierarchy_depth_correct"] and
            def_results["hierarchy_values_exist"] and
            cond_results["section_index_correct"] and
            cond_results["paragraph_map_correct"] and
            cond_results["subtitle_mapping_correct"]
        )

        if all_passed:
            print("\n✅ 전체 검증 통과")
            total_results["passed"] += 1
        else:
            print("\n❌ 검증 실패")
            total_results["failed"] += 1

        total_results["details"].append({
            "file": plan_file.name,
            "passed": all_passed,
            "definition": def_results,
            "condition": cond_results
        })

    # 최종 결과
    print(f"\n{'='*80}")
    print("📊 최종 결과")
    print(f"{'='*80}")
    print(f"총 파일 수: {total_results['total']}")
    print(f"✅ 통과: {total_results['passed']}")
    print(f"❌ 실패: {total_results['failed']}")
    print(f"통과율: {total_results['passed'] / total_results['total'] * 100:.1f}%")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
