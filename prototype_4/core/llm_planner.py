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

    # OLD signature (deprecated):
    # def create_plan(self, doc: Any, structure_analysis: Dict[str, Any], goal: str = ...) -> Dict[str, Any]:

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
        # 문서 샘플 (일부만)
        doc_sample = json.dumps(doc, ensure_ascii=False)[:2000]

        # Tool schemas 가져오기
        tool_schemas = get_schema_prompt()

        # DocumentAccessor로 형식 정보 가져오기
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        doc_summary = accessor.get_summary()

        # [DEPRECATED] DocumentAnalyzer 결과 사용 중단
        # OLD prompt included: **문서 구조 분석 결과**: {json.dumps(structure_analysis, ...)}

        prompt = f"""다음 문서에서 "{goal}"하는 계획을 수립하세요.

**문서 형식 정보**:
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

**형식별 섹션 분포**:
- Table 형식: {len(doc_summary['sections_by_format']['table_only'])}개
- Text 형식: {len(doc_summary['sections_by_format']['text_only'])}개
- Mixed 형식: {len(doc_summary['sections_by_format']['mixed'])}개

**문서 샘플**:
{doc_sample}

**목표**: {goal}

{tool_schemas}

**계획 수립 전략**:
1. **RECOMMENDED (V2 Workflow)**: 정의 추출 작업에는 section_classifier + definition_extract_v2 사용
   - Task 1: section_classifier로 모든 섹션 분류 (type: "classify")
   - Task 2: definition_extract_v2로 정의 추출 (type: "extract")
   - Task 3: rule_cartesian으로 조합 생성 (type: "transform")
   - 이 방식이 100% recall을 보장하며 가장 안정적입니다

2. **Legacy Workflow (호환성용)**: definition_search + definition_extract 또는 rule_search + rule_extract
   - 표준적인 키워드나 구조가 명확한 경우에만 사용
   - 비표준 제목이나 제목 없는 섹션은 놓칠 수 있음

3. 일반 원칙:
   - Rule 도구 우선, 실패 시 LLM fallback
   - content_type 파라미터를 명시적으로 전달
   - 각 Task는 이전 Task 결과 참조 가능 ("depends_on")

**Task 타입**:
- "classify": 섹션 분류 (section_classifier 전용)
- "search": 정의 섹션/테이블 찾기 (legacy)
- "extract": 데이터 추출
- "transform": 데이터 변환 (Cartesian Product 등)

**중요**:
- 정의 추출 작업에는 **section_classifier + definition_extract_v2를 우선 사용**하세요
- 단계 수는 유동적 (3단계일 필요 없음)
- 파라미터에 이전 Task 결과 참조는 "{{{{taskN.field}}}}" 형식
- Runtime injection 파라미터("$sections" 등)는 정확히 명시된 대로 사용할 것

**예시 출력 (V2 Workflow - RECOMMENDED)**:
{{
  "tasks": [
    {{
      "task_id": 1,
      "type": "classify",
      "description": "전체 섹션을 4가지 카테고리로 분류",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "section_classifier",
      "parameters": {{
        "sections": "$sections"
      }},
      "depends_on": null
    }},
    {{
      "task_id": 2,
      "type": "extract",
      "description": "분류된 정의 섹션에서 데이터 추출",
      "strategy": "hybrid",
      "fallback": null,
      "tool_name": "definition_extract_v2",
      "parameters": {{
        "sections": "$sections",
        "core_indices": "{{{{task1.definition_core}}}}",
        "annotation_indices": "{{{{task1.definition_annotation}}}}"
      }},
      "depends_on": 1
    }},
    {{
      "task_id": 3,
      "type": "transform",
      "description": "Cartesian Product 생성",
      "strategy": "rule",
      "fallback": null,
      "tool_name": "rule_cartesian",
      "parameters": {{
        "header": "{{{{task2.header}}}}",
        "data": "{{{{task2.data}}}}"
      }},
      "depends_on": 2
    }}
  ],
  "reasoning": "section_classifier를 사용하여 100% recall 보장, V2 workflow 적용",
  "estimated_difficulty": "medium"
}}

**예시 출력 (Legacy - 표준 구조인 경우만)**:
{{
  "tasks": [
    {{
      "task_id": 1,
      "type": "search",
      "description": "정의 섹션 찾기",
      "strategy": "rule",
      "fallback": "llm",
      "tool_name": "rule_search",
      "parameters": {{
        "keywords": ["정의", "명칭", "보험종목"],
        "sections": "$sections",
        "search_in_content": true
      }},
      "depends_on": null
    }},
    {{
      "task_id": 2,
      "type": "extract",
      "description": "데이터 추출 (형식 자동 감지)",
      "strategy": "rule",
      "fallback": "llm",
      "tool_name": "rule_extract",
      "parameters": {{
        "content": "{{{{task1.found_content}}}}",
        "content_type": "{{{{task1.content_type}}}}"
      }},
      "depends_on": 1
    }},
    {{
      "task_id": 3,
      "type": "transform",
      "description": "Cartesian Product 생성",
      "strategy": "rule",
      "fallback": null,
      "tool_name": "rule_cartesian",
      "parameters": {{
        "header": "{{{{task2.header}}}}",
        "data": "{{{{task2.data}}}}"
      }},
      "depends_on": 2
    }}
  ],
  "reasoning": "문서가 표준 구조이며 형식 정보를 활용하여 content_type을 자동 전달",
  "estimated_difficulty": "easy"
}}

위 형식의 JSON으로 계획을 반환하세요."""

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

        prompt = f"""Task가 실패했습니다. 새로운 전략을 수립하세요.

**실패한 Task**:
{json.dumps(failed_task, ensure_ascii=False, indent=2)}

**에러 메시지**:
{error_message}

**Validation 결과** (있는 경우):
{json.dumps(validation_result, ensure_ascii=False, indent=2) if validation_result else "N/A"}

**이전 시도 횟수**: {len(previous_attempts)}
**이전 시도 내역**:
{json.dumps(previous_attempts, ensure_ascii=False, indent=2)}

{tool_schemas}

**분석 및 재계획**:

1. **실패 원인 분석**:
   - Rule-based 도구 실패? → 대응하는 LLM 도구로 전환
   - 파라미터 문제? → 수정
   - 데이터 형식 문제? → instruction 추가

2. **새 전략**:
   - 도구 변경: rule → llm (정확한 tool 이름 사용!)
   - 파라미터 조정 (schema 참고)
   - instruction 추가 (LLM 도구인 경우)
     - transform task에서 llm_cartesian을 다시 사용할 때는, validation_result.errors를 요약해서 parameters.instruction에 넣어라.

3. **이전 실수 회피**:
   - 같은 도구/파라미터 재시도 금지
   - Validation 제안사항 반영

**중요**: 위의 Tool Schemas를 정확히 참고하여 올바른 tool_name을 사용하세요!
- transform task → rule_cartesian 또는 llm_cartesian
- extract task → rule_extract 또는 llm_extract
- search task → rule_search 또는 llm_search

다음 JSON 형식으로 반환:
{{
  "tool_name": "llm_extract",
  "parameters": {{
    "content": "{{{{task1.found_table}}}}",
    "instruction": "주석 행(※, 주:)을 제거하고 데이터만 추출"
  }},
  "reasoning": "Rule 추출이 주석을 못 거르므로 LLM으로 전환",
  "changes": "rule_extract → llm_extract, instruction 추가"
}}"""

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
