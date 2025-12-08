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
from core.prompt import build_planner_prompt, build_replan_prompt, build_dynamic_planning_prompt_v7, build_next_task_prompt
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

    def create_plan(
        self,
        doc: Any,
        instruction: Optional[str] = "",
        goal: str = "보험 상품 약관 문서에서, '정의'와 '조건' 섹션을 모두 식별하고, 각 섹션에서 데이터를 추출한 뒤, 이 둘을 정규화하고 그룹핑하여 최종 보험 상품 목록을 생성하세요."
    ) -> Dict[str, Any]:
        """
        문서에 맞는 동적 계획 수립

        Args:
            doc: 원본 문서
            goal: 최종 목표

        Returns:
            Dict: 계획
                {
                    "tasks": [
                        {
                            "task_id": str,
                            "task_type": str,
                            "tool_name": str,
                            "fallback_tool": str | null,
                            "parameters": Dict,
                            "dependencies": List[str],
                            "output_key": str
                        },
                        ...
                    ],
                    "reasoning": str,
                    "estimated_difficulty": "easy" | "medium" | "hard",
                    "total_tasks": int
                }
        """
        doc_sample = json.dumps(doc, ensure_ascii=False)
        tool_schemas = get_schema_prompt()
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        doc_summary = accessor.get_summary()

        prompt = build_dynamic_planning_prompt_v7(
            doc_summary=doc_summary,
            doc_sample=doc_sample,
            goal=goal,
            tool_schemas=tool_schemas,
            instruction=instruction,
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            plan = json.loads(response.choices[0].message.content)
            return plan

        except Exception as e:
            return {"error": f"Planning failed: {str(e)}"}

    def replan(
        self,
        failed_task: Dict[str, Any],
        error_message: str,
        validation_result: Dict[str, Any] = None,
        previous_attempts: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        실패한 Task에 대한 재계획

        Args:
            failed_task: 실패한 Task 정보
            error_message: 에러 메시지
            validation_result: Validator 결과 (있으면)
            previous_attempts: 이전 시도 기록

        Returns:
            Dict: 새로운 Task 계획
                {
                    "tool_name": str,
                    "parameters": Dict,
                    "reasoning": str,
                    "changes": str
                }
        """
        if previous_attempts is None:
            previous_attempts = []

        tool_schemas = get_schema_prompt()
        
        prompt = build_replan_prompt(
            failed_task=failed_task,
            error_message=error_message,
            validation_result=validation_result,
            previous_attempts=previous_attempts,
            tool_schemas=tool_schemas,
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.5
            )

            new_plan = json.loads(response.choices[0].message.content)
            return new_plan

        except Exception as e:
            return {"error": f"Replanning failed: {str(e)}"}

    # ========== PROTOTYPE 7: New Methods ==========

    # _validate_plan_structure 메소드는 Pydantic으로 대체되었으므로 삭제 또는 더 이상 사용되지 않음
    # Pydantic 모델에 이미 검증 로직이 포함되어 있음

    def suggest_replan(
        self,
        current_plan: Dict[str, Any],
        failed_task: TaskDefinition,
        validation_feedback: Dict[str, Any],
        task_results: List[TaskResult]
    ) -> Dict[str, Any]:
        """
        Task 실패 후 계획 조정 방법을 제안 (Prototype 7).

        세 가지 재계획 유형 중 하나를 반환:
        1. adjust_parameters: 현재 Task 파라미터 수정
        2. insert_task: 현재 Task 앞에 새 Task 삽입
        3. full_replan: 완전히 새로운 계획 생성

        Args:
            current_plan: 현재 계획 딕셔너리
            failed_task: 실패한 TaskDefinition
            validation_feedback: 에러/제안이 포함된 검증 결과
            task_results: 완료된 Task 결과 목록

        Returns:
            Dict with replan action:
            {
              "type": "adjust_parameters" | "insert_task" | "full_replan",
              "new_parameters": {...},  # if adjust
              "new_task": {...},        # if insert
              "new_instruction": "..."  # if full_replan
            }
        """
        failed_task_json = json.dumps(failed_task, ensure_ascii=False, indent=2)
        validation_json = json.dumps(validation_feedback, ensure_ascii=False, indent=2)
        plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)

        results_summary = [
            {
                "task_id": r["task_id"],
                "success": r["success"],
                "error": r.get("error")
            }
            for r in task_results
        ]
        results_json = json.dumps(results_summary, ensure_ascii=False, indent=2)

        prompt = build_replan_prompt(
            failed_task=failed_task_json,
            error_message=validation_feedback.get('errors', ['Unknown error'])[0],
            validation_result=validation_json,
            previous_attempts=results_json, # 이전 시도 내역
            tool_schemas=get_schema_prompt(),
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            replan_action = json.loads(response.choices[0].message.content)
            return replan_action

        except Exception as e:
            return {
                "type": "adjust_parameters", # Fallback to simply re-adjusting parameters
                "new_parameters": failed_task.get("parameters", {}),
                "reasoning": f"Fallback due to error in replanning: {str(e)}"
            }

    def generate_next_task(
        self,
        doc: Any,
        task_results: List[Dict[str, Any]],
        goal: str = "보험 상품 약관 문서에서, '정의'와 '조건' 섹션을 모두 식별하고, 각 섹션에서 데이터를 추출한 뒤, 이 둘을 정규화하고 그룹핑하여 최종 보험 상품 목록을 생성하세요."
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

        prompt = build_next_task_prompt(
            doc_summary=doc_summary,
            goal=goal,
            task_results=task_results,
            tool_schemas=tool_schemas,
            instruction=instruction_for_next_task # instruction 인자 추가
        )

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result = json.loads(response.choices[0].message.content)

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