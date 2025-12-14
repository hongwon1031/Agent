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

## 다음 단계

1. **End-to-end 테스트**
   - 실제 PDF 문서로 전체 workflow 실행
   - 각 task 결과 검증

2. **Planner 검증**
   - 고정 workflow를 올바르게 생성하는지
   - Task 순서를 지키는지

3. **LLM 성능 검증**
   - Semantic splitting 정확도
   - Schema mapping 정확도
   - Formula preservation (계산 안 하는지)

4. **Hallucination 모니터링**
   - 정규화 로직이 모든 케이스 커버하는지
   - Edge case 테스트

5. **성능 최적화**
   - LLM call 횟수 최소화
   - 캐싱 전략 고려
