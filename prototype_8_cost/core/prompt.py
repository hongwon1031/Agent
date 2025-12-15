import json
from typing import List, Dict, Any

# ================================ 🔥🔥🔥🔥🔥PLANNER🔥🔥🔥🔥🔥================================

# ==================================================================================================
# create_plan
# ==================================================================================================

# ==================================================================================================
# replan
# ==================================================================================================

def build_replan_prompt(
    failed_task: Dict[str, Any],
    error_message: str,
    validation_result: Dict[str, Any] | None,
    previous_attempts: List[Dict[str, Any]],
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
   - `validation_result.suggestions`를 최우선적으로 반영하여 도구 전환, 파라미터 조정 또는 instruction 추가를 결정하세요.
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
   - `validation_result.suggestions`에 'LLM 기반 Cartesian으로 재시도'가 있다면, `rule_cartesian`에서 `llm_cartesian`으로 도구를 전환하세요.
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
    "header": "{{{{task2.data.header}}}}",
    "data": "{{{{task2.data.data}}}}",
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
    "core_indices": "{{{{task1.data.definition_core}}}}",
    "annotation_indices": "{{{{task1.data.definition_annotation}}}}",
    "instruction": "주석 행(※, 주:)을 데이터로 포함하지 말 것. 원본 테이블의 모든 데이터 행을 누락 없이 추출할 것."
  }},
  "reasoning": "Validator가 지적한 주석 포함 및 데이터 누락 문제 해결",
  "changes": "instruction parameter 추가로 추출 기준 조정"
}} """
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
     - 기간/연령/납입 조건을 수치/범위로 표현
     - 표 제목이 "가입가능 조건", "보험기간/보험료 납입기간/가입나이/납입주기" 등인 경우가 많음
     - 정의(상품 구조)를 새로 소개하기보다는, 이미 정의된 유형에 대한 조건을 설명

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
- definition_annotation은 비어있을 수 있음

**명백한 오류 (is_valid=false가 될 수 있음)**:
- definition_core에 정의 관련 내용이 전혀 없고 조건만 있음
- condition에 정의 테이블만 있고 조건이 없음
- **3개 이상**의 섹션이 명백하게 잘못 분류됨

**무시해야 할 것들**:
- "정의한다" vs "설명한다" 같은 표현 차이 → 실질적으로 같음
- core vs annotation의 경계 애매함 → 둘 다 합리적이면 OK
- 제목과 내용의 미묘한 불일치 → 내용 우선

### suggestions 작성 규칙 (매우 중요)

suggestions는 planner가 그대로 재계획/백트래킹 instruction으로 사용합니다.
따라서 아래 규칙을 반드시 따르세요.

1) suggestions는 "해야 할 행동" 형태로 구체적으로 작성하세요. (추상적 조언 금지)
   - 나쁜 예: "분류가 이상합니다. 다시 확인하세요."
   - 좋은 예: "섹션 [2,5]는 보험기간/납입기간/가입나이 키워드가 강하므로 other → condition으로 재분류하세요."

2) 가능하면 반드시 section index 목록을 포함하세요.
   - 형식 예: section_indices=[2,5]

3) suggestion 문장 안에 최소 1개의 근거 키워드를 포함하세요.
   - 예: 보험기간, 납입기간, 가입나이, 납입주기, 만xx세, min[, 명칭, 특약, 보험종목, 유형, 보장계약, 각주, 참고, ※

4) 아래 표준 포맷 중 하나로 작성하세요 (자유형 금지):
   - "REPLAN_HINT: move section_indices=[...] from other->condition (evidence: ...)"
   - "REPLAN_HINT: move section_indices=[...] from other->definition_core (evidence: ...)"
   - "REPLAN_HINT: move section_indices=[...] from definition_core->condition (evidence: ...)"
   - "REPLAN_HINT: move section_indices=[...] from condition->other (evidence: ...)"
   - "REPLAN_HINT: move section_indices=[...] from definition_core->definition_annotation (evidence: 각주/※/참고/주))"


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

**참고**: 당신의 역할은 재분류가 아니라 합리성 확인입니다. 애매한 경우는 is_valid=true를 반환하세요.
"""

    return base

# ==================================================================================================
# validate_definition_extract_v2_llm
# ==================================================================================================

def build_validate_definition_extract_v2_llm(
    core_sections_preview : List[Dict[str, Any]],
    annotation_sections_preview : List[Dict[str, Any]],
    header: List[str],
    data: List[List[str]],
) -> str:
    base = f"""당신은 데이터 추출 품질을 검토하는 전문가입니다.

**임무**:
- DefinitionExtractV2 도구가 원본 섹션에서 테이블을 **올바르게 추출**했는지 확인하세요.
- 정의 관련 섹션들(테이블 + 텍스트)를 보고, DefinitinoExtractV2가 추출한 테이블이 이 섹션들의 정의 + 주석/예외를 대체로 잘 반영했는지 확인하세요

**원본 정의 관련 섹션들 (샘플)**:
주요 정의 섹션
{json.dumps(core_sections_preview, ensure_ascii=False, indent=2)}
정의 보조 섹션(추가 설명/주석 등)
{json.dumps(annotation_sections_preview, ensure_ascii=False, indent=2)}

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
4. 여러 테이블 병합 시 명백한 헤더 불일치로 데이터 깨짐
5. 정의 테이블과 주석/예외 병합 과정에서 정의 데이터가 손실되거나 완전히 잘못됨
6. 원본 테이블의 컬럼이 누락됨 (예: 원본 4개 컬럼 → 추출 결과 3개 컬럼)

**무시해야 할 것들** (다음 단계의 역할):
- ❌ 컬럼명 정규화 ("명칭" → "보종명" 등)
- ❌ 계층 구조 확장/재구성
- ❌ 데이터 변환/재배치

### 검토 규칙

**중요한 마음가짐**:
- ExtractV2는 **변환기가 아니라 추출기**입니다
- 원본에 있는 내용을 **있는 그대로** 잘 가져왔는지 확인하세요
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
    instruction: str = "" # instruction 추가
) -> str:
    header_json = json.dumps(header, ensure_ascii=False)
    data_json = json.dumps(data, ensure_ascii=False, indent=2)
    defs_json = json.dumps(definitions, ensure_ascii=False, indent=2)

    count = len(definitions)

    extra_instruction = ""
    if instruction:
        extra_instruction = (f"""
**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:
{instruction}

---

"""
        )

    base = f"""
{extra_instruction}다음은 Cartesian Product 생성 결과입니다.

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

1. **보종명 무결성 검사 (매우 중요)**
   - 최종 definitions의 `보종명` 값이 원본 데이터에 비해 중간에 잘리거나, 쉼표(,) 등으로 인해 여러 행으로 쪼개졌는지 반드시 확인해야 합니다.
   - **오류 예시**: 원본의 `(무배당, 해약환급금 미지급형)`이 `(무배당` 과 `해약환급금 미지급형)` 으로 나뉘어 각각 다른 `보종명`이 된 경우. 이는 명백한 오류입니다.
   - `보종명`은 `[3-100%장해형]재해장해특약 (무배당, 해약환급금 미지급형)` 처럼 완전한 형태를 유지해야 합니다.

2. **구분자 사용 (`,` vs `/`)**
   - 각 컬럼별로 `/`와 `,` 중 **어느 것이 더 자주** 등장하는지 보고
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
   - 줄바꿈(`
`)이 공백으로 바뀌는 것은 허용되지만, 텍스트 일부가 사라지면 안 됩니다.

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
    // 예: "보종명+유형1+유형2 조합이 5건 ߺ"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안(근본적인 문제를 해결할 수 있도록)
    // 예: "LLM 기반 Cartesian으로 재시도"
  ],
  "reasoning": "Cartesian Product 결과가 원본 테이블을 얼마나 잘 반영하는지에 대한 평가",
  "actual_count": {count}
}}
"""

    return base

# ==================================================================================================
# validate_table_split_llm
# ==================================================================================================

def build_validate_table_split_llm_prompt(
    original_header: List[str],
    original_data: List[List[str]],
    split_header: List[str],
    split_data: List[List[str]],
) -> str:
    """
    LLMTableSplitTool 결과 검증용 프롬프트 생성

    Args:
        original_header: 원본 테이블 헤더
        original_data: 원본 테이블 데이터
        split_header: Split 후 헤더
        split_data: Split 후 데이터

    Returns:
        LLM 검증 프롬프트
    """
    original_header_json = json.dumps(original_header, ensure_ascii=False)
    original_data_json = json.dumps(original_data, ensure_ascii=False, indent=2)
    split_header_json = json.dumps(split_header, ensure_ascii=False)
    split_data_json = json.dumps(split_data, ensure_ascii=False, indent=2)

    base = f"""당신은 데이터 변환 품질을 검토하는 전문가입니다.

**임무**:
- LLMTableSplitTool이 Definition 테이블의 셀 값을 **의미적으로 올바르게 분리**했는지 확인하세요.
- **중요**: Header는 **표준 스키마로 정규화될 수 있습니다** (예: "명칭" → "보종명", "보험종목" → "유형1")
- 각 셀의 값은 리스트로 split됩니다.

**원본 테이블**:
Header: {original_header_json}
Data 행 수: {len(original_data)}
전체 Data:
{original_data_json}

**Split 결과**:
Header: {split_header_json}
Data 행 수: {len(split_data)}
전체 Data:
{split_data_json}

### LLMTableSplitTool의 역할 이해하기

**TableSplit이 하는 일**:
- Definition 테이블의 셀 값을 **의미 기반으로 분리**
- **Header 정규화**: 표준 스키마로 변환 (명칭→보종명, 보험종목→유형1, 보험종목_1→유형2)
- Row 수는 **절대 변경하지 않음** (행 추가/삭제 금지)
- 각 셀 값을 `str` 또는 `list[str]`로 split
- 예: `"간편심사(315)형/간편심사(335)형/일반심사형"`
  → `["간편심사(315)형", "간편심사(335)형", "일반심사형"]` (원자 단위 분리)

**TableSplit이 하지 않는 일**:
- ❌ Row 추가/삭제 (행 수는 동일해야 함)
- ❌ 데이터 손실/변형 (원본 값 보존)

### 검증 기준 (명백한 오류만 확인)

**합리적인 split (is_valid=true)**:
1. **Header 정규화 허용**:
   - Header는 **표준 스키마로 정규화될 수 있음** (예: "명칭" → "보종명", "보험종목" → "유형1", "보험종목_1" → "유형2")
   - 컬럼 순서는 유지됨
   - **허용되는 정규화**: 명칭/상품명/보장명칭 → 보종명, 보험종목/구분/유형/심사형 → 유형1, 보험종목_1 → 유형2
2. **Row 수 일치**: `len(split_data) == len(original_data)` (행 개수 동일)
3. **셀 타입 제약**: 각 셀이 `str` 또는 `list[str]`
4. **의미 있는 split**:
   - 리스트로 분리된 값들이 의미적으로 그룹핑되어 있음
   - 예: `["간편심사(315)형/간편심사(335)형", "일반심사형"]` ✅
   - 같은 계열(간편심사)은 함께, 다른 계열(일반심사)은 분리
5. **원본 보존**: 분리 과정에서 값 손실/변형 없음

**명백한 오류 (is_valid=false가 될 수 있음)**:
1. **Header 비정상 변경**: 표준 스키마 외의 임의 변경 (예: "보종명" → "상품명칭_수정" ❌)
2. Row 수가 변경됨 (원본 5행 → 결과 4행 등)
3. 셀 타입이 잘못됨 (숫자, dict 등 비허용 타입)
4. 의미 없는 split:
   - 예: `["간편심사(315", ")형/간편심사(335)형/일반심사형"]` ❌ (잘못된 분리)
   - 예: `["간편", "심사(315)형/간편심사(335)형/일반심사형"]` ❌ (무의미한 분리)
5. 원본 데이터 손실:
   - 예: 원본 `"A/B/C"` → 결과 `["A", "B"]` (C 누락) ❌
6. 분리 대상이 아닌 컬럼도 변경됨 (보종명 등 단일값 컬럼)

### 검토 규칙

**중요한 마음가짐**:
- TableSplit은 **Row 수를 절대 변경하지 않습니다**
- **Header 정규화는 허용됩니다** (표준 스키마로 변환: 명칭→보종명, 보험종목→유형1 등)
- **셀 값만** str → list[str]로 의미 기반 split합니다
- 의미적 그룹핑이 합리적인지 확인하세요 (완벽하지 않아도 OK)
- **명백한 오류**만 지적하세요

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오류만 기록
    // 예: "Header가 비정상적으로 변경되었습니다: 원본 ['보종명', '유형1'] → 결과 ['보종명_잘못된변경', '유형1']"
    // 예: "Row 수가 원본 5행에서 4행으로 감소했습니다"
    // 예: "셀 값이 잘못 분리되었습니다: '간편심사(315' + ')형/일반심사형'"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "Header는 표준 스키마(보종명, 유형1, 유형2)로만 정규화하세요"
    // 예: "누락된 행을 복원하세요"
  ],
  "reasoning": "TableSplit이 Header/Row 수를 유지하면서 셀 값을 의미적으로 올바르게 split했는지 평가"
}}

**참고**: 의미적 그룹핑이 완벽하지 않아도, Header/Row 수가 유지되고 데이터 손실이 없으면 is_valid=true를 반환하세요."""

    return base

# ==================================================================================================
# validate_condition_transform_llm
# ==================================================================================================

def build_validate_condition_transform_llm_prompt(
    original_header: List[str],
    original_data: List[List[str]],
    transformed_header: List[str],
    transformed_data: List[List[str]],
) -> str:
    """
    ConditionTransformTool 결과 검증용 프롬프트 생성

    Args:
        original_header: 원본 Condition 테이블 헤더
        original_data: 원본 Condition 테이블 데이터
        transformed_header: 변환된 헤더
        transformed_data: 변환된 데이터

    Returns:
        LLM 검증 프롬프트
    """
    original_header_json = json.dumps(original_header, ensure_ascii=False)
    original_data_json = json.dumps(original_data, ensure_ascii=False, indent=2)
    transformed_header_json = json.dumps(transformed_header, ensure_ascii=False)
    transformed_data_json = json.dumps(transformed_data, ensure_ascii=False, indent=2)

    base = f"""당신은 데이터 변환 품질을 검토하는 전문가입니다.

**임무**:
- ConditionTransformTool이 Condition 테이블을 **올바르게 변환**했는지 확인하세요.
- Split + Schema mapping + Age parsing을 수행한 결과를 검증합니다.

**원본 Condition 테이블**:
Header: {original_header_json}
Data 행 수: {len(original_data)}
전체 Data:
{original_data_json}

**변환 결과**:
Header: {transformed_header_json}
Data 행 수: {len(transformed_data)}
전체 Data:
{transformed_data_json}

### ConditionTransformTool의 역할 이해하기

**Transform이 하는 일**:
1. **독립값 리스트 분리**:
   - `"80/90/100세 만기"` → `["80세 만기", "90세 만기", "100세 만기"]`
   - `"10/15/20년납"` → `["10년납", "15년납", "20년납"]`

2. **가입나이 파싱**:
   - 최소가입연령: 상수 추출 (예: `"만 15세"`)
   - 최대가입연령: **수식 문자열 그대로 보존** (예: `"min[세만기 - 년납, 70] 세"`)
   - ⚠️ **계산하지 않음** (수식을 숫자로 변환하면 안 됨)

3. **성별 추출**:
   - `"가입나이_남"`, `"가입나이_여"` → `["(1)남자", "(2)여자"]` 또는 단일값

4. **연령구분코드 생성**:
   - "만" 포함 → `"(2)만연령"`
   - "만" 미포함 → `"(1)보험연령"`

5. **Schema mapping**:
   - 원본 `"가입나이_남"` → 최종 `"주피보험자최소가입연령"` 등
   - 필수 컬럼 추가

**Transform이 하지 않는 일**:
- ❌ 수식 계산 (최대가입연령은 수식 문자열 그대로)
- ❌ 데이터 손실 (모든 원본 행 보존)

### 검증 기준 (명백한 오류만 확인)

**합리적인 변환 (is_valid=true)**:

1. **필수 스키마 존재**:
   ```
   - "보험기간" (list 또는 str)
   - "납입기간" (list 또는 str)
   - "주피보험자최소가입연령" (str 상수)
   - "주피보험자최대가입연령" (str 수식)
   - "주피보험자최소가입연령구분코드" ("(1)보험연령" or "(2)만연령")
   - "주피보험자최대가입연령구분코드" ("(1)보험연령" or "(2)만연령")
   - "주피보험자가입성별" (list 또는 str)
   ```

2. **리스트 분리 정확성**:
   - `보험기간`: `["80세 만기", "90세 만기"]` 형태 (list)
   - `납입기간`: `["10년납", "15년납"]` 형태 (list)
   - `주피보험자가입성별`: `["(1)남자", "(2)여자"]` 또는 단일값

3. **가입연령 형식**:
   - `주피보험자최소가입연령`: 상수 문자열 (예: `"만 15세"`, `"15세"`)
   - `주피보험자최대가입연령`: **수식 문자열** (예: `"min[세만기 - 년납, 70] 세"`)
   - ⚠️ **중요**: 최대가입연령이 숫자(70)가 아닌 수식 문자열이어야 함

4. **연령구분코드 형식**:
   - 값이 `"(1)보험연령"` 또는 `"(2)만연령"`
   - 최소/최대 각각 올바른 코드 부여

5. **원본 데이터 보존**:
   - 모든 원본 행이 변환 결과에 포함
   - 필수값 null 비율 < 10%

**명백한 오류 (is_valid=false가 될 수 있음)**:

1. **필수 컬럼 누락**:
   - 위 7개 필수 컬럼 중 하나라도 없음

2. **리스트 분리 실패**:
   - 보험기간/납입기간이 `"80/90세"` 형태 그대로 (split 안 됨)
   - 또는 잘못된 split: `["80/", "90세"]`

3. **수식 계산 오류** (가장 중요):
   - 최대가입연령이 숫자로 계산됨: `70` ❌ (수식 문자열이어야 함)
   - 올바른 예: `"min[세만기 - 년납, 70] 세"` ✅

4. **연령구분코드 형식 오류**:
   - 값이 `"(1)보험연령"` / `"(2)만연령"` 이 아님
   - 예: `"만연령"`, `"1"`, `null` 등

5. **원본 데이터 손실**:
   - 원본 5행 → 결과 4행
   - 필수값 null 비율 > 10%

### 검토 규칙

**중요한 마음가짐**:
- Transform은 **Split + Schema mapping**을 수행합니다
- **최대가입연령은 수식 문자열**이어야 합니다 (계산 금지)
- 리스트 분리가 완벽하지 않아도, 필수 스키마와 수식 형식이 맞으면 OK
- **명백한 오류**만 지적하세요

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오류만 기록
    // 예: "필수 컬럼 '납입기간'이 누락되었습니다"
    // 예: "최대가입연령이 숫자 70으로 계산되었습니다 (수식 문자열이어야 함)"
    // 예: "연령구분코드가 '(1)보험연령' 또는 '(2)만연령'이 아닙니다: '만연령'"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "최대가입연령을 수식 문자열로 보존하세요 (계산하지 마세요)"
    // 예: "누락된 컬럼을 추가하세요"
  ],
  "reasoning": "ConditionTransform이 스키마 매핑, 리스트 분리, 수식 보존을 올바르게 수행했는지 평가"
}}

**참고**: 수식 보존이 가장 중요합니다. 최대가입연령이 `"min[세만기-년납,70] 세"` 같은 수식 문자열이면 is_valid=true를 반환하세요."""

    return base

def build_validate_condition_extract_llm_prompt(
    condition_sections: List[Dict[str, Any]],
    extracted_header: List[str],
    extracted_data: List[List[str]],
    definition_sections: List[Dict[str, Any]] = None,
) -> str:
    """
    Condition Extract 결과 검증용 LLM 프롬프트 생성

    Args:
        condition_sections: 원본 condition 섹션들 (섹션 제목, 테이블 등)
        extracted_header: 추출된 테이블 header
        extracted_data: 추출된 테이블 data
        definition_sections: 원본 definition 섹션들 (주석 참조용, optional)

    Returns:
        str: LLM 검증 프롬프트
    """
    definition_section_text = ""
    if definition_sections:
        definition_section_text = f"""

## Definition Sections (참조용)

Definition 섹션의 주석을 참조하여 조건을 추가했는지 확인하는 데 사용합니다:

```json
{json.dumps(definition_sections, ensure_ascii=False, indent=2)}
```
"""

    base = f"""당신은 **보험 상품 문서 파싱 검증 전문가**입니다.

## 역할

Condition Extract Tool이 원본 섹션들에서 가입 조건 테이블을 올바르게 추출했는지 검증합니다.

## 원본 Condition Sections

다음은 문서에서 분류된 condition 섹션들입니다:

```json
{json.dumps(condition_sections, ensure_ascii=False, indent=2)}
```
{definition_section_text}
## 추출된 Condition Table

Condition Extract Tool이 위 섹션들에서 다음 테이블을 추출했습니다:

**Header**: {json.dumps(extracted_header, ensure_ascii=False)}

**Data** ({len(extracted_data)} rows):
```json
{json.dumps(extracted_data, ensure_ascii=False, indent=2)}
```

## Condition Extract Tool의 역할

이 도구는 다음 작업을 수행합니다:

1. **가입 조건 테이블 식별 및 추출**
   - condition_sections 내의 여러 섹션에서 "가입 조건", "가입가능 조건" 등의 테이블 찾기
   - 여러 섹션의 테이블을 하나로 병합

2. **계층 정보를 컬럼으로 추가**
   - 섹션 제목 (title)에서 계층 정보 추출하여 "유형1", "유형2", "유형3" 등의 컬럼 생성
   - 예: "가. 해약환급금 미지급형" → 유형1 컬럼에 "해약환급금 미지급형" 추가

3. **컬럼명 정규화**
   - 원본 테이블의 다양한 컬럼명을 표준 형식으로 변환
   - 예: "보험 기간" → "보험기간", "납입 기간" → "납입기간"
   - 성별 구분 컬럼: "가입나이_남", "가입나이_여"

4. **데이터 보존**
   - 원본 테이블의 모든 행을 포함 (데이터 손실 금지)
   - 셀 값은 그대로 유지 (계산/변환하지 않음)

## 검증 기준

다음 항목들을 체크하세요:

### 1. **테이블 구조 유효성** (필수)
- Header와 data가 존재하는가?
- 각 행의 컬럼 수가 header 수와 일치하는가?
- 빈 테이블이 아닌가? (condition_sections가 있으면 최소 1행 이상 기대)

### 2. **컬럼명 정규화** (중요)
- 표준화된 컬럼명을 사용하는가?
  - 일반적 컬럼: "보험기간", "납입기간", "가입나이_남", "가입나이_여", "납입주기" 등
- JOIN key 컬럼이 존재하는가?
  - 최소 1개 이상의 유형 컬럼 ("유형1", "유형2", "심사형", "보장형" 등)

### 3. **데이터 내용 품질** (중요)
- 보험기간/납입기간 형식이 합리적인가?
  - 예: "80/90/100세 만기, 종신", "10/15/20년납"
  - 오류 예: 빈 문자열, "unknown", 숫자만 있음

- 가입나이 수식이 유효한가?
  - 예: "만15세 - min[세만기 - 년납, 70] 세"
  - 수식 문자열 그대로 보존되어야 함 (계산하면 안 됨)
  - 오류 예: 숫자로 계산됨 (70), 빈 문자열

- 비어있는 셀 비율이 과도하지 않은가?
  - 전체 셀의 30% 이상이 비어있으면 경고
  - "-", "없음" 등은 유효한 값으로 간주

### 4. **계층 정보 추출** (선택적)
- 유형 컬럼들에 의미 있는 값이 있는가?
  - 예: "해약환급금 미지급형", "간편심사형", "일반형"
  - 모든 행이 "-" 또는 빈 값이면 문제

### 5. **원본 섹션과의 일치성** (중요)
- condition_sections의 테이블 데이터가 추출 결과에 포함되었는가?
- 불필요한 정보 (주석, 설명 등)는 제외되었는가?
- "가입불가 조건", "제외 사항" 등은 일반적으로 제외되어야 함

### 6. **⚠️ 주석 참조 처리 (CRITICAL!)** (선택적 - definition_sections가 있을 때만)
- Definition 섹션의 주석(text paragraph)에 **"A는 B와 동일"** 패턴이 있는가?
  - 예: "데이터사이언스 트랙은 컴퓨터공학 트랙과 동일한 필수과목 규정을 적용한다."
- 참조 패턴이 있으면, **참조된 조건(A)이 추출 결과에 포함**되었는가?
  - 예: "데이터사이언스" 조건이 "컴퓨터공학" 조건을 복사하여 추가되었는가?
- **검증 방법**:
  1. Definition 섹션의 모든 text paragraph를 읽기
  2. "A는 B와 동일", "A의 경우 B와 동일한" 패턴 찾기
  3. 추출된 Condition 테이블에서 A 유형의 행이 있는지 확인
  4. 없으면 오류: "주석에서 'A는 B와 동일'을 발견했으나, A 조건이 추출되지 않았습니다"

## 흔한 오류 패턴

다음과 같은 명백한 오류만 지적하세요:

1. **빈 테이블**:
   - condition_sections에 테이블이 있는데 extracted_data가 비어있음

2. **컬럼명 미정규화**:
   - "보험 기간" (공백 포함), "Period" (영어), "기간1" (숫자 suffix) 등
   - JOIN key 컬럼이 하나도 없음

3. **데이터 손실**:
   - 원본 섹션에 5행이 있는데 2행만 추출됨
   - 중요한 컬럼 (보험기간, 납입기간)이 모두 빈 값

4. **불필요한 데이터 포함**:
   - "가입불가 조건" 테이블의 데이터가 포함됨
   - 설명 텍스트가 셀에 포함됨

5. **잘못된 병합**:
   - 여러 섹션의 테이블을 병합했는데 컬럼 구조가 맞지 않음
   - 예: 한 섹션은 "가입나이_남/여" 구분, 다른 섹션은 "가입나이" 단일 컬럼

## 검토 규칙

**중요한 마음가짐**:
- Condition Extract는 **테이블 추출 + 컬럼명 정규화**를 수행합니다
- 데이터는 **원본 그대로 보존**되어야 합니다 (계산/변환 금지)
- 컬럼명이 완벽하지 않아도, 의미가 명확하고 JOIN key가 있으면 OK
- **명백한 오류**만 지적하세요

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오류만 기록
    // 예: "condition_sections에 테이블이 있으나 추출 결과가 비어있습니다"
    // 예: "JOIN key 컬럼 (유형1, 유형2 등)이 하나도 없습니다"
    // 예: "보험기간/납입기간 컬럼이 모두 빈 값입니다"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "원본 섹션의 테이블을 다시 확인하세요"
    // 예: "계층 정보를 유형 컬럼으로 추가하세요"
  ],
  "reasoning": "Condition Extract가 테이블 추출, 컬럼명 정규화, 계층 정보 추가를 올바르게 수행했는지 평가"
}}

**참고**: 데이터 보존과 컬럼명 정규화가 가장 중요합니다. 원본 테이블의 모든 데이터가 포함되고, JOIN key 컬럼이 있으면 is_valid=true를 반환하세요."""

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
    5. 셀 값은 원본 그대로 유지 (분리하지 않음)
    """
    extra = f"**최우선 지시사항(있는 경우 절대적으로 우선 적용)**: {instruction}" if instruction else ""
    tail = """
    다음 JSON 형식으로 반환:
    {{
      "header": ["컬럼1", "컬럼2", ...],
      "data": [
        ["값1", "값2", ...],
        ...
      ],
      "extraction_method": "table" or "text",
      "notes": "처리 내용 설명"
    }}
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
    4. 셀 내용은 정리하되, 줄바꿈( 
)은 공백으로 변환
    5. 데이터 손실 없이 모든 셀의 값을 추출"""

    extra = f"**최우선 지시사항(있는 경우 절대적으로 우선 적용)**: {instruction}" if instruction else ""
    
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
        extra_instruction = (f"""
**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:
{instruction}

---

"""
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

2. 줄바꿈( 
)과 공백은 strip하되, 보종명(첫 번째 컬럼)은 줄바꿈 유지

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
    print(f'instruction : {instruction}')
    print(f'7'*20)
    base = ""
    if instruction and instruction.strip():
        base = f"""
          **추가 지시사항** (최우선 - 반드시 따를 것):
          {instruction.strip()}"""
    
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
     - 기간/연령/납입 조건을 수치/범위로 표현
     - 표 제목이 "가입가능 조건", "보험기간/보험료 납입기간/가입나이/납입주기" 등인 경우가 많음
     - 정의(상품 구조)를 새로 소개하기보다는, 이미 정의된 유형에 대한 조건을 설명

4. **other** (기타 섹션)

   - 위 3가지에 해당하지 않는 모든 섹션

### 중요 규칙

- 제목이 비표준이어도(예: "상품 구성", 숫자만 있는 제목 등) 내용상
  상품/보장 구조를 정의하면 **definition_core**로 분류하세요.
- 기간/가입나이/납입기간/납입주기에 대한 수치/범위가 중심이면 **condition**으로 분류하세요.
- "※", "참고", "주)", "단," 등으로 시작하는 정의 관련 설명은
  구조 정의가 아니면 **definition_annotation**으로 분류하세요.
- 모든 섹션은 정확히 한 카테고리에만 속해야 합니다.

## 예시로 배우기 (Few-shot Learning)

**입력 예시 1**:
```
[Section 5]
Title: 3. 보험기간, 보험료 납입기간...
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

    prompt += "\n**입력 섹션**:"

    for s in summaries:
        prompt += f"\n[Section {s['index']}]\n"
        prompt += f"Title: {s.get('title') or '(제목 없음)'}\n"
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
    return base + prompt

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

# ------------------------------------------------------------------------------------------------------------------------------
# --------------------------------------------grouping 일반화 test ------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------------------------------------

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
당신은 두 개의 테이블(Definitions / Conditions) 사이에서 행들을 논리적으로 매칭하고 그룹핑하는 전문가입니다
{extra_instruction}

## 입력 데이터

**Definitions 테이블**:
```
{def_table}
```

**Conditions 테이블**:
```
{cond_table}
```

---

## 작업 목표

1. Definitions와 Conditions 사이에서 어떤 컬럼 조합이 JOIN 키로 동작하는지 파악합니다.
2. **각 Condition 행마다**, 그 Condition의 JOIN 키 값과 일치하는 **모든 Definition 행들을 한 그룹으로 묶습니다.**
3. 최종적으로 Python 코드가 이 그룹 정보를 이용해 조합을 생성할 수 있도록,
   인덱스 기반의 간단한 JSON 구조를 만듭니다.

- 같은 JOIN 키 값(같은 조건 조합)을 가진 Definition 행들 → 항상 같은 그룹
- **⚠️ CRITICAL**: 각 그룹은 **하나 또는 여러 개의 Condition 행**(`condition_indices`)과 연결될 수 있습니다
  - 같은 JOIN 키 값을 가진 Condition 행이 여러 개 있으면 **모두 리스트에 포함**해야 합니다
  - 예: 주계약/해약환급금 미지급형 조건이 3개 행(0,1,2)으로 나뉘어 있으면 `condition_indices: [0, 1, 2]`
- 하나의 Definition 행이 여러 그룹에 포함될 수 있습니다 (리스트 컬럼 때문에 JOIN 키 조합이 여러 개인 경우).

---


### 1. JOIN 키 파악

Definition과 Condition 테이블에서 **같은 개념을 담고 있는 컬럼들**을 찾아 JOIN 키로 사용하세요.

- 예시: Definition의 `"보험종목"` ↔ Condition의 `"유형1"`
- 예시: Definition의 `"보험종목_1"`(심사형) ↔ Condition의 `"유형2"`

**중요**:

- JOIN 키로 사용할 컬럼들은 나중에 `column_mapping.join_keys`에 모두 포함해야 합니다.
- JOIN 키가 아닌 컬럼(예: 상품명/명칭 등)은 **그룹을 쪼개는 기준으로 절대 사용하지 마세요.**
  - 같은 JOIN 키 값을 가진 Definition 행들이 여러 개라면, 그 행들은 **항상 같은 그룹의 `definition_indices`에 모두 포함**되어야 합니다.

**컬럼명이 다르더라도 의미적으로 같으면 JOIN 키로 사용할 수 있습니다.**

#### 1-1. 컬럼명 Shift 처리 (CRITICAL!)

두 테이블의 컬럼명이 **한 칸씩 shift되어 있는 경우**, 데이터 값을 보고 올바른 매핑을 찾아야 합니다.

**예시: 컬럼명 shift 케이스**

**Definition 테이블:**
```
보종명 | 유형1 | 유형2 | 유형3
-------|-------|-------|-------
상품A  | 보장형 계약 | 해약환급금 일부지급형 | 1종
상품A  | 보장형 계약 | 해약환급금 일부지급형 | 2종
```

**Condition 테이블:**
```
유형1 | 유형2 | 유형3 | 보험기간
------|-------|-------|----------
보장형 계약 | 해약환급금 일부지급형 | 1종 | 종신
보장형 계약 | 해약환급금 일부지급형 | 2종 | 종신
```

**올바른 매핑 (데이터 값 기준):**
- Definition `유형1` (보장형 계약) ↔ Condition `유형1` (보장형 계약) ✅
- Definition `유형2` (해약환급금 일부지급형) ↔ Condition `유형2` (해약환급금 일부지급형) ✅
- Definition `유형3` (1종/2종) ↔ Condition `유형3` (1종/2종) ✅

**JOIN keys 선택:**
- Definition 기준: `['유형1', '유형2', '유형3']` ✅
- 또는 Condition 기준: `['유형1', '유형2', '유형3']` ✅
- **둘 다 같은 개념이므로 어느 쪽을 선택해도 무방합니다.**

**매칭 시 주의:**
- `join_mappings`에는 **Definition 컬럼명, Condition 컬럼명, 매칭 값**을 명시적으로 기록합니다:
  ```json
  [
    {{"def_col": "컬럼A", "cond_col": "컬럼X", "value": "값1"}},
    {{"def_col": "컬럼B", "cond_col": "컬럼Y", "value": "값2"}}
  ]
  ```
- Definition 행과 Condition 행의 **값이 일치하면 매칭**합니다 (컬럼명이 달라도 OK!)

### 2. Fuzzy Matching (의미 기반 매칭)
문자열이 정확히 일치하지 않아도 **의미적으로 같으면 매칭**하세요.

**예시**:
- 표기 차이: `"일반형"` vs `"일반 형"`, `"GENERAL"` vs `"General"`
- 코드 포함: `"TYPE_A(001)"` vs `"TYPE_A"`
- 계열 차이: `"고급(13)형"` vs `"고급형"`

### 3. Wildcard/미기재 처리 (CRITICAL!)

`"-"`, `"—"`, `""`, `null`, `"해당없음"` 은 상황에 따라 의미가 다릅니다. 아래 규칙을 따르세요.

(1) 미기재(생략) 우선 해석
- Condition 행이 특정 상위 섹션(title) 아래에 있고(예: "나. 적립형 계약(전환형)"),
  그 섹션명이 이미 어떤 상품유형을 지칭한다면,
  표 내부의 `유형1="-"`, `유형2="-"` 는 "ANY"가 아니라 "표에서 생략된 값"일 가능성이 큽니다.
- 이 경우 매칭은 상위 섹션에서 추출된 계층 컬럼(예: 유형0 등)과 다른 join key로 수행하고,
  `"-"` 컬럼은 join에서 제외(무시)하되, "모든 정의를 확장"하는 근거로 사용하지 마세요.

(2) ANY(모든 값 허용) 해석 조건
- Condition 행에 `유형X="-"`가 있고,
  그 행이 "특정 유형1은 지정되어 있으나 유형2만 미지정"처럼 명확히 옵션 축을 열어둔 형태라면
  (예: 유형1="해약환급금 미지급형", 유형2="-"),
  이때의 `"-"`는 ANY로 해석합니다.
- ANY로 해석하는 경우:
  - 해당 컬럼은 join 조건에서 제외하고,
  - 나머지 join key로 매칭되는 Definition 행들을 가능한 한 많이 포함시킵니다.
  - Definition 쪽에 실제로 존재하는 유형2 값들만 허용됩니다(새 값을 생성하지 않음).

(3) 금지
- `"-"`가 있다는 이유만으로 근거 없이 coverage_ratio를 높이기 위해 임의 매칭을 만들지 마세요.


**예시 2: Condition에 와일드카드 (일반적인 케이스)**
```
Definition row: 유형1=적립형 계약, 유형2=적립형 계약, 유형3=적립형 계약
Condition row: 유형0=적립형 계약(전환형), 유형1="-", 유형2="-"
```

**매칭 로직:**
1. 유형1 비교: "적립형 계약" (Def) ↔ "적립형 계약(전환형)" (Cond) → Fuzzy 매칭 O ✅
2. 유형2 비교: "적립형 계약" (Def) ↔ **`"-"` (Cond)** → 와일드카드이므로 **무시** ✅
3. 유형3 비교: "적립형 계약" (Def) ↔ **`"-"` (Cond)** → 와일드카드이므로 **무시** ✅
4. **결과**: 매칭 성공! ✅

**join_mappings 기록:**
```json
[
  {{"def_col": "컬럼A", "cond_col": "컬럼A", "value": "타입X"}},
  {{"def_col": "컬럼B", "cond_col": "컬럼B", "value": "-"}},   // 와일드카드 표시
  {{"def_col": "컬럼C", "cond_col": "컬럼C", "value": "-"}}
]
```

**중요:** JOIN keys에 포함된 컬럼이라도 **값이 와일드카드면 해당 키는 무시**하고 나머지 키만으로 매칭하세요.

### 4. 우선순위
매칭 시 다음 우선순위를 따르세요:
1. **Exact Match** (정확히 일치) - 최우선
2. **Fuzzy Match** (의미 일치) - 차선
3. **Wildcard** (`"-"`) - 최후

### 5. 다중값 처리
한 컬럼 내에 여러값들이 존재할 경우 판단해서 의미적으로 매칭되지 않는 값은 지우세요
- `"환급(A)형 / 환급(B)형 / 일반형"` ≈ `"환급형"` →  "환급(A)형 / 환급(B)형" 만 매칭

### 6. 리스트 값 매칭 (CRITICAL)

Definitions 테이블의 셀 값이 리스트인 경우:

- 각 리스트 요소를 독립적인 후보값으로 간주합니다.
- 같은 Definition 행이라도, 리스트의 서로 다른 요소가 서로 다른 Condition 행과 매칭될 수 있습니다.
- **Fuzzy matching 적용 시**, 하나의 Condition 값이 **여러 리스트 요소와 동시에 매칭**될 수 있습니다.
  - 이 경우 `matched_list_items`에 **모든 매칭되는 인덱스를 리스트로** 포함하세요.
- 각 그룹에서, `definition_indices[i]`에 해당하는 Definition 행이 어떤 리스트 요소를 사용했는지 `matched_list_items[i]`에 **0-based 인덱스 (또는 인덱스 리스트)**로 기록하세요.


**예시 1: 서로 다른 Condition에 매칭**:

- Definition 행 0: `{{"유형": ["일반", "특약(A,B,C)"]}}`
- Condition 행 0: `{{"유형": "일반"}}`
- Condition 행 1: `{{"유형": "특약"}}`

**출력**:
```json
{{
  "id": 0,
  "definition_indices": [0],
  "matched_list_items": [0],
  "condition_indices": [0]
}},
{{
  "id": 1,
  "definition_indices": [0],
  "matched_list_items": [1],
  "condition_indices": [1]
}}
```

**예시 2: Fuzzy matching으로 여러 리스트 요소가 동시에 매칭 (IMPORTANT!)**:

- Definition 행 0: `{{"유형2": ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형", "일반심사형"]}}`
- Condition 행 0: `{{"유형1": "간편심사형"}}`  ← "간편심사"로 fuzzy 매칭
- Condition 행 1: `{{"유형1": "일반심사형"}}`

**출력**:
```json
{{
  "id": 0,
  "definition_indices": [0],
  "matched_list_items": [[0, 1, 2]],  ← 315, 335, 355 모두 "간편심사형"과 매칭!
  "condition_indices": [0],
  "reasoning": "'간편심사형'은 fuzzy matching으로 '간편심사(315)형', '간편심사(335)형', '간편심사(355)형' 모두와 매칭됩니다."
}},
{{
  "id": 1,
  "definition_indices": [0],
  "matched_list_items": [3],
  "condition_indices": [1]
}}
```

**주의**:
- matched_list_items의 길이는 definition_indices 길이와 같아야 합니다.
- **Fuzzy matching으로 여러 요소가 매칭되면**, 해당 위치에 **인덱스 리스트** `[0, 1, 2]`를 넣습니다.
- **정확히 하나만 매칭되면**, 단일 정수 `0` 또는 `[0]` 형태로 넣습니다 (둘 다 허용).
- Definition 셀이 리스트가 아닌 문자열인 경우, 해당 위치에 null을 넣습니다.

---

## 출력 형식

다음 JSON 형식으로 그룹핑 로직을 반환하세요:

```json
{{
  "column_mapping": {{
    "join_keys": ["JOIN_KEY_1", "JOIN_KEY_2", "..."],
    "value_columns": ["VALUE_COL_1", "VALUE_COL_2", "..."]
  }},
  "groups": [
    {{
      "id": 0,
      "join_mappings": [
        {{"def_col": "컬럼A", "cond_col": "컬럼X", "value": "값1"}},
        {{"def_col": "컬럼B", "cond_col": "컬럼Y", "value": "값2"}}
      ],
      "definition_indices": [0, 3],
      "matched_list_items": [null, null],
      "condition_indices": [1, 2, 3],
      "reasoning": "이 그룹이 이렇게 매칭된 이유를 1~2문장으로 간단히 설명합니다. 같은 JOIN 키 값을 가진 Condition 행이 여러 개 있어 모두 포함했습니다."
    }}
  ],
  "unmatched": {{
    "definition_indices": [5, 6],
    "condition_indices": [4]
  }},
  "summary": {{
    "total_definitions": {len(definition_data)},
    "total_conditions": {len(condition_data)},
    "total_groups": 1,
    "matched_definition_count": {len(definition_data) - 2},
    "unmatched_definition_count": 2,
    "coverage_ratio": 0.9
  }}
}}

```

**필드 설명**:
- `column_mapping`:
  - `join_keys`: Definition과 Condition을 매칭하는 데 사용된 컬럼들
    - Definition 기준 컬럼명 또는 Condition 기준 컬럼명 사용 가능 (예: `['유형1', '유형2', '유형3']` 또는 `['유형1', '유형2', '유형3']`)
    - 컬럼명이 shift되어 있어도 **같은 개념**을 나타내면 어느 쪽 이름을 사용해도 무방
  - `value_columns`: 이후 Python에서 Condition으로부터 값을 가져올 컬럼 이름 리스트 (Condition 기준 컬럼명 사용)

- `groups`: 각 그룹의 매칭 정보
  - `id`: 그룹 고유 번호
  - `join_mappings`: 이 그룹의 조인 매핑 정보 (리스트)
    - 각 매핑 객체는 `def_col` (Definition 컬럼명), `cond_col` (Condition 컬럼명), `value` (매칭 값)을 포함
    - **컬럼명이 다르더라도 값이 같으면 매칭 가능** (예: def_col="유형A", cond_col="유형B", value="타입1")
  - `definition_indices`: 이 그룹에 속한 Definition 행 번호들 (0-based)
  - `condition_indices`: 매칭되는 Condition 행 번호들 (0-based, **⚠️ LIST로 변경됨!**)
    - **같은 JOIN 키 값을 가진 Condition 행이 여러 개 있으면 모두 포함**해야 합니다
    - 예: 같은 조건이 3개 행으로 나뉘어 있으면 `[0, 1, 2]`
  - `reasoning`: 왜 이렇게 그룹핑했는지 설명

- `unmatched`:
  - `definition_indices`: 어떤 Condition과도 매칭되지 않은 Definition 행들
  - `condition_indices`: 어떤 Definition과도 매칭되지 않은 Condition 행들

- `summary`: 전체 통계 요약

---

## 주의사항
1. **인덱스는 0-based**: 첫 번째 행은 인덱스 0
2. **중복 허용 (리스트 값의 경우)**: Definition 행이 리스트 값을 가진 경우, **여러 그룹에 속할 수 있습니다** (각 그룹은 서로 다른 리스트 요소 또는 요소 조합과 매칭).
3. **완전성**: "조건이 있는 조합"을 우선 정확히 매칭하세요.
   Definition에만 존재하고 Condition에 없는 조합(unmatched_defs)은 정상일 수 있습니다.
4. **일관성**: 같은 조건을 가진 Definition 행들은 반드시 같은 그룹으로
5. **정확성**: `definition_indices`, `condition_indices`의 범위를 반드시 검증
6. **Fuzzy matching 우선**: 정확히 일치하지 않아도 의미적으로 같으면 매칭 (예: "간편심사형" ↔ "간편심사(315)형")
7. **값 기반 매칭 (CRITICAL)**: 컬럼명이 다르더라도 **데이터 값**을 보고 매칭하세요
   - Definition의 "보장형 계약" 값이 Condition의 "보장형 계약" 값과 일치하면 → 매칭 O
   - 컬럼명(유형1 vs 유형0)은 다를 수 있지만, 값이 같으면 같은 개념입니다
8. **와일드카드 우선 처리 (CRITICAL)**: `"-"` 값은 와일드카드(ANY)로 취급하여 **해당 키는 무시**하고 매칭
   - Condition의 유형2="-"이면, Definition의 유형2는 어떤 값이든 매칭됩니다
   - 와일드카드가 있는 row도 반드시 매칭하여 coverage_ratio를 높이세요

--- 

이제 위 규칙에 따라 Definition과 Condition 테이블을 분석하여 그룹핑 로직을 JSON으로 반환하세요.
"""
    return prompt



# ------------------------------------------------------------------------------------------------------------------------------

def build_intelligent_condition_extract_prompt(
    condition_sections: List[Dict[str, Any]],
    definition_sections: List[Dict[str, Any]] = None,
    instruction: str = ""
) -> str:
    sections_json = json.dumps(condition_sections, ensure_ascii=False, indent=2)

    definition_json = ""
    if definition_sections:
        definition_json = json.dumps(definition_sections, ensure_ascii=False, indent=2)

    extra_instruction = ""
    if instruction:
        extra_instruction = (
            "**최우선 지시사항 (있는 경우 절대적으로 우선 적용)**:\n"
            f"{instruction}\n\n"
        )

    definition_section = ""
    if definition_json:
        definition_section = f"""

**Definition 섹션 (참조용)**:
아래는 `definition_core` 및 `definition_annotation`으로 분류된 섹션들입니다.
이 섹션들의 **주석(text paragraph)**에 조건 참조 정보가 있을 수 있습니다.
{definition_json}

---
"""

    prompt = f"""
{extra_instruction}

당신은 보험 문서에서 가입 조건 정보를 추출하고 재구성하는 전문가입니다.

**입력 데이터**:
- `condition`으로 분류된 섹션들의 전체 내용입니다.
- 각 섹션은 `title`과 `table` 같은 다양한 `type`의 content item을 포함합니다.
{sections_json}
{definition_section}
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
    - 예: `나. 특약` → `유형1: 특약`, `① 해약환급금 미지급형` → `유형2: 해약환급금 미지급형` 과 같이 새로운 `유형` 컬럼을 생성합니다. 테이블에 이미 `유형1`이 있다면, `유형2`, `유형3` 등으로 순서를 조정하세요.

3.  **컬럼명 정규화**:
    - 추출된 테이블의 헤더(컬럼명)를 다음 규칙에 따라 표준화하세요.
      - "보험료 납입기간" 또는 "납입기간" → "납입기간"
      - "보험기간" → "보험기간"
      - "가입나이" 또는 "남자나이", "여자나이" → "가입나이_남", "가입나이_여" (필요시 분리)
      - "보험료 납입주기" 또는 "납입주기" → "납입주기"
    - `유형1`, `유형2` 등 이미 존재하는 유형 컬럼은 그대로 유지합니다.

4.  **데이터 정리**:
    - 테이블 데이터에서 불필요한 줄바꿈(`\n`)이나 공백을 제거하여 값을 정제합니다.

5.  **⚠️⚠️⚠️ 주석 참조 처리 (CRITICAL! 최우선 규칙!) ⚠️⚠️⚠️**:

    **핵심**: Definition 섹션의 **모든 text paragraph (주석)**를 **한 문장도 빠짐없이 읽어야** 합니다!

    **찾아야 할 패턴**:
    - **"A의 경우 B와 동일"**
    - **"A는 B와 동일한"**
    - **"A는 B와 같은"**
    - **"A 상품은 B 상품과 동일"**

    **처리 방법**:
    1. Definition 섹션의 **모든 text paragraph를 읽기** (여러 문장이 있으면 모두 확인!)
    2. 위 패턴을 찾으면 → "A"와 "B"를 추출
    3. Condition 테이블에서 "B" 유형의 모든 조건을 찾기
    4. 각 조건을 복사하되, 유형만 "B" → "A"로 변경
    5. 복사한 조건들을 Condition 테이블에 **추가**

    **⚠️ 실제 예시 (이 케이스를 꼭 처리해야 함!):**
    ```
    주석 (Definition 섹션):
    "※ 1. 다만, 'Student 플랜'의 경우 'Starter 플랜'과 동일한 기능/제한/정책을 적용한다.
    2. Enterprise 플랜은 Pro 플랜에서 업그레이드하는 경우에 한하여 제공한다."

    → 첫 번째 문장에서 "'Student 플랜'의 경우 'Starter 플랜'과 동일한" 패턴 발견!
    → A = "Student 플랜", B = "Starter 플랜"

    기존 Policy/Condition (주석 확인 전):
    [0] 플랜=Starter 플랜, 지원=Email, SLA=99.9%, 청구주기=월간
    [1] 플랜=Starter 플랜, 지원=Email, SLA=99.9%, 청구주기=연간
    [2] 플랜=Pro 플랜, 지원=Chat, SLA=99.95%, 청구주기=월간

    → "Starter 플랜" (B) 정책을 찾음: row 0, 1

    추가할 Policy/Condition:
    [3] 플랜=Student 플랜, 지원=Email, SLA=99.9%, 청구주기=월간
    [4] 플랜=Student 플랜, 지원=Email, SLA=99.9%, 청구주기=연간

    최종 Policy/Condition (주석 처리 후):
    [0] Starter 플랜, Email, 99.9%, 월간
    [1] Starter 플랜, Email, 99.9%, 연간
    [2] Pro 플랜, Chat, 99.95%, 월간
    [3] Student 플랜, Email, 99.9%, 월간 ← 추가됨!
    [4] Student 플랜, Email, 99.9%, 연간 ← 추가됨!
    ```

    **⚠️⚠️ 절대 잊지 마세요 ⚠️⚠️**:
    - 주석에 **여러 문장이 있으면 모든 문장을 확인**해야 합니다!
    - **첫 번째 문장만 읽고 끝내지 마세요!**
    - "Student 플랜"처럼 **정확한 키워드**를 찾으세요!
    - **"A는 B와 동일" 패턴이 있으면 무조건 조건을 추가**해야 합니다!

    **⚠️ CRITICAL: "판매하지 않는" 상품도 추가하세요! ⚠️**
    - 주석에 "판매하지 않는다", "비교용", "안내용"이라는 말이 있어도 **무시**하세요!
    - "A는 B와 동일" 패턴만 있으면 **반드시 추가**해야 합니다!
    - 예: "Pro 플랜은 판매하지 않고 비교·안내용으로 운영" → **그래도 추가!**
    - 이유: 데이터 완전성을 위해 모든 유형의 조건이 필요합니다!

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
  "header": ["유형1", "유형2", "유형3", "보험기간", ...],
  "data": [
    ["특약", "해약환급금 미지급형", "-", "10, 20년만기", ...],
    ["특약", "해약환급금 미지급형", "-", "60, 70세만기", ...]
  ],
  "reasoning": "'가입가능 조건' 테이블을 선택했습니다. 테이블 앞의 title '나. 특약'과 '① 해약환급금 미지급형'에서 계층 정보를 추출하여 각각 '유형1'과 '유형2' 컬럼으로 추가했습니다. 테이블 내 기존 '유형2'은 '유형3'로 조정했습니다."
}}
```

이제 위 규칙에 따라 조건 테이블을 추출하고 재구성하여 결과를 JSON으로 반환하세요.
"""
    return prompt

# -----------------------------------------------------------------------------------------------------------
# ----------------------------------------------------기존----------------------------------------------------
# -----------------------------------------------------------------------------------------------------------

def build_table_split_prompt_1(
    header: List[str],
    data: List[List[str]],
    instruction: str = ""
) -> str:
    """
    테이블 데이터의 multi-value 셀을 의미 기반으로 분리하는 프롬프트 생성 (범용)

    Args:
        header: 테이블 헤더
        data: 테이블 데이터
        instruction: 추가 지시사항 (optional)

    Returns:
        Table Split을 위한 LLM 프롬프트
    """
    # Format table for prompt
    table_str = format_table_for_prompt(header, data, max_rows=50)

    extra_instruction = ""
    if instruction:
        extra_instruction = f"""
**⚠️ 추가 지시사항 (최우선 적용)**:
{instruction}

---

"""

    prompt = f"""
{extra_instruction}당신은 테이블 데이터의 multi-value 셀을 의미 기반으로 분리하는 전문가입니다.

## 입력 데이터

**테이블**:
```
{table_str}
```

---

## 작업 목표

셀에 여러 값이 구분자(/, ,)로 나뉘어 있을 때, **의미적으로 다른 그룹**을 리스트로 분리하세요.

---

## 분리 규칙

### 0. 형태 보존 규칙 (매우 중요)

- 헤더(header)의 컬럼 개수와 순서는 절대로 바꾸지 마세요.
- 새로운 컬럼(예: "Index", "RowId" 등)을 추가하지 마세요.
- 새로운 행(row)을 추가하거나 기존 행을 삭제하지 마세요.
- **각 셀의 값만** 분리하거나 리스트로 바꿀 수 있습니다.
  - 예: "A유형/B유형" → ["A유형", "B유형"]
  - 예: "80/90/100세 만기, 종신" → ["80세 만기", "90세 만기", "100세 만기", "종신"]
- 즉, index와 같은 새로운 값을 만들지 말고, 기존 데이터만 활용해 변환하세요.

### 1. ⚠️ JOIN KEY 컬럼 특별 규칙 (최우선 적용!)

**JOIN KEY 컬럼이란?**: 나중에 Condition 테이블과 매칭될 핵심 식별자
- 예: "보종명", "명칭", "유형1", "유형2", "보험종목", "보험종목_1", "심사형" 등
- **특징**: 괄호 안에 숫자/코드가 있는 경우가 많음 (예: "간편심사(315)형", "프리미엄(A)형")

**핵심 원칙**: JOIN KEY 컬럼은 **원자 단위까지 완전히 분리**

**예시**:
```
❌ 잘못된 분리 (그룹핑):
입력: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
출력: "간편심사(315)형/간편심사(335)형/간편심사(355)형" (문자열 유지)
→ 이유: 같은 간편심사 계열이라고 판단하여 분리 안 함 (X)

✅ 올바른 분리 (원자 단위):
입력: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
출력: ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형"]
→ 이유: 각각 다른 Condition과 매칭될 수 있으므로 완전 분리 (O)
```

```
✅ 더 많은 예시:
"프리미엄(A)형/프리미엄(B)형/프리미엄(C)형/기본형"
→ ["프리미엄(A)형", "프리미엄(B)형", "프리미엄(C)형", "기본형"]

"1종/2종/3종"
→ ["1종", "2종", "3종"]

"일반형/간편형/표준형"
→ ["일반형", "간편형", "표준형"]
```

**판단 기준**:
- 컬럼명이 "보종명", "유형1", "유형2", "명칭", "종류" 등 → 원자 단위로 완전 분리
- 괄호 안에 구분 코드/숫자가 있음 (315, A, B 등) → 원자 단위로 완전 분리
- VALUE 컬럼 (보험기간, 납입기간 등)은 아래 규칙 2 적용

### 2. VALUE 컬럼: 의미 기반 그룹핑

**핵심 원칙**: 같은 의미 계열은 묶고, 다른 의미 계열은 분리

**예시 1**: 프리미엄 vs 기본
```
입력: "프리미엄A형/프리미엄B형/프리미엄C형/기본형"
출력: ["프리미엄A형/프리미엄B형/프리미엄C형", "기본형"]
이유: 프리미엄 계열 vs 기본형은 의미가 다름

```

**예시 2**: 환급형 vs 무환급형
```
입력: "환급(A)형/환급(B)형/무환급형"
출력: ["환급(A)형/환급(B)형", "무환급형"]
이유: 환급 계열 vs 무환급은 의미가 다름

```

**예시 3**: 독립 값들 (기간, 납입기간 등)
```
입력: "1/3/5년 만기, 종신형"
출력: ["1년 만기", "3년 만기", "5년 만기", "종신형"]
이유: 각 값이 독립적인 옵션

입력: "1/3/5/10년 납입"
출력: ["1년 납입", "3년 납입", "5년 납입", "10년 납입"]
이유: 각 값이 독립적인 옵션

```

**예시 4**: 단일 그룹 (분리 불필요)
```
입력: "표준(A)형/표준(B)형"
출력: "표준(A)형/표준(B)형" (문자열 유지)
이유: 모두 같은 표준 계열

입력: "기본형"
출력: "기본형" (문자열 유지)
이유: 단일 값

```

### 2. 구분자 처리

- **슬래시(/)**와 **쉼표(,)**를 구분자로 인식
- 분리 후 불필요한 공백 제거
- 같은 의미 그룹 내에서는 슬래시(/) 유지

### 3. 단위 처리

분리 시 단위를 각 값에 붙이세요:
- "80/90세" → ["80세", "90세"] (X: ["80", "90세"])
- "10/15년납" → ["10년납", "15년납"] (X: ["10", "15년납"])

---

## 출력 형식

동일한 header와 data 구조를 유지하되, **셀 값만 변경**:

```json
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", ["분리된값1", "분리된값2"], "값3", ...],
    ...
  ],
  "notes": "어떤 셀을 어떻게 분리했는지 간략히 설명"
}}
```

**필드 설명**:
- `header`: 입력과 동일
- `data`: 각 셀은 문자열 또는 리스트
  - 문자열: 분리 불필요한 경우
  - 리스트: 의미 기반으로 분리한 경우
- `notes`: 처리 내용 요약

---

## 예시

### Example 1: Definition 테이블 (카테고리 컬럼)

**Input**:

```
Header: ["상품명", "카테고리"]
Data: [
  ["프리미엄 패키지", "온라인전용/모바일전용/오프라인전용/기본형"]
]
```

**Output**:
```json
{{
  "header": ["상품명", "카테고리"],
  "data": [
    ["프리미엄 패키지", ["온라인전용/모바일전용", "오프라인전용/기본형"]]
  ],
  "notes": "카테고리 컬럼: 온라인/모바일 전용 vs 오프라인/기본형 계열로 분리"
}}
```

Example 2: Condition 테이블 (기간, 옵션)

**Input**:
```
Header: ["플랜", "이용기간", "추가옵션"]
Data: [
  ["스탠다드", "1/3/6개월, 연간", "백업/모니터링/알림"]
]
```

**Output**:
```json
{{
  "header": ["플랜", "이용기간", "추가옵션"],
  "data": [
    [
      "스탠다드",
      ["1개월", "3개월", "6개월", "연간"],
      ["백업", "모니터링", "알림"]
    ]
  ],
  "notes": "이용기간: 4개 독립값 분리, 추가옵션: 3개 독립값 분리"
}}
```

### Example 3: 분리 불필요

**Input**:
```
Header: ["플랜", "설명"]
Data: [
  ["베이직", "기본 기능만 제공"]
]

```

**Output**:
```json
{{
  "header": ["플랜", "설명"],
  "data": [
    ["베이직", "기본 기능만 제공"]
  ],
  "notes": "분리할 multi-value 셀 없음"
}}
```

---

이제 위 규칙에 따라 입력 테이블을 처리하여 JSON으로 반환하세요.
"""
    return prompt

# -----------------------------------------------------------------------------------------------------------
# ----------------------------------------------------기존----------------------------------------------------
# -----------------------------------------------------------------------------------------------------------

def build_table_split_prompt(
    header: List[str],
    data: List[List[str]],
    instruction: str = ""
) -> str:
    """
    테이블 데이터의 multi-value 셀을 의미 기반으로 분리하는 프롬프트 생성 (범용)

    Args:
        header: 테이블 헤더
        data: 테이블 데이터
        instruction: 추가 지시사항 (optional)

    Returns:
        Table Split을 위한 LLM 프롬프트
    """
    # Format table for prompt
    table_str = format_table_for_prompt(header, data, max_rows=50)

    extra_instruction = ""
    if instruction:
        extra_instruction = f"""
**⚠️ 추가 지시사항 (최우선 적용)**:
{instruction}

---

"""

    prompt = f"""
{extra_instruction}

당신은 테이블의 multi-value 셀을 “구분자 기반으로만” 원자 분리하는 작업자입니다.
의미 기반 그룹핑/요약/재해석은 금지합니다.

## 입력 데이터

**테이블**:
```
{table_str}
```

---
0. 형태 보존 + 헤더 표준화 규칙 (최우선)
  - 행(row) 개수, 열(column) 개수, 열의 순서(order)는 절대 바꾸지 마세요.
  - 새로운 컬럼(예: "Index", "RowId") 추가 금지, 행 추가/삭제 금지.
  - 단, header의 “이름”은 표준 스키마로 반드시 변경하세요. (개수/순서는 유지)
  
  헤더 표준 스키마: ["보종명", "유형1", "유형2", ..., "유형K"]
  - 입력 header 중 "상품/특약/담보/보장"의 명칭에 해당하는 컬럼 1개를 골라 그 컬럼명을 **보종명**으로 바꾸세요.
    - 힌트(일반화): header에 명칭/상품명/특약명/담보명/보장명/플랜명/상품(명) 같은 단어가 있으면 그 컬럼이 보종명일 가능성이 큽니다.
    - header만으로 애매하면, data 셀의 값이 “긴 한글 상품명/특약명” 형태인 컬럼을 보종명으로 선택하세요.
  - 나머지 모든 컬럼은 왼쪽부터 순서대로 유형1, 유형2, … 로 이름을 바꾸세요.
  - 이미 보종명, 유형1 같은 표준 이름이 있으면 그 의미를 유지하되, 최종적으로는 전체가 보종명 + 유형K 형태가 되게 맞추세요.
  - note에는 반드시 “어떤 원본 헤더가 어떤 표준 헤더로 바뀌었는지”를 1~2줄로 요약하세요.

  1. 셀 분리 규칙 (일반화 / 안전 split)
  목표: 셀 안에 여러 “항목(option/item)”이 나열된 경우에만 리스트로 분리합니다.
  금지: 의미 기반 재작성/요약/그룹핑은 하지 마세요. (그냥 올바르게 분리만)

  1-1) “구분자 문자”가 아니라 “나열 구분자”만 분리
  다음 문자가 있다고 해서 무조건 분리하지 마세요: /, ,, \n
  대신 아래 조건을 만족할 때만 “나열 구분자(list separator)”로 간주하고 분리하세요.

  - 반복성: 같은 패턴이 셀에서 2회 이상 반복되거나, 명백히 항목 나열 형태임
    형태: 보통 ", "(쉼표+공백), " / "(양쪽 공백), "\n"(줄바꿈 나열)처럼 항목 경계를 나타냄
  - 항목성: 분리했을 때 각 조각이 “독립 항목”처럼 보임(너무 짧은 조각/단독 기호만 남으면 분리하지 않음)
    애매하면 분리하지 말고 원문 문자열 유지가 기본입니다.

  1-2) 괄호/따옴표 내부 보호 (최우선)
  아래 구간 내부에 있는 /, ,, \n은 “내용”일 수 있으므로 절대 분리 기준으로 사용하지 마세요.

  괄호: (...), [...], {{...}}
  따옴표: "...", '...'
  즉, 괄호/따옴표 밖(깊이=0)에서만 나열 구분자를 적용해 분리하세요.

  예시

  입력: 유방암, (A형/B형)피부암, 위암
  출력: ["유방암", "(A형/B형)피부암", "위암"]
  설명: /는 괄호 내부이므로 분리 금지, 실제 나열 구분자는 ", ".
  1-3) 단위/접미어 보존 (분리 후 항목 완결성)
  분리로 인해 단위/접미어가 한쪽에만 남으면 안 됩니다. 각 항목이 완전한 표현이 되도록 보정하세요.

  예: 80/90/100세 만기, 종신 → ["80세 만기","90세 만기","100세 만기","종신"]
  예: S/M/L 사이즈 → ["S 사이즈","M 사이즈","L 사이즈"] (필요한 경우에만)
  1-4) 출력 형태
  분리한 경우: 해당 셀을 문자열 리스트로 변환
  분리 불필요/애매한 경우: 원문 문자열 그대로 유지
  공백 정리: 각 항목의 좌우 공백은 제거하되, 내부 공백은 보존

```json
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", ["분리된값1", "분리된값2"], "값3", ...],
    ...
  ],
  "note": "어떤 셀을 어떻게 분리했는지 간략히 설명"
}}
```

**필드 설명**:
- `header`: 개수/순서는 동일, 이름은 표준화된 header 반환
- `data`: 각 셀은 문자열 또는 리스트
  - 문자열: 분리 불필요한 경우
  - 리스트: 의미 기반으로 분리한 경우
- `note`: 처리 내용 요약

---

## 예시

### Example 1: SaaS 요금제/플랜 테이블

**Input**:

```
{{
  "header": ["플랜명", "배포채널", "청구주기"],
  "data": [
    ["Pro", "web/mobile/desktop", "월/연"],
    ["Enterprise", "web, mobile", "연"]
  ]
}}

```

**Output**:
```json
{{
  "header": ["보종명", "유형1", "유형2"],
  "data": [
    ["Pro", ["web", "mobile", "desktop"], ["월", "연"]],
    ["Enterprise", ["web", "mobile"], "연"]
  ],
  "note": "헤더 표준화: 플랜명→보종명, 배포채널→유형1, 청구주기→유형2. 유형1/유형2는 '/' ',' 기준으로 원자 분리."
}}
```

Example 2: 전자상거래 상품 옵션 테이블

**Input**:
```
{{
  "header": ["상품명", "색상", "사이즈"],
  "data": [
    ["오프화이트 티셔츠", "black/white, navy", "S/M/L"],
    ["러닝화", "red/blue", "260/270/280"]
  ]
}}

```

**Output**:
```json
{{
  "header": ["보종명", "유형1", "유형2"],
  "data": [
    ["오프화이트 티셔츠", ["black", "white", "navy"], ["S", "M", "L"]],
    ["러닝화", ["red", "blue"], ["260", "270", "280"]]
  ],
  "note": "헤더 표준화: 상품명→보종명, 색상→유형1, 사이즈→유형2. '/' ',' 기준으로 원자 분리."
}}
```

---

이제 위 규칙에 따라 입력 테이블을 처리하여 JSON으로 반환하세요.
"""
    return prompt


# -----------------------------------------------------------------------------------------------------------
# ----------------------------------------------------기존----------------------------------------------------
# -----------------------------------------------------------------------------------------------------------

def build_table_split_prompt_2(
    header: List[str],
    data: List[List[str]],
    instruction: str = ""
) -> str:
    """
    테이블 데이터의 multi-value 셀을 의미 기반으로 분리하는 프롬프트 생성 (범용)

    Args:
        header: 테이블 헤더
        data: 테이블 데이터
        instruction: 추가 지시사항 (optional)

    Returns:
        Table Split을 위한 LLM 프롬프트
    """
    # Format table for prompt
    table_str = format_table_for_prompt(header, data, max_rows=50)

    extra_instruction = ""
    if instruction:
        extra_instruction = f"""
**⚠️ 추가 지시사항 (최우선 적용)**:
{instruction}

---

"""

    prompt = f"""
{extra_instruction}당신은 테이블 데이터의 multi-value 셀을 의미 기반으로 분리하는 전문가입니다.

## 입력 데이터

**테이블**:
```
{table_str}
```

---

## 작업 목표

셀에 여러 값이 구분자(/, ,)로 나뉘어 있을 때, **의미적으로 다른 그룹**을 리스트로 분리하세요.

---

## 분리 규칙

### 0. 형태 보존 규칙 (매우 중요)

- 헤더(header)의 컬럼 개수와 순서는 절대로 바꾸지 마세요.
- 새로운 컬럼(예: "Index", "RowId" 등)을 추가하지 마세요.
- 새로운 행(row)을 추가하거나 기존 행을 삭제하지 마세요.
- **각 셀의 값만** 분리하거나 리스트로 바꿀 수 있습니다.
  - 예: "A유형/B유형" → ["A유형", "B유형"]
  - 예: "80/90/100세 만기, 종신" → ["80세 만기", "90세 만기", "100세 만기", "종신"]
- 즉, index와 같은 새로운 값을 만들지 말고, 기존 데이터만 활용해 변환하세요.

### 1. ⚠️ JOIN KEY 컬럼 특별 규칙 (최우선 적용!)

**JOIN KEY 컬럼이란?**: 나중에 Condition 테이블과 매칭될 핵심 식별자
- 예: "보종명", "명칭", "유형1", "유형2", "보험종목", "보험종목_1", "심사형" 등
- **특징**: 괄호 안에 숫자/코드가 있는 경우가 많음 (예: "간편심사(315)형", "프리미엄(A)형")

**핵심 원칙**: JOIN KEY 컬럼은 **원자 단위까지 완전히 분리**

**예시**:
```
❌ 잘못된 분리 (그룹핑):
입력: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
출력: "간편심사(315)형/간편심사(335)형/간편심사(355)형" (문자열 유지)
→ 이유: 같은 간편심사 계열이라고 판단하여 분리 안 함 (X)

✅ 올바른 분리 (원자 단위):
입력: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
출력: ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형"]
→ 이유: 각각 다른 Condition과 매칭될 수 있으므로 완전 분리 (O)
```

```
✅ 더 많은 예시:
"프리미엄(A)형/프리미엄(B)형/프리미엄(C)형/기본형"
→ ["프리미엄(A)형", "프리미엄(B)형", "프리미엄(C)형", "기본형"]

"1종/2종/3종"
→ ["1종", "2종", "3종"]

"일반형/간편형/표준형"
→ ["일반형", "간편형", "표준형"]
```

**판단 기준**:
- 컬럼명이 "보종명", "유형1", "유형2", "명칭", "종류" 등 → 원자 단위로 완전 분리
- 괄호 안에 구분 코드/숫자가 있음 (315, A, B 등) → 원자 단위로 완전 분리
- VALUE 컬럼 (보험기간, 납입기간 등)은 아래 규칙 2 적용

### 2. VALUE 컬럼: 의미 기반 그룹핑

**핵심 원칙**: 같은 의미 계열은 묶고, 다른 의미 계열은 분리

**예시 1**: 프리미엄 vs 기본
```
입력: "프리미엄A형/프리미엄B형/프리미엄C형/기본형"
출력: ["프리미엄A형/프리미엄B형/프리미엄C형", "기본형"]
이유: 프리미엄 계열 vs 기본형은 의미가 다름

```

**예시 2**: 환급형 vs 무환급형
```
입력: "환급(A)형/환급(B)형/무환급형"
출력: ["환급(A)형/환급(B)형", "무환급형"]
이유: 환급 계열 vs 무환급은 의미가 다름

```

**예시 3**: 독립 값들 (기간, 납입기간 등)
```
입력: "1/3/5년 만기, 종신형"
출력: ["1년 만기", "3년 만기", "5년 만기", "종신형"]
이유: 각 값이 독립적인 옵션

입력: "1/3/5/10년 납입"
출력: ["1년 납입", "3년 납입", "5년 납입", "10년 납입"]
이유: 각 값이 독립적인 옵션

```

**예시 4**: 단일 그룹 (분리 불필요)
```
입력: "표준(A)형/표준(B)형"
출력: "표준(A)형/표준(B)형" (문자열 유지)
이유: 모두 같은 표준 계열

입력: "기본형"
출력: "기본형" (문자열 유지)
이유: 단일 값

```

### 2. 구분자 처리

- **슬래시(/)**와 **쉼표(,)**를 구분자로 인식
- 분리 후 불필요한 공백 제거
- 같은 의미 그룹 내에서는 슬래시(/) 유지

### 3. 단위 처리

분리 시 단위를 각 값에 붙이세요:
- "80/90세" → ["80세", "90세"] (X: ["80", "90세"])
- "10/15년납" → ["10년납", "15년납"] (X: ["10", "15년납"])

---

## 출력 형식

동일한 header와 data 구조를 유지하되, **셀 값만 변경**:

```json
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", ["분리된값1", "분리된값2"], "값3", ...],
    ...
  ],
  "notes": "어떤 셀을 어떻게 분리했는지 간략히 설명"
}}
```

**필드 설명**:
- `header`: 입력과 동일
- `data`: 각 셀은 문자열 또는 리스트
  - 문자열: 분리 불필요한 경우
  - 리스트: 의미 기반으로 분리한 경우
- `notes`: 처리 내용 요약

---

## 예시

### Example 1: Definition 테이블 (카테고리 컬럼)

**Input**:

```
Header: ["상품명", "카테고리"]
Data: [
  ["프리미엄 패키지", "온라인전용/모바일전용/오프라인전용/기본형"]
]
```

**Output**:
```json
{{
  "header": ["상품명", "카테고리"],
  "data": [
    ["프리미엄 패키지", ["온라인전용/모바일전용", "오프라인전용/기본형"]]
  ],
  "notes": "카테고리 컬럼: 온라인/모바일 전용 vs 오프라인/기본형 계열로 분리"
}}
```

Example 2: Condition 테이블 (기간, 옵션)

**Input**:
```
Header: ["플랜", "이용기간", "추가옵션"]
Data: [
  ["스탠다드", "1/3/6개월, 연간", "백업/모니터링/알림"]
]
```

**Output**:
```json
{{
  "header": ["플랜", "이용기간", "추가옵션"],
  "data": [
    [
      "스탠다드",
      ["1개월", "3개월", "6개월", "연간"],
      ["백업", "모니터링", "알림"]
    ]
  ],
  "notes": "이용기간: 4개 독립값 분리, 추가옵션: 3개 독립값 분리"
}}
```

### Example 3: 분리 불필요

**Input**:
```
Header: ["플랜", "설명"]
Data: [
  ["베이직", "기본 기능만 제공"]
]

```

**Output**:
```json
{{
  "header": ["플랜", "설명"],
  "data": [
    ["베이직", "기본 기능만 제공"]
  ],
  "notes": "분리할 multi-value 셀 없음"
}}
```

---

이제 위 규칙에 따라 입력 테이블을 처리하여 JSON으로 반환하세요.
"""
    return prompt



def build_condition_transform_prompt(
    header: List[str],
    data: List[List[str]],
    instruction: str = ""
) -> str:
    """
    Condition 데이터를 최종 스키마로 변환하는 프롬프트 생성

    Args:
        header: 원본 Condition 테이블 헤더
        data: 원본 Condition 테이블 데이터
        instruction: 추가 지시사항 (optional)

    Returns:
        Condition Transform을 위한 LLM 프롬프트
    """
    # Format table for prompt
    table_str = format_table_for_prompt(header, data, max_rows=50)

    extra_instruction = ""
    if instruction:
        extra_instruction = f"""
**⚠️ 최우선 지시사항 (반드시 적용)**:
{instruction}

---

"""

    prompt = f"""
{extra_instruction}당신은 보험 조건 데이터를 최종 스키마로 변환하는 전문가입니다.

## 입력 데이터

**원본 Condition 테이블**:
```
{table_str}
```

---

## 작업 목표

원본 Condition 테이블을 최종 스키마로 변환하세요:
- 독립값들을 리스트로 분리
- 가입나이를 최소/최대로 분리 (수식은 절대 계산 금지!)
- 컬럼명 변환 및 코드 생성
- 성별 정보 추출

---

## 변환 규칙

### 1. 독립값 리스트 분리

보험기간, 납입기간처럼 독립적인 옵션들을 리스트로 분리하세요.

**예시**:
- "80/90/100세 만기, 종신" → ["80세 만기", "90세 만기", "100세 만기", "종신"]
- "10/15/20/25/30년납" → ["10년납", "15년납", "20년납", "25년납", "30년납"]
- "월납" → ["월납"] (단일값도 리스트)

**주의**:
- 각 값은 독립적인 옵션입니다
- 쉼표(,)와 슬래시(/)를 모두 구분자로 인식
- 불필요한 공백 제거

### 2. 가입나이 파싱 및 분리

- 입력 최대가입연령(또는 가입나이_남/여)에 줄바꿈(\n)으로 구분된 여러 개의 수식이 있으면,
  최대가입연령 필드에 **원문 그대로 줄바꿈 포함하여 모두 보존**하세요. (한 줄만 선택/삭제 금지)


가입나이 컬럼을 분석하여 최소/최대 연령으로 분리하세요.

**예시**:
입력: "가입나이_남": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세"

출력:
- 최소: "만 15세" (공백 정규화, **계산 X**)
- 최대: "min[세만기 - 년납, 90 - 년납, 70] 세" (수식 그대로, **계산 절대 금지**)


**🔴 중요 🔴**:
- 수식(min[], max[] 등)은 **절대 계산하지 마세요**!
- 수식은 문자열로 그대로 보존
- 최소 연령에서 "만"이 있으면 공백 추가 ("만15세" → "만 15세")

### 3. 연령구분코드 생성

연령 값을 보고 연령구분코드를 생성하세요.

**규칙**:
- 최소 연령에 "만" 포함 → 최소가입연령구분코드 = "(2)만연령"
- 최소 연령에 "만" 미포함 → 최소가입연령구분코드 = "(1)보험연령"
- 최대 연령에 "만" 포함 → 최대가입연령구분코드 = "(2)만연령"
- 최대 연령에 "만" 미포함 (수식 포함) → 최대가입연령구분코드 = "(1)보험연령"

- 최대가입연령구분코드는 최대가입연령 문자열 전체(여러 줄 포함)에서 "만"이 한번이라도 나오면 "(2)만연령",
  그렇지 않으면 "(1)보험연령"으로 설정하세요.


**예시**:
- "만 15세" → "(2)만연령"
- "min[세만기 - 년납, 70] 세" → "(1)보험연령" (만이 없음)

### 4. 성별 추출

컬럼명에서 성별 정보를 추출하여 리스트로 생성하세요.

**규칙**:
- 남성에 대한 가입나이와 여성에 대한 가입나이 둘 다 존재 → ["(1)남자", "(2)여자"]
- 남성에 대한 가입나이만 존재 → ["(1)남자"]
- 여성에 대한 가입나이만 존재 → ["(2)여자"]
- 둘 다 없으면 → ["-"] (기본값)

### 5. 컬럼명 변환

최종 스키마 컬럼명으로 변환하세요.

**매핑**:
- 원본 컬럼 유지: "유형1", "유형2", "유형3" 등
- "보험기간" → "보험기간" (리스트)
- "납입기간" → "납입기간" (리스트)
-  가입나이  → 다음 5개 컬럼으로 분리:
  - "주피보험자최소가입연령" (문자열)
  - "주피보험자최대가입연령" (문자열 또는 수식)
  - "주피보험자최소가입연령구분코드" (코드)
  - "주피보험자최대가입연령구분코드" (코드)
  - "주피보험자가입성별" (리스트)
- "납입주기" → "납입주기" (리스트로 변환, 필요시)

---

## 출력 형식

다음 JSON 형식으로 변환된 데이터를 반환하세요:

```json
{{
  "header": [
    "보종명",
    "유형1",
    "유형2",
    "보험기간",
    "납입기간",
    "주피보험자최소가입연령",
    "주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드",
    "주피보험자최대가입연령구분코드",
    "주피보험자가입성별"
  ],
  "data": [
    [
      "해약환급금 미지급형",
      "간편심사형",
      "-",
      ["80세 만기", "90세 만기", "100세 만기", "종신"],
      ["10년납", "15년납", "20년납", "25년납", "30년납"],
      "만 15세",
      "min[세만기 - 년납, 90 - 년납, 70] 세",
      "(2)만연령",
      "(1)보험연령",
      ["(1)남자", "(2)여자"]
    ]
  ],
  "notes": "변환 과정 설명 (선택)"
}}
```

**필드 설명**:
- `header`: 최종 스키마 컬럼명 (위 순서 유지)
- `data`: 변환된 데이터
  - 리스트 타입: 보험기간, 납입기간, 주피보험자가입성별
  - 문자열 타입: 최소/최대 가입연령 (수식 포함 가능)
  - 코드 타입: 연령구분코드
- `notes`: (선택) 변환 과정의 특이사항 설명

---

## 예시

### Example 1: 남녀 모두 있는 경우

**Input**:
```
Header: ["유형1", "유형2", "가입나이_남", "가입나이_여", "보험기간", "납입기간"]
Data: [
  ["해약환급금 미지급형",
   "간편심사형", 
   "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세\n만15세 - min[100 - 년만기, 90 - 년납, 80] 세",
   "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세\n만15세 - min[100 - 년만기, 90 - 년납, 80] 세", 
   "80/90/100세 만기, 종신", 
   "10/15/20/25/30년납"]
]
```

**Output**:
```json
{{
  "header": ["유형1", "유형2", "유형3", "보험기간", "납입기간",
             "주피보험자최소가입연령", "주피보험자최대가입연령",
             "주피보험자최소가입연령구분코드", "주피보험자최대가입연령구분코드",
             "주피보험자가입성별"],
  "data": [
    [
      "해약환급금 미지급형",
      "간편심사형",
      "-",
      ["80세 만기", "90세 만기", "100세 만기", "종신"],
      ["10년납", "15년납", "20년납", "25년납", "30년납"],
      "만 15세",
      "min[세만기 - 년납, 90 - 년납, 80] 세\nmin[100 - 년만기, 90 - 년납, 80] 세",
      "(2)만연령",
      "(1)보험연령",
      ["(1)남자", "(2)여자"]
    ]
  ]
}}
```

### Example 2: 단순 연령 (수식 없음)

**Input**:
```
가입나이: "만15세 - 만70세"
```

**Output**:
```
최소: "만 15세"
최대: "만 70세"
최소코드: "(2)만연령"
최대코드: "(2)만연령"
```

---

## 주의사항

1. **수식 계산 금지**: min[], max[] 등의 수식은 절대 계산하지 마세요. 문자열로 보존하세요.
2. **리스트 형식 유지**: 단일값도 리스트로 변환하세요 (예: "월납" → ["월납"])
3. **컬럼 순서**: header의 순서를 정확히 유지하세요
4. **데이터 정합성**: 모든 data 행은 header와 같은 개수의 요소를 가져야 합니다
5. **공백 정리**: 불필요한 공백은 제거하되, "만 15세"처럼 의미 있는 공백은 유지하세요

---

이제 위 규칙에 따라 Condition 테이블을 변환하여 JSON으로 반환하세요.
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
    json_plan = """
{
  "total_tasks": 5,
  "tasks": [
    {
      "task_id": "task0",
      "task_type": "classify_sections",
      "tool_name": "section_classifier",
      "fallback_tool": null,
      "parameters": {{
        "sections": "$sections"
      }},
      "dependencies": [],
      "output_key": "classification_result"
    },
    {
      "task_id": "task1",
      "task_type": "extract_definitions",
      "tool_name": "definition_extract_v2",
      "fallback_tool": null,
      "parameters": {{
        "sections": "$sections",
        "core_indices": "{{{{task0.data.definition_core}}}}",
        "annotation_indices": "{{{{task0.data.definition_annotation}}}}"
      }},
      "dependencies": ["task0"],
      "output_key": "extraction_result"
    }
  ],
  "reasoning": "문서 구조와 도구 선택 근거 요약"
}

"""
    prompt = f"""
{extra_instruction}당신은 보험 상품 문서를 분석하여 최적의 실행 계획을 세우는 전문가입니다.

## 입력 문서 요약
{doc_summary_json}

## 입력 문서 샘플
{doc_sample[:2000]}... (총 {len(doc_sample)}자)

## 목표
{goal}
문서 복잡도에 따라 **3~7개의 작업**으로 구성된 실행 계획을 작성하세요.

## 사용 가능 도구 (tool_name 목록)
- section_classifier
- definition_extract_v2
- normalize_definitions
- normalize_conditions
- rule_cartesian
- llm_cartesian
- condition_extract
- grouping_logic_extractor
- combination_generator


## 계획 수립 가이드라인
- **최종 목표**: '정의'와 '조건' 섹션을 모두 추출하고, 이 둘을 정규화한 뒤, 그룹핑 로직을 통해 최종 조합을 생성해야 합니다.
- **단순 문서**: `extract_definitions` → `normalize_definitions` → `rule_cartesian` → (필요 시 `llm_cartesian`)
- **일반 문서**: `extract_definitions` → `normalize_definitions` → `extract_conditions` → `normalize_conditions` → `grouping_logic_extractor` → `combination_generator`
- **복잡 문서**: `classify_sections` 추가 후 위 '일반 문서' 흐름 따름.

## 출력 형식 (JSON)

{json_plan}

## 중요 규칙
1) **dependencies**: 이전 task_id만 참조 (순환 참조 금지)
2) **이전 결과 참조**: `"{{"{{taskN.data.필드명}}}}"`형식 사용 (.data 필수! 예: `"{{"{{task0.data.definition_core}}}}"`) 
3) **State 참조**: `$sections`
4) **종료 조건**: '조건' 추출, '그룹핑', '최종 조합' 단계 중 **미수행된 단계가 있다면 절대 `END` 하지 마세요.** 최종 결과까지 모든 단계가 완료되어야 합니다.

위 규칙에 따라 JSON만 반환하세요.
"""
    return prompt


def build_next_task_prompt(
    doc_summary: dict,
    goal: str,
    task_results: list,
    tool_schemas: str,
    instruction: str = "", # instruction 추가
    last_feedback: dict | None = None,
    last_task: dict | None = None,
) -> str:
    """
    PROTOTYPE 7 v2: Build prompt for generating next single task.

    Called after each task execution to decide the next step.

    Args:
        doc_summary: Document summary from DocumentAccessor
        goal: User's overall goal
        task_results: List of completed task results
        tool_schemas: Available tools and their schemas

    Returns:
        Prompt string for LLM
    """
    doc_summary_json = json.dumps(doc_summary, ensure_ascii=False, indent=2)

    # Build task history summary (limit to recent tasks to prevent token explosion)
    MAX_HISTORY_TASKS = 10  # Only include last 10 tasks
    recent_tasks = task_results[-MAX_HISTORY_TASKS:] if len(task_results) > MAX_HISTORY_TASKS else task_results

    task_history = []
    for result in recent_tasks:
        task_history.append({
            "task_id": result.get("task_id"),
            "tool_used": result.get("tool_used"),
            "success": result.get("success"),
            "data_keys": list(result.get("data", {}).keys()) if isinstance(result.get("data"), dict) else "non-dict"
        })

    # Add summary if we truncated
    history_note = ""
    if len(task_results) > MAX_HISTORY_TASKS:
        history_note = f"\n(Showing last {MAX_HISTORY_TASKS} of {len(task_results)} total tasks)\n"

    task_history_json = history_note + json.dumps(task_history, ensure_ascii=False, indent=2)

    # FIX: Calculate successful tasks count for clear prompting
    num_successful_tasks = sum(1 for r in task_results if r.get("success"))
    num_total_tasks = len(task_results)
    # 직전 task / 검증 결과를 요약해서 넣기
    if last_task:
        last_task_brief = {
            "task_id": last_task.get("task_id"),
            "task_type": last_task.get("task_type"),
            "tool_name": last_task.get("tool_name"),
        }
    else:
        last_task_brief = None
    last_task_json = json.dumps(last_task_brief, ensure_ascii=False, indent=2) if last_task_brief else "null"
    last_feedback_json = json.dumps(last_feedback or {}, ensure_ascii=False, indent=2)

    # FIX: next_task_id is sequential (based on total tasks, not just successful ones)
    next_task_id = f"task{num_total_tasks}"
    prev_task_id = f"task{num_total_tasks-1}" if task_results else "none"

    extra_instruction = ""
    if instruction:
        extra_instruction = (
            f"""\n**추가 지시사항 (반드시 반영)**:\n{instruction}\n\n---\n\n"""
        )
    print(f'task_history_json : {task_history_json}')
    print('-'*20)
    print(f'last_task_json : {last_task_json}')
    print('-'*20)
    print(f'last_feedback_json : {last_feedback_json}')
    print('-'*20)
    prompt = f"""
{extra_instruction}
당신은 보험 상품 문서 처리 작업을 **단계별로 계획하는** 전문가입니다.

## 목표
{goal}

## 문서 요약
{doc_summary_json}

## 지금까지 성공한 작업 ({num_successful_tasks}개) / 전체 작업 ({num_total_tasks}개)
{task_history_json if task_results else "[]"}

## 직전 작업 메타 (backtracking 시 null일 수 있음)
{last_task_json}

## 직전 검증 결과 (last_validation_feedback)
{last_feedback_json}

**주의**: last_validation_feedback에 `root_cause_task_id` 필드가 있으면, 이는 실패의 근본 원인이 되는 task를 가리킵니다.

## 사용 가능한 도구
{tool_schemas}

## 당신의 임무

**다음 작업 1개**를 결정하세요:

### Option 1: 다음 작업 생성
```json
{{
  "action": "next_task",
  "task": {{
    "task_id": "{next_task_id}",  // 자동으로 생성됨 (task0, task1, task2, ...)
    "task_type": "작업 타입",  // 위 규칙 6번에 따라 결정 (성공한 작업 개수 기준)
    "description": "이 작업이 하는 일",
    "tool_name": "사용할 도구명",
    "fallback_tool": null,
    "parameters": {{
      "sections": "$sections",
      "field": "{{"{{taskN.data.field_name}}}}"
    }},
    "dependencies": ["{prev_task_id}"],  // 성공한 이전 task들만
    "output_key": "result_key_name"
  }},
  "reasoning": "왜 이 작업이 필요한가"
}}
```

### Option 2: 모든 작업 완료
```json
{{
  "action": "end",
  "reasoning": "목표 달성 완료"
}}
```

## 매우 중요: 다음 Task 결정 규칙

[CRITICAL RETRY/BACKTRACK RULE]
- last_feedback_json.is_valid == false 이면 절대 다음 stage로 넘어가지 말 것.
- 먼저 last_feedback_json.root_cause_task_id를 확인할 것.

Case A) root_cause_task_id가 존재하고, 직전 task_id와 다름:
- 백트래킹 상황이다.
- 다음 next_task는 root_cause_task_id에 해당하는 task를 다시 수행하도록 계획할 것
  (직전 task 재시도 금지)

Case B) root_cause_task_id가 없거나(null), 또는 직전 task_id와 같음:
- 직전 task 자체 문제다.
- 다음 next_task는 반드시 직전 task를 같은 task_id/같은 task_type으로 재시도할 것
  (다음 stage로 진행 금지)

**추가 지시사항이 있는 경우 (맨 위에 표시됨):**
- `[BACKTRACK]`로 시작하는 instruction이 있으면, 그 지시를 따르세요.
- Backtracking 시 "직전 작업 메타"는 null이므로, **task_history의 성공한 작업 개수만 보고 판단**하세요.

**실패한 작업을 재시도하는 경우:**
1. 직전 검증 결과가 `is_valid == false`이고
2. `직전 작업 메타`가 null이 아니고
3. task_history에서 해당 작업이 `success == false`이면

   → **같은 task_type으로 재시도**하되, validation feedback의 suggestions를 반영하세요.

   예시:
   - task_history: [..., {{"task_id": "task3", "success": false, ...}}]
   - 직전 작업 메타: {{"task_id": "task3", "task_type": "condition_extraction"}}
   - last_validation_feedback: {{"is_valid": false, "errors": [...], "suggestions": [...]}}
   - → 다음 task: task_type="condition_extraction" (재시도), suggestions 반영

**정상 진행 (다음 단계로):**
- task_history에서 **성공한 작업 개수(success=true)를 세어**, 규칙 6번에 따라 다음 task_type을 결정하세요.
- 예: 성공한 작업이 2개 → 다음 task_type = "table_split"

**중요:**
- 실패한 작업의 output을 사용하는 downstream task를 절대 만들지 마세요.
  (예: grouping이 실패했는데 combination_generation을 만드는 것 금지)


## 중요 규칙

1. **이전 결과 참조**: 위 task_history의 data_keys를 보고 실제 필드명 사용
   - 예: task0의 data_keys가 ["definition_core", "condition"]이면
   - `"{{"{{task0.data.definition_core}}}}"`
2. **State 참조**: `$sections`
3. **Dependencies**: 이전 완료된 task_id들만
   - 첫 번째 작업: `"dependencies": []` (빈 리스트)
   - 의존성 있는 작업: `"dependencies": ["task0", "task1"]`
   - ❌ 절대 "none"이나 null 사용 금지
4. **종료 조건**: '조건' 추출, '그룹핑', '최종 조합' 단계 중 **미수행된 단계가 있다면 절대 `END` 하지 마세요.** 최종 결과까지 모든 단계가 완료되어야 합니다.
    - 중요 : combination_generation의 “마지막 validation이 is_valid=true”가 아니면 END 금지
5. task_type 는 다음 값 중 하나여야 한다:

- "classify_sections"        # 섹션 분류 (section_classifier)
- "extract_definitions"      # 정의 추출 (definition_extract_v2)
- "table_split"              # Definition 테이블 셀 분리 (llm_table_split)
- "condition_extraction"     # 조건 추출 (condition_extract)
- "condition_transform"      # Condition 테이블 변환 (condition_transform)
- "grouping"                 # 그룹핑 로직 추출 (grouping_logic_extractor)
- "combination_generation"   # 최종 조합 생성 (combination_generator)
  task_type은 반드시 위의 문자열 중 하나만 사용하라. 한국어나 다른 문구 금지
  description은 자유롭게 써도 되지만, task_type은 절대 바꾸지 말라.

6. task 순서는 고정되어야 합니다 (backtracking/재시도 제외).

   **성공한 작업 개수(success=true인 task 개수)**에 따라 다음 task_type은 다음 중 하나만 허용됩니다:

   - 성공한 작업이 0개일 때 → 다음 task_type = "classify_sections"
   - 성공한 작업이 1개일 때 → 다음 task_type = "extract_definitions"
   - 성공한 작업이 2개일 때 → 다음 task_type = "table_split"
   - 성공한 작업이 3개일 때 → 다음 task_type = "condition_extraction"
   - 성공한 작업이 4개일 때 → 다음 task_type = "condition_transform"
   - 성공한 작업이 5개일 때 → 다음 task_type = "grouping"
   - 성공한 작업이 6개일 때 → 다음 task_type = "combination_generation"

   위 표에서 task_history를 보고 success=true인 task 개수를 세어 다음 task_type을 결정하세요.
   위 순서를 건너뛰거나, 역순으로 실행하거나, 다른 task_type을 끼워 넣으면 안 됩니다
   (단, 검증 실패로 인한 backtracking/재시도인 경우는 예외입니다).


  
  JSON만 반환하세요.
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
3. 주석 행(\"※\", \"주:\", \"*\")이 데이터로 잘못 포함되지 않음
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
- 각 그룹에 definition_indices, condition_indices 존재

**검증 항목**:
1. 필수 키 존재 (groups, column_mapping)
2. 인덱스 범위 검증 (definition_indices, condition_indices)
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


def build_validate_grouping_logic_llm_prompt(
    definition_header: List[str],
    condition_header: List[str],
    groups_detail: List[Dict[str, Any]],
    unmatched_defs: List[Dict[str, Any]],
    unmatched_conds: List[Dict[str, Any]],
    column_mapping: Dict[str, Any],
    summary: Dict[str, Any]
) -> str:
    """
    Build prompt for LLM-based grouping logic validation.

    Validates semantic consistency of grouping logic.

    Args:
        definition_header: Definition table column names
        condition_header: Condition table column names
        groups_detail: Detailed group information with actual row data
        unmatched_defs: Unmatched definition rows
        column_mapping: JOIN keys and value columns
        summary: Summary statistics

    Returns:
        Prompt string for LLM validation
    """
    # Format headers
    def_header_str = ", ".join(definition_header)
    cond_header_str = ", ".join(condition_header)
    

    # Format groups
    groups_str = ""
    for group in groups_detail:
        group_id = group.get("id")
        matched = group.get("matched_list_items")
        join_mappings = group.get("join_mappings", [])
        def_rows = group.get("definition_rows", [])
        cond_rows = group.get("condition_row") or []

        if cond_rows:
            groups_str += f"\n**Condition Rows ({len(cond_rows)}):**\n"
            for cr in cond_rows:
                groups_str += f"  - row{cr['index']}: {json.dumps(cr['data'], ensure_ascii=False)}\n"
        else:
            groups_str += f"\n**Condition Rows:** None (unmatched)\n"


        groups_str += f"\n### Group {group_id}\n"
        groups_str += f"**Join Mappings**: {json.dumps(join_mappings, ensure_ascii=False)}\n\n"
        groups_str += f"**Matched List Items**: {json.dumps(matched, ensure_ascii=False)}\n"

        groups_str += f"**Definition Rows ({len(def_rows)}):**\n"
        for dr in def_rows:
            groups_str += f"  - row{dr.get('index')}: {json.dumps(dr.get('data'), ensure_ascii=False)}\n"

        # ✅ Condition rows (multi-row 지원)
        if cond_rows:
            groups_str += f"\n**Condition Rows:**\n"

            # cond_rows가 dict면 list로 통일
            if isinstance(cond_rows, dict):
                cond_rows = [cond_rows]

            for cr in cond_rows:
                groups_str += f"  - row{cr.get('index')}: {json.dumps(cr.get('data'), ensure_ascii=False)}\n"
        else:
            groups_str += f"\n**Condition Rows:** None (unmatched)\n"


    # Format unmatched
    unmatched_str = ""
    if unmatched_defs:
        unmatched_str = "\n### Unmatched Definitions\n"
        for ud in unmatched_defs:
            unmatched_str += f"  - row{ud['index']}: {json.dumps(ud['data'], ensure_ascii=False)}\n"
    else:
        unmatched_str = "\n### Unmatched Definitions\nNone - all definitions matched.\n"

    unmatched_con_str = ""
    if unmatched_conds:
        unmatched_con_str = "\n### Unmatched Conditions\n"
        for ud in unmatched_conds:
            unmatched_con_str += f"  - row{ud['index']}: {json.dumps(ud['data'], ensure_ascii=False)}\n"
    else:
        unmatched_con_str = "\n### Unmatched Conditions\nNone - all Conditions matched.\n"

    # Format column mapping
    join_keys = column_mapping.get("join_keys", [])
    value_columns = column_mapping.get("value_columns", [])
    mapping_str = f"**JOIN Keys**: {join_keys}\n**Value Columns**: {value_columns}"

    # Format summary
    def_coverage = summary.get("coverage_ratio", 0.0)
    def_matched = summary.get("matched_definition_count", 0)
    def_total = summary.get("total_definitions", 0)

    cond_matched = summary.get("matched_condition_count", None)
    cond_total = summary.get("total_conditions", None)
    cond_coverage = None
    if cond_matched is not None and cond_total not in (None, 0):
        cond_coverage = cond_matched / cond_total

    summary_str = f"Definition Coverage: {def_matched}/{def_total} ({def_coverage:.1%})"
    if cond_coverage is not None:
        summary_str += f"\nCondition Coverage: {cond_matched}/{cond_total} ({cond_coverage:.1%})"

    output_schema = """
    {
      "is_valid": true,
      "confidence": 0.0,
      "errors": [],
      "suggestions": [],
      "reasoning": "",
      "root_cause_task_id": null
    }
    """
    prompt = f"""
당신은 보험 상품 정의(Definition)와 가입 조건(Condition)을 그룹핑하는 로직의
**논리적 일관성**을 검증하는 전문가입니다.

### 핵심 원칙

- 목표: Definition/Condition 매칭이 **논리적으로 말이 되는지** 검증하고,
  **제공된 데이터로 근거(인덱스/행)가 확인되는 경우에만** is_valid=false 를 사용합니다.
- fuzzy matching, 표기 차이, multi-value 셀은 넉넉하게 허용합니다.
- is_valid=false 를 사용할 수 있는 대표 케이스는 아래 2가지뿐입니다(추측 금지, 증거 필수):
  1) 단일값 join_key가 정규화/퍼지 규칙(4.1)을 적용해도 전혀 match되지 않는 경우
     (증거: group_id + definition_rows.index/condition_row.index 제시)
  2) 특정 join_key 조합이 Condition에 **명시적으로 존재**하고, Definition에도 존재하는데,
     그 조합이 어떤 그룹에도 매칭되지 않은 것이 **인덱스로 확인**되는 경우
     (증거: 해당 condition row index + definition row index 제시)


## 데이터 구조

### Definition Table
- **Header**: {def_header_str}

### Condition Table
- **Header**: {cond_header_str}

### Column Mapping
{mapping_str}

## Grouping Logic 결과

{groups_str}

{unmatched_str}
{unmatched_con_str}

### Summary
{summary_str}

---
4. 검증 기준 (CRITICAL / 규칙만)
4.0 출력 강제 규칙 (최우선)
- 당신은 “검증기”입니다. 추측/상상/상식으로 errors를 만들지 마세요.
- errors에 항목을 추가하려면 반드시 아래 증거 중 하나를 포함해야 합니다(인덱스 필수):
  - group_id, condition_row.index, definition_rows의 row index 목록
  - unmatched_conds의 row index
  - unmatched_defs의 row index
- 위 증거를 제시할 수 없으면:
  - errors에는 쓰지 말고 suggestions에만 적고, is_valid=true를 유지하세요.
- errors에서 금지 표현: “명백히 있어야”, “가능성이 높다”, “상식적으로”.

---

4.1 문자열 동일성/유사성 판단 (정규화 후 비교)
모든 비교는 아래 정규화 후 수행합니다.

정규화 규칙:

- 양끝 공백 제거, 연속 공백 1칸으로 축약
- 모든 공백 제거 버전도 함께 비교(공백 깨짐 대응)
- 괄호 접미는 “동일 범주”로 허용: X ↔ X(전환형) ↔ X(간편) ↔ X(TC) 등
- 특수문자 제거 버전도 함께 비교(·, -, /, 괄호 등)

match로 간주(하나라도 만족하면 match):
- 정규화 후 정확 일치
- 한쪽이 다른쪽을 포함(substring)
- 괄호 내용 제거 후 일치
- 공백/특수문자 제거 후 일치

예시(모두 정상 match):
- 적립형 계약 ↔ 적립형 계약(전환형)
- 적립형 계약 ↔ 적립형 계 약(전환형)
- 치매간병전환형 계약 ↔ 치매간병전환형 계약(전환형)

---

4.2 와일드카드/미기재 처리 (매우 중요)
다음 값들은 **ANY로 단정하지 말고 기본적으로 “비교 제외(unknown/omitted)”**로 처리합니다:

- "-", "—", "", null, "해당없음", "미기재"
검증 규칙:

- join_mappings의 value가 위 값이면 → 해당 매핑은 검증에서 제외(그것으로 모순 판정 금지)
- condition_row의 컬럼 값이 위 값이어도 → 오류로 보지 않음
- "-" 자체만으로 is_valid=false를 주지 마세요.

---

4.3 그룹 내부 정합성 (핵심)
각 그룹 g에 대해:

(1) join_mappings vs definition_rows

- 각 join_mapping {{def_col, cond_col, value}}에 대해:
  - value가 와일드카드/미기재가 아니라면
  - definition_rows의 def_col 컬럼 값이 value와 4.1 규칙으로 match되어야 합니다
- 하나라도 "정규화 후에도 전혀 match되지 않으면" 오류 후보입니다. (증거 인덱스 포함 필수)

(2) join_mappings vs condition_row

- 각 join_mapping {{def_col, cond_col, value}}에 대해:
  - condition_row의 cond_col 컬럼 값이 value와 일치하는지 검사합니다
  - value가 와일드카드/미기재면 해당 매핑은 검사에서 제외합니다

(3) 다중값(any-match) 규칙

- definition 또는 condition 값이 리스트이거나 "A/B/C" 형태라면:
  - 요소 중 하나라도 match되면 정상입니다.
  - "다른 값이 함께 있다"는 이유만으로 오류로 보지 마세요.

---

4.4 unmatched_defs 처리 (기본 정상)
- unmatched_defs(Definition에만 있고 Condition에 없는 조합)은 기본적으로 정상입니다.
- 아래를 만족하지 않으면 unmatched_defs 때문에 is_valid=false를 주면 안 됩니다.

unmatched_defs를 오류로 볼 수 있는 최소 조건(모두 만족해야 함):

- 같은 join_key 조합이 Condition 쪽에서 “명시적으로” 존재함
  (증거: unmatched_conds/condition_row.index 또는 condition_data에서 해당 조합 행 index 제시)
- Definition에도 같은 join_key 조합이 존재함 (증거: unmatched_defs row index 제시)
- 그런데도 그 조합이 어떤 그룹에도 매칭되지 않음(증거: groups에서 누락을 인덱스로 제시)

---

4.5 unmatched_conds 처리 (더 중요)
- unmatched_conds(Condition 행이 어떤 그룹에도 매칭되지 않음)는 상대적으로 중요한 오류 후보입니다.
- 다만 아래를 모두 만족할 때만 is_valid=false를 고려하세요:

오류 조건(모두 만족):

- 해당 condition row의 join_key 중 와일드카드/미기재가 아닌 값이 있음
- 그 값(또는 조합)이 Definition에 실제로 존재함 (증거 인덱스)
- 그런데도 어떤 그룹에도 매칭되지 않음 (unmatched_conds row index 증거)

---

이 규칙만으로 판단하여 JSON을 반환하세요.
(규칙을 어기는 오류 문장은 errors에 쓰지 마세요.)

## 출력 형식 (JSON)

반드시 다음 형식으로 응답하세요:
{output_schema}

- is_valid:
  - 위 기준(4.1~4.6)을 적용했을 때
    명백한 모순 또는 조합 누락이 있다고 판단되면 false,
    그렇지 않으면 true 로 설정합니다.
- errors:
  - critical 이라고 확신할 수 있는 문제만 한국어로 구체적으로 기술하세요.
- suggestions:
  - 문제가 있을 때 어떻게 수정하면 좋을지에 대한 제안을 적되,
    가능하다면 근본 원인 수준으로 작성하세요.
- reasoning:
  - 전체 판단 근거를 간단히 요약해서 설명하세요.
- root_cause_task_id:
  - 문제가 특정 task (예: "task3")에 명확히 연결될 경우 해당 id 를 지정하고,
    그렇지 않으면 null 로 둡니다.

JSON만 반환하세요.
"""


    return prompt