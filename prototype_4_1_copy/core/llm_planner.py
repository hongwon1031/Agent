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

        prompt = f"""당신은 문서 분석 파이프라인의 계획 수립 전문가입니다.
주어진 문서와 목표를 분석하여 최적의 실행 계획을 수립하세요.

**문서 정보**:
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

**형식별 섹션 분포**:
- Table 형식: {len(doc_summary['sections_by_format']['table_only'])}개
- Text 형식: {len(doc_summary['sections_by_format']['text_only'])}개
- Mixed 형식: {len(doc_summary['sections_by_format']['mixed'])}개

**문서 샘플**:
{doc_sample}

**목표**: {goal}

---

**사용 가능한 도구**:
{tool_schemas}

---

**계획 수립 가이드라인**:

1. **도구 선택 원칙**:
   - 각 도구의 description과 supported_formats를 확인하여 문서에 적합한 도구를 선택하세요
   - Rule 기반 도구가 적용 가능하면 우선 사용하고, 필요시 LLM 도구를 fallback으로 지정하세요
   - [DEPRECATED] 표시된 도구는 가급적 사용하지 마세요 (새 버전이 있다면 그것을 우선)

2. **Task 구성**:
   - 정확히 3단계의 Task를 구성하세요 (고정된 워크플로우)
    **Step 1: Classify Task**
      - Tool: section_classifier (고정)
      - Type: "classify"
    **Step 2: Extract Task**
      - Tool: definition_extract_v2 (고정)
      - Type: "extract"
    **Step 3: Transform Task**
      - Tool: rule_cartesian 또는 llm_cartesian (선택 가능)
      - Type: "transform"
   - 각 Task는 명확한 목적을 가지며, 이전 Task 결과에 의존합니다


3. **파라미터 참조**:
   - 이전 Task 결과 참조: "{{{{taskN.field}}}}" 형식 사용
   - Runtime injection: "$sections" (전체 섹션), "$doc" (전체 문서)
   - 도구 스키마의 parameter 설명을 참고하여 정확히 전달하세요

4. **Strategy 지정**:
   - "rule": Rule 기반 도구
   - "llm": LLM 기반 도구
   - "hybrid": Rule + LLM 조합
   - Fallback: 실패 시 시도할 다른 strategy (예: "rule" → "llm")

---

**출력 형식** (JSON):
{{
  "tasks": [
    {{
      "task_id": 1,
      "type": "classify | extract | transform",
      "description": "Task에서 수행할 작업 설명",
      "strategy": "rule | llm | hybrid",
      "fallback": "llm | null",
      "tool_name": "도구 이름",
      "parameters": {{
        "param1": "value or {{{{taskN.field}}}} or $runtime_var"
      }},
      "depends_on": null | task_id
    }}
  ],
  "reasoning": "이 계획을 선택한 이유 (문서 특성, 도구 선택 근거 등)",
  "estimated_difficulty": "easy | medium | hard"
}}

---

**예시 1** (섹션 분류가 필요한 경우):
{{
  "tasks": [
    {{
      "task_id": 1,
      "type": "classify",
      "description": "전체 섹션을 의미 기반으로 분류",
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
      "description": "분류된 섹션에서 정의 데이터 추출",
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
      "description": "정의 조합 생성",
      "strategy": "rule",
      "fallback": "llm",
      "tool_name": "rule_cartesian",
      "parameters": {{
        "header": "{{{{task2.header}}}}",
        "data": "{{{{task2.data}}}}"
      }},
      "depends_on": 2
    }}
  ],
  "reasoning": "비표준 섹션 제목이 예상되므로 semantic classification 사용, 조합 생성은 rule 기반으로 빠르게 처리",
  "estimated_difficulty": "medium"
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

   **A. Classify Task (section_classifier - 도구 고정)**:
   - **tool_name은 "section_classifier"로 유지** (변경 불가)
   - **validation_result.errors와 suggestions를 요약하여 parameters.instruction에 추가**
   - 예: "섹션 3은 definition_core로 분류할 것. 섹션 5는 condition이 아니라 other로 분류할 것."
   - 다른 parameters는 그대로 유지

   **B. Extract Task (definition_extract_v2 - 도구 고정)**:
   - **tool_name은 "definition_extract_v2"로 유지** (변경 불가)
   - **validation_result.errors와 suggestions를 요약하여 parameters.instruction에 추가**
   - 예: "주석 행(※, 주:)을 제거할 것. 원본 테이블의 모든 행을 누락 없이 추출할 것."
   - 다른 parameters는 그대로 유지

   **C. Transform Task (도구 변경 가능)**:
   - 도구 변경: rule_cartesian → llm_cartesian (정확한 tool 이름 사용!)
   - 파라미터 조정 (schema 참고)
   - instruction 추가 (LLM 도구인 경우)
     - transform task에서 llm_cartesian을 다시 사용할 때는, validation_result.errors를 요약해서 parameters.instruction에 넣어라.

3. **이전 실수 회피**:
   - 같은 도구/파라미터 재시도 금지 (instruction은 변경해야 함!)
   - Validation 제안사항 반영

**중요**: 다음 도구만 사용 가능합니다:
- classify task → section_classifier (고정, instruction으로 조정)
- extract task → definition_extract_v2 (고정, instruction으로 조정)
- transform task → rule_cartesian 또는 llm_cartesian (선택 가능)

다음 JSON 형식으로 반환:

**예시 1 - Transform Task (도구 변경)**:
{{
  "tool_name": "llm_cartesian",
  "parameters": {{
    "header": "{{{{task2.header}}}}",
    "data": "{{{{task2.data}}}}",
    "instruction": "보종명과 유형을 명확히 구분할 것. 첫 번째 컬럼이 보종명이어야 함."
  }},
  "reasoning": "Rule cartesian이 계층 구조를 잘못 해석하므로 LLM으로 전환",
  "changes": "rule_cartesian → llm_cartesian, instruction 추가"
}}

**예시 2 - Classify Task (도구 고정, instruction 추가)**:
{{
  "tool_name": "section_classifier",
  "parameters": {{
    "sections": "$sections",
    "instruction": "섹션 2는 definition_core로 분류할 것 (상품 종류를 정의하는 테이블 포함). 섹션 5는 condition으로 분류할 것 (보험기간 정보 포함)."
  }},
  "reasoning": "Validator 지적사항을 반영하여 특정 섹션 분류 기준 명시",
  "changes": "instruction parameter 추가로 분류 기준 조정"
}}

**예시 3 - Extract Task (도구 고정, instruction 추가)**:
{{
  "tool_name": "definition_extract_v2",
  "parameters": {{
    "sections": "$sections",
    "core_indices": "{{{{task1.definition_core}}}}",
    "annotation_indices": "{{{{task1.definition_annotation}}}}",
    "instruction": "주석 행(※, 주:)을 데이터로 포함하지 말 것. 원본 테이블의 모든 데이터 행을 누락 없이 추출할 것."
  }},
  "reasoning": "Validator가 지적한 주석 포함 및 데이터 누락 문제 해결",
  "changes": "instruction parameter 추가로 추출 기준 조정"
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
