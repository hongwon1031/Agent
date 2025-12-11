# Prototype 8 구현 완료 (2025-12-11)

## 최종 아키텍처 (Option A: Fixed Workflow)

### 문제 분석
- Definition: 단순 split만 필요 (header 유지)
- Condition: split + schema mapping 필요 (header 변경)
- 하나의 범용 tool로는 returns가 불명확 → Example이 꼬임

### 해결책: 역할 분리 (Option A)

**Fixed Workflow**:
```
Task0: section_classifier
Task1: definition_extract_v2 (원본 그대로 추출)
Task2: llm_table_split (Definition 전용, header 유지)
Task3: condition_extract (원본 그대로 추출)
Task4: condition_transform (Condition 전용, header 변경)
Task5: grouping_logic_extractor
Task6: combination_generator
```

### 구현된 Tools

**1. LLMTableSplitTool** (Definition 전용)
- 역할: 의미 기반 셀 분리
- Input: Definition 테이블
- Output: **Header 유지**, data에 리스트 추가
- 예시: "간편심사(315)형/일반심사형" → ["간편심사(315)형", "일반심사형"]

**2. ConditionTransformTool** (Condition 전용)
- 역할: Split + Age parsing + Schema mapping
- Input: Condition 테이블 (가입나이_남, 가입나이_여, 보험기간 등)
- Output: **Header 변경** (주피보험자최소가입연령, 주피보험자최대가입연령, 주피보험자가입성별 등)
- 기능:
  - "80/90세 만기" → ["80세 만기", "90세 만기"]
  - "가입나이_남/여" → 최소/최대 파싱, 성별 추출 ["남", "여"]
  - 연령구분코드 생성
  - 수식 보존 (계산 안함)

**3. RuleTableSplitTool** (범용, 미사용)
- 역할: 규칙 기반 단순 split
- 현재 workflow에서는 사용 안함 (향후 확장용)

### Tool Schemas 수정

```python
"llm_table_split": {
    "description": "LLM-based semantic splitting (Definition용, header 유지)",
    "parameters": {
        "header": "{{task1.data.header}}",  # definition_extract_v2
        "data": "{{task1.data.data}}",
        ...
    }
}

"condition_transform": {
    "description": "Transform condition to final schema (Condition 전용, header 변경)",
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

"combination_generator": {
    "parameters": {
        "grouping_logic": "{{task5.data}}",  # grouping_logic_extractor
        ...
    }
}
```

### Task Types (build_next_task_prompt)

```
- "classify_sections"
- "extract_definitions"
- "table_split"           ← Definition split
- "condition_extraction"
- "condition_transform"   ← Condition transform
- "grouping"
- "combination_generation"
```

### 장점
✅ **명확한 역할 분리**: Definition split vs Condition transform
✅ **고정 task 번호**: Example이 명확 (task2, task4, task5)
✅ **실용적**: Planner 부담 감소
✅ **디버깅 쉬움**: 각 단계 output이 예측 가능

### 단점
❌ **범용성 제한**: Definition/Condition 각각 전용 tool
❌ **확장성**: 새로운 테이블 타입 추가 시 새 tool 필요

---

## 기존 구현 (Formula + Cartesian)

### 1. Formula Utils (tools/formula_utils.py)
- AST 기반 안전한 수식 평가
- parse_age(), evaluate_formula(), parse_period()

### 2. CombinationGeneratorTool
- Cartesian product (보험기간 × 납입기간 × 성별)
- Formula 평가 with context (세만기, 년납)
- matched_list_items로 Definition 리스트 처리

### 3. GroupingLogicExtractorTool
- matched_list_items 필드로 리스트 매칭 추적

---

## 구현 과정 및 이슈 해결

### Phase 1: 범용 Tool 시도 (실패)

**목표**: ConditionTransformTool을 LLMTableSplitTool로 일반화

**문제점**:
1. Definition과 Condition의 **Returns가 다름**
   - Definition: Header 유지, 셀만 split
   - Condition: Header 변경 (schema mapping), 셀 split + age parsing
2. tool_schemas의 example이 꼬임 (task 번호 유동적)
3. Planner 부담 증가 (instruction으로 모든 걸 제어)

**결론**: 범용성보다 명확성 선택 → **Option A로 전환**

### Phase 2: Option A vs Option B 비교

**Option A (채택)**: 역할 분리
```
- LLMTableSplitTool: Definition 전용 (header 유지)
- ConditionTransformTool: Condition 전용 (header 변경)
- Fixed task 번호: task0~task6
```

**Option B (포기)**: 완전 범용
```
- 하나의 LLMTableSplitTool로 모든 처리
- instruction으로 schema mapping 여부 제어
- task 번호 고정되지만 output schema 유동적
```

**선택 이유**:
- ✅ Example 명확 (task2, task4 고정)
- ✅ Planner 부담 감소
- ✅ 디버깅 쉬움
- ❌ 범용성은 포기 (실용성 우선)

### Phase 3: LLMTableSplitTool Hallucination 문제

**문제**: LLM이 data를 반환할 때 **앞에 index를 hallucination으로 추가**

**예시**:
```python
# LLM 출력 (잘못됨)
{
  "data": [
    [0, "암보험", "일반형"],  # ← 앞에 0이 붙음
    [1, "암보험", "간편심사형"]
  ]
}

# 기대 출력
{
  "data": [
    ["암보험", "일반형"],
    ["암보험", "간편심사형"]
  ]
}
```

**해결책**: 후처리 정규화 로직 추가

```python
# LLMTableSplitTool.execute() 내부
split_data = result["data"]

normalized = []
for row in split_data:
    # 1) header보다 1개 더 길면 → 앞 index 제거
    if len(row) == len(header) + 1:
        row = row[1:]

    # 2) header보다 훨씬 길면 → 뒤에서부터 header 길이만큼만
    elif len(row) > len(header):
        row = row[-len(header):]

    # 3) header보다 짧으면 → None으로 padding
    elif len(row) < len(header):
        row = list(row) + [None] * (len(header) - len(row))

    normalized.append(row)

# 검증 및 반환
for row_idx, row in enumerate(normalized):
    if len(row) != len(header):
        print(f"[WARN] Row {row_idx} mismatch")

return ToolResult(
    success=True,
    data={
        "header": header,  # 원본 유지
        "data": normalized,  # ← 정규화된 데이터
        "notes": result.get("notes", "")
    },
    tool_name=self.name
)
```

**효과**:
- ✅ LLM hallucination 문제 해결
- ✅ 데이터 길이 불일치 자동 수정
- ✅ 안정적인 downstream processing

### Phase 4: Planner 순서 고정

**문제**: Planner가 task 순서를 임의로 바꿀 수 있음

**해결**: `build_next_task_prompt`에 순서 강제

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

**효과**:
- ✅ Task 번호 예측 가능
- ✅ Example 항상 올바름
- ✅ 디버깅 쉬움

---

## 다음 단계
- End-to-end 테스트
- Planner가 고정 workflow를 잘 생성하는지 확인
- LLM이 instruction 없이도 제대로 동작하는지 검증
- Hallucination 정규화 로직이 모든 케이스를 커버하는지 검증
