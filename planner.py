import argparse
import os
from pathlib import Path
from textwrap import dedent
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

# planner 프롬프트에 노출할 툴 설명
# Planner 가 선택할 수 있는 Tool 목록 (LLM 기반/룰 기반 혼재)
TOOL_LIST = [
    {
        "name": "DefinitionAgentRule",
        "description": "규칙 기반으로 Title1 표에서 보종/유형을 추출 (표 구조가 일정할 때 추천)."
    },
    {
        "name": "DropAgent",
        "description": "파싱된 문서에서 정의/가입조건 구간만 남기고 기타 내용을 정리합니다."
    },
    {
        "name": "ConditionAgentLLM",
        "description": "LLM을 이용해 Title3 표/텍스트를 자유롭게 해석하여 가입조건 룰을 추출합니다."
    },
    {
        "name": "DefinitionAgentLLM",
        "description": "LLM을 이용해 Title1 설명/표를 해석하여 보종/유형 관계를 도식화합니다."
    },
    {
        "name": "ConditionAgentRule",
        "description": "규칙 기반 파서로 정형화된 Title3 표에서 기간·납입·가입나이를 추출합니다."
    },
    {
        "name": "MappingAgent",
        "description": "정의 결과와 가입조건 룰을 매칭해 보종·유형별 가입조건을 연결합니다."
    },
    {
        "name": "NormalizationAgent",
        "description": "매핑 결과를 최종 스키마 필드와 코드 규칙에 맞게 정규화합니다."
    },
    {
        "name": "ValidationAgent",
        "description": "각 단계 결과의 누락/오류 여부를 검증하고 지표를 제공합니다."
    },
    {
        "name": "FinalOutputAgent",
        "description": "정규화된 데이터를 최종 가입가능조건 JSON으로 저장합니다."
    }
]

# 최종 결과가 맞춰야 할 필드 명세
TARGET_FIELDS = [
    "보종명",
    "유형1",
    "유형2",
    "유형3",
    "보험기간",
    "납입기간",
    "주피보험자최소가입연령",
    "주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드",
    "주피보험자최대가입연령구분코드",
    "주피보험자가입성별",
]

DEFAULT_MODEL = "gpt-4o"


def read_excerpt(path: Path, max_chars: int = 4000) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def format_tool_list() -> str:
    lines = []
    for idx, tool in enumerate(TOOL_LIST, start=1):
        lines.append(f"{idx}. {tool['name']}: {tool['description']}")
    return "\n".join(lines)


def format_target_fields() -> str:
    return "\n".join(f"- {field}" for field in TARGET_FIELDS)


def build_prompt(doc_excerpt: str) -> str:
    tools_block = format_tool_list()
    schema_block = format_target_fields()
    instructions = dedent(
        f"""
        당신은 Planner Agent 입니다. 아래 Tool 목록에 정의된 에이전트만 사용해서
        "가입가능조건 JSON 생성"이라는 목표를 달성하기 위한 단계별 계획을 세우세요.

        작성 규칙:
        - 단계(step)마다 사용할 Tool 이름을 정확히 명시하세요.
        - 해당 Tool을 사용하는 이유, 집중할 입력 구간, 성공 기준을 간결히 설명하세요.
        - ValidationAgent를 언제 실행할지 반드시 명시하세요.
        - 출력은 아래 JSON 스키마를 따라야 합니다.
            {{
              "overall_objective": "...",
              "plan": [
                {{"step": 1, "tool": "DropAgent",
                  "reason": "...", "input_focus": "...", "success_criteria": "..."}},
                ...
              ],
              "validation_focus": "validation 단계에서 중점적으로 확인할 항목"
            }}

        Tool 목록:
        {tools_block}

        타겟 스키마 주요 필드:
        {schema_block}

        입력 문서 일부:
        ```json
        {doc_excerpt}
        ```
        """
    ).strip()
    return instructions


def request_plan(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "너는 꼼꼼한 Planner 이다. 제공된 Tool 만 사용해 실행 계획을 JSON 으로 작성하라."
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


def main():
    parser = argparse.ArgumentParser(description="Planner Agent 테스트")
    parser.add_argument("input", type=Path, help="파싱된 JSON 파일 경로")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="사용할 OpenAI 모델")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="프롬프트에 포함할 문서 최대 길이(문자 수)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"입력 파일을 찾을 수 없습니다: {args.input}")

    doc_excerpt = read_excerpt(args.input, args.max_chars)
    prompt = build_prompt(doc_excerpt)
    plan_text = request_plan(prompt, args.model)

    print("===== Planner Response =====")
    print(plan_text)


if __name__ == "__main__":
    main()
