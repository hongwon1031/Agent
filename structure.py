import os
import json
import re
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_structure_planner(parsed_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    📘 Structure Planner
    - 문서의 물리적 구조(섹션, 테이블, 텍스트)를 계층적으로 분석
    - 내용 의미 요약은 하지 않음
    """

    doc_data = json.dumps(parsed_doc, ensure_ascii=False)


    schema = '''
    "doc_title": "string",
    "sections": [
        {
        "title": "string",
        "paragraphs": [
            {
            "type": "table" | "text",
            "content": "원본 내용",
            "info": {
                "has_multicolumn": true/false,
                "has_rowspan": true/false,
                "has_colspan": true/false,
                "is_main_contract_section": true/false,
                "is_rider_section": true/false
            }
            }
        ]
        }
    ]
    '''
    prompt = f"""
    당신은 Structure Agent입니다.

    당신의 역할은 JSON 형태의 보험 문서 데이터를 구조적으로 분석하여
    각 섹션의 구조, paragraph 타입, multi-column 존재 여부, 
    주계약/특약 여부 등을 추출하는 것입니다.

    ### 입력 JSON ###
    {doc_data}

    ### 출력 조건 ###
    - 문서 내용을 해석하거나 요약하지 말고, '구조적 정보'만 정리한다.
    - 각 section 단위로 title, paragraph 목록, paragraph 타입(table/text)을 분류한다.
    - 표가 multi-column인지, row-span/col-span이 있는지 판단한다.
    - 주계약/특약 관련 텍스트가 포함되면 info에 표시한다.

    ### 출력 JSON Schema ###
    {schema}

    위 Schema에 맞춰 JSON만 출력하라.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a document structure analyzer. Output strict JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
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
    # 예시 문서 로드
    with open(
        r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json",
        "r", encoding="utf-8"
    ) as f:
        parsed_doc = json.load(f)

    structure = run_structure_planner(parsed_doc)
    print(json.dumps(structure, ensure_ascii=False, indent=2))
    
    # ✅ 결과 저장
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\structure_output.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 구조 분석 결과가 저장되었습니다: {output_path}")