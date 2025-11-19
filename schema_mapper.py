import os
import json
import re
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_schema_mapper(semantic_context: Dict[str, Any], target_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    🎯 Schema Mapper
    - semantic_context(문서 의미 구조)와 target_schema를 기반으로
      각 스키마 필드가 문서의 어느 섹션/테이블/필드에 해당하는지 매핑한다.
    """

    context_data = json.dumps(semantic_context, ensure_ascii=False)
    schema_data = json.dumps(target_schema, ensure_ascii=False)

    prompt = f"""
    당신은 보험 문서 구조 해석 결과를 기반으로 target_schema의 각 필드를
    문서 내 실제 필드와 연결하는 Schema Mapper입니다.

    --- 
    🔹 입력 데이터
    1. semantic_context (문서 의미 구조):
    {context_data}

    2. target_schema:
    {schema_data}

    ---
    🔹 작업 목표:
    - 각 target_schema 필드가 의미적으로 대응되는 문서의 section, element, field를 찾아 매핑합니다.
    - 매핑 근거(reason)를 명확히 기술하세요.
    - 명시적 매핑이 불가능한 경우 "unmapped"로 표시합니다.
    - 각 필드가 문서에서 수행하는 역할(functional role)을 기준으로 매핑하세요.
        예:
        - 주요 상품 분류를 나타내는 필드 ↔ target_schema.유형1
        - 상품의 세부 형태나 조건을 나타내는 필드 ↔ target_schema.유형2
        - 가입 가능한 나이 범위를 설명하는 필드 ↔ target_schema.주피보험자최소가입연령 또는 최대가입연령
        - 계약 기간에 대한 필드 ↔ target_schema.보험기간
        - 납입 방식이나 기간에 대한 필드 ↔ target_schema.납입기간

        필드 이름이 일치하지 않아도,
        문서에서 어떤 역할을 수행하는지 semantic_context와 parsed_doc의 내용을 기반으로 판단하세요.
    ---
    🔹 출력 형식(JSON)
    {{
      "doc_title": string,
      "schema_mapping": {{
        "<target_field>": {{
          "section_id": string | null,
          "element_id": string | null,
          "source_field": string | null,
          "reason": string
        }},
        ...
      }},
      "metadata": {{
        "total_mapped_fields": int,
        "unmapped_fields": [string, ...]
      }}
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise schema mapping agent. Output strict JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    try:
        content = response.choices[0].message.content.strip()
        cleaned = re.sub(r"^```json\s*|\s*```$", "", content)
        json_output = json.loads(cleaned)
        return json_output
    except Exception as e:
        print("❌ JSON 파싱 오류:", e)
        print("원문 응답:", response.choices[0].message.content)
        return {}

if __name__ == "__main__":
    # 입력 파일 경로
    context_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\semantic_context.json"

    with open(context_path, "r", encoding="utf-8") as f:
        semantic_context = json.load(f)

    target_schema = {
        "보종명": "string",
        "유형1": "string",
        "보험기간": "string",
        "납입기간": "string",
        "주피보험자최소가입연령": "int",
        "주피보험자최대가입연령": "int",
        "주피보험자최소가입연령구분코드": "string",
        "주피보험자최대가입연령구분코드": "string"
    }

    # 실행
    mapping_result = run_schema_mapper(semantic_context, target_schema)

    # 결과 출력
    print(json.dumps(mapping_result, ensure_ascii=False, indent=2))

    # 결과 저장
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\schema_mapping.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapping_result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 스키마 매핑 결과가 저장되었습니다: {output_path}")
