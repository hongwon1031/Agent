import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# 원본 파싱 결과와 실행 계획 경로
PARSED_PATH = BASE_DIR / "data" / "토이프로젝트_데이터" / "파싱결과" / "(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json"
EXEC_PLAN_PATH = BASE_DIR / "data" / "토이프로젝트_데이터" / "파싱결과" / "only_plan" / "(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed_execution_plan.json"


def resolve_access_path(root_obj, access_path: str):
    """
    access_path 예: "elements[0].paragraphs[0].table.table_elements"
    root_obj는 parsed.json의 문서(dict 또는 list의 0번째)라고 가정.
    """
    current = root_obj
    parts = access_path.split(".")

    for part in parts:
        if "[" in part and part.endswith("]"):
            # 예: "elements[0]"
            key, index_str = part[:-1].split("[", 1)
            if key:
                current = current[key]
            idx = int(index_str)
            current = current[idx]
        else:
            current = current[part]

    return current


def load_data():
    with PARSED_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # parsed.json은 보통 [ { "doc_title": ..., "elements": [...] } ] 형태
    if isinstance(raw, list) and raw:
        doc = raw[0]
    else:
        doc = raw

    with EXEC_PLAN_PATH.open("r", encoding="utf-8") as f:
        plan = json.load(f)

    return doc, plan


def print_definition_and_condition():
    doc, plan = load_data()

    steps = plan.get("plan", [])

    print("=== Definition Steps ===")
    for step in steps:
        tool = step.get("tool", "")
        if not tool.lower().startswith("definition"):
            continue

        meta = step.get("metadata", {})
        access_path = meta.get("access_path")
        if not access_path:
            continue

        table_elements = resolve_access_path(doc, access_path)

        target_columns = meta.get("target_columns") or meta.get("hierarchy_info", {}).get("columns") or []

        print(f"\n[Step {step.get('step')}] tool={tool}")
        print(f"access_path = {access_path}")
        print("rows:")
        for row in table_elements:
            if target_columns:
                out = {col: row.get(col) for col in target_columns}
            else:
                out = row
            print(out)

    print("\n=== Condition Steps ===")
    for step in steps:
        tool = step.get("tool", "")
        if not tool.lower().startswith("condition"):
            continue

        meta = step.get("metadata", {})
        section_index = meta.get("section_index")
        if section_index is None:
            continue

        # section_index를 이용해 해당 섹션의 paragraph들에 접근
        elements = doc.get("elements") or []
        if not (0 <= section_index < len(elements)):
            continue

        section = elements[section_index]
        paragraphs = section.get("paragraphs", [])

        subtitle_mappings = meta.get("subtitle_mappings") or []

        print(f"\n[Step {step.get('step')}] tool={tool}")
        print(f"section_index = {section_index}")

        for mapping in subtitle_mappings:
            table_idx = mapping.get("table_index")
            if table_idx is None or not (0 <= table_idx < len(paragraphs)):
                continue

            para = paragraphs[table_idx]
            table = para.get("table", {}).get("table_elements", [])

            subtitle = mapping.get("subtitle")
            print(f"\n  - subtitle: {subtitle} (table_index={table_idx})")
            print("    rows:")
            for row in table:
                print(f"      {row}")


if __name__ == "__main__":
    print_definition_and_condition()
