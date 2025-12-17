# test_condition_transform_multiline_formula.py
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
# ✅ 너 프로젝트에서 가져오기 (경로만 맞춰줘)
# from tools.prompts import build_condition_transform_prompt


def main():
    load_dotenv()

    prompt = f"""json 형식으로만 응답해라.
    출력 스키마 : 
    {{
        answer : 대답
    }}"""

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # resp = client.chat.completions.create(
    #     model="gpt-4o",
    #     messages=[{"role": "user", "content": prompt}],
    #     temperature=0,
    #     max_output_tokens=4000,
    # )

    resp = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},   # ✅ 여기로 옮김
        max_output_tokens=4000,
    
    )

    #content = resp.output_text
    content = resp.output_text
    
    # stats["total_prompt_tokens"] += usage.input_tokens
    # stats["total_completion_tokens"] += usage.output_tokens
    
    print(content)
    print(resp.usage)


if __name__ == "__main__":
    main()
