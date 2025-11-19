from openai import OpenAI
import json
import os
from dotenv import load_dotenv 

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 실험용 약관 표 + 텍스트
with open(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json", "r", encoding="utf-8") as f:
    parsed_doc = json.load(f)

# 고정된 스키마 정의
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

# LLM 호출 (Interpreter Node 시뮬레이션)
prompt = f"""
다음은 보험 약관의 일부입니다. 
이 표와 텍스트를 분석하여 target_schema의 필드들과 의미적으로 매핑하고,
필드 간의 관계를 의미 그래프 형태로 표현하세요.

출력은 반드시 아래 JSON 구조를 따르세요:
{{
  "nodes": [{{"id": "...", "type": "...", "name": "...", "value": "...", "expression": "..."}}],
  "edges": [{{"source": "...", "target": "...", "relation": "..."}}]
}}

문서:
{json.dumps(parsed_doc, ensure_ascii=False)}

target_schema:
{json.dumps(target_schema, ensure_ascii=False)}
"""

response = client.chat.completions.create(
    model="gpt-4o-mini",  # 가볍고 reasoning 잘됨
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2
)

print(response.choices[0].message.content)
