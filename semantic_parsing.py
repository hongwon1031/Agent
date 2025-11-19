import os
import json
import re
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def run_drop_agent(parsed_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Drop Agent:
    - 원본 JSON 구조를 유지하면서, 필요 없는 title 섹션만 제거(drop)
    - 의미 추론 금지
    """

    doc_data = json.dumps(parsed_doc, ensure_ascii=False)

    prompt = f"""
    당신은 Drop Agent입니다.

    📌 목적
    - 원본 JSON 구조를 절대 변경하지 않는다.
    - 필요한 섹션(title)은 남기고, 필요 없는 섹션만 제거(drop)한다.
    - 의미 추론 금지.
    - 구조 변형 금지.
    - 새로운 key 생성 금지.
    - 요약/재구성 금지.

    📌 삭제 대상 제목 리스트 (포함되면 제거)
    - "의무가입"
    - "배당"
    - "보험료 할인"
    - "보험료 선납"
    - "연체이율"
    - "중도인출"
    - "공시이율"
    - "보험계약대출"
    - "기타"
    - "특약의 중도 가입"
    - "해약환급금"  (단, '해약환급금 미지급형'은 유지)

    📌 유지 대상 핵심 정보
    - 보종명, 명칭, 보험종목
    - 유형1/유형2/유형3 등
    - 보험기간 / 납입기간 / 가입나이 / 납입주기
    - 가입가능 조건 / 가입불가 조건
    - '해약환급금 미지급형'

    📌 출력 형식
    - 원본 JSON 구조를 유지하되, 제거 대상 title이 포함된 element만 제거한 JSON을 반환하라
    - JSON만 출력
    - 코드블록 금지

    🔽 이것이 원본 JSON이다:
    {doc_data}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a JSON filtering Drop Agent. Output strict JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    try:
        content = response.choices[0].message.content.strip()

        # Remove ```json ``` wrapper
        cleaned = re.sub(r"^```json\s*|\s*```$", "", content)

        json_output = json.loads(cleaned)
        return json_output

    except Exception as e:
        print("❌ JSON 파싱 오류:", e)
        print("원문 응답:", response.choices[0].message.content)
        return {}


if __name__ == "__main__":
    # 원본 데이터 로드
    input_path = r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json"

    with open(input_path, "r", encoding="utf-8") as f:
        parsed_doc = json.load(f)

    # Drop Agent 실행
    dropped_json = run_drop_agent(parsed_doc)

    print("\n===== DROP 결과 =====")
    print(json.dumps(dropped_json, ensure_ascii=False, indent=2))

    # 저장 경로
    output_path = r"C:\Users\NT-165\Desktop\Project\Toy\results\dropped_output.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dropped_json, f, ensure_ascii=False, indent=2)

    print(f"\n✅ drop 결과 저장 완료: {output_path}")
