import json
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_condition_parsing_agent(title3_cleaned):
    system_prompt = """
    당신은 'Semantic Condition Parsing Agent'입니다.

    🎯 목적:
    보험 문서 Title3(가입가능 조건) 데이터를 기반으로 다음 스키마를 채우십시오:

    {
      "가입가능조건": [
        {
          "상위유형": "",
          "세부유형": "",
          "보험기간": "",
          "납입기간": "",
          "가입나이": {
            "남자": "",
            "여자": ""
          },
          "납입주기": ""
        }
      ]
    }

    ---------------------------------------------
    🔐 반드시 지켜야 할 규칙
    ---------------------------------------------

    1) 입력 데이터의 key 이름은 무시하고, value의 의미만을 기반으로 매핑하십시오.
       예:
       - "유형1" → 상위유형
       - "유형2" → 세부유형
       - 그러나 key 이름이 달라도, 값 의미를 보고 추론해야 한다.

    2) 모든 table row는 각각 하나의 조건 객체가 되어야 한다.

    3) 가입나이는 다음과 같이 구성해야 한다:
       "가입나이": {
          "남자": 남자나이 value,
          "여자": 여자나이 value
       }

    4) 보험기간 / 납입기간 / 나이 / 납입주기 값은 원문 그대로 사용.

    5) table 위의 type=title("가. ~형")은 해당 table의 상위유형이며,
       row의 상위유형 값 판단에 활용해야 한다.

    6) 출력에는 입력 값을 절대 누락시키지 말고,
       모든 row를 변환하여 JSON 리스트에 추가해야 한다.

    7) 반드시 JSON만 출력한다.
    """

    user_prompt = f"""
    아래는 Title3(가입가능 조건) 정제 데이터입니다.

    이를 기반으로 스키마 형태로 변환하세요.

    {json.dumps(title3_cleaned, ensure_ascii=False, indent=2)}
    """

    res = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        max_tokens=5000
    )

    try:
        return json.loads(res.choices[0].message.content)
    except:
        print("LLM JSON 파싱 오류\n", res.choices[0].message.content)
        raise


# -------------------------------------------------------------
# 🔽 실행 파트
# -------------------------------------------------------------
if __name__ == "__main__":

    # 🔹 입력 파일 (Title_1.py 결과)
    input_path = r"C:\Users\NT-165\Desktop\Project\Toy\Parsing\Title3\title1.json"

    # 🔹 출력 파일
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\Tree\Title3/condition_tree1.json"

    # 🔹 입력 JSON 로드
    with open(input_path, "r", encoding="utf-8") as f:
        title1_json = json.load(f)

    # title1_json 구조:
    # { "title": "...", "table_elements": [ {...}, {...} ] }
    title1_rows = title1_json.get("table_elements", [])

    # 🔹 에이전트 실행
    result = run_condition_parsing_agent(title1_rows)

    # 🔹 결과 출력
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 🔹 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Definition Tree 생성 완료 → {output_path}")
