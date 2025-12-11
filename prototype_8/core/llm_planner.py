"""
LLM-based Dynamic Planner

PROTOTYPE 7: 동적 Task 실행 계획 수립
- 문서 복잡도 기반 3~7단계 동적 계획
- TaskDefinition 형식 사용 (task_id, dependencies, templates)
- True backtracking 지원을 위한 Root cause 분석
- Replan 전략: adjust_parameters, insert_task, full_replan
"""

import json
import os
from typing import Dict, Any, List, Optional
from openai import OpenAI
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add tools directory to path
tools_path = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_path))

from tool_schemas import get_schema_prompt
from core.prompt import build_next_task_prompt
from core.state import TaskDefinition, TaskResult


class LLMPlanner:
    """
    LLM 기반 동적 계획 수립기

    역할:
        - 문서 구조 분석 결과를 보고 최적의 계획 수립
        - 각 Task의 도구 선택 (rule vs llm)
        - Fallback 전략 포함
        - 파라미터 생성
    """

    def __init__(self):
        """Initialize OpenAI client"""
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    

    # ========== PROTOTYPE 7: New Methods ==========

    # _validate_plan_structure 메소드는 Pydantic으로 대체되었으므로 삭제 또는 더 이상 사용되지 않음
    # Pydantic 모델에 이미 검증 로직이 포함되어 있음

    

    def generate_next_task(
        self,
        doc: Any,
        task_results: List[Dict[str, Any]],
        goal: str = "보험 상품 약관 문서에서, '정의'와 '조건' 섹션을 모두 식별하고, 각 섹션에서 데이터를 추출한 뒤, 이 둘을 정규화하고 그룹핑하여 최종 보험 상품 목록을 생성하세요.",
        instruction: str = "",
        last_feedback: Optional[Dict[str, Any]] = None,
        last_task: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        PROTOTYPE 7 v2: 완료된 Task 이력을 기반으로 다음 단일 Task를 생성합니다.

        Args:
            doc: 원본 문서
            task_results: 완료된 Task 결과 목록
            goal: 최종 목표 설명

        Returns:
            Dict with either:
            - {"action": "next_task", "task": TaskDefinition}
            - {"action": "end", "reasoning": "..."}
        """
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        doc_summary = accessor.get_summary()
        tool_schemas = get_schema_prompt()

        instruction_for_next_task = (
            "조건 추출, 그룹핑, 최종 조합 단계 중 미수행된 단계가 있다면 절대 `END` 하지 마세요."
            "최종 결과까지 모든 단계가 완료되어야 합니다."
        )
        if instruction:
            instruction_for_next_task += f"\n추가 지시: {instruction}"

        prompt = build_next_task_prompt(
            doc_summary=doc_summary,
            goal=goal,
            task_results=task_results,
            tool_schemas=tool_schemas,
            instruction=instruction_for_next_task,
            last_feedback=last_feedback,
            last_task=last_task
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result = json.loads(response.choices[0].message.content)
            print("🙄🙄[PLANNER REASONING]", result.get("reasoning"))
            action = result.get("action")
            if action == "end":
                return {"action": "end", "reasoning": result.get("reasoning", "All tasks completed")}
            elif action == "next_task":
                task = result.get("task")
                if not task:
                    return {"error": "LLM returned next_task but no task object"}

                required_fields = ["task_id", "task_type", "tool_name", "parameters", "dependencies", "output_key"]
                missing = [f for f in required_fields if f not in task]
                if missing:
                    return {"error": f"Task missing required fields: {missing}"}

                return {"action": "next_task", "task": task, "reasoning": result.get("reasoning", "")}
            else:
                return {"error": f"Unknown action from LLM: {action}"}

        except Exception as e:
            return {"error": f"Next task generation failed: {str(e)}"}
