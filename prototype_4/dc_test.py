# dc_test.py
import json
from pathlib import Path

from core.document_accessor import DocumentAccessor


def load_docs(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def inspect_doc(doc, label: str, src_path: Path):
    print("=" * 80)
    print(f"[DOC] {label}")
    print("=" * 80)

    accessor = DocumentAccessor(doc)
    sections = accessor.get_all_sections()

    # --- 섹션 구조 저장용 JSON 생성 ---
    sections_dump = []
    for s in sections:
        sections_dump.append({
            "index": s.index,
            "title": s.title,
            "content_items": s.content_items,
            "metadata": getattr(s, "metadata", None),
        })

    out_path = Path(__file__).with_name(f"{src_path.stem}_sections.json")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(sections_dump, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] Sections dumped to: {out_path}")

    # --- 기존 요약 출력 ---
    print(f"- format: {accessor.format}")
    print(f"- total sections: {len(sections)}")
    print()

    for s in sections:
        idx = s.index
        title = s.title or "(no title)"
        print(f"[Section {idx}] {title}")

        content_items = s.content_items
        types = []
        for item in content_items:
            if isinstance(item, dict):
                if "table" in item:
                    types.append("table")
                elif "content" in item or "text" in item:
                    types.append("text")
                else:
                    types.append("other")
            else:
                types.append(type(item).__name__)

        print(f"  - content types: {types}")
        for item in content_items[:2]:
            if isinstance(item, dict) and "table" in item:
                table = item["table"]
                headers = []
                if isinstance(table, dict):
                    elems = table.get("table_elements") or []
                    if elems and isinstance(elems[0], dict):
                        headers = list(elems[0].keys())
                print(f"    * table preview headers: {headers}")
            elif isinstance(item, dict):
                text = item.get("content") or item.get("text") or ""
                if isinstance(text, str):
                    d = text[:80].replace('\\n', ' ')
                    print(f"* text preview: {d}")
        print()


def main():
    base = Path(__file__).resolve().parent.parent
    file_path = base / "data" / "토이프로젝트_데이터" / "파싱결과"/ "신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json"
    
    docs = load_docs(file_path)
    for i, doc in enumerate(docs):
        label = f"{file_path.name} (doc[{i}])"
        inspect_doc(doc, label, file_path)


if __name__ == "__main__":
    main()
