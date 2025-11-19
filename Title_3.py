import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def run_title3_condition_drop_agent(title3_section):
    """
    LLM이 Title3 paragraph 전체를 보고
    - '가입가능 조건' 테이블
    - 그 위의 type:title (상위 유형)
    만 남기고 나머지를 drop하도록 한다.
    """

    system_prompt = """
    당신은 'Semantic Condition Filtering Agent'입니다.

    목적:
      - 보험 문서의 Title3(가입조건 섹션) 전체를 받아서,
        그 중에서 '가입가능 조건'에 해당하는 정보만 남기고
        나머지는 모두 drop 해야 합니다.

    Title3는 보통 다음 요소로 구성됩니다:
      - type=title : "가. ~~형", "나. ~~형" (상품의 유형 분류)
      - type=table : 가입가능 조건, 가입불가 조건 테이블
      - type=text : 주석, 안내문

    ------------------------------
    ⭐ 필수 규칙
    ------------------------------

    1) 반드시 '가입가능 조건' table만 남긴다.
       - table.table_title == "가입가능 조건"
       - 또는 semantic하게 '가입가능'에 해당한다고 판단되는 table

    2) '가입가능 조건' table 바로 위에 있는 type=title 도 함께 남긴다.

    3) '가입불가 조건' 또는 기타 조건은 DROP한다.

    4) type=text는 DROP한다.

    5) 출력 형식은 다음과 같아야 한다:

        [
          {
            "type": "title",
            "content": "가. 해약환급금 미지급형"
          },
          {
            "type": "table",
            "table_title": "가입가능 조건",
            "table_elements": [...]
          },
          ...
        ]

    6) JSON만 출력한다.
    """

    user_prompt = f"""
    아래는 Title3 전체 섹션입니다.

    이 중에서:
      - 가입가능 조건 테이블
      - 바로 위의 title

    만 남기고 모두 삭제하여 JSON으로 출력하세요.

    Title3 내용:
    {json.dumps(title3_section, ensure_ascii=False, indent=2)}
    """

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=6000,
    )

    # JSON 파싱
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("❌ JSON 파싱 오류")
        print(content)
        return None


# ---------------------------
# 실행 예시
# ---------------------------
if __name__ == "__main__":

    # Title3 JSON 불러오기
    with open(
        r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json",
        "r", encoding="utf-8"
    ) as f:
        title3_data = json.load(f)

    # Title3 Condition Filtering 실행
    filtered = run_title3_condition_drop_agent(title3_data)

    print(json.dumps(filtered, ensure_ascii=False, indent=2))

    # 저장
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\Parsing\Title3/title5.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Title3 LLM 기반 추출 결과 저장됨: {output_path}")
