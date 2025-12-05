"""
LLM-based Dynamic Planner

문서를 분석하고 동적으로 N단계 계획을 수립합니다.
- 고정된 3단계 아님
- Rule/LLM 도구 전략 자동 선택
- 문서 특성에 맞는 최적화된 계획
"""

import json
import os
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add tools directory to path
tools_path = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_path))

from tool_schemas import get_schema_prompt
from core.prompt import build_planner_prompt, build_replan_prompt


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
