import json
from typing import List, Dict, Any
# ================================ 🔥🔥🔥🔥🔥PLANNER🔥🔥🔥🔥🔥================================

# ==================================================================================================
# create_plan
# ==================================================================================================

def build_planner_prompt(
    doc_summary: dict,
    doc_sample: str,
    goal: str,
    tool_schemas: str,
) -> str:
    doc_summary_json = json.dumps(doc_summary, ensure_ascii=False, indent=2)

    prompt = f"""당신은 문서 분석 파이프라인의 계획 수립 전문가입니다.
주어진 문서와 목표를 분석하여 최적의 실행 계획을 수립하세요.

**문서 정보**:
{doc_summary_json}

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
    return prompt

# ==================================================================================================
# replan
# ==================================================================================================

def build_replan_prompt(
    failed_task: dict,
    error_message: str,
    validation_result: dict | None,
    previous_attempts: list[dict],
    tool_schemas: str,
) -> str:
    failed_task_json = json.dumps(failed_task, ensure_ascii=False, indent=2)
    validation_json = (
        json.dumps(validation_result, ensure_ascii=False, indent=2)
        if validation_result else "N/A"
    )
    attempts_json = json.dumps(previous_attempts, ensure_ascii=False, indent=2)

    prompt = f"""Task가 실패했습니다. 새로운 전략을 수립하세요.

**실패한 Task**:
{failed_task_json}

**에러 메시지**:
{error_message}

**Validation 결과** (있는 경우):
{validation_json}

**이전 시도 횟수**: {len(previous_attempts)}
**이전 시도 내역**:
{attempts_json}

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
    return prompt

# ================================ 🔥🔥🔥🔥🔥VALIDATOR🔥🔥🔥🔥🔥================================

# ==================================================================================================
# validate_section_classifier_llm
# ==================================================================================================

def build_validate_section_classifier_llm(
    definition_core: List[int],
    definition_annotation: List[int],
    condition: List[int],
    other: List[int],
    core_samples: List[Dict[str, Any]],
    annotation_samples: List[Dict[str, Any]],
    condition_samples: List[Dict[str, Any]],
    other_samples: List[Dict[str, Any]],
) -> str:
    base = f"""당신은 보험 약관 문서의 섹션 분류 결과를 검토하는 전문가입니다.

**임무**: 다음 분류 결과가 **전반적으로 합리적인지** 확인하세요.

**분류 결과 요약**:
- definition_core (정의 핵심): {len(definition_core)}개 섹션
- definition_annotation (정의 보조): {len(definition_annotation)}개 섹션
- condition (보장 조건): {len(condition)}개 섹션
- other (기타): {len(other)}개 섹션

**definition_core 샘플 섹션들**:
{json.dumps(core_samples, ensure_ascii=False, indent=2)}

**definition_annotation 샘플 섹션들**:
{json.dumps(annotation_samples, ensure_ascii=False, indent=2)}

**condition 샘플 섹션들**:
{json.dumps(condition_samples, ensure_ascii=False, indent=2)}

**other 샘플 섹션들**:
{json.dumps(other_samples, ensure_ascii=False, indent=2)}

### 카테고리 정의 (참고용)

1. **definition_core** (핵심 정의 섹션)
   - 질문: 이 문서에서 정의하는 **상품/특약/보장계약이 무엇이며, 어떤 종류/조합으로 구성되어 있는가?**
   - 예: 상품/특약의 명칭과 버전(해약환급금 미지급형 vs 일반형), 1종/2종, 주계약/특약 등
   - 특징: "무엇으로 구성되어 있는지"를 설명하는 정적인 구조 정의
   - **"정의"와 "설명"은 실질적으로 같은 의미입니다. 구분하지 마세요.**

2. **definition_annotation** (정의 주석/보충 섹션)
   - 질문: 위에서 정의한 구조에 대해 **어떤 예외/변경/추가 설명**이 있는가?
   - 예: 명칭/표기법 설명, 정의값에 대한 보충, 각주, "※", "참고" 등
   - 특징: definition_core에서 정의한 값들을 수정/보완/해석하는 텍스트

3. **condition** (계약/가입 조건 섹션)
   - 질문: 각 종류(유형/종/보장형)를 **어떤 조건으로 가입/유지할 수 있는가?**
   - 예: 보험기간, 보험료 납입기간, 가입나이, 보험료 납입주기 등
   - 특징: 기간/연령/납입 조건을 수치/범위로 표현
   - **중요**: "유형1", "유형2" 같은 컬럼이 있어도 condition일 수 있음 (숫자 조건 컬럼이 2개 이상이면 condition 가능성 높음)

4. **other** (기타 섹션)
   - 위 3가지에 해당하지 않는 모든 섹션

### 검토 규칙

**중요한 마음가짐**:
- 분류 시스템이 이미 전문적으로 분류했다고 가정하세요
- **명백하고 심각한 오류**만 지적하세요
- 사소한 차이나 애매한 경계는 무시하세요
- **3개 이상의 명백한 오분류**가 있을 때만 is_valid=false로 설정하세요

**합리적인 분류 (is_valid=true)**:
- definition_core에 상품 구조/종류/명칭 관련 내용이 있음
- condition에 기간/나이 등 조건 정보가 있음
- 대부분의 분류가 말이 됨

**명백한 오류 (is_valid=false가 될 수 있음)**:
- definition_core에 정의 관련 내용이 전혀 없고 조건만 있음
- condition에 정의 테이블만 있고 조건이 없음
- **3개 이상**의 섹션이 명백하게 잘못 분류됨

**무시해야 할 것들**:
- "정의한다" vs "설명한다" 같은 표현 차이 → 실질적으로 같음
- core vs annotation의 경계 애매함 → 둘 다 합리적이면 OK
- 제목과 내용의 미묘한 불일치 → 내용 우선

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오분류만 기록 (사소한 차이는 무시)
    // 예: "섹션 5가 definition_core로 분류되었으나 명백히 조건 테이블임"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
  ],
  "reasoning": "분류 결과가 전반적으로 합리적인지 평가"
}}

**참고**: 당신의 역할은 재분류가 아니라 합리성 확인입니다. 애매한 경우는 is_valid=true를 반환하세요."""

    return base

# ==================================================================================================
# validate_definition_extract_v2_llm
# ==================================================================================================

def build_validate_definition_extract_v2_llm(
    definition_sections: List[Dict[str, Any]],
    header: List[str],
    data: List[List[str]],
) -> str:
    base = f"""당신은 데이터 추출 품질을 검토하는 전문가입니다.

**임무**:
- DefinitionExtractV2 도구가 원본 섹션에서 테이블을 **올바르게 추출**했는지 확인하세요.
- 정의 관련 섹션들(테이블 + 텍스트)를 보고, DefinitinoExtractV2가 추출한 테이블이 이 섹션들의 정의 + 주석/예외를 대체로 잘 반영했는지 확인하세요

**원본 정의 관련 섹션들 (샘플)**:
{json.dumps(definition_sections, ensure_ascii=False, indent=2)}

**추출된 테이블**:
Header: {json.dumps(header, ensure_ascii=False)}
Data 행 수: {len(data)}
전체 Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

### DefinitionExtractV2의 역할 이해하기

**ExtractV2가 하는 일**:
- 원본 core 섹션의 테이블/텍스트에서 **있는 그대로** header와 data 추출
- 원본 컬럼명 유지 (예: "명칭", "보험종목" → 그대로 사용)
- 여러 core 섹션의 테이블 병합
- **Annotation 섹션이 있으면** LLM으로 병합 (주석 반영해서 테이블 업데이트)

**ExtractV2가 하지 않는 일** (이건 다음 단계인 Cartesian의 역할):
- ❌ 컬럼명 정규화 ("명칭" → "보종명", "보험종목" → "유형1" 변환 등)
- ❌ 계층 구조 확장/재구성
- ❌ 데이터 변환/재배치

### 검증 기준 (추출 품질만 확인)

**합리적인 추출 (is_valid=true)**:
1. Header와 Data가 비어있지 않음
2. 원본 정의 섹션의 주요 내용이 누락되지 않음
3. 주석 행("※", "주:", "*")이 데이터로 잘못 포함되지 않음
4. 여러 섹션 병합 시 데이터 손실이나 중복이 없음
5. 정의 섹션 안에 주석/예외 텍스트가 있는 경우, 주석/예외 내용이 합리적으로 반영됨 (완벽하지 않아도 OK)

**명백한 추출 오류 (is_valid=false가 될 수 있음)**:
1. Header나 Data가 완전히 비어있음
2. 원본 데이터의 col,row값과 Header,Data의 값이 일치하지 않음
3. 원본 정의 섹션에 있는 중요한 데이터 행이 추출되지 않음
4. "※", "주:", "참고" 같은 주석이 데이터 행으로 잘못 포함됨
5. 여러 테이블 병합 시 명백한 헤더 불일치로 데이터 깨짐
6. 정의 테이블과 주석/예외 병합 과정에서 정의 데이터가 손실되거나 완전히 잘못됨
7. 원본 테이블의 컬럼이 누락됨 (예: 원본 4개 컬럼 → 추출 결과 3개 컬럼)

**무시해야 할 것들** (다음 단계의 역할):
- ❌ "보종명" 컬럼이 없다 → 원본에 "명칭"이면 그대로 추출하는 게 맞음
- ❌ "유형1", "유형2"로 표준화 안 됨 → Cartesian의 역할
- ❌ 계층 구조가 부족함 → 원본 그대로 추출하면 OK
- ❌ 컬럼명이 이상함 → 원본이 이상한 거면 그대로 추출하는 게 맞음

### 검토 규칙

**중요한 마음가짐**:
- ExtractV2는 **변환기가 아니라 추출기**입니다
- 원본에 있는 내용을 **있는 그대로** 잘 가져왔는지만 확인하세요
- 컬럼명 표준화나 구조 개선은 다음 단계의 역할입니다
- **명백한 추출 오류**만 지적하세요

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 추출 오류만 기록
    // 예: "원본 테이블의 2번째 행이 누락됨"
    // 예: "주석 행 '※ 참고사항'이 데이터로 잘못 포함됨"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "LLM 기반 추출로 재시도"
  ],
  "reasoning": "원본 섹션의 내용이 테이블로 올바르게 추출되었는지 평가"
}}

**참고**: 컬럼명이나 구조가 이상해도, 원본이 그렇다면 올바른 추출입니다. is_valid=true를 반환하세요."""

    return base

# ==================================================================================================
# validate_transform
# ==================================================================================================

def build_validate_transform_llm(
    header: List[str],
    data: List[List[str]],
    definitions: List[Dict[str, Any]],
) -> str:
    header_json = json.dumps(header, ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    defs_json = json.dumps(definitions, ensure_ascii=False, indent=2)

    count = len(definitions)

    base = f"""다음은 Cartesian Product 생성 결과입니다.

**원본 Data**:
Header: {header_json}
Data 전체:
{data_json}

**생성된 definitions**:
개수: {count}
전체 목록:
{defs_json}

**검증 목표**: Cartesian Product가 원본 정의 테이블을 기반으로 **합리적인 조합**을 생성했는지 확인하세요.

### 검증 기준

1. **핵심 컬럼 보존**
   - 최종 definitions의 각 항목에는 원본 Header에서 온 핵심 컬럼
     (예: "명칭"/"보종명", "보험종목"/"유형1" 등)이 빠짐없이 존재해야 합니다.
   - 보종명 값이 중간에서 끊기거나 둘로 쪼개진 경우는 오류입니다.
     (예: "[3-100%장해형]재해장해특약(무배당" / "해약환급금 미지급형)")

2. **구분자 사용 (`,` vs `/`)**
   - 각 컬럼별로 `/`와 `,` 중 **어느 것이 더 자주 등장하는지** 보고
     그 컬럼의 **주 구분자(primary delimiter)** 를 판단해야 합니다.
   - 주 구분자가 `,`인 컬럼에서는 `/`는 내용의 일부로 취급해야 합니다.
     예: "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"
       → `,`가 주 구분자, "남성/여성생식기암"은 하나의 값으로 유지해야 함.
   - 주 구분자가 `/`인 컬럼에서는 `/`로 옵션을 나누고, `,`는 값 내부에서만 사용됩니다.

3. **개수/조합 합리성**
   - definitions 개수가 원본 Data의 구조로부터 기대되는 범위에서 크게 벗어나지 않아야 합니다
     (불필요한 과분할 혹은 너무 적은 조합은 의심 대상).
   - 보종명 + 유형 조합이 명백히 중복되는 경우가 많다면 오류입니다.

4. **값 잘림 여부**
   - 보종명(명칭) 값이 중간에서 끊기지 않고 온전히 유지되어야 합니다.
   - 줄바꿈(`\n`)이 공백으로 바뀌는 것은 허용되지만, 텍스트 일부가 사라지면 안 됩니다.

5. **유형 컬럼 정합성**
   - "보험종목", "보험종목_1", "유형1", "유형2" 등 유형 관련 값들이 서로 섞여 있지 않고,
     사람이 보기에도 자연스럽게 조합된 경우라면 OK입니다.

### 판단 규칙

**합리적인 결과 (is_valid=true)**:
- 위 기준들을 대체로 만족하고,
- 보종명/유형 조합이 중복 없이, 잘리지 않고, 구분자 사용도 자연스러우면 됩니다.

**명백한 오류 (is_valid=false)**:
- 원본 Header 개수와 definitions에서 실질적으로 쓰이는 컬럼 축 개수가 달라지는 경우
- 보종명 값이 중간에서 끊겨 여러 조각으로 분리된 경우
- 원본 명칭/보험종목 값에서 괄호 안 내용, 버전 정보 등 핵심 정보가 삭제되거나 과도하게 축약된 경우
  (예: "ABC보험(일반형, 환급금 지급형)" → "ABC보험")
- 명확한 중복 조합이 다수 존재하는 경우
- `/`와 `,` 사용 규칙을 어겨 값이 잘못 분리된 경우
- definitions 개수가 원본 구조에 비해 지나치게 많거나 적은 경우


다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오류만 기록
    // 예: "보종명 값이 '[3-100%장해형]재해장해특약(무배당' 과 '해약환급금 미지급형)' 으로 잘못 분리됨"
    // 예: "보종명+유형1+유형2 조합이 5건 중복됨"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "LLM 기반 Cartesian으로 재시도"
  ],
  "reasoning": "Cartesian Product 결과가 원본 테이블을 얼마나 잘 반영하는지에 대한 평가",
  "actual_count": {count}
}}
"""

    return base

# ================================ 🔥🔥🔥🔥🔥TOOL🔥🔥🔥🔥🔥================================

# ==================================================================================================
# _llm_extract_helper
# ==================================================================================================

def build_llm_extract_prompt(content_str: str, content_type: str, instruction: str = "") -> str:
    base = f"""
    다음은 보험 문서의 콘텐츠입니다 (형식: {content_type}).

    콘텐츠:
    {content_str}

    **추출 목표**: 보험 상품의 명칭과 유형 정보

    **형식별 처리**:
    - 테이블 형식: 행과 열을 파싱
    - 텍스트 형식: 번호/들여쓰기 구조를 파싱하여 구조화

    **요구사항**:
    1. 주석 행 제외 (※, 주:, 주), *, - 로 시작하는 설명)
    2. Header와 Data rows로 구분
    3. 텍스트 형식인 경우, 계층 구조를 평면화하여 표 형태로 변환
    4. 특수문자 정규화
    """
    extra = f"\n**최우선 지시사항(있는 경우 절대적으로 우선 적용)**: {instruction}\n" if instruction else ""
    tail = """
    다음 JSON 형식으로 반환:
    {{
      "header": ["컬럼1", "컬럼2", ...],
      "data": [
        ["값1", "값2", ...],
        ...
      ],
      "extraction_method": "table" or "text",
      "notes": "처리 내용"
    }
    """
    return extra + base + tail

# ==================================================================================================
# _llm_merge_helper
# ==================================================================================================

def build_llm_merge_prompt(content_str: str, instruction: str = "") -> str:
    base = f"""
    당신은 테이블과 텍스트 주석을 병합하는 전문가입니다.

    **입력**:
    {content_str}

    **임무**: `base_table`에 `annotations`의 내용을 분석하고 적용하여 최종 테이블을 만드세요.

    ## 기본 원칙
    Annotations는 base_table에 대한 **수정 지시사항**입니다. 각 annotation 문장의 **의도**를 파악하고, 테이블을 그에 맞게 변경하세요:

    1. **통합/동일 취급 지시**: 여러 값을 하나로 합치라는 의미 (예: "A와 B는 동일하게 취급")
    → **행동**: 둘 중 하나를 선택하거나, "A/B" 형태로 병합하여 행을 합칩니다.

    2. **제외/삭제 지시**: 특정 값을 제거하라는 의미 (예: "X를 제외")
    → **행동**: 해당 값이 포함된 행을 삭제합니다.

    3. **대체/변경 지시**: 값이나 명칭을 바꾸라는 의미 (예: "A를 B로 변경")
    → **행동**: 테이블에서 'A'를 찾아 'B'로 교체합니다.

    4. **조건부 적용**: 특정 조건에서만 값이 달라지는 경우 (예: "2024년 이후 X형 추가")
    → **행동**: 맥락 판단 후 적절히 반영 (행 추가/수정).

    5. **단순 설명**: 테이블 변경이 필요 없는 정보성 텍스트
    → **행동**: 테이블을 그대로 유지합니다.

    **중요 원칙**:
    1. ⚠️ **원본 컬럼 구조를 절대 변경하지 마세요**
        - 컬럼명이 비슷해도 절대 합치지 마세요
        - 모든 컬럼을 원본 그대로 유지하세요
        - 컬럼 개수와 이름을 정확히 보존하세요
    2. 주석 행 제외 (※, 주:, 주), *, - 로 시작하는 설명)
    3. Header와 Data rows로 구분
    4. 셀 내용은 정리하되, 줄바꿈(\n)은 공백으로 변환
    5. 데이터 손실 없이 모든 셀의 값을 추출"""

    extra = f"\n**최우선 지시사항(있는 경우 절대적으로 우선 적용)**: {instruction}\n" if instruction else ""
    
    tail = """
    **출력 형식 (JSON)**:
    {{
      "header": ["최종 컬럼1", "최종 컬럼2", ...],
      "data": [
        ["최종 값1", "최종 값2", ...],
        ...
      ],
      "notes": "병합 과정에 대한 설명"
    }
    """
    return extra + base + tail

# ==================================================================================================
# LLMCartesianTool
# ==================================================================================================

def build_llm_cartesian_prompt(header, data, instruction: str = "") -> str:
    header_json = json.dumps(header, ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False, indent=2)

    extra_instruction = ""
    if instruction:
        extra_instruction = (
            "**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:\n"
            f"{instruction}\n\n"
        )
    prompt = f"""
{extra_instruction}

다음 데이터의 각 셀 값을 문맥을 고려하여 독립된 옵션들로 분리하고, JSON 형식으로 반환하세요.

Header: {header_json}
Data:
{data_json}



**중요 규칙**:
1. **컬럼별 주 구분자(primary delimiter) 파악**:
   각 셀의 값을 분리하기 전에, **해당 셀이 속한 컬럼 전체**를 관찰하세요:

   - 컬럼에서 `/`와 `,` 중 **어느 것이 더 자주** 등장하는지 확인
   - **더 자주 등장하는 구분자**를 실제 구분자로 사용
   - **덜 등장하는 구분자**는 내용의 일부로 취급 (분리하지 않음)

   **예시**:
   - 컬럼 값: "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"
     → `,`가 여러 번, `/`는 한 번만 등장
     → 주 구분자: `,`
     → 분리 결과: ["두경부암(전이포함)", "위암(전이포함)", "남성/여성생식기암(전이포함)"]
     → "남성/여성생식기암"은 분리하지 않음 (/ is not primary delimiter)

   - 컬럼 값: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
     → `/`가 여러 번, `,` 없음
     → 주 구분자: `/`
     → 분리 결과: ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형"]

2. 줄바꿈(\n)과 공백은 strip하되, 보종명(첫 번째 컬럼)은 줄바꿈 유지

3. 각 행은 독립적으로 처리

**출력 형식 (중요!)**:
각 행을 셀 단위로 분리하고, 각 셀은 옵션 리스트로 표현.

{{
  "parsed_rows": [
    [
      ["보종명1"],
      ["유형값1"],
      ["옵션A", "옵션B", "옵션C"],
      ["암종류1", "암종류2", ...]
    ],
    [...]
  ]
}}

**예시 1**:
Input:
Header: ["명칭", "유형", "보험종목"]
Data: [["특약A", "일반형", "간편심사(315)형/간편심사(335)형"]]

Output:
{{
  "parsed_rows": [
    [
      ["특약A"],
      ["일반형"],
      ["간편심사(315)형", "간편심사(335)형"]
    ]
  ]
}}

**예시 2**:
Input:
Header: ["명칭", "유형", "보험종목", "보장계약"]
Data: [["특약B", "해약환급금미지급형", "간편심사(315)형/간편심사(335)형", "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"]]

Output:
{{
  "parsed_rows": [
    [
      ["특약B"],
      ["해약환급금미지급형"],
      ["간편심사(315)형", "간편심사(335)형"],
      ["두경부암(전이포함)", "위암(전이포함)", "남성/여성생식기암(전이포함)"]
    ]
  ]
}}

주의:
- 위 예시 2에서 "보장계약" 컬럼은 `,`가 주 구분자이므로 `/`는 내용의 일부입니다!
- 각 셀은 header 개수와 동일하게 맞춰야 함!
"""
    return prompt


# ==================================================================================================
# Sectionclassifier
# ==================================================================================================


def build_section_classifier_prompt(
    summaries: List[Dict[str, Any]],
    instruction: str = "",
) -> str:
    prompt = """당신은 보험 약관 문서의 섹션을 분류하는 전문가입니다.

**임무**: 주어진 모든 섹션을 4가지 카테고리로 분류하세요.

### 카테고리 정의 (의미 기준)

1. **definition_core** (핵심 정의 섹션)

   - 질문: 이 문서에서 정의하는 **상품/특약/보장계약이 무엇이며, 어떤 종류/조합으로 구성되어 있는가?**
   - 예:
     - 상품/특약의 명칭과 버전(해약환급금 미지급형 vs 일반형)
     - 1종/2종, 주계약/특약, 보장계약 타입 등
     - 각 버전이 어떤 축(유형1/유형2/심사형/보장계약 등)으로 나뉘는지
   - 특징:
     - "무엇으로 구성되어 있는지"를 설명하는 정적인 구조 정의
     - 표(table)인 경우가 많지만, 텍스트만으로 정의하는 경우도 있음
     - 기간, 가입나이, 납입기간, 납입주기 등 **숫자 기반 가입조건은 핵심이 아님**

2. **definition_annotation** (정의 주석/보충 섹션)

   - 질문: 위에서 정의한 구조에 대해 **어떤 예외/변경/추가 설명**이 있는가?
   - 예:
     - 명칭/표기법 설명: "상품명 앞에 '(간편)'을 붙인다"
     - 정의값에 대한 보충: "N은 1, 3, 5를 의미한다"
     - 정의에 대한 예외/주의: "단, 일부 채널에서는 OO라는 명칭을 사용"
     - 각주, "※", "참고", "주)", 로 시작하는 문장 등
   - 특징:
     - definition_core에서 정의한 값들을 수정/보완/해석하는 텍스트
     - 가입조건(보험기간, 가입나이, 납입기간 등)을 새로 정의하는 것은 아님

3. **condition** (계약/가입 조건 섹션)

   - 질문: 각 종류(유형/종/보장형)를 **어떤 조건으로 가입/유지할 수 있는가?**
   - 예:
     - 보험기간: 10/20/30년, 60/70/80세, 종신
     - 보험료 납입기간: 10/15/20/25/30년납, 전기납
     - 가입나이: "만15세 ~ min(세만기 - 년납, 70세)"
     - 보험료 납입주기: 월납/연납 등
   - 특징:
     - "언제까지, 얼마 동안, 몇 살부터 몇 살까지, 어떻게 내야 하는지" 같은
       기간/연령/납입 조건을 수치/범위로 표현
     - 표 제목이 "가입가능 조건", "보험기간/보험료 납입기간/가입나이/납입주기" 등인 경우가 많음
     - 정의(상품 구조)를 새로 소개하기보다는, 이미 정의된 유형에 대한 조건을 설명

4. **other** (기타 섹션)

   - 위 3가지에 해당하지 않는 모든 섹션
   - 예: 목차, 서문, 일반 설명, 부록, 클레임/면책조항 등

### 중요 규칙

- 제목이 비표준이어도(예: "상품 구성", 숫자만 있는 제목 등) 내용상
  상품/보장 구조를 정의하면 **definition_core**로 분류하세요.
- 기간/가입나이/납입기간/납입주기에 대한 수치/범위가 중심이면 **condition**으로 분류하세요.
- "※", "참고", "주)", "단," 등으로 시작하는 정의 관련 설명은
  구조 정의가 아니면 **definition_annotation**으로 분류하세요.
- 제목이 없더라도 내용(preview)을 보고 판단하세요.
- 표/텍스트 형식은 보조 정보일 뿐, 의미(정의 vs 조건)를 우선적으로 고려하세요.
- 모든 섹션은 정확히 한 카테고리에만 속해야 합니다.

## 예시로 배우기 (Few-shot Learning)

**입력 예시 1**:
```
[Section 5]
Title: 3. 보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기
Has Table: true
Has Text: true
Preview: [Table: 유형1, 유형2, 보험기간 | 간편심사형, -, 80/90/100세]
---
```
**판단 과정**:
1.  **제목**: "보험기간", "납입기간", "가입나이" 등 명백한 '조건' 키워드가 포함됨.
2.  **내용**: Preview를 보니 테이블에 '보험기간' 같은 조건 컬럼이 있음. '유형' 컬럼이 있긴 하지만, 이 섹션의 핵심 목적은 상품 구조 정의가 아니라 가입 '조건'을 나열하는 것임.
3.  **결론**: `condition`으로 분류하는 것이 가장 적절함.

**입력 예시 2**:
```
[Section 1]
Title: 1. 보험종목의 명칭
Has Table: true
Has Text: false
Preview: [Table: 명칭, 보험종목, 보험종목_1 | [3-100%장해형]재해장해특약, 해약환급금 미지급형, 간편심사(315)형]
---
```
**판단 과정**:
1.  **제목**: "보험종목의 명칭"은 상품의 구조를 정의하는 핵심 키워드임.
2.  **내용**: 테이블에 '명칭', '보험종목' 등 정의 관련 컬럼이 명확하게 있음.
3.  **결론**: `definition_core`로 분류하는 것이 가장 적절함.


"""

    if instruction:
        prompt += f"""
**추가 지시사항** (중요 - 반드시 따를 것):
{instruction}
"""

    prompt += """
**입력 섹션**:
"""

    for s in summaries:
        prompt += f"\n[Section {s['index']}]\n"
        prompt += f"Title: {s.get('title') or '(no title)'}\n"
        prompt += f"Has Table: {s.get('has_table')}\n"
        prompt += f"Has Text: {s.get('has_text')}\n"
        preview = (s.get('preview') or "")[:200]
        prompt += f"Preview: {preview}\n"
        prompt += "---\n"

    prompt += """
**출력 형식** (JSON):

{{
  "definition_core": [섹션 인덱스들],
  "definition_annotation": [섹션 인덱스들],
  "condition": [섹션 인덱스들],
  "other": [섹션 인덱스들],
  "reasoning": "분류 근거에 대한 간단한 설명"
}

**예시**:
{{
  "definition_core": [0, 2],
  "definition_annotation": [1, 3],
  "condition": [4],
  "other": [5, 6],
  "reasoning": "Section 0과 2는 보험종목/명칭 테이블, Section 1과 3은 정의에 대한 주석, Section 4는 가입조건, 나머지는 목차/서문"
}

이제 위 섹션들을 분류해주세요:
"""
    return prompt

def build_llm_intelligent_merge_prompt(
    definitions: List[Dict[str, Any]],
    condition_header: List[str],
    condition_data: List[List[str]],
    instruction: str = ""
) -> str:
    definitions_json = json.dumps(definitions, ensure_ascii=False, indent=2)
    condition_header_json = json.dumps(condition_header, ensure_ascii=False)
    condition_data_json = json.dumps(condition_data, ensure_ascii=False, indent=2)

    extra_instruction = ""
    if instruction:
        extra_instruction = (
            "**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:\n"
            f"{instruction}\n\n"
        )

    prompt = f"""
{extra_instruction}

당신은 두 개의 다른 데이터셋을 지능적으로 병합하는 데이터 전문가입니다.

**입력 데이터**:

1. `definitions`: 모든 상품/유형 조합이 생성된 리스트입니다.
{definitions_json}

2. `conditions`: 각 상품/유형에 대한 가입 조건 테이블 원본입니다.
   - Header: {condition_header_json}
   - Data:
{condition_data_json}

---

**병합 목표**:
`definitions` 리스트의 각 항목에 가장 적합한 `conditions` 테이블의 **단일 행**을 찾아 `LEFT JOIN` 하세요.

---

**★★★★★ 중요 병합 규칙 ★★★★★**

1.  **Join Key는 유동적입니다**:
    - `definitions`의 `보종명`, `유형1`, `유형2`... 와 `conditions`의 `유형1`, `유형2`... 사이의 관계는 고정되어 있지 않습니다.
    - 예시: `definitions`의 `보종명`이 `conditions`의 `유형1`과 대응될 수도 있고, `definitions`의 `유형1`이 `conditions`의 `유형1`과 대응될 수도 있습니다.
    - 문맥을 파악하여 **가장 논리적인 Join Key 조합**을 스스로 판단해야 합니다.

2.  **의미 기반 매칭 (Fuzzy Matching)**:
    - 이름이 문자 그대로 똑같지 않아도 의미적으로 같다면 매칭해야 합니다.
    - 예: `definitions`의 `유형1` 값이 "간편심사(315)형"이고 `conditions`의 `유형1` 값이 "간편심사형"이라면, 이 둘은 **같은 그룹으로 취급하여 매칭**해야 합니다.

3.  **와일드카드 매칭**:
    - `conditions` 테이블의 `유형` 관련 컬럼 값이 `"-"` 나 `""` (빈 문자열)일 경우, 이는 **모든 `definitions` 항목에 적용될 수 있는 기본(default) 조건**을 의미합니다.
    - 정확히 일치하는 조건이 없을 때 이 와일드카드 조건을 적용해야 합니다.

4.  **매칭 우선순위**:
    1.  **가장 구체적인 매칭**을 최우선으로 합니다 (e.g., "유형1", "유형2" 모두 일치).
    2.  구체적인 매칭이 없으면, **의미 기반 매칭**을 시도합니다.
    3.  그래도 없으면, **와일드카드 매칭**을 적용합니다.
    4.  모든 매칭에 실패하면, `conditions`에서 온 컬럼들은 `null`로 채워져야 합니다.

---

**출력 형식 (JSON)**:

- 최종 병합된 `definitions` 리스트와 `join_stats`를 포함한 JSON 객체로 반환하세요.
- `join_stats`에는 매칭되지 않은 `definitions`와 `conditions`의 **인덱스**를 기록해야 합니다.

```json
{{
  "definitions": [
    {{
      "보종명": "...",
      "유형1": "...",
      "유형2": "...",
      "보험기간": "...",
      "납입기간": "...",
      "가입나이_남": "...",
      "가입나이_여": "...",
      "납입주기": "..."
    }}
  ],
  "join_stats": {{
    "definition_count": 4,
    "condition_count": 3,
    "merged_count": 4,
    "unmatched_definition_indices": [정의 인덱스],
    "unmatched_condition_indices": [조건 인덱스]
  }},
  "reasoning": "어떤 Join Key를 사용했고, 매칭을 어떻게 수행했는지에 대한 설명"
}}
```

**예시**:

**Input `definitions`**:
```json
[
  {{ "보종명": "A상품", "유형1": "간편심사(315)형" }},
  {{ "보종명": "A상품", "유형1": "간편심사(335)형" }},
  {{ "보종명": "B상품", "유형1": "일반형" }}
]
```

**Input `conditions`**:
Header: `["유형1", "보험기간"]`
Data:
```json
[
  ["간편심사형", "10년"],
  ["-", "20년"]
]
```

**Correct Output**:
```json
{{
  "definitions": [
    {{
      "보종명": "A상품",
      "유형1": "간편심사(315)형",
      "보험기간": "10년"
    }},
    {{
      "보종명": "A상품",
      "유형1": "간편심사(335)형",
      "보험기간": "10년"
    }},
    {{
      "보종명": "B상품",
      "유형1": "일반형",
      "보험기간": "20년"
    }}
  ],
  "join_stats": {{
    "definition_count": 3,
    "condition_count": 2,
    "merged_count": 3,
    "unmatched_definition_indices": [],
    "unmatched_condition_indices": []
  }},
  "reasoning": "definitions의 '유형1'과 conditions의 '유형1'을 join key로 사용했습니다. '간편심사(315)형'과 '간편심사(335)형'은 '간편심사형'과 의미적으로 매칭했습니다. '일반형'은 매칭되는 조건이 없어 와일드카드('-') 조건을 적용했습니다."
}}
```

이제 위 규칙에 따라 병합을 수행하고 결과를 JSON으로 반환하세요.
"""
    return prompt

def build_intelligent_condition_extract_prompt(
    condition_sections: List[Dict[str, Any]],
    instruction: str = ""
) -> str:
    sections_json = json.dumps(condition_sections, ensure_ascii=False, indent=2)

    extra_instruction = ""
    if instruction:
        extra_instruction = (
            "**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:\n"
            f"{instruction}\n\n"
        )

    prompt = f"""
{extra_instruction}

당신은 보험 문서에서 가입 조건 정보를 추출하고 재구성하는 전문가입니다.

**입력 데이터**:
- `condition`으로 분류된 섹션들의 전체 내용입니다.
- 각 섹션은 `title`과 `table` 같은 다양한 `type`의 content item을 포함합니다.
{sections_json}

---

**임무**:
주어진 `condition` 섹션들에서 최종적으로 사용할 **'가입 가능 조건'** 테이블을 추출하고, 문맥 정보를 활용하여 데이터를 보강하세요.

---

**★★★★★ 중요 처리 규칙 ★★★★★**

1.  **'가입 가능 조건' 테이블 식별**:
    - 섹션 내용 전체를 보고 '가입 가능 조건'에 해당하는 핵심 테이블을 찾아야 합니다.
    - 테이블의 제목(`table_title`)이나 바로 앞 `title` content에 "가입 가능" 또는 유사한 문구가 있는지 확인하세요.
    - 만약 "가입 불가 조건" 테이블이 있다면, 그 데이터는 **절대 포함해서는 안 됩니다.**

2.  **계층적 유형 정보(Contextual Types) 추가**:
    - '가입 가능 조건' 테이블 바로 앞에 있는 `title` 타입의 content들을 분석하세요.
    - `가. 주계약`, `나. 특약`, `① 해약환급금 미지급형`과 같은 제목들은 **상위 계층의 유형 정보**입니다.
    - 이 제목들의 값을 추출하여, '가입 가능 조건' 테이블의 **모든 행 앞부분에 새로운 컬럼으로 추가**해야 합니다.
    - 예: `나. 특약` → `유형0: 특약`, `① 해약환급금 미지급형` → `유형1: 해약환급금 미지급형` 과 같이 새로운 `유형` 컬럼을 생성합니다. 테이블에 이미 `유형1`이 있다면, `유형2`, `유형3` 등으로 순서를 조정하세요.

3.  **컬럼명 정규화**:
    - 추출된 테이블의 헤더(컬럼명)를 다음 규칙에 따라 표준화하세요.
      - "보험료 납입기간" 또는 "납입기간" → "납입기간"
      - "보험기간" → "보험기간"
      - "가입나이" 또는 "남자나이", "여자나이" → "가입나이_남", "가입나이_여" (필요시 분리)
      - "보험료 납입주기" 또는 "납입주기" → "납입주기"
    - `유형1`, `유형2` 등 이미 존재하는 유형 컬럼은 그대로 유지합니다.

4.  **데이터 정리**:
    - 테이블 데이터에서 불필요한 줄바꿈(`\n`)이나 공백을 제거하여 값을 정제합니다.

---

**출력 형식 (JSON)**:

- 최종적으로 재구성된 `header`와 `data`를 JSON 형식으로 반환하세요.
- `header`에는 계층 정보로 인해 새로 추가된 유형 컬럼들이 포함되어야 합니다.

```json
{{
  "header": ["새로운 유형 컬럼1", "새로운 유형 컬럼2", "기존 유형1", "보험기간", ...],
  "data": [
    ["특약", "해약환급금 미지급형", "-", "10, 20년만기", ...],
    ["특약", "해약환급금 미지급형", "-", "60, 70세만기", ...]
  ],
  "reasoning": "어떤 테이블을 '가입 가능 조건'으로 선택했고, 어떤 title에서 계층 정보를 추출하여 새로운 컬럼으로 추가했는지 설명합니다."
}}
```

**예시**:

**Input `condition_sections`**:
```json
[
  {{
    "index": 5,
    "title": "3. 보험기간, 보험료 납입기간...",
    "content": [
      {{ "type": "title", "content": "나. 특약" }},
      {{ "type": "title", "content": "① 해약환급금 미지급형" }},
      {{
        "type": "table",
        "table": {{
          "table_title": "가입가능 조건",
          "table_elements": [
            {{ "유형1": "해약환급금 미지급형", "보험기간": "10, 20년만기", ... }},
            {{ "유형1": "해약환급금 미지급형", "보험기간": "60, 70세만기", ... }}
          ]
        }}
      }}
    ]
  }}
]
```

**Correct Output**:
```json
{{
  "header": ["유형0", "유형1", "유형2", "보험기간", ...],
  "data": [
    ["특약", "해약환급금 미지급형", "-", "10, 20년만기", ...],
    ["특약", "해약환급금 미지급형", "-", "60, 70세만기", ...]
  ],
  "reasoning": "'가입가능 조건' 테이블을 선택했습니다. 테이블 앞의 title '나. 특약'과 '① 해약환급금 미지급형'에서 계층 정보를 추출하여 각각 '유형0'과 '유형1' 컬럼으로 추가했습니다. 테이블 내 기존 '유형1'은 '유형2'로 조정했습니다."
}}
```

이제 위 규칙에 따라 조건 테이블을 추출하고 재구성하여 결과를 JSON으로 반환하세요.
"""
    return prompt


# ================================ 🔥🔥🔥🔥🔥 GROUPING LOGIC EXTRACTOR 🔥🔥🔥🔥🔥 ================================

def format_table_for_prompt(header: List[str], data: List[List[str]], max_rows: int = 20) -> str:
    """
    테이블을 보기 좋은 형식으로 포맷팅 (프롬프트용)

    Args:
        header: 헤더 리스트
        data: 데이터 리스트
        max_rows: 표시할 최대 행 수 (너무 길면 샘플만)

    Returns:
        포맷팅된 테이블 문자열
    """
    if not header or not data:
        return "(empty table)"

    # 샘플링
    sample_data = data[:max_rows]
    is_truncated = len(data) > max_rows

    # 헤더
    result = "Index | " + " | ".join(header) + "\n"
    result += "------|" + "|".join(["---" for _ in header]) + "\n"

    # 데이터
    for i, row in enumerate(sample_data):
        row_str = " | ".join(str(cell) for cell in row)
        result += f"{i:5d} | {row_str}\n"

    if is_truncated:
        result += f"\n... ({len(data) - max_rows} more rows, total {len(data)} rows)\n"

    return result


def build_grouping_extraction_prompt(
    definition_header: List[str],
    definition_data: List[List[str]],
    condition_header: List[str],
    condition_data: List[List[str]],
    instruction: str = ""
) -> str:
    """
    LLM이 Definition-Condition 매칭 그룹을 추출하기 위한 프롬프트 생성

    Args:
        definition_header: Definition 테이블 헤더
        definition_data: Definition 테이블 데이터
        condition_header: Condition 테이블 헤더
        condition_data: Condition 테이블 데이터
        instruction: 추가 지시사항 (optional)

    Returns:
        그룹핑 추출을 위한 LLM 프롬프트
    """
    # 테이블 포맷팅 (너무 길면 샘플만)
    def_table = format_table_for_prompt(definition_header, definition_data, max_rows=50)
    cond_table = format_table_for_prompt(condition_header, condition_data, max_rows=20)

    extra_instruction = ""
    if instruction:
        extra_instruction = f"""
**⚠️ 최우선 지시사항 (반드시 적용)**:
{instruction}

---

"""

    prompt = f"""
{extra_instruction}당신은 보험 상품 정의(Definitions)와 가입 조건(Conditions)을 매칭하는 전문가입니다.

## 입력 데이터

**Definitions 테이블** (상품/유형 정의):
```
{def_table}
```

**Conditions 테이블** (가입 조건):
```
{cond_table}
```

---

## 작업 목표

Definition 테이블의 각 행이 Condition 테이블의 어떤 행과 매칭되는지 분석하여 **그룹**으로 묶으세요.

- **같은 조건을 공유하는 Definition 행들 → 같은 그룹**
- 각 그룹은 하나의 Condition 행과 연결됨
- 최종적으로 Python이 이 그룹 정보를 바탕으로 조합을 생성함

---

## 매칭 규칙

### 1. JOIN 키 파악
Definition과 Condition 테이블 사이의 **공통 컬럼**을 찾아 JOIN 키로 사용하세요.

**일반적인 JOIN 키 후보**:
- `유형1`, `유형2`, `유형3`, ...
- `심사형`, `보장형`
- `보험기간`, `납입기간` (경우에 따라)

**주의**:
- Definition의 `보종명`은 보통 JOIN 키가 **아닙니다** (고정값이므로)
- 컬럼명이 다르더라도 의미적으로 같으면 매칭 가능

### 2. Fuzzy Matching (의미 기반 매칭)
문자열이 정확히 일치하지 않아도 **의미적으로 같으면 매칭**하세요.

**예시**:
- `"간편심사(315)형"` ≈ `"간편심사형"` → 매칭 O
- `"일반심사형"` ≈ `"일반형"` → 매칭 O
- `"유형1"` (Definition) ≈ `"심사형"` (Condition) → 같은 개념이면 매칭 O

### 3. Wildcard 처리
`"-"` 값은 **모든 값과 매칭**됩니다.

**예시**:
- Definition: `유형2 = "-"`
- Condition: `유형2 = "특정값"` 또는 `유형2 = "-"`
- → 둘 다 매칭 O

### 4. 우선순위
매칭 시 다음 우선순위를 따르세요:
1. **Exact Match** (정확히 일치) - 최우선
2. **Fuzzy Match** (의미 일치) - 차선
3. **Wildcard** (`"-"`) - 최후

---

## 출력 형식

다음 JSON 형식으로 그룹핑 로직을 반환하세요:

```json
{{
  "column_mapping": {{
    "join_keys": ["유형1", "유형2"],
    "value_columns": ["보험기간", "납입기간", "가입나이_남", "가입나이_여", "납입주기"]
  }},
  "groups": [
    {{
      "id": 0,
      "match_condition": {{"유형1": "일반형", "유형2": "-"}},
      "definition_indices": [0, 3, 7, 11],
      "condition_index": 0,
      "fuzzy_matches": {{
        "유형1": {{
          "definition_value": "일반형",
          "condition_value": "일반형",
          "match_type": "exact"
        }},
        "유형2": {{
          "definition_value": "-",
          "condition_value": "-",
          "match_type": "wildcard"
        }}
      }},
      "reasoning": "Definition 행 0, 3, 7, 11은 모두 유형1='일반형', 유형2='-' 조건을 만족하므로 Condition 행 0과 매칭됩니다."
    }},
    {{
      "id": 1,
      "match_condition": {{"유형1": "간편심사형"}},
      "definition_indices": [1, 2, 4, 8],
      "condition_index": 1,
      "fuzzy_matches": {{
        "유형1": {{
          "definition_value": "간편심사(315)형",
          "condition_value": "간편심사형",
          "match_type": "fuzzy"
        }}
      }},
      "reasoning": "Definition 행들의 '간편심사(315)형'은 Condition의 '간편심사형'과 의미적으로 같으므로 Condition 행 1과 매칭됩니다."
    }}
  ],
  "unmatched": {{
    "definition_indices": [15, 20],
    "condition_indices": [5]
  }},
  "summary": {{
    "total_definitions": {len(definition_data)},
    "total_conditions": {len(condition_data)},
    "total_groups": 2,
    "matched_definition_count": {len(definition_data) - 2},
    "unmatched_definition_count": 2,
    "coverage_ratio": 0.95
  }}
}}
```

**필드 설명**:
- `column_mapping`:
  - `join_keys`: Definition과 Condition을 매칭하는 데 사용된 컬럼들
  - `value_columns`: Condition에서 가져올 값 컬럼들 (보험기간, 납입기간 등)

- `groups`: 각 그룹의 매칭 정보
  - `id`: 그룹 고유 번호
  - `match_condition`: 이 그룹의 매칭 조건 (JOIN 키 값들)
  - `definition_indices`: 이 그룹에 속한 Definition 행 번호들 (0-based)
  - `condition_index`: 매칭되는 Condition 행 번호 (0-based)
  - `fuzzy_matches`: 각 JOIN 키의 매칭 상세 정보
  - `reasoning`: 왜 이렇게 그룹핑했는지 설명

- `unmatched`:
  - `definition_indices`: 어떤 Condition과도 매칭되지 않은 Definition 행들
  - `condition_indices`: 어떤 Definition과도 매칭되지 않은 Condition 행들

- `summary`: 전체 통계 요약

---

## 예시

**Input Definitions**:
```
Index | 보종명    | 유형1        | 유형2
------|-----------|--------------|-------
    0 | 암보험    | 일반형       | -
    1 | 암보험    | 간편심사형   | -
    2 | 암보험    | 일반형       | 특정A
```

**Input Conditions**:
```
Index | 유형1    | 유형2 | 보험기간 | 납입기간
------|----------|-------|----------|----------
    0 | 일반형   | -     | 10년     | 10년
    1 | 간편심사형 | -   | 종신     | 전기납
    2 | 일반형   | 특정A | 20년     | 20년
```

**Correct Output**:
```json
{{
  "column_mapping": {{
    "join_keys": ["유형1", "유형2"],
    "value_columns": ["보험기간", "납입기간"]
  }},
  "groups": [
    {{
      "id": 0,
      "match_condition": {{"유형1": "일반형", "유형2": "-"}},
      "definition_indices": [0],
      "condition_index": 0,
      "fuzzy_matches": {{
        "유형1": {{"definition_value": "일반형", "condition_value": "일반형", "match_type": "exact"}},
        "유형2": {{"definition_value": "-", "condition_value": "-", "match_type": "exact"}}
      }},
      "reasoning": "Definition 행 0은 유형1='일반형', 유형2='-'이므로 Condition 행 0과 정확히 매칭됩니다."
    }},
    {{
      "id": 1,
      "match_condition": {{"유형1": "간편심사형", "유형2": "-"}},
      "definition_indices": [1],
      "condition_index": 1,
      "fuzzy_matches": {{
        "유형1": {{"definition_value": "간편심사형", "condition_value": "간편심사형", "match_type": "exact"}},
        "유형2": {{"definition_value": "-", "condition_value": "-", "match_type": "exact"}}
      }},
      "reasoning": "Definition 행 1은 유형1='간편심사형'이므로 Condition 행 1과 매칭됩니다."
    }},
    {{
      "id": 2,
      "match_condition": {{"유형1": "일반형", "유형2": "특정A"}},
      "definition_indices": [2],
      "condition_index": 2,
      "fuzzy_matches": {{
        "유형1": {{"definition_value": "일반형", "condition_value": "일반형", "match_type": "exact"}},
        "유형2": {{"definition_value": "특정A", "condition_value": "특정A", "match_type": "exact"}}
      }},
      "reasoning": "Definition 행 2는 유형1='일반형', 유형2='특정A'이므로 Condition 행 2와 매칭됩니다."
    }}
  ],
  "unmatched": {{
    "definition_indices": [],
    "condition_indices": []
  }},
  "summary": {{
    "total_definitions": 3,
    "total_conditions": 3,
    "total_groups": 3,
    "matched_definition_count": 3,
    "unmatched_definition_count": 0,
    "coverage_ratio": 1.0
  }}
}}
```

---

## 주의사항

1. **인덱스는 0-based**: 첫 번째 행은 인덱스 0
2. **중복 방지**: 한 Definition 행은 오직 하나의 그룹에만 속함
3. **완전성**: 가능한 한 모든 Definition 행을 매칭하려고 노력 (coverage_ratio 높이기)
4. **일관성**: 같은 조건을 가진 Definition 행들은 반드시 같은 그룹으로
5. **정확성**: `definition_indices`, `condition_index`의 범위를 반드시 검증

---

이제 위 규칙에 따라 Definition과 Condition 테이블을 분석하여 그룹핑 로직을 JSON으로 반환하세요.
"""
    return prompt


# ================================ 🔥🔥🔥🔥🔥 PROTOTYPE 7: Dynamic Planning 🔥🔥🔥🔥🔥 ================================



def build_dynamic_planning_prompt_v7(
    doc_summary: dict,
    doc_sample: str,
    goal: str,
    tool_schemas: str,
    instruction: str = ""
) -> str:
    """Build prompt for dynamic task planning (3-7 tasks)."""

    doc_summary_json = json.dumps(doc_summary, ensure_ascii=False, indent=2)
    extra_instruction = ""
    if instruction:
        extra_instruction = (
            f"""\n**추가 지시사항(반드시 반영)**:\n{instruction}\n\n---\n\n"""
        )

    prompt = f"""
{extra_instruction}당신은 보험 상품 문서를 분석하여 최적의 실행 계획을 세우는 전문가입니다.

## 입력 문서 요약
{doc_summary_json}

## 입력 문서 샘플
{doc_sample[:2000]}... (총 {len(doc_sample)}자)

## 목표
{goal}
문서 복잡도에 따라 **3~7개의 작업**으로 구성된 실행 계획을 작성하세요.

## 사용 가능 도구/스키마
{tool_schemas}

## 작업 타입(사용 도구)
- classify_sections → section_classifier (output: classification_result)
- extract_definitions → definition_extract_v2 (output: extraction_result)
- normalize_definitions → rule_cartesian mapping (output: normalized_definitions)
- extract_conditions → condition_extract (output: condition_result)
- normalize_conditions → column check (output: normalized_conditions)
- extract_grouping_logic → grouping_logic_extractor (output: grouping_logic)
- generate_combinations → combination_generator (output: final_result)

## 계획 수립 가이드라인
- 단순: extract_definitions → normalize_definitions → 결과 확정
- 일반: extract_definitions → normalize_definitions → extract_conditions → normalize_conditions → extract_grouping_logic → generate_combinations
- 복잡: classify_sections 추가 후 동일 흐름

## 출력 형식 (JSON)
{{
  "total_tasks": 5,
  "tasks": [
    {{
      "task_id": "task0",
      "task_type": "extract_definitions",
      "tool_name": "definition_extract_v2",
      "fallback_tool": null,
      "parameters": {{"document": "{{{{document}}}}"}},
      "dependencies": [],
      "output_key": "extraction_result"
    }}
  ],
  "reasoning": "문서 구조와 도구 선택 근거 요약"
}}

## 중요 규칙
1) dependencies는 이전 task_id만 참조
2) 이전 결과 참조 시 "{{{{taskN.output_key.field}}}}" 문법 사용
3) 필요 시 fallback_tool 지정
4) 불필요한 작업 생략, output_key를 명확히 기입

위 규칙에 따라 JSON만 반환하세요.
"""
    return prompt
def get_task_validation_criteria(task_type: str) -> str:
    """
    PROTOTYPE 7: Get validation criteria for specific task type.

    Args:
        task_type: Type of task (e.g., "extract_definitions", "normalize_definitions")

    Returns:
        Validation criteria string for the task type
    """
    criteria = {
        "extract_definitions": """
**기대 출력**:
- header: 컬럼명 리스트 (비어있지 않음)
- data: 2D 리스트 (최소 1개 행)
- 각 행의 길이가 header 길이와 동일

**검증 항목**:
1. Header와 Data가 비어있지 않음
2. 원본 정의 섹션의 주요 내용이 누락되지 않음
3. 주석 행("※", "주:", "*")이 데이터로 잘못 포함되지 않음
""",
        "normalize_definitions": """
**기대 출력**:
- header: 정규화된 컬럼명 ("보종명", "유형1", "유형2", ...)
- data: 정규화된 데이터
- 누락된 행 없음

**검증 항목**:
1. 필수 컬럼 존재 ("보종명" 또는 이에 준하는 컬럼)
2. 데이터 행 수가 입력과 동일
3. 컬럼명이 표준 형식을 따름
""",
        "extract_conditions": """
**기대 출력**:
- header: 조건 컬럼명 리스트
- data: 조건 데이터 (최소 1개 행)

**검증 항목**:
1. Header와 Data가 비어있지 않음
2. 조건 관련 컬럼 포함 (보험기간, 납입기간 등)
3. 유형 컬럼과 조건 컬럼이 모두 존재
""",
        "normalize_conditions": """
**기대 출력**:
- header: 정규화된 조건 컬럼명
- data: 정규화된 조건 데이터

**검증 항목**:
1. 표준 컬럼명 사용 ("납입기간", "보험기간", "가입나이_남", "가입나이_여")
2. 데이터 누락 없음
3. 각 행의 길이가 header 길이와 동일
""",
        "extract_grouping_logic": """
**기대 출력**:
- groups: 그룹 리스트 (최소 1개)
- column_mapping: join_keys, value_columns 명시
- 각 그룹에 definition_indices, condition_index 존재

**검증 항목**:
1. 필수 키 존재 (groups, column_mapping)
2. 인덱스 범위 검증 (definition_indices, condition_index)
3. 커버리지 검증 (50% 이상의 definitions 매칭)
4. JOIN 키 명시됨
""",
        "generate_combinations": """
**기대 출력**:
- definitions: 최종 조합 리스트
- total_count: 총 개수
- generation_stats: 통계 정보

**검증 항목**:
1. Definitions 리스트가 비어있지 않음
2. 필수 컬럼 존재 ("보종명")
3. Match rate 50% 이상
4. 통계 정보 일관성
""",
        "classify_sections": """
**기대 출력**:
- definition_core: 정의 핵심 섹션 인덱스
- definition_annotation: 정의 주석 섹션 인덱스
- condition: 조건 섹션 인덱스
- other: 기타 섹션 인덱스

**검증 항목**:
1. 모든 카테고리 키 존재
2. definition_core에 최소 1개 섹션
3. 인덱스 중복 없음
4. 분류 합리성
"""
    }
    return criteria.get(task_type, "일반적인 데이터 품질 검증 수행")