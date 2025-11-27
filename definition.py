import json
from typing import Any, Dict, List, Optional

from openai import OpenAI


def _resolve_access_path(root_obj: Any, access_path: str) -> Any:
    """
    access_path 예시: "elements[0].paragraphs[0].table.table_elements"

    raw_doc는 [{doc_title, elements: [...]}] 형태이므로,
    먼저 [0]을 자동으로 적용한 후 access_path를 따라간다.
    """
    # raw_doc가 리스트인 경우 첫 번째 요소 가져오기
    if isinstance(root_obj, list):
        current = root_obj[0]
    else:
        current = root_obj

    for part in access_path.split("."):
        if "[" in part and part.endswith("]"):
            # "elements[0]" 또는 "[0]" 형태
            key, index_str = part[:-1].split("[", 1)
            if key:  # "elements[0]" 형태
                current = current[key]
            # 인덱스 접근
            current = current[int(index_str)]
        else:
            # "table" 또는 "table_elements" 형태
            if isinstance(current, dict):
                current = current[part]
            else:
                raise TypeError(f"Cannot access key '{part}' on non-dict type: {type(current)}")

    return current


def extract_definition_rule(doc: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
    metadata = step.get("metadata", {})
    access_path: Optional[str] = metadata.get("access_path")
    if not access_path:
        raise ValueError("metadata.access_path is required for rule-based definition extraction")

    table_elements = _resolve_access_path(doc, access_path)
    if not isinstance(table_elements, list):
        raise ValueError("access_path did not resolve to a list of rows")

    hierarchy_info = metadata.get("hierarchy_info") or {}
    hierarchy_columns: List[str] = hierarchy_info.get("columns") or []
    target_columns: List[str] = metadata.get("target_columns") or []

    if not hierarchy_columns and target_columns:
        hierarchy_columns = [c for c in target_columns if c != "구 분"]

    if not hierarchy_columns:
        raise ValueError("No hierarchy columns available in metadata")

    tree: Dict[str, Any] = {}
    for row in table_elements:
        cursor = tree
        for col in hierarchy_columns:
            value = row.get(col)
            if value is None:
                break
            if isinstance(value, str):
                value = value.replace("\n", " ").strip()
            cursor = cursor.setdefault(col, {}).setdefault(value, {})

    products: List[Dict[str, Any]] = []
    root_col = hierarchy_columns[0]
    root_layer = tree.get(root_col, {})
    for bojong, rest in root_layer.items():
        product: Dict[str, Any] = {"보종명": bojong}
        current_layer = rest
        for level, col in enumerate(hierarchy_columns[1:], start=1):
            layer = current_layer.get(col, {})
            values = sorted(layer.keys())
            product[f"유형{level}"] = values
            if values and isinstance(layer.get(values[0]), dict):
                current_layer = layer
        products.append(product)

    return {
        "raw_rows": table_elements,
        "hierarchy_columns": hierarchy_columns,
        "products": products,
        "tree": tree,
    }


def extract_definition_llm(
    doc: Dict[str, Any],
    step: Dict[str, Any],
    *,
    client: Optional[OpenAI] = None,
    model: str = "gpt-4o",
) -> Dict[str, Any]:
    if client is None:
        client = OpenAI()

    metadata = step.get("metadata", {})
    access_path: Optional[str] = metadata.get("access_path")
    if not access_path:
        raise ValueError("metadata.access_path is required for LLM-based definition extraction")

    table_elements = _resolve_access_path(doc, access_path)
    if not isinstance(table_elements, list):
        raise ValueError("access_path did not resolve to a list of rows")

    hierarchy_info = metadata.get("hierarchy_info") or {}
    hierarchy_columns: List[str] = hierarchy_info.get("columns") or []
    target_columns: List[str] = metadata.get("target_columns") or []

    table_json = json.dumps(table_elements, ensure_ascii=False, indent=2)

    prompt = f"""
너는 보험 약관 파싱을 돕는 도구 정의 에이전트다.

[입력 테이블]
다음은 정의 섹션에서 추출한 표의 각 행(row)이다. 파이썬 dict 리스트 형태이다.

```json
{table_json}
```

각 행의 컬럼은 대략 다음과 같은 의미를 가진다:
- 상품/보종명: 특정 특약이나 상품의 전체 이름
- 상위 유형: 해약환급금/일반형 등 상위 분류
- 하위 유형: 심사형(간편심사형, 일반심사형 등)이나 세부 타입

주어진 컬럼 이름을 직접 사용해서, 아래 스키마를 따르는 JSON만 출력하라.
추측은 최소화하고, 실제 행에 존재하는 값만 사용하라.

[원본 메타데이터 힌트]
- hierarchy_columns: {hierarchy_columns}
- target_columns: {target_columns}

[요구 스키마]
```json
{{
  "hierarchy_columns": ["보종명_컬럼명", "유형1_컬럼명", "유형2_컬럼명(있으면)"],
  "products": [
    {{
      "보종명": "보종명 문자열",
      "유형1": [
        {{
          "값": "유형1 값",
          "유형2": ["유형2 값1", "유형2 값2", "..."]  // 없으면 빈 배열
        }}
      ]
    }}
  ]
}}
```

규칙:
1. hierarchy_columns는 실제 테이블 컬럼 이름으로 채운다.
2. 보종명/유형1/유형2에 들어가는 값은 실제 행에서 등장하는 문자열만 사용한다.
3. 줄바꿈/공백은 적절히 정리하되 정보는 유지한다.
4. 추가적인 설명 문장은 쓰지 말고 JSON만 출력한다.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that outputs strict JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1500,
    )

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("LLM returned empty content for definition extraction")

    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    parsed = json.loads(content)
    parsed["raw_rows"] = table_elements
    return parsed


if __name__ == "__main__":
    """
    definition.py 테스트 실행
    """
    from pathlib import Path
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # 1. 원본 문서 로드
    raw_doc_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json")

    if not raw_doc_path.exists():
        print(f"❌ 원본 문서가 존재하지 않습니다: {raw_doc_path}")
        exit(1)

    raw_doc = json.load(raw_doc_path.open("r", encoding="utf-8"))

    # 2. execution_plan 로드 (only_plan.py로 생성한 결과)
    plan_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_plan\신한SOL암보험(무배당, 해약환급금 미지급형)_parsed_execution_plan.json")

    if not plan_path.exists():
        print(f"❌ 먼저 only_plan.py를 실행하여 execution plan을 생성하세요: {plan_path}")
        exit(1)

    plan = json.load(plan_path.open("r", encoding="utf-8"))

    # 3. Definition 추출 단계 찾기
    definition_steps = [s for s in plan.get("plan", []) if "Definition" in s.get("tool", "")]

    if not definition_steps:
        print("❌ Definition 추출 단계를 찾을 수 없습니다.")
        exit(1)

    # 첫 번째 Definition 단계 사용 (보통 하나만 있음)
    step = definition_steps[0]

    # 4. Rule과 LLM 둘 다 실행해서 비교
    print("=" * 80)
    print("Definition Extraction 비교 테스트")
    print("=" * 80)
    print()
    print(f"📋 Step: {step.get('step', 'N/A')}")
    print(f"💡 Original Tool: {step.get('tool', 'N/A')}")
    print(f"📝 Reason: {step.get('reason', 'N/A')}")
    print()

    results = {}

    # 4-1. Rule 기반 추출
    print("=" * 80)
    print("1️⃣ DefinitionRule (규칙 기반)")
    print("=" * 80)
    try:
        result_rule = extract_definition_rule(raw_doc, step)
        results['rule'] = result_rule
        print("✅ Rule 기반 추출 성공!")
        print(f"   계층 컬럼: {result_rule['hierarchy_columns']}")
        print(f"   추출된 상품 수: {len(result_rule['products'])}")
        print()
        print("📊 추출된 상품:")
        for i, prod in enumerate(result_rule['products'], 1):
            print(f"   {i}. {prod}")
        print()
    except Exception as e:
        print(f"❌ Rule 추출 실패: {e}")
        import traceback
        traceback.print_exc()
        results['rule'] = None

    print()

    # 4-2. LLM 기반 추출
    print("=" * 80)
    print("2️⃣ DefinitionLLM (LLM 기반)")
    print("=" * 80)
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  OPENAI_API_KEY가 설정되지 않아 LLM 테스트를 건너뜁니다.")
            results['llm'] = None
        else:
            client = OpenAI(api_key=api_key)
            result_llm = extract_definition_llm(raw_doc, step, client=client, model="gpt-4o")
            results['llm'] = result_llm
            print("✅ LLM 기반 추출 성공!")
            print(f"   계층 컬럼: {result_llm['hierarchy_columns']}")
            print(f"   추출된 상품 수: {len(result_llm['products'])}")
            print()
            print("📊 추출된 상품:")
            for i, prod in enumerate(result_llm['products'], 1):
                print(f"   {i}. {prod}")
            print()
    except Exception as e:
        print(f"❌ LLM 추출 실패: {e}")
        import traceback
        traceback.print_exc()
        results['llm'] = None

    print()

    # 5. 결과 비교
    print("=" * 80)
    print("📊 결과 비교")
    print("=" * 80)
    print()

    if results['rule'] and results['llm']:
        print("🔍 Rule vs LLM 비교:")
        print()
        print(f"   계층 컬럼:")
        print(f"      Rule: {results['rule']['hierarchy_columns']}")
        print(f"      LLM:  {results['llm']['hierarchy_columns']}")
        print()
        print(f"   상품 수:")
        print(f"      Rule: {len(results['rule']['products'])}")
        print(f"      LLM:  {len(results['llm']['products'])}")
        print()

        # 상품 비교
        print("   상품별 비교:")
        max_len = max(len(results['rule']['products']), len(results['llm']['products']))
        for i in range(max_len):
            print(f"\n   [{i+1}번째 상품]")
            if i < len(results['rule']['products']):
                print(f"      Rule: {results['rule']['products'][i]}")
            else:
                print(f"      Rule: (없음)")

            if i < len(results['llm']['products']):
                print(f"      LLM:  {results['llm']['products'][i]}")
            else:
                print(f"      LLM:  (없음)")

    elif results['rule']:
        print("⚠️  Rule 방식만 성공")
    elif results['llm']:
        print("⚠️  LLM 방식만 성공")
    else:
        print("❌ 둘 다 실패")

    print()
    print("=" * 80)
    print("✅ 테스트 완료!")
    print("=" * 80)
