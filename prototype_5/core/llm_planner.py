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
        goal: str = "문서에서 모든 의미적 엔티티와 그 조합을 추출한다"
    ) -> Dict[str, Any]:
        """
        도메인 특화 instruction이 포함된 고정 3단계 실행 계획을 생성합니다.

        이 메서드는 고정된 워크플로우(Classify → Extract → Transform)를 강제하지만,
        문서 분석 결과와 사용자 목표에 따라 각 단계별로 도메인 특화 instruction을 생성합니다.

        Args:
            doc: 원본 문서
            goal: 사용자의 추출 목표(도메인 특화 목표, 기본값은 일반적인 목표)

        Returns:
            Dict: 정확히 3개의 task를 갖는 계획
                {
                    "domain_analysis": {
                        "entities": "무엇을 추출하는지에 대한 설명",
                        "categories": ["cat1", "cat2", ...],
                        "key_fields": ["field1", "field2", ...]
                    },
                    "tasks": [
                        {
                            "task_id": 1,
                            "type": "classify",
                            "description": "섹션 분류",
                            "tool_name": "section_classifier",
                            "parameters": {
                                "sections": "$sections",
                                "instruction": "상세한 분류용 instruction"
                            },
                            "depends_on": null
                        },
                        # Task 2: extract
                        # Task 3: transform
                    ],
                    "reasoning": str,
                    "estimated_difficulty": "easy" | "medium" | "hard"
                }
        """

        # 문서 샘플
        doc_sample = json.dumps(doc, ensure_ascii=False, indent=2)
        tool_schemas = get_schema_prompt()
        # DocumentAccessor로 형식 정보 가져오기
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        doc_summary = accessor.get_summary()

        prompt = f"""당신은 도메인별 추출 워크플로우를 설계하는 문서 분석 파이프라인 플래너입니다.

**Task**: 주어진 문서와 사용자 목표를 분석한 뒤, 각 단계에 대해 도메인 특화 지시사항이 포함된 고정 3단계 실행 계획(Classify → Extract → Transform)을 작성하세요.

**문서 요약(Document Summary)**:
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

**섹션 형식 분포(Section Format Distribution)**:
- Table 형식: {len(doc_summary['sections_by_format']['table_only'])}개 섹션
- Text 형식: {len(doc_summary['sections_by_format']['text_only'])}개 섹션
- Mixed 형식: {len(doc_summary['sections_by_format']['mixed'])}개 섹션

**원본 문서(Document Sample)**:
{doc_sample}...

**사용 가능한 도구**:
{tool_schemas}

**사용자 목표(User Goal)**: {goal}

---

**Your Job**:

1. **도메인 분석(Analyze the Domain)**:
   - 어떤 엔티티를 추출해야 하나요? (예: 상품 정의, 법률 조항, 재고 항목 등)
   - 어떤 카테고리들이 존재하나요? (예: core definitions, annotations, conditions)
   - 어떤 key field들을 추출해야 하나요? (예: name, type, coverage)

2. **3단계 Instruction 설계(Design 3-Stage Instructions)**:
   - **Stage 1 (Classify)**: 카테고리 정의를 포함한 분류용 instruction 작성
   - **Stage 2 (Extract)**: 필드 이름과 규칙이 포함된 추출용 instruction 작성
   - **Stage 3 (Transform)**: 구분자(delimiter) 규칙이 포함된 변환용 instruction 작성

3. **문서 특성 고려(Consider Document Characteristics)**:
   - 구조가 표준화되어 있으면 → 키워드와 rule 기반 도구 활용
   - 구조가 비표준이면 → 의미 기반 분류와 LLM 도구 활용
   - 형식이 섞여 있으면 → 하이브리드 접근

---

**출력 형식(Output Format)** (JSON):

세 task 모두 parameters.instruction가 반드시 있어야 한다.

{{
  "domain_analysis": {{
    "entities": "우리가 무엇을 추출하는지에 대한 짧은 설명",
    "categories": ["category1", "category2", "category3"],
    "key_fields": ["field1", "field2", "field3"]
  }},
  "tasks": [
    {{
      "task_id": 1,
      "type": "classify",
      "description": "섹션들을 의미 기반 카테고리로 분류",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "section_classifier",
      "parameters": {{
        "sections": "$sections",
        "instruction": "여기에 상세한 분류용 instruction을 작성하세요. 반드시 다음 내용을 포함해야 합니다:
- 도메인 컨텍스트 (예: 'This is an insurance policy document')
- 카테고리 정의 (예: 'definition_core: sections containing product names and types')
- 분류 기준 (예: 'Look for tables with columns like Name, Type')
- 출력 형식 명세 (카테고리명을 key, 섹션 인덱스 배열을 value로 갖는 JSON)"
      }},
      "depends_on": null
    }},
    {{
      "task_id": 2,
      "type": "extract",
      "description": "분류된 섹션에서 구조화된 데이터 추출",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "definition_extract_v2",
      "parameters": {{
        "content": "{{{{task1.definition_core}}}}",
        "content_type": "table",
        "instruction": "여기에 상세한 추출용 instruction을 작성하세요. 반드시 다음 내용을 포함해야 합니다:
- 어떤 데이터를 추출할지 (예: 'Extract product name, type, and coverage fields')
- 특수 케이스 처리 방식 (예: 'Skip annotation rows marked with ※')
- 기대되는 출력 구조 (예: 'header: [Name, Type, Coverage], data: [[...], [...]]')"
      }},
      "depends_on": 1
    }},
    {{
      "task_id": 3,
      "type": "transform",
      "description": "추출된 데이터로부터 모든 조합 생성",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "llm_cartesian",
      "parameters": {{
        "header": "{{{{task2.header}}}}",
        "data": "{{{{task2.data}}}}",
        "instruction": "여기에 상세한 변환용 instruction을 작성하세요. 반드시 다음 내용을 포함해야 합니다:
- 구분자(delimiter) 판단 규칙 (예: 'Column 1 uses / as delimiter, Column 2 uses , as delimiter')
- 어떤 컬럼을 split하고 어떤 컬럼은 그대로 둘지
- 조합 생성 방법 (예: 'Create one definition per combination of split values')
- 출력 형식 (필드를 가진 definitions 배열)"
      }},
      "depends_on": 2
    }}
  ],
  "reasoning": "이 접근법이 해당 문서에 적합한 이유에 대한 설명 (예: 섹션 제목이 비표준이므로 의미 기반 분류가 필요하고, 테이블 형식이 구조화된 추출에 유리하다 등)",
  "estimated_difficulty": "easy | medium | hard"
}}

---

**Important Guidelines**:

1. 항상 **classify → extract → transform 순서의 3개 task**만 반환해야 합니다.
2. **각 instruction은 상세하고 도메인 특화되어야** 하며, 기존 하드코딩된 프롬프트를 대체합니다.
3. 도구들이 일반화된 base 프롬프트를 가지므로, **strategy는 'llm'을 사용**하는 것이 좋습니다.
4. 이전 task 출력은 `{{{{task1.field_name}}}}` 와 같은 형식으로 참조하세요.
5. 문서 샘플을 분석하여 도메인과 구조를 충분히 이해한 뒤 계획을 세우세요.

**예시(Example)** (보험 문서):

{{
  "domain_analysis": {{
    "entities": "상품명, 유형, 보장 카테고리 등을 포함한 보험 상품 정의",
    "categories": ["definition_core", "definition_annotation", "condition", "other"],
    "key_fields": ["product_name", "product_type", "coverage_category"]
  }},
  "tasks": [
    {{
      "task_id": 1,
      "type": "classify",
      "description": "정의 관련 카테고리로 섹션 분류",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "section_classifier",
      "parameters": {{
        "sections": "$sections",
        "instruction": "이 문서는 보험 약관 문서입니다. 각 섹션을 다음 카테고리 중 하나로 분류하세요:
        \n\n- definition_core: 상품명과 유형이 포함된 주요 상품 정의 테이블이 있는 섹션 (키워드 예: 명칭, 보험종목, 보장명)
        \\n- definition_annotation: 정의에 대한 주석/설명을 담고 있는 섹션 (예: 주, ※, 가입유형)
        \\n- condition: 보장 조건이나 가입 요건을 설명하는 섹션
        \n- other: 위 어느 쪽에도 속하지 않는 나머지 섹션
        \n\n출력 JSON 형식 예시: {{\\"definition_core\\": [0, 3], \"\definition_annotation\":\ [1], \"co\ndition\": [\5, 7], 
        \"othe\r\": [2,\ 4, 6], \"reason\ing\": \"...\\"}}"
      }},
      "depends_on": null
    }},
    {{
      "task_id": 2,
      "type": "extract",
      "description": "상품 정의 테이블 추출",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "definition_extract_v2",
      "parameters": {{
        "content": "{{{{task1.definition_core}}}}",
        "content_type": "table",
        "instruction": "아래 필드를 포함하도록 상품 정의 테이블을 추출하세요:\n- Product name (보종명, 명칭)\\n- Product type (유형, 가입유형)\\n- Coverage category (보장종목, 보장구분)\\n\\nRules:\\n- ※, 주:, 주), *, - 가 포함된 주석 행은 모두 건너뛰세요.\\n- 특수 문자와 공백은 정규화(normalize)하세요.\\n- header는 컬럼 이름 리스트로, data는 행 리스트(각 행은 값 리스트)로 반환하세요.\\n\\nOutput: {{\\"header\\": [...], \"\data\":\ [[...], [...]], \"ex\traction_method\": \\"tabl\e\", \"n\otes\\": \"...\\"}}"
      }},
      "depends_on": 1
    }},
    {{
      "task_id": 3,
      "type": "transform",
      "description": "모든 상품 정의 조합 생성",
      "strategy": "llm",
      "fallback": null,
      "tool_name": "llm_cartesian",
      "parameters": {{
        "header": "{{{{task2.header}}}}",
        "data": "{{{{task2.data}}}}",
        "instruction": "다중 값이 들어 있는 셀을 파싱하여 가능한 모든 조합을 생성하세요:\n\nDelimiter Detection (컬럼 단위):\n- 상품명 컬럼: 기본 구분자는 보통 / 입니다.\n- 유형 컬럼: 기본 구분자는 , 또는 / 일 수 있습니다.\n- 카테고리 컬럼: 기본 구분자는 보통 / 입니다.\n\nRules:\n1. 컬럼 전체를 대상으로 구분자 등장 빈도를 계산하여 기본 구분자를 식별하세요.\n2. 셀은 기본 구분자로만 split 하세요.\n3. 각 값에서 공백과 줄바꿈을 제거하세요.\n4. 컬럼 간 Cartesian product를 생성하여, 각 조합마다 하나의 definition을 만들세요.\n\nOutput: {{\\"parsed_rows\\": [[[val1], [val2a, val2b], ...], ...]}}"
      }},
      "depends_on": 2
    }}
  ],
  "reasoning": "보험 약관 문서는 보통 정의 테이블 구조가 표준화되어 있지만, 섹션 제목은 다양할 수 있습니다. 따라서 의미 기반 분류로 정의 섹션을 찾고, LLM 기반 추출로 주석을 처리하며, LLM 기반 변환으로 유연한 구분자 처리와 조합 생성을 수행하는 것이 적합합니다.",
  "estimated_difficulty": "medium"
}}

위 JSON 형식에 맞추어 당신의 계획을 반환하세요."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            plan = json.loads(response.choices[0].message.content)
            print(plan)
            # Validate 3-stage workflow
            if "tasks" not in plan:
                return {"error": "Plan must contain 'tasks' field"}

            tasks = plan["tasks"]

            # Must have exactly 3 tasks
            if len(tasks) != 3:
                return {"error": f"Plan must have exactly 3 tasks, got {len(tasks)}"}

            # Validate task sequence: classify → extract → transform
            expected_types = ["classify", "extract", "transform"]
            for i, task in enumerate(tasks):
                if task.get("type") != expected_types[i]:
                    return {
                        "error": f"Task {i+1} must be type '{expected_types[i]}', got '{task.get('type')}'"
                    }

                # Validate task_id matches position
                if task.get("task_id") != i + 1:
                    return {
                        "error": f"Task {i+1} must have task_id={i+1}, got {task.get('task_id')}"
                    }

                # Validate instruction exists in parameters
                if "parameters" not in task or "instruction" not in task["parameters"]:
                    return {
                        "error": f"Task {i+1} must have 'instruction' in parameters"
                    }

            # Validate domain_analysis exists
            if "domain_analysis" not in plan:
                return {"error": "Plan must contain 'domain_analysis' field"}

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
        Replan a failed task with targeted instruction refinement

        Uses problem_type from validation_result to apply targeted fixes:
        - "no_sections_found" → improve classification criteria
        - "empty_extraction" → add field identification hints
        - "delimiter_detection_error" → add column-wise delimiter hints
        - etc.

        Args:
            failed_task: Failed task information
            error_message: Error message
            validation_result: Validator result with problem_type
            previous_attempts: Previous attempt history

        Returns:
            Dict: New task plan
                {
                    "tool_name": str,
                    "parameters": Dict,
                    "reasoning": str,
                    "changes": str
                }
        """
        if previous_attempts is None:
            previous_attempts = []

        problem_type = validation_result.get("problem_type") if validation_result else None
        tool_schemas = get_schema_prompt()
        prompt = f"""어떤 Task가 실패했으며, 더 나은 instruction으로 재계획이 필요합니다.

**실패한 Task(Failed Task)**:
{json.dumps(failed_task, ensure_ascii=False, indent=2)}

**에러 메시지(Error Message)**:
{error_message}

**사용 가능한 도구**:
{tool_schemas}

**검증 결과(Validation Result)**:
{json.dumps(validation_result, ensure_ascii=False, indent=2) if validation_result else "N/A"}

**Problem Type**: {problem_type or "Unknown"}

**이전 시도 횟수(Previous Attempts)**: {len(previous_attempts)}
{json.dumps(previous_attempts, ensure_ascii=False, indent=2) if previous_attempts else "None"}

---

**Your Task**: 위에서 확인된 문제를 해결할 수 있도록 `instruction` 파라미터를 개선하세요.

**Problem-Specific Guidance**:

1. **no_sections_found** (Classify 단계):
   - 더 구체적인 분류 기준을 추가하세요.
   - 찾아야 할 키워드의 대안을 제시하세요.
   - 섹션 내용 패턴(예: 어떤 표현/구조를 갖는지)을 더 자세히 설명하세요.

2. **classification_schema_error** (Classify 단계):
   - 기대하는 카테고리 이름들을 명확히 하세요.
   - 출력 JSON 형식을 명시적으로 설명하세요.
   - 카테고리 정의 예시를 제공하세요.

3. **empty_extraction** (Extract 단계):
   - 필드 식별 힌트(컬럼명, 패턴 등)를 추가하세요.
   - 엣지 케이스를 어떻게 처리할지 명시하세요.
   - 기대되는 데이터 구조를 더 분명하게 설명하세요.

4. **schema_mismatch** (Extract 단계):
   - 기대하는 필드 이름을 명시적으로 나열하세요.
   - 필드 값의 형식/패턴을 정의하세요.
   - 올바른 데이터 예시를 포함하세요.

5. **delimiter_detection_error** (Transform 단계):
   - 컬럼별 구분자 힌트를 추가하세요.
   - 어떤 컬럼이 어떤 구분자를 사용하는지 명시하세요.
   - 검증 에러에서 나온 예시를 instruction에 반영하세요.
   - 구분자 빈도 분석 방법을 설명하세요.

6. **missing_fields** (Transform 단계):
   - 어떤 필드가 필수인지 명확히 적으세요.
   - 원본 데이터 필드를 결과 필드에 어떻게 매핑할지 지시하세요.
   - 필드 값을 어떻게 생성/보완해야 하는지 설명하세요.

7. **duplicate_combinations** (Transform 단계):
   - 중복 제거(deduplication) 규칙을 추가하세요.
   - 어떤 기준으로 “유일한 조합”을 정의하는지 명시하세요.
   - 중복된 조합을 어떻게 병합할지 설명하세요.

8. **한국어로 작성하세요**
---

**Strategy**:

1. **같은 Tool을 유지합니다** - Tool을 바꾸는 것이 아니라 instruction을 개선합니다.
2. **Validation 에러를 분석합니다** - 구체적인 예시와 패턴을 뽑아내세요.
3. **instruction을 강화합니다** - problem_type에 맞는 타깃 지침을 추가하세요.
4. **같은 실수를 반복하지 마세요** - previous_attempts를 참고하여 새로운 접근을 설계하세요.

**Important**: 초점은 `instruction` 파라미터 개선입니다.  
instruction은 식별된 문제를 정확히 겨냥해서, 충분히 구체적이고 상세해야 합니다.

---

**출력 형식(Output Format)** (JSON):

{{
  "tool_name": "same_tool_as_before",
  "parameters": {{
    "sections": "$sections",  // 또는 원래 task에서 사용하던 다른 파라미터들
    "instruction": "REFINED INSTRUCTION HERE - problem_type을 구체적으로 해결하는 지시문"
  }},
  "reasoning": "어떤 점이 변경되었고, 왜 이 변경이 문제를 해결할 것인지에 대한 짧은 설명",
  "changes": "instruction 수정 사항 요약"
}}

**예시(Example)** (Transform 단계에서 delimiter_detection_error 발생 시):

{{
  "tool_name": "llm_cartesian",
  "parameters": {{
    "header": "{{{{task2.header}}}}",
    "data": "{{{{task2.data}}}}",
    "instruction": "다음과 같이 컬럼별 구분자를 고려하여 다중 값 셀을 파싱하세요:\\n\\n**Column 1 (보종명)**: 기본 구분자는 / 입니다 (콤마로는 split 하지 마세요).\\n- 예시: '암보장/CI보장' → ['암보장', 'CI보장']\\n\\n**Column 2 (유형)**: 기본 구분자는 , 입니다 (슬래시로는 split 하지 마세요).\\n- 예시: '일반형, 간편심사형' → ['일반형', '간편심사형']\\n\\n**Column 3 (보장종목)**: 기본 구분자는 / 입니다.\\n\\nRules:\\n1. 각 컬럼별로 전체 데이터에 대해 구분자 빈도를 먼저 분석합니다.\\n2. 각 컬럼에서 가장 많이 등장하는 구분자만 split에 사용합니다.\\n3. 나머지 구분자는 내용의 일부로 취급합니다.\\n4. split된 각 값의 공백을 제거합니다.\\n5. 컬럼 간 Cartesian product를 생성하여 조합별 정의를 만듭니다."
  }},
  "reasoning": "Validation 결과에서 구분자 탐지가 잘못된 것이 원인이었다는 점을 반영하여, 컬럼별 구분자 규칙과 실제 데이터 패턴 기반 예시를 instruction에 명시적으로 추가했습니다.",
  "changes": "컬럼별 구분자 규칙과 Validation 에러에서 나온 예시를 포함하도록 instruction을 강화함"
}}

이제 위 형식에 맞추어 개선된 plan을 생성하세요:
"""

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
