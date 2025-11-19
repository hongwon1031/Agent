import json
from openai import OpenAI
import os
from dotenv import load_dotenv

# ⭐ API 키를 먼저 로드
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def find_title1_section(parsed_json):
    """
    정규식/하드코딩 없이
    LLM이 전체 문서를 보고 '보험종목의 명칭'에 해당하는 section을 추론하여 반환.
    """
    system_prompt = """
    당신은 'Definition Locator Agent'입니다.

    임무:
      - 보험 상품 문서의 전체 구조화된 JSON을 보고,
      - 이 중 '보험종목의 명칭 / 상품 정의 / 보종명 / 유형 정의'가 포함된 섹션을 찾아야 합니다.

    기준:
      - Title1은 일반적으로 상품의 '정의'에 해당하는 정보이며,
        다음과 같은 특징을 가질 수 있습니다:
          * 명칭 / 보종명 / 상품명
          * 보험종목 / 유형 / (무배당) 등 상품 정의 정보
          * 심사유형 / 315형 / 335형 / 일반형 등의 분류
          * 보장계약 정보가 포함될 수 있음

      - Title3(조건 섹션)과 혼동하지 마십시오.
        Title3는 '가입조건, 나이, 기간, 납입기간, 보험기간, 유형1/2' 등이 나오며,
        상품의 정의가 아니라 조건을 나타냅니다.

    출력:
      - Title1이라고 판단한 section의 'table_elements'만 JSON으로 반환.
      - 여러 section이 candidate라면 가장 정의적 성격이 강한 것(상품의 기본 속성을 설명하는 것)을 반환.

    출력형식:
      {
        "title": "...",
        "table_elements": [...]
      }

    JSON ONLY로 출력하세요.
    """

    user_prompt = (
        "아래는 전체 문서의 파싱된 JSON입니다. "
        "이 중 Title1(상품 정의 영역)을 찾아 table_elements를 반환하십시오.\n\n"
        + json.dumps(parsed_json, ensure_ascii=False)
    )

    res = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=4096,
    )

    # JSON 파싱
    try:
        return json.loads(res.choices[0].message.content)
    except:
        print("LLM 출력:", res.choices[0].message.content)
        raise


if __name__ == "__main__":
    # 예시 문서 로드
    with open(
        r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json",
        "r", encoding="utf-8"
    ) as f:
        parsed_doc = json.load(f)

    structure = find_title1_section(parsed_doc)
    print(json.dumps(structure, ensure_ascii=False, indent=2))
    
    # 결과 저장
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\Parsing\Title1\title5.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 구조 분석 결과가 저장되었습니다: {output_path}")
