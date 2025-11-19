import json
import os
from typing import Any, Dict, List
from openai import OpenAI
from dotenv import load_dotenv

# ⭐ API 키를 먼저 로드
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_definition_parsing_agent(title1_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Title1의 모든 key:value 를 사용하여
    semantic하게 보종명~유형N 으로 계층화하는 Agent.
    """

    system_prompt = """
    당신은 'Semantic Hierarchical Definition Agent'입니다.

    🎯 목적:
    Title1 테이블의 모든 key:value 를 의미 기반으로 분석하여,
    다음과 같은 계층 구조로 재구조화하십시오:

        보종명 (가장 상위 개념 / 상품 전체 명칭)
        └─ 유형1 (상위 분류)
             └─ 유형2 (하위 분류)
                  └─ 유형3 (세부 보장/조건)
                       ...
        ※ 필요한 만큼 유형4, 유형5 생성 가능

    ----------------------------------------------------
    🔐 **반드시 지켜야 할 규칙**
    ----------------------------------------------------
    1) 입력 key:value 는 단 하나도 버리면 안 된다.
       - 모든 value는 반드시 보종명 또는 유형N 중 하나에 포함되어야 함.

    2) 보종명은 "상품의 고유 명칭"에 해당하며,
       보통 '명칭' 또는 제품명의 역할을 하는 문자열이다.
       괄호는 절대로 삭제하면 안 된다.

    3) value 의 의미적 위계를 판단하여
       더 일반적인 개념 → 상위 유형
       더 세부적인 개념 → 하위 유형
       순으로 자동 재배치한다.

    4) 리스트(보장계약 등)는 각각 분리된 항목으로 유형N에 넣는다.

    5) key 이름 자체는 절대 출력하지 않는다.
       (ex. "보장계약"이라는 key를 출력하면 안 됨)
       오직 value만 계층 구조에 포함한다.

    6) 출력은 반드시 다음 JSON 형식:

    {
      "보종명": [...],
      "유형1": [...],
      "유형2": [...],
      "유형3": [...],
      ...
    }

    ----------------------------------------------------
    """

    user_prompt = f"""
    Title1 rows:
    {json.dumps(title1_rows, ensure_ascii=False, indent=2)}
    """

    res = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=3000,
    )

    try:
        result = json.loads(res.choices[0].message.content)
        return result
    except Exception:
        print("❌ LLM 출력 JSON 파싱 오류\n", res.choices[0].message.content)
        raise


# -------------------------------------------------------------
# 🔽 실행 파트
# -------------------------------------------------------------
if __name__ == "__main__":

    # 🔹 입력 파일 (Title_1.py 결과)
    input_path = r"C:\Users\NT-165\Desktop\Project\Toy\Parsing\Title1\title5.json"

    # 🔹 출력 파일
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\Tree\Title1\definition_tree5.json"

    # 🔹 입력 JSON 로드
    with open(input_path, "r", encoding="utf-8") as f:
        title1_json = json.load(f)

    # title1_json 구조:
    # { "title": "...", "table_elements": [ {...}, {...} ] }
    title1_rows = title1_json.get("table_elements", [])

    # 🔹 에이전트 실행
    result = run_definition_parsing_agent(title1_rows)

    # 🔹 결과 출력
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 🔹 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Definition Tree 생성 완료 → {output_path}")
