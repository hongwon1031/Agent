import os
import json
import re
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_document_context_builder(parsed_doc: Dict[str, Any], structure_plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    🧩 Document Context Builder
    - Structure Planner의 뼈대(structure_plan)와 원문(parsed_doc)을 함께 입력으로 받아
      각 섹션 및 테이블의 의미적 구조(semantic context)를 해석한다.
    """

    doc_data = json.dumps(parsed_doc, ensure_ascii=False)
    structure_data = json.dumps(structure_plan, ensure_ascii=False)

    prompt = f"""
    당신은 보험 약관 문서의 의미적 구조를 해석하는 Document Context Builder입니다.

    입력으로 문서의 전체 내용(parsed_doc)과 그 문서의 물리적 구조(structure_plan)가 주어집니다.
    당신의 목표는 각 섹션과 그 안의 테이블이 **어떤 의미적 역할을 수행하는지**를 분석하는 것입니다.

    --- 
    🔹 규칙:
    1. 각 section에 대해 그 섹션이 다루는 주제나 의미를 간결히 기술합니다. (예: 상품명 정의, 가입조건 명시 등)
    2. 각 table은 테이블 제목과 열 이름을 근거로 의미적 역할(예: 가입조건 표, 연령 제한표 등)을 기술합니다.
    3. 내용 요약은 간결히 하되, 의미 중심으로 작성합니다.
    4. output은 반드시 JSON 형식으로만 작성합니다.

    --- 
    📘 출력 형식(JSON)
    {{
      "doc_title": string,
      "semantic_context": [
        {{
          "section_id": string,
          "title": string,
          "semantic_summary": string,
          "elements": [
            {{
              "element_id": string,
              "type": string,
              "semantic_role": string,
              "fields_detected": [string, ...]
            }}
          ]
        }}
      ],
      "metadata": {{
        "sections_analyzed": int,
        "tables_analyzed": int
      }}
    }}

    ---
    📄 입력 데이터
    - 문서 내용(parsed_doc):
    {doc_data}

    - 문서 구조(structure_plan):
    {structure_data}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a semantic structure interpreter. Output strict JSON only."},
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
    parsed_path = r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json"
    structure_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\structure_output.json"

    with open(parsed_path, "r", encoding="utf-8") as f:
        parsed_doc = json.load(f)

    with open(structure_path, "r", encoding="utf-8") as f:
        structure_plan = json.load(f)

    # 실행
    semantic_context = run_document_context_builder(parsed_doc, structure_plan)

    # 결과 출력
    print(json.dumps(semantic_context, ensure_ascii=False, indent=2))

    # 결과 저장
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\semantic_context.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(semantic_context, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 의미 구조 해석 결과가 저장되었습니다: {output_path}")
