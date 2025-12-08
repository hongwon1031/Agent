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
from core.prompt import build_planner_prompt, build_replan_prompt, build_dynamic_planning_prompt_v7
from core.state import TaskDefinition, TaskResult


class LLMPlanner:
    """
    LLM 기반 동적 계획 수립기

    역할:
        - 문서와 구조 분석 결과를 보고 최적의 계획 수립
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
        goal: str = """
        - 보험 상품 정의(보종명,유형계층)의 모든 조합 추출
        - 조건(보험기간/납입기간 등)에 대한 Task는 이번 계획에 포함하지 말 것
        """
    ) -> Dict[str, Any]:
        """
        문서에 맞는 동적 계획 수립

        Args:
            doc: 원본 문서
            # structure_analysis: [DEPRECATED] LLMDocumentAnalyzer의 분석 결과
            goal: 최종 목표

        Returns:
            Dict: 계획
                {
                    "tasks": [
                        {
                            "task_id": int,
                            "type": "search" | "extract" | "transform",
                            "description": str,
                            "strategy": "rule" | "llm",
                            "fallback": "llm" | null,
                            "tool_name": str,
                            "parameters": Dict,
                            "depends_on": int | null
                        },
                        ...
                    ],
                    "reasoning": str,
                    "estimated_difficulty": "easy" | "medium" | "hard"
                }
        """
        # 문서 샘플
        doc_sample = json.dumps(doc, ensure_ascii=False)

        # Tool schemas 가져오기
        tool_schemas = get_schema_prompt()
        
        # DocumentAccessor로 형식 정보 가져오기
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        doc_summary = accessor.get_summary()

        prompt = build_planner_prompt(
            doc_summary=doc_summary,
            doc_sample=doc_sample,
            goal=goal,
            tool_schemas=tool_schemas,
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3  # 약간의 창의성
            )

            plan = json.loads(response.choices[0].message.content)

            # PROTOTYPE 7: Validate plan structure if it has Prototype 7 format
            if "total_tasks" in plan and "tasks" in plan:
                if not self._validate_plan_structure(plan):
                    return {
                        "error": "Invalid plan structure (failed validation)",
                        "original_plan": plan
                    }

            return plan

        except Exception as e:
            return {
                "error": f"Planning failed: {str(e)}"
            }

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

        # Tool schemas 가져오기
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
                temperature=0.5  # 더 높은 창의성
            )

            new_plan = json.loads(response.choices[0].message.content)
            return new_plan

        except Exception as e:
            return {
                "error": f"Replanning failed: {str(e)}"
            }

    # ========== PROTOTYPE 7: New Methods ==========

    def _validate_plan_structure(self, plan: Dict[str, Any]) -> bool:
        """
        Validate plan structure for Prototype 7 dynamic execution.

        Checks:
        - Required fields exist (total_tasks, tasks, reasoning)
        - Each task has required fields
        - Dependencies only reference earlier tasks (no circular deps)
        - Task IDs are sequential

        Args:
            plan: Plan dict from LLM

        Returns:
            True if valid, False otherwise
        """
        # Check top-level keys
        required_keys = ["total_tasks", "tasks", "reasoning"]
        if not all(k in plan for k in required_keys):
            return False

        tasks = plan.get("tasks", [])
        if len(tasks) != plan.get("total_tasks", 0):
            return False

        # Check each task definition
        required_task_fields = ["task_id", "task_type", "tool_name", "parameters", "dependencies", "output_key"]
        for i, task in enumerate(tasks):
            # Check required fields
            if not all(k in task for k in required_task_fields):
                return False

            # Check task_id is sequential
            expected_id = f"task{i}"
            if task.get("task_id") != expected_id:
                return False

            # Check dependencies only reference earlier tasks
            for dep in task.get("dependencies", []):
                dep_idx = int(dep.replace("task", ""))
                if dep_idx >= i:
                    # Circular or forward dependency!
                    return False

        return True

    def suggest_replan(
        self,
        current_plan: Dict[str, Any],
        failed_task: TaskDefinition,
        validation_feedback: Dict[str, Any],
        task_results: List[TaskResult]
    ) -> Dict[str, Any]:
        """
        Suggest how to adjust plan after task failure (Prototype 7).

        Returns one of three replan types:
        1. adjust_parameters: Modify current task params
        2. insert_task: Add new task before current
        3. full_replan: Generate completely new plan

        Args:
            current_plan: Current plan dict
            failed_task: The TaskDefinition that failed
            validation_feedback: Validation result with errors/suggestions
            task_results: List of completed task results

        Returns:
            Dict with replan action:
            {
              "type": "adjust_parameters" | "insert_task" | "full_replan",
              "new_parameters": {...},  # if adjust
              "new_task": {...},        # if insert
              "new_instruction": "..."  # if full_replan
            }
        """
        # Prepare context for LLM
        failed_task_json = json.dumps(failed_task, ensure_ascii=False, indent=2)
        validation_json = json.dumps(validation_feedback, ensure_ascii=False, indent=2)
        plan_json = json.dumps(current_plan, ensure_ascii=False, indent=2)

        # Simplified task results (only show success/failure)
        results_summary = [
            {
                "task_id": r["task_id"],
                "success": r["success"],
                "error": r.get("error")
            }
            for r in task_results
        ]
        results_json = json.dumps(results_summary, ensure_ascii=False, indent=2)

        # Build prompt (will add to prompt.py in Phase 1.4)
        # For now, use inline prompt
        prompt = f"""
당신은 실행 계획을 수정하는 전문가입니다.

## 현재 계획
{plan_json}

## 실패한 작업
{failed_task_json}

## 검증 피드백
{validation_json}

## 이전 작업 결과들
{results_json}

## 목표
실패를 해결하기 위한 최소한의 계획 수정을 제안하세요.

## 수정 유형

### 1. adjust_parameters (파라미터 조정)
- 언제: 작업 로직은 맞지만 파라미터가 잘못됨
- 예시: 페이지 범위 조정, threshold 값 변경
- 출력:
{{
  "type": "adjust_parameters",
  "new_parameters": {{"pages": "3-8", "threshold": 0.7}},
  "reasoning": "조정 이유 설명"
}}

### 2. insert_task (작업 삽입)
- 언제: 현재 작업 전에 전처리가 필요함
- 예시: 섹션 분류를 안 했는데 필요함
- 출력:
{{
  "type": "insert_task",
  "new_task": {{
    "task_id": "taskN_new",
    "task_type": "classify_sections",
    "description": "섹션 분류 추가",
    "tool_name": "section_classifier",
    "fallback_tool": null,
    "parameters": {{"sections": "$sections"}},
    "dependencies": ["taskN-1"],
    "output_key": "section_info"
  }},
  "reasoning": "삽입 이유 설명"
}}

### 3. full_replan (전면 재계획)
- 언제: 근본적인 전략 변경 필요
- 예시: 문서 구조를 완전히 잘못 이해함
- 출력:
{{
  "type": "full_replan",
  "new_instruction": "문서가 단일 테이블이 아니라 여러 섹션으로 나뉨. 섹션 분류부터 시작.",
  "reasoning": "재계획 이유 설명"
}}

위 3가지 유형 중 하나를 선택하여 JSON으로 출력하세요.
특히 validation_feedback의 errors와 suggestions를 반영하세요.
"""

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
            # Fallback: adjust_parameters
            return {
                "type": "adjust_parameters",
                "new_parameters": failed_task.get("parameters", {}),
                "reasoning": f"Fallback due to error: {str(e)}"
            }
