"""
location 정보를 사용하여 원본 문서에 접근하는 예제 코드
"""
import json
from pathlib import Path


def test_definition_access():
    """Definition section에 location 정보로 접근"""

    # 1. 원본 문서 로드
    raw_doc_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json")
    raw_doc = json.load(raw_doc_path.open("r", encoding="utf-8"))

    # 2. document_analysis 로드 (only_doc.py로 생성한 결과)
    analysis_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed_plan.json")

    if not analysis_path.exists():
        print(f"❌ 먼저 only_doc.py를 실행하여 plan을 생성하세요: {analysis_path}")
        return

    analysis = json.load(analysis_path.open("r", encoding="utf-8"))

    # 3. Definition section 접근
    def_section = analysis["document_analysis"]["definition_section"]
    section_idx = def_section["section_index"]

    # ✅ location 정보로 바로 접근!
    location = def_section["location"]
    primary_table_idx = location["primary_table_index"]

    # 원본 문서에서 정확한 위치로 접근
    section = raw_doc[0]["elements"][section_idx]
    table_para = section["paragraphs"][primary_table_idx]
    table_elements = table_para["table"]["table_elements"]

    print("✅ Definition Section 접근 성공!")
    print(f"   Section: {section['title']}")
    print(f"   Primary Table Index: {primary_table_idx}")
    print(f"   Table Elements Count: {len(table_elements)}")
    print(f"   계층 정보: {def_section['sample_data']['계층구조']}")
    print()

    # 실제 데이터 확인
    print("📊 Table Elements 샘플:")
    for i, elem in enumerate(table_elements[:]):
        print(f"   Row {i}: {elem}")

    return True


def test_condition_access():
    """Condition section에 location 정보로 접근"""

    # 1. 원본 문서 로드
    raw_doc_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json")
    raw_doc = json.load(raw_doc_path.open("r", encoding="utf-8"))

    # 2. document_analysis 로드
    analysis_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed_plan.json")

    if not analysis_path.exists():
        print(f"❌ 먼저 only_doc.py를 실행하여 plan을 생성하세요: {analysis_path}")
        return

    analysis = json.load(analysis_path.open("r", encoding="utf-8"))

    # 3. Condition section 접근
    cond_section = analysis["document_analysis"]["condition_section"]
    section_idx = cond_section["section_index"]

    # ✅ location 정보로 paragraph map 확인
    location = cond_section["location"]
    paragraph_map = location["paragraph_map"]

    section = raw_doc[0]["elements"][section_idx]

    print("✅ Condition Section 접근 성공!")
    print(f"   Section: {section['title']}")
    print(f"   Total Paragraphs: {len(section['paragraphs'])}")
    print()

    print("📍 Paragraph Map:")
    print(paragraph_map)
    #print("📍 section")
    #print(section)
    for p in paragraph_map[:]:  # 처음 5개만
        print("📍 para")
        para = section["paragraphs"][p["index"]]
        content = p.get("content")
        if not content:
            content = para.get("table", {}).get("table_title", "N/A")

        print(f"   [{p['index']}] {p['type']}: {content}")


    print()

    # 4. subtitle_mapping으로 소제목 ↔ 표 매핑
    if "condition_hierarchy" in cond_section:
        subtitle_mapping = cond_section["condition_hierarchy"]["subtitle_mapping"]

        print("🔗 Subtitle → Table Mapping:")
        for mapping in subtitle_mapping[:]:  # 처음 2개만
            subtitle_idx = mapping["paragraph_index"]
            table_idx = mapping["table_index"]

            subtitle_para = section["paragraphs"][subtitle_idx]
            table_para = section["paragraphs"][table_idx]

            print(f"   소제목 [{subtitle_idx}]: {subtitle_para['content']}")
            print(f"   → 표 [{table_idx}]: {table_para['table']['table_title']}")
            print(f"      유형 정보: {mapping['table_types']}")
            print()

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Location 정보 접근 테스트")
    print("=" * 60)
    print()

    print("1️⃣ Definition Section 테스트")
    print("-" * 60)
    test_definition_access()

    print()
    print("2️⃣ Condition Section 테스트")
    print("-" * 60)
    test_condition_access()

    print()
    print("=" * 60)
    print("✅ 모든 테스트 완료!")
    print("=" * 60)
