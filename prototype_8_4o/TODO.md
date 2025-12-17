# Prototype 8 구현 완료 (2025-12-11)

## 오늘 작업 전체 타임라인

### Phase 0: 문제 정의
**문제**: Definition 테이블에서 "간편심사(315)형/간편심사(335)형/일반심사형" 같은 multi-value가 하나의 Condition만 매칭되고 나머지는 누락됨

**목표**:
- 1:N 매칭 지원 (Definition 1개 → Condition N개)
- 리스트 기반 Cartesian product 생성
- 수식 평가 (AST 기반, eval() 사용 금지)

---

### Phase 1: Formula Utils 생성

**파일**: `prototype_8/tools/formula_utils.py` (NEW)

**구현 내용**:
```python
class FormulaEvaluator:
    def parse_age(self, age_str: str) -> Optional[int]:
        """만 15세 → 15"""

    def evaluate_formula(self, formula_str: str, **context) -> Optional[int]:
        """min[세만기 - 년납, 70] → AST로 안전하게 계산"""

    def parse_period(self, period_str: str) -> Optional[int]:
        """80세 만기 → 80, 10년납 → 10"""
```

**핵심 기술**:
- `ast.parse()` 사용 (eval() 금지)
- 함수 whitelist: min, max, abs, round
- Binary operations: +, -, *, /
- 한국어 변수명 replace: 세만기, 년납

**예시**:
```python
evaluate_formula(
    "min[세만기 - 년납, 90 - 년납, 70] 세",
    세만기=80,
    년납=10
)
# → min(80-10, 90-10, 70) = 70
```

---

### Phase 2: Condition Transform 생성

**파일**: `prototype_8/core/prompt.py`

**함수**: `build_condition_transform_prompt()` (NEW)

**역할**:
1. 독립값 리스트 분리
   - "80/90/100세 만기" → ["80세 만기", "90세 만기", "100세 만기"]
2. 가입나이 파싱
   - "만15세 - min[세만기-년납, 70]" → 최소="만 15세", 최대="min[...]" (계산 안함)
3. 성별 추출
   - "가입나이_남", "가입나이_여" → ["남", "여"]
4. 연령구분코드 생성
   - "만" 포함 → "(2)만연령"
   - "만" 미포함 → "(1)보험연령"
5. Schema mapping
   - 가입나이_남/여 → 주피보험자최소/최대가입연령, 주피보험자가입성별

**파일**: `prototype_8/tools/hybrid_tools.py`

**클래스**: `ConditionTransformTool` (NEW)

**Output 예시**:
```python
{
  "header": ["보종명", "유형1", "유형2", "보험기간", "납입기간",
             "주피보험자최소가입연령", "주피보험자최대가입연령",
             "주피보험자최소가입연령구분코드", "주피보험자최대가입연령구분코드",
             "주피보험자가입성별"],
  "data": [
    ["해약환급금 미지급형", "간편심사형", "-",
     ["80세 만기", "90세 만기", "100세 만기"],  # List
     ["10년납", "15년납"],  # List
     "만 15세",  # String (not calculated)
     "min[세만기 - 년납, 70] 세",  # Formula string
     "(2)만연령",
     "(1)보험연령",
     ["남", "여"]]  # List
  ]
}
```

---

### Phase 3: Definition Extract 리스트화

**파일**: `prototype_8/core/prompt.py`

**수정**: `build_llm_extract_prompt()`

**추가 규칙**:
```python
**값 그룹핑 규칙**:
- 셀 값이 의미적으로 다른 그룹으로 나뉘는 경우, 리스트로 반환
- 예: "간편심사(315)형/간편심사(335)형/일반심사형"
  → ["간편심사(315)형/간편심사(335)형", "일반심사형"]
- 같은 의미는 슬래시 유지
- 단일 그룹은 문자열
```

**파일**: `prototype_8/tools/hybrid_tools.py`

**수정**: `DefinitionExtractToolV2`
- `_llm_extract_helper`, `_llm_merge_helper`가 리스트 값 처리 가능

---

### Phase 4: Grouping Logic 수정

**파일**: `prototype_8/core/prompt.py`

**수정**: `build_grouping_extraction_prompt()`

**추가 로직**: `matched_list_items` 필드

```python
### 리스트 값 매칭 (NEW)
Definition 셀이 리스트면:
- 각 요소를 별도 매칭
- matched_list_items 필드에 인덱스 기록

예시:
Definition[0]["유형1"] = ["일반형", "간편심사형"]
→ Group 0: matched_list_items=[0]  # 일반형
→ Group 1: matched_list_items=[1]  # 간편심사형
```

**파일**: `prototype_8/tools/hybrid_tools.py`

**수정**: `GroupingLogicExtractorTool`
- Output에 `matched_list_items` 추가
- Validation 로직 수정

**Output 예시**:
```python
{
  "groups": [{
    "definition_indices": [0, 3],
    "matched_list_items": [0, 1],  # NEW
    "condition_index": 0
  }]
}
```

---

### Phase 5: Combination Generator 수정

**파일**: `prototype_8/tools/hybrid_tools.py`

**수정**: `CombinationGeneratorTool._generate_combinations()`

**주요 변경**:

1. **Formula utils import**:
```python
from tools.formula_utils import parse_age, evaluate_formula, parse_period
```

2. **Cartesian Product**:
```python
보험기간_list = cond_row.get("보험기간", [])
if not isinstance(보험기간_list, list):
    보험기간_list = [보험기간_list]

납입기간_list = cond_row.get("납입기간", [])
성별_list = cond_row.get("주피보험자가입성별", [])

for 보험기간, 납입기간, 성별 in product(보험기간_list, 납입기간_list, 성별_list):
    # Generate combination
```

3. **Formula 평가**:
```python
세만기 = parse_period(보험기간)  # "80세 만기" → 80
년납 = parse_period(납입기간)    # "10년납" → 10

최소나이 = parse_age(최소나이_raw)
if 최소나이 is None and 세만기 and 년납:
    최소나이 = evaluate_formula(최소나이_raw, 세만기=세만기, 년납=년납)
```

4. **Definition 리스트 처리**:
```python
matched_item_idx = matched_list_items[idx]
if isinstance(value, list) and matched_item_idx is not None:
    processed_def_row[col] = value[matched_item_idx]
```

5. **JOIN key category 제거**:
```python
# for jk in join_keys:  ← 주석 처리
#     category_col = f"{jk}_category"
```

6. **가입나이 컬럼 제거**:
```python
for col in value_columns:
    if col in ("가입나이_남", "가입나이_여"):
        continue  # Skip
```

---

### Phase 6: Tool 등록

**파일**: `prototype_8/agent.py`

**변경**:
```python
from tools.hybrid_tools import (
    ConditionTransformTool,  # NEW
    ...
)

tools = {
    "condition_transform": ConditionTransformTool(),  # NEW
    ...
}
```

---

### Phase 7: 범용 Tool 시도 (실패)

**목표**: ConditionTransformTool을 LLMTableSplitTool로 일반화

**문제점**:
1. Definition: header 유지, 셀만 split
2. Condition: header 변경, 셀 split + schema mapping
3. **Returns가 다름** → tool_schemas example 꼬임
4. Planner 부담 증가 (instruction으로 모든 걸 제어)

**결론**: 범용성보다 명확성 우선 → Option A로 전환

---

### Phase 8: Option A 구현 (역할 분리)

#### 8.1: build_llm_extract_prompt에서 리스트 규칙 제거

**이유**: DefinitionExtractTool과 LLMTableSplitTool이 충돌

**변경**:
```python
# Before
**값 그룹핑 규칙**: 리스트로 반환...

# After
**요구사항**:
5. 셀 값은 원본 그대로 유지 (분리하지 않음)
```

#### 8.2: build_table_split_prompt 생성

**파일**: `prototype_8/core/prompt.py`

**함수**: `build_table_split_prompt()` (NEW)

**역할**: 범용 의미 기반 split (Definition/Condition 무관)

**예시**:
```python
입력: "간편심사(315)형/간편심사(335)형/일반심사형"
출력: ["간편심사(315)형/간편심사(335)형", "일반심사형"]
이유: 간편심사 계열 vs 일반심사는 의미가 다름

입력: "80/90/100세 만기"
출력: ["80세 만기", "90세 만기", "100세 만기"]
이유: 각 값이 독립적인 옵션
```

#### 8.3: LLMTableSplitTool 생성

**파일**: `prototype_8/tools/hybrid_tools.py`

**클래스**: `LLMTableSplitTool` (NEW)

**특징**:
- Definition 전용
- Header 유지
- row_indices 지원
- Semantic splitting

#### 8.4: RuleTableSplitTool 생성

**파일**: `prototype_8/tools/hybrid_tools.py`

**클래스**: `RuleTableSplitTool` (NEW)

**특징**:
- 규칙 기반 (/, , 구분자)
- 빠르고 결정적
- 현재 workflow에서는 미사용 (향후 확장용)

#### 8.5: ConditionTransformTool 복원

**파일**: `prototype_8/tools/hybrid_tools.py`

- 기존 ConditionTransformTool 그대로 복원
- Condition 전용
- Header 변경

#### 8.6: Tool Schemas 수정

**파일**: `prototype_8/tools/tool_schemas.py`

**변경**:
```python
"llm_table_split": {
    "description": "Definition용, header 유지",
    "parameters": {
        "header": "{{task1.data.header}}",  # definition_extract_v2
        "data": "{{task1.data.data}}",
        ...
    }
}

"condition_transform": {
    "description": "Condition 전용, header 변경",
    "parameters": {
        "header": "{{task3.data.header}}",  # condition_extract
        "data": "{{task3.data.data}}",
        ...
    }
}

"grouping_logic_extractor": {
    "parameters": {
        "definition_header": "{{task2.data.header}}",  # llm_table_split
        "condition_header": "{{task4.data.header}}",   # condition_transform
        ...
    }
}
```

**핵심**: Task 번호 고정 (task1, task2, task3, task4)

#### 8.7: Task Types 업데이트

**파일**: `prototype_8/core/prompt.py`

**수정**: `build_next_task_prompt()`

**변경**:
```python
task_type 는 다음 값 중 하나여야 한다:
- "classify_sections"
- "extract_definitions"
- "table_split"           ← Definition split (NEW)
- "condition_extraction"
- "condition_transform"   ← Condition transform
- "grouping"
- "combination_generation"
```

#### 8.8: Task 순서 고정

**파일**: `prototype_8/core/prompt.py`

**추가**:
```python
6. task 순서는 고정되어야 합니다:
   - 완료 0개 → "classify_sections"
   - 완료 1개 → "extract_definitions"
   - 완료 2개 → "table_split"
   - 완료 3개 → "condition_extraction"
   - 완료 4개 → "condition_transform"
   - 완료 5개 → "grouping"
   - 완료 6개 → "combination_generation"
```

#### 8.9: Agent 등록

**파일**: `prototype_8/agent.py`

**변경**:
```python
from tools.hybrid_tools import (
    LLMTableSplitTool,        # NEW
    RuleTableSplitTool,       # NEW
    ConditionTransformTool,   # 복원
    ...
)

tools = {
    "llm_table_split": LLMTableSplitTool(),
    "rule_table_split": RuleTableSplitTool(),
    "condition_transform": ConditionTransformTool(),
    ...
}
```

---

### Phase 9: LLMTableSplitTool Hallucination 해결

**문제**: LLM이 data 앞에 index를 hallucination으로 추가

**예시**:
```python
# LLM 출력 (잘못됨)
{
  "data": [
    [0, "암보험", "일반형"],  # ← 0이 붙음
    [1, "암보험", "간편심사형"]
  ]
}
```

**해결책**: 정규화 로직 추가

**파일**: `prototype_8/tools/hybrid_tools.py`

**수정**: `LLMTableSplitTool.execute()`

```python
split_data = result["data"]

normalized = []
for row in split_data:
    # 1) header보다 1개 더 길면 → 앞 index 제거
    if len(row) == len(header) + 1:
        row = row[1:]

    # 2) header보다 훨씬 길면 → 뒤에서부터 header 길이만큼만
    elif len(row) > len(header):
        row = row[-len(header):]

    # 3) header보다 짧으면 → None padding
    elif len(row) < len(header):
        row = list(row) + [None] * (len(header) - len(row))

    normalized.append(row)

# row_indices 처리 시에도 normalized 사용
if row_indices is not None:
    final_data = [list(r) for r in data]
    for i, idx in enumerate(row_indices):
        if i < len(normalized):
            final_data[idx] = normalized[i]
else:
    final_data = normalized

return ToolResult(
    success=True,
    data={
        "header": header,
        "data": final_data,  # ← normalized
        ...
    }
)
```

**효과**:
- ✅ LLM hallucination 자동 수정
- ✅ 데이터 길이 불일치 처리
- ✅ 안정적인 downstream processing

---

### Phase 10: P0 - LLM 기반 Validator 정비 (2025-12-12)

**목표**: Prototype 8에서 누락된 2개의 LLM validator 추가 (table_split, condition_transform)

#### 10.1: build_validate_table_split_llm_prompt() 추가

**파일**: `prototype_8/core/prompt.py`

**위치**: Line 793 이후 (build_validate_condition_transform_llm_prompt 다음)

**함수 시그니처**:
```python
def build_validate_table_split_llm_prompt(
    original_header: List[str],
    original_data: List[List[str]],
    split_header: List[str],
    split_data: List[List[str]],
) -> str:
```

**검증 기준**:
1. **Header 불변성**: split_header == original_header (컬럼명/순서 변경 금지)
2. **Row 수 일치**: len(split_data) == len(original_data) (행 추가/삭제 금지)
3. **셀 타입 제약**: 각 셀은 str 또는 list[str]만 허용
4. **의미 있는 split**:
   - 리스트로 분리된 값이 의미적으로 그룹핑되어 있는지
   - 예: ["간편심사(315)형/간편심사(335)형", "일반심사형"] ✅
   - 예: ["간편심사(315)", "형/간편심사(335)형/일반심사형"] ❌
5. **원본 데이터 보존**: 분리 과정에서 값 손실/변형이 없는지

**라인 수**: ~120 lines

#### 10.2: build_validate_condition_transform_llm_prompt() 추가

**파일**: `prototype_8/core/prompt.py`

**위치**: Line 527 이후 (build_validate_transform_llm 다음)

**함수 시그니처**:
```python
def build_validate_condition_transform_llm_prompt(
    original_header: List[str],
    original_data: List[List[str]],
    transformed_header: List[str],
    transformed_data: List[List[str]],
) -> str:
```

**검증 기준**:
1. **필수 스키마 존재**:
   - 보험기간, 납입기간
   - 주피보험자최소가입연령, 주피보험자최대가입연령
   - 주피보험자최소가입연령구분코드, 주피보험자최대가입연령구분코드
   - 주피보험자가입성별

2. **리스트 분리 정확성**:
   - 보험기간: list (예: ["80세 만기", "90세 만기"])
   - 납입기간: list (예: ["10년납", "15년납"])
   - 주피보험자가입성별: list (예: ["남", "여"]) 또는 단일값

3. **가입연령 형식**:
   - 주피보험자최소가입연령: 상수 (예: "만 15세")
   - 주피보험자최대가입연령: **수식 문자열** (예: "min[세만기 - 년납, 70] 세")
   - ⚠️ **계산된 숫자가 아님을 확인** (수식 그대로 보존)

4. **연령구분코드 형식**: "(1)보험연령" 또는 "(2)만연령"

5. **원본 데이터 손실 없음**: 필수값 null 비율 < 10%

**라인 수**: ~130 lines

#### 10.3: validate_table_split_llm() 메서드 추가

**파일**: `prototype_8/core/llm_validator.py`

**위치**: Line 407 이후 (validate_definition_extract_v2_llm 다음)

**메서드 시그니처**:
```python
def validate_table_split_llm(
    self,
    task_output: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    LLMTableSplitTool 결과를 LLM으로 검증

    Args:
        task_output: {"header": [...], "data": [...], "notes": "..."}
        context: {
            "original_header": [...],
            "original_data": [...],
            "previous_results": [...]
        }

    Returns:
        {
            "is_valid": bool,
            "confidence": float,
            "errors": List[str],
            "suggestions": List[str],
            "reasoning": str
        }
    """
```

**구현 로직**:
1. task_output에서 split 결과 추출
2. context에서 원본 데이터 추출
3. 기본 형태 검증 (빈 데이터 체크)
4. prompt builder 호출
5. LLM 호출 (gpt-4o, temperature=0)
6. 결과 파싱 및 반환

**라인 수**: ~76 lines

#### 10.4: validate_condition_transform_llm() 메서드 추가

**파일**: `prototype_8/core/llm_validator.py`

**위치**: Line 483 이후 (validate_table_split_llm 다음)

**메서드 시그니처**:
```python
def validate_condition_transform_llm(
    self,
    task_output: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    ConditionTransformTool 결과를 LLM으로 검증

    Args:
        task_output: {"header": [...], "data": [...], "notes": "..."}
        context: {
            "original_header": [...],
            "original_data": [...],
            "previous_results": [...]
        }
    """
```

**구현 로직**:
1. 필수 컬럼 존재 여부 사전 체크 (빠른 실패)
2. 원본 데이터 추출
3. prompt builder 호출
4. LLM 호출
5. 결과 검증 및 반환

**라인 수**: ~97 lines

#### 10.5: validate() 메서드에 task_type 매핑 추가

**파일**: `prototype_8/core/llm_validator.py`

**위치**: Line 95-106

**변경 내용**:
```python
# Line 97-99: table_split 추가
elif task_type == "table_split":
    # NEW: LLMTableSplitTool validation
    result = self.validate_table_split_llm(task_output, context)

# Line 102-104: condition_transform 추가
elif task_type == "condition_transform":
    # NEW: ConditionTransformTool validation
    result = self.validate_condition_transform_llm(task_output, context)
```

#### 10.6: validate_task_node에 context 준비 로직 추가

**파일**: `prototype_8/agent.py`

**위치**: Line 674-704

**table_split용 context 준비** (Line 674-688):
```python
if task_type == "table_split":
    task_results = state.get('task_results', [])

    # task1 (definition_extract_v2) 결과에서 원본 데이터 추출
    for result in task_results:
        if result.get("task_id") == "task1" and result.get("success"):
            data = result.get("data", {})
            context["original_header"] = data.get("header", [])
            context["original_data"] = data.get("data", [])
            break

    print(f"[CONTEXT] Table split validation context prepared:")
    print(f"  - original_header: {context.get('original_header', 'NOT FOUND')}")
    print(f"  - original_data rows: {len(context.get('original_data', []))}")
```

**condition_transform용 context 준비** (Line 690-704):
```python
if task_type == "condition_transform":
    task_results = state.get('task_results', [])

    # task3 (condition_extract) 결과에서 원본 데이터 추출
    for result in task_results:
        if result.get("task_id") == "task3" and result.get("success"):
            data = result.get("data", {})
            context["original_header"] = data.get("header", [])
            context["original_data"] = data.get("data", [])
            break

    print(f"[CONTEXT] Condition transform validation context prepared:")
    print(f"  - original_header: {context.get('original_header', 'NOT FOUND')}")
    print(f"  - original_data rows: {len(context.get('original_data', []))}")
```

**라인 수**: ~30 lines

#### P0 작업 요약

**총 코드 라인 수**: ~380 lines

**파일별 변경**:
- `core/prompt.py`: 2개 prompt builder 추가 (~250 lines)
- `core/llm_validator.py`: 2개 validator 메서드 + validate() 수정 (~180 lines)
- `agent.py`: context 준비 로직 (~30 lines)

**검증 커버리지**:
- ✅ Task0 (classify): validate_section_classifier_llm
- ✅ Task1 (extract): validate_definition_extract_v2_llm
- ✅ **Task2 (table_split): validate_table_split_llm** ← NEW
- ⚠️ Task3 (condition_extract): 규칙 기반만 (P1에서 추가)
- ✅ **Task4 (condition_transform): validate_condition_transform_llm** ← NEW
- ✅ Task5 (grouping): validate_grouping_logic (Hybrid)
- ⚠️ Task6 (generate): 규칙 기반만

---

### Phase 11: P1 - condition_extract LLM Validator 추가 (2025-12-12)

**목표**: Task3 (condition_extract)에 LLM 기반 validator 추가하여 검증 품질 강화

#### 11.1: build_validate_condition_extract_llm_prompt() 추가

**파일**: `prototype_8/core/prompt.py`

**위치**: Line 947 이후 (build_validate_condition_transform_llm_prompt 다음)

**함수 시그니처**:
```python
def build_validate_condition_extract_llm_prompt(
    condition_sections: List[Dict[str, Any]],
    extracted_header: List[str],
    extracted_data: List[List[str]],
) -> str:
```

**검증 기준**:

1. **테이블 구조 유효성** (필수):
   - Header와 data가 존재하는가?
   - 각 행의 컬럼 수가 header 수와 일치하는가?
   - 빈 테이블이 아닌가? (condition_sections가 있으면 최소 1행 이상 기대)

2. **컬럼명 정규화** (중요):
   - 표준화된 컬럼명 사용 (보험기간, 납입기간, 가입나이_남, 가입나이_여, 납입주기 등)
   - JOIN key 컬럼 존재 (유형0, 유형1, 유형2, 심사형, 보장형 등 최소 1개)

3. **데이터 내용 품질** (중요):
   - 보험기간/납입기간 형식이 합리적인가?
     - 예: "80/90/100세 만기, 종신", "10/15/20년납"
     - 오류 예: 빈 문자열, "unknown", 숫자만
   - 가입나이 수식이 유효한가?
     - 예: "만15세 - min[세만기 - 년납, 70] 세"
     - 수식 문자열 그대로 보존 (계산 금지)
   - 비어있는 셀 비율 < 30%

4. **계층 정보 추출** (선택적):
   - 유형 컬럼들에 의미 있는 값 존재
   - 예: "해약환급금 미지급형", "간편심사형", "일반형"

5. **원본 섹션과의 일치성** (중요):
   - condition_sections의 테이블 데이터가 추출 결과에 포함되었는가?
   - 불필요한 정보 (주석, 설명) 제외되었는가?
   - "가입불가 조건", "제외 사항" 등은 제외되어야 함

**라인 수**: ~155 lines

#### 11.2: validate_condition_extract_llm() 메서드 추가

**파일**: `prototype_8/core/llm_validator.py`

**위치**: Line 736 이후 (validate_condition_extract 다음)

**메서드 시그니처**:
```python
def validate_condition_extract_llm(
    self,
    task_output: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Condition Extract 결과를 LLM으로 검증

    Args:
        task_output: {"header": [...], "data": [...], "reasoning": "..."}
        context: {
            "condition_sections": [...],
            "all_sections": [...],
            "previous_results": [...]
        }

    Returns:
        Dict: {
            "is_valid": bool,
            "confidence": float,
            "errors": List[str],
            "suggestions": List[str],
            "reasoning": str
        }
    """
```

**구현 로직**:
1. extracted_header/data 추출
2. 기본 형태 검증:
   - 빈 데이터 체크
   - condition_sections 없으면 빈 결과도 valid
   - sections 있는데 빈 결과면 invalid
3. condition_sections 없으면 빠른 실패:
   - 기본 JOIN key 체크만 수행
   - LLM 호출 생략
4. LLM 검증:
   - prompt builder 호출
   - gpt-4o로 상세 검증
   - 결과 파싱 및 필드 검증

**라인 수**: ~130 lines

#### 11.3: validate() 메서드 업데이트

**파일**: `prototype_8/core/llm_validator.py`

**위치**: Line 95-97

**변경 내용**:
```python
elif task_type == "extract_condition":
    # NEW: LLM-based validation for condition_extract
    result = self.validate_condition_extract_llm(task_output, context)
```

**이전**: validate_condition_extract (규칙 기반)
**이후**: validate_condition_extract_llm (LLM 기반)

#### 11.4: validate_task_node에 context 준비 로직 추가

**파일**: `prototype_8/agent.py`

**위치**: Line 706-730 (condition_transform context 준비 다음)

**extract_condition용 context 준비**:
```python
if task_type == "extract_condition":
    task_results = state.get('task_results', [])

    # Get all_sections from state
    all_sections = state.get("sections", [])

    # task0 (section_classifier) 결과에서 condition indices 추출
    condition_indices = []
    for result in task_results:
        if result.get("task_id") == "task0" and result.get("success"):
            data = result.get("data", {})
            condition_indices = data.get("condition", [])
            break

    # Build condition_sections from all_sections and condition_indices
    if all_sections and condition_indices:
        condition_sections = [s for s in all_sections if s.get("index") in condition_indices]
        context["condition_sections"] = condition_sections
        context["all_sections"] = all_sections

    print(f"[CONTEXT] Condition extract validation context prepared:")
    print(f"  - all_sections count: {len(all_sections)}")
    print(f"  - condition_indices: {condition_indices}")
    print(f"  - condition_sections count: {len(context.get('condition_sections', []))}")
```

**핵심 로직**:
- state에서 all_sections 가져오기
- task0 결과에서 condition indices 추출
- condition_sections 생성 (인덱스 필터링)
- context에 condition_sections, all_sections 추가

**라인 수**: ~25 lines

#### P1 작업 요약

**총 코드 라인 수**: ~310 lines

**파일별 변경**:
- `core/prompt.py`: 1개 prompt builder 추가 (~155 lines)
- `core/llm_validator.py`: 1개 validator 메서드 + validate() 수정 (~130 lines)
- `agent.py`: context 준비 로직 (~25 lines)

**최종 검증 커버리지** (P0 + P1):
- ✅ Task0 (classify): validate_section_classifier_llm
- ✅ Task1 (extract): validate_definition_extract_v2_llm
- ✅ Task2 (table_split): validate_table_split_llm
- ✅ **Task3 (condition_extract): validate_condition_extract_llm** ← NEW (P1)
- ✅ Task4 (condition_transform): validate_condition_transform_llm
- ✅ Task5 (grouping): validate_grouping_logic (Hybrid)
- ⚠️ Task6 (generate): 규칙 기반만

**주요 개선사항**:
1. **원본 섹션 기반 검증**: condition_sections와 추출 결과 비교
2. **빠른 실패 전략**: sections 없으면 LLM 호출 생략
3. **상세 품질 검증**: 컬럼명, 데이터 형식, 계층 정보, 일치성 모두 검증

---

## 최종 아키텍처

### Fixed Workflow

```
Task0: section_classifier
Task1: definition_extract_v2 (원본 그대로)
Task2: llm_table_split (Definition, header 유지)
Task3: condition_extract (원본 그대로)
Task4: condition_transform (Condition, header 변경)
Task5: grouping_logic_extractor (matched_list_items 사용)
Task6: combination_generator (Cartesian + formula)
```

### Tool 역할 분담

**LLMTableSplitTool** (Definition 전용):
- 의미 기반 split
- Header 유지
- "간편심사형/일반심사형" → ["간편심사형", "일반심사형"]

**ConditionTransformTool** (Condition 전용):
- Split + Age parsing + Schema mapping
- Header 변경
- "80/90세", "가입나이_남/여" → 리스트 + 주피보험자* 컬럼

**CombinationGeneratorTool**:
- Cartesian product
- Formula evaluation
- matched_list_items 처리

### 핵심 기술

1. **AST 기반 수식 평가** (eval() 금지)
2. **Semantic list splitting** (LLM 기반)
3. **1:N 매칭** (matched_list_items)
4. **Cartesian product** (itertools.product)
5. **Hallucination 정규화** (후처리)
6. **Fixed workflow** (task 순서 고정)

---

## 파일 변경 요약

### 신규 파일
1. `prototype_8/tools/formula_utils.py` - AST 기반 수식 평가

### 수정 파일
1. `prototype_8/tools/hybrid_tools.py`
   - ConditionTransformTool (NEW)
   - LLMTableSplitTool (NEW)
   - RuleTableSplitTool (NEW)
   - DefinitionExtractToolV2 (리스트 처리)
   - GroupingLogicExtractorTool (matched_list_items)
   - CombinationGeneratorTool (Cartesian + formula)

2. `prototype_8/core/prompt.py`
   - build_condition_transform_prompt() (NEW)
   - build_table_split_prompt() (NEW)
   - build_llm_extract_prompt() (수정)
   - build_grouping_extraction_prompt() (수정)
   - build_next_task_prompt() (task_type 목록 + 순서)

3. `prototype_8/tools/tool_schemas.py`
   - llm_table_split (NEW)
   - condition_transform (복원)
   - grouping_logic_extractor (example 수정)
   - combination_generator (example 수정)

4. `prototype_8/agent.py`
   - Import + Tool 등록

### 코드 라인 수
- 신규 코드: ~900 lines
- 수정 코드: ~300 lines
- 총 ~1200 lines

---

## P0 + P1 작업 총 정리 (2025-12-12)

### 총 코드 라인 수
- **P0**: ~380 lines (table_split, condition_transform validators)
- **P1**: ~310 lines (condition_extract validator)
- **총합**: ~690 lines

### 검증 커버리지 (최종)
```
Task0 (section_classifier)      ✅ validate_section_classifier_llm
Task1 (definition_extract_v2)    ✅ validate_definition_extract_v2_llm
Task2 (llm_table_split)          ✅ validate_table_split_llm          ← P0
Task3 (condition_extract)        ✅ validate_condition_extract_llm    ← P1
Task4 (condition_transform)      ✅ validate_condition_transform_llm  ← P0
Task5 (grouping_logic)           ✅ validate_grouping_logic (Hybrid)
Task6 (combination_generator)    ⚠️  규칙 기반만 (P2 대상)
```

### 파일별 최종 변경사항

**1. prototype_8/core/prompt.py** (~405 lines 추가)
- build_validate_table_split_llm_prompt() - ~120 lines
- build_validate_condition_transform_llm_prompt() - ~130 lines
- build_validate_condition_extract_llm_prompt() - ~155 lines

**2. prototype_8/core/llm_validator.py** (~310 lines 추가)
- validate_table_split_llm() - ~76 lines
- validate_condition_transform_llm() - ~97 lines
- validate_condition_extract_llm() - ~130 lines
- validate() 메서드 수정 - 3개 task_type 매핑 추가

**3. prototype_8/agent.py** (~55 lines 추가)
- table_split context 준비 - ~15 lines
- condition_transform context 준비 - ~15 lines
- extract_condition context 준비 - ~25 lines

---

## 다음 단계 (우선순위 순)

### P2: combination_generator LLM Validator 추가 (선택적)

**목표**: Task6 (combination_generator)에 LLM validator 추가하여 최종 조합 품질 검증

**필요성 평가**:
- ✅ 장점: 전체 파이프라인 검증 완성도 (7/7 Task 커버)
- ⚠️ 단점: Cartesian product는 결정적이므로 LLM 검증 효과 제한적
- 📊 우선순위: **낮음** (규칙 기반 검증으로도 충분할 수 있음)

**예상 작업량**: ~300 lines
- build_validate_combination_generator_llm_prompt()
- validate_combination_generator_llm()
- validate() 메서드 업데이트
- context 준비 로직 (definition/condition 데이터 필요)

**검증 기준** (예상):
1. **Cartesian Product 완전성**: 모든 조합 생성되었는지
2. **수식 평가 정확성**: 가입연령 계산이 올바른지
3. **Definition 리스트 처리**: matched_list_items가 올바르게 적용되었는지
4. **Schema 일치**: 최종 출력이 표준 스키마 준수하는지
5. **중복 제거**: 동일한 조합이 중복되지 않았는지

---

### P3: Validator 성능 및 품질 검증 (중요)

#### 3.1 End-to-end 테스트

**목표**: 실제 보험 약관 문서로 전체 workflow 실행 및 검증

**테스트 케이스** (최소 10개 문서):
1. **정상 케이스**: 모든 validator 통과
2. **오류 케이스**: 의도적 오류 주입 후 validator가 탐지하는지 확인
3. **Edge 케이스**:
   - 빈 테이블
   - 누락된 컬럼
   - 잘못된 수식
   - 계산된 숫자 (수식이어야 하는데)

**검증 항목**:
- [ ] Task0-6 모든 validation 통과율
- [ ] 각 validator의 is_valid 분포
- [ ] confidence 점수 분포
- [ ] errors/suggestions 품질
- [ ] False positive/negative 비율

#### 3.2 Validator 성능 측정

**측정 항목**:
1. **정확도 (Accuracy)**:
   - True positive: 정상 데이터를 valid로 판정
   - True negative: 오류 데이터를 invalid로 판정
   - False positive: 오류 데이터를 valid로 판정 ❌
   - False negative: 정상 데이터를 invalid로 판정 ❌

2. **성능 (Performance)**:
   - LLM 호출 시간 (평균, 최대, 최소)
   - 전체 validation 시간 비율
   - 빠른 실패 (fast-fail) 적중률

3. **품질 (Quality)**:
   - errors 메시지의 명확성
   - suggestions의 실행 가능성
   - reasoning의 논리성

**목표 기준**:
- False positive < 5%
- False negative < 3%
- Validation 시간 < 전체 실행 시간의 20%
- LLM 호출당 평균 < 3초

#### 3.3 Prompt 튜닝

**최적화 대상**:
1. **프롬프트 길이 최적화**:
   - 불필요한 설명 제거
   - 핵심 검증 기준만 유지
   - 예시 간소화

2. **검증 기준 조정**:
   - 과도하게 엄격한 기준 완화
   - 명백한 오류에만 집중
   - confidence 임계값 조정

3. **Few-shot 예시 추가** (필요시):
   - 정상/오류 케이스 예시
   - is_valid=true/false 판정 예시

---

### P4: Self-Healing 및 Backtracking 강화 (중요)

#### 4.1 Root Cause Analysis 개선

**현재 상태**: 기본적인 RCA만 구현
**개선 방향**:
1. **Validator 피드백 활용**:
   - errors/suggestions를 RCA에 포함
   - 구체적인 수정 방향 제시

2. **의존성 추적 강화**:
   - Task 간 데이터 흐름 명시적 추적
   - 상위 task 오류가 하위에 미친 영향 분석

3. **패턴 인식**:
   - 반복되는 오류 패턴 학습
   - 유사 케이스 재사용

#### 4.2 Backtracking 전략 고도화

**현재**: 단순 의존성 기반 backtrack
**개선**:
1. **선택적 Backtrack**:
   - 오류 심각도에 따라 backtrack 범위 결정
   - 경미한 오류: 현재 task만 재시도
   - 중대한 오류: 상위 task부터 재실행

2. **Backtrack 횟수 제한**:
   - 무한 루프 방지
   - 3회 재시도 후 실패 처리

3. **Alternative Path**:
   - 동일 task를 다른 tool로 재시도
   - 예: llm_table_split 실패 → rule_table_split 사용

---

### P5: 성능 최적화 (선택적)

#### 5.1 LLM 호출 최적화

**현재 문제**: 각 validation마다 LLM 호출 (비용/시간 증가)

**개선 방안**:
1. **배치 검증**:
   - 여러 validator를 하나의 prompt로 통합
   - 한 번의 LLM 호출로 여러 검증 수행

2. **빠른 실패 전략 확대**:
   - 규칙 기반 사전 체크 강화
   - LLM 호출 전에 명백한 오류 탐지

3. **캐싱**:
   - 동일한 validation 요청 캐싱
   - 같은 문서 재처리 시 재사용

#### 5.2 병렬 처리

**현재**: 순차 실행
**개선**:
1. **Task 병렬화** (불가능한 경우 많음):
   - 의존성 없는 task 동시 실행
   - 예: task2, task3 병렬 실행 불가 (task0 → task1 → task2 순서 고정)

2. **Validation 병렬화**:
   - 여러 task의 validation 동시 수행
   - 결과 취합 후 판정

---

### P6: 모니터링 및 로깅 강화 (중요)

#### 6.1 Validation 로그 상세화

**현재**: 기본 print 로그만
**개선**:
1. **구조화된 로그**:
   - JSON 형식으로 validation 결과 저장
   - task_id, validator_name, is_valid, confidence, errors, suggestions, timestamp

2. **Validation 히스토리**:
   - 각 document별 validation 결과 누적
   - 실패 패턴 분석

3. **대시보드** (선택적):
   - Validation 성공률 실시간 모니터링
   - 오류 유형별 통계
   - Validator별 성능 비교

#### 6.2 디버깅 도구

1. **Validation Replay**:
   - 실패한 validation을 로그에서 재현
   - 프롬프트/응답 저장 및 재실행

2. **Diff 도구**:
   - 원본 vs 변환 데이터 시각적 비교
   - Header/data 차이 하이라이트

---

### P7: 문서화 및 테스트 코드 (중요)

#### 7.1 Validator 문서화

**작성 내용**:
1. **각 validator의 역할 및 검증 기준**
2. **입력/출력 스펙**
3. **예시 케이스** (정상/오류)
4. **Troubleshooting 가이드**

#### 7.2 단위 테스트

**테스트 대상**:
1. **각 prompt builder**:
   - 다양한 입력에 대해 프롬프트 생성
   - 형식 검증

2. **각 validator 메서드**:
   - Mock LLM 응답으로 테스트
   - 정상/오류 케이스 분기 검증

3. **Context 준비 로직**:
   - state에서 데이터 추출 검증
   - 누락된 데이터 처리

#### 7.3 통합 테스트

**시나리오**:
1. **Happy Path**: 모든 task 성공
2. **Validation 실패 → Backtrack**: task3 실패 → task0부터 재실행
3. **Self-Healing**: validator 제안으로 자동 수정
4. **Edge Cases**: 빈 데이터, 잘못된 형식 등

---

## 작업 우선순위 요약

### 🔴 High Priority (필수)
1. **P3.1 - End-to-end 테스트**: 실제 문서로 검증
2. **P3.2 - Validator 성능 측정**: False positive/negative 비율 확인
3. **P4.1 - Root Cause Analysis 개선**: Validator 피드백 활용
4. **P6.1 - Validation 로그 상세화**: 디버깅 및 분석용

### 🟡 Medium Priority (중요하지만 선택적)
1. **P3.3 - Prompt 튜닝**: 성능 개선
2. **P4.2 - Backtracking 전략 고도화**: 무한 루프 방지
3. **P7.1 - Validator 문서화**: 유지보수성
4. **P7.2 - 단위 테스트**: 안정성

### 🟢 Low Priority (시간 여유 있을 때)
1. **P2 - combination_generator LLM Validator**: 7/7 완성도
2. **P5.1 - LLM 호출 최적화**: 비용/시간 절감
3. **P6.2 - 디버깅 도구**: 개발 편의성
4. **P7.3 - 통합 테스트**: 자동화

---

## 현재 상태 체크리스트

### ✅ 완료된 작업
- [x] Phase 1-9: 핵심 workflow 구현
- [x] Phase 10 (P0): table_split, condition_transform LLM validators
- [x] Phase 11 (P1): condition_extract LLM validator
- [x] 6/7 Task에 LLM validator 적용
- [x] Context 준비 로직 완료
- [x] TODO.md 문서화

### 🚧 진행 중인 작업
- 없음

### 📋 다음 작업
- [ ] P3.1: End-to-end 테스트 실행
- [ ] P3.2: Validator 성능 측정
- [ ] P4.1: RCA 개선 (validator 피드백 활용)
- [ ] P6.1: Validation 로그 구조화
