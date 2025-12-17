# tests/test_reflection_validator_planner_llm.py
from __future__ import annotations
from dotenv import load_dotenv
import os
import json
from typing import Any, Dict, List

from openai import OpenAI

# ✅ 네 프로젝트 경로에 맞게 조정
from core.prompt import (
    build_next_task_prompt,
    build_validate_definition_extract_v2_llm,
)

load_dotenv()


MODEL = os.getenv("P8_MODEL", "gpt-4o-mini")  # 필요하면 gpt-4o-mini 등으로 바꿔


def jdump(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, indent=2)


def call_llm_json(client: OpenAI, prompt: str, *, model: str = MODEL, max_tokens: int = 800) -> Dict[str, Any]:
    """
    OpenAI Chat Completions로 JSON only 응답 받기.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except Exception:
        # 혹시 JSON 깨졌을 때 디버깅용
        return {"_parse_error": True, "raw": content}


def main():
    # ---------------------------------------------------------
    # 0) definition_extract_v2 결과 하드코딩
    # ---------------------------------------------------------
    header = ["보종명", "유형1", "유형2", "유형3"]
    data = [
        [
            "통합암(전이포함)진단특약TC (무배당, 해약환급금 미지급형)",
            "해약환급금 미지급형",
            ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형", None],
            ["두경부암(전이포함)", "위암 및 식도암(전이포함)", "혈액암(전이포함)"],
        ],
        [
            "통합암(전이포함)진단특약TC (무배당)",
            "일반형",
            ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형", "일반심사형"],
            ["두경부암(전이포함)", "위암 및 식도암(전이포함)", "혈액암(전이포함)"],
        ],
    ]

    core_sections_preview: List[Dict[str, Any]] = [
        {"title": "1. 가입가능조건", "type": "table", "content": "…(core preview)…"},
    ]
    annotation_sections_preview: List[Dict[str, Any]] = [
        {"title": "주석", "type": "text", "content": "…(annotation preview)…"},
    ]

    # ---------------------------------------------------------
    # 1) Validator prompt 생성 + LLM 호출
    # ---------------------------------------------------------
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    validator_prompt = build_validate_definition_extract_v2_llm(
        core_sections_preview=core_sections_preview,
        annotation_sections_preview=annotation_sections_preview,
        header=header,
        data=data,
    )

    print("\n" + "=" * 100)
    print("[VALIDATOR PROMPT]")
    print("=" * 100)
    print(validator_prompt)

    validator_result = call_llm_json(client, validator_prompt, model=MODEL, max_tokens=900)

    print("\n" + "=" * 100)
    print("[VALIDATOR RESULT JSON]")
    print("=" * 100)
    print(jdump(validator_result))

    # ---------------------------------------------------------
    # 2) Planner(next_task) prompt 생성 + LLM 호출
    # ---------------------------------------------------------
    # doc_summary = {
    #     "doc_id": "TEST_DOC_001",
    #     "doc_title": "신한SOL암보험(테스트)",
    #     "tables_found": 2,
    #     "notes": "validator→planner reflection 테스트",
    # }

    # goal = "Definitions/Conditions 그룹핑 로직을 안정적으로 추출하고 최종 조합을 생성한다."

    # # tool_schemas는 next_task 프롬프트에 들어갈 스키마 문자열(최소 예시)
    # tool_schemas = jdump(
    #     {
    #         "tools": [
    #             {
    #                 "name": "grouping_logic_extractor",
    #                 "description": "Definitions/Conditions에서 join_keys 및 그룹핑 로직 추출",
    #                 "input_schema": {"def_table": "str", "cond_table": "str"},
    #                 "output_schema": {"column_mapping": "dict", "groups": "list[dict]"},
    #             },
    #             {
    #                 "name": "combination_generator",
    #                 "description": "그룹핑 로직 기반 조합 생성",
    #                 "input_schema": {"definition_header": "list[str]", "definition_data": "list[list[Any]]", "grouping_logic": "dict"},
    #                 "output_schema": {"definitions": "list[dict]", "total_count": "int"},
    #             },
    #         ]
    #     }
    # )

    # task_results = [
    #     {
    #         "task_id": "task1",
    #         "tool_name": "definition_extract_v2",
    #         "success": True,
    #         "data": {"header": header, "data": data},
    #     },
    #     {
    #         "task_id": "task2",
    #         "tool_name": "validate_definition_extract_v2",
    #         "success": True,
    #         "data": validator_result,
    #     },
    # ]

    # last_task = {"task_id": "task2", "tool_name": "validate_definition_extract_v2"}

    # instruction = (
    #     "validator 결과의 issues/suggestions를 반영해서 다음 태스크를 설계하라. "
    #     "불필요한 tool 호출을 줄이고, join key/wildcard/shift 가능성을 우선 해결하라."
    # )

    # next_task_prompt = build_next_task_prompt(
    #     doc_summary=doc_summary,
    #     goal=goal,
    #     task_results=task_results,
    #     tool_schemas=tool_schemas,
    #     instruction=instruction,
    #     last_feedback=validator_result,  # ✅ reflection 포인트
    #     last_task=last_task,
    # )

    # print("\n" + "=" * 100)
    # print("[PLANNER NEXT_TASK PROMPT]")
    # print("=" * 100)
    # print(next_task_prompt)

    # next_task = call_llm_json(client, next_task_prompt, model=MODEL, max_tokens=900)

    # print("\n" + "=" * 100)
    # print("[NEXT_TASK JSON]")
    # print("=" * 100)
    # print(jdump(next_task))


if __name__ == "__main__":
    # 실행 전:
    #   set OPENAI_API_KEY=...
    #   (옵션) set P8_MODEL=gpt-4o-mini
    main()
