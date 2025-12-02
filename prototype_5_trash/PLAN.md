# Prototype 5: Reflection-Based Prompt Tuning System

## 🎯 목표

현재 Prototype 4의 문제점을 해결하고, **Validator 피드백을 통한 동적 프롬프트 튜닝** 시스템 구축

### 핵심 아이디어

- **고정된 3단계 워크플로우** (section 분류 → 정의 추출 → 조합 생성)
- **초기 프롬프트는 일반화**되어 있음
- **Validator 실패 시** → Planner가 실패 원인 분석 → **instruction으로 프롬프트 튜닝**
- **Replanning을 통한 Self-Reflection**에 초점

---

## 🔍 현재 문제점 분석 (Prototype 4)

### 1. **고정된 프롬프트의 한계**
```python
# SectionClassifierTool 내부 프롬프트 (하드코딩)
"다음 섹션들을 4가지 카테고리로 분류하세요..."
# → 조건 섹션을 정의로 오분류하는 문제 발생
# → 하지만 프롬프트 수정 불가 (도구 내부에 고정)
```

### 2. **주석 처리 불가 문제**
```
섹션 구조:
  content[0]: table (핵심 정의)
  content[1]: text ("315형은 555형으로 변경") ← 이거 수집 안됨!

현재: DefinitionExtractToolV2가 table만 추출
```

### 3. **Planner 역할 모호**
- 초기 계획은 거의 고정 (선택지 없음)
- `replan()` 기능은 있지만 제대로 활용 안됨

---

## 💡 Prototype 5 설계

### 아키텍처 변경 사항

#### **1. 워크플로우 고정 (Hardcoded)**

```python
# core/fixed_workflow.py (NEW)
class DefinitionExtractionWorkflow:
    """고정된 3단계 워크플로우"""

    def __init__(self):
        self.tasks = [
            {
                "task_id": 1,
                "type": "classify",
                "tool_name": "section_classifier",
                "base_params": {"sections": "$sections"},
                "tunable": True  # instruction 튜닝 가능
            },
            {
                "task_id": 2,
                "type": "extract",
                "tool_name": "definition_extract_v2",
                "base_params": {
                    "sections": "$sections",
                    "core_indices": "{{task1.definition_core}}",
                    "annotation_indices": "{{task1.definition_annotation}}"
                },
                "tunable": True
            },
            {
                "task_id": 3,
                "type": "transform",
                "tool_name": "rule_cartesian",  # 초기값
                "base_params": {
                    "header": "{{task2.header}}",
                    "data": "{{task2.data}}"
                },
                "tunable": True,
                "alternatives": ["llm_cartesian"]  # 전환 가능
            }
        ]
```

#### **2. LLM 도구에 instruction 파라미터 추가**

```python
# tools/hybrid_tools.py

class SectionClassifierTool:
    def execute(self, doc, params):
        sections = params["sections"]
        instruction = params.get("instruction", "")  # ← NEW!

        prompt = f"""다음 섹션들을 4가지 카테고리로 분류하세요:
        - definition_core
        - definition_annotation
        - condition
        - other

        {instruction}  # ← 추가 지시사항 삽입!

        섹션 목록:
        {sections}
        """

class DefinitionExtractToolV2:
    def execute(self, doc, params):
        instruction = params.get("instruction", "")  # ← NEW!

        prompt = f"""정의 데이터를 추출하세요.

        {instruction}  # ← "text 요소도 수집하세요" 같은 지시 가능

        섹션:
        {sections[core_indices]}
        """
```

#### **3. Planner 역할 재정의**

```python
# core/reflection_planner.py (RENAMED from llm_planner.py)

class ReflectionPlanner:
    """
    초기 계획 수립보다 '실패 대응 및 프롬프트 튜닝'에 집중
    """

    def create_initial_plan(self, doc):
        """
        초기 계획은 단순 - 고정 워크플로우 로드
        """
        workflow = DefinitionExtractionWorkflow()
        return {
            "tasks": workflow.tasks,
            "reasoning": "Standard 3-stage workflow"
        }

    def reflect_and_tune(
        self,
        failed_task: Dict,
        validation_result: Dict,
        previous_attempts: List[Dict]
    ) -> Dict:
        """
        Validator 피드백 분석 → instruction 생성

        핵심 로직:
        1. Validation errors 분석
        2. 실패 패턴 파악
        3. 구체적인 instruction 생성
        4. Tool 전환 여부 결정
        """

        prompt = f"""Task가 실패했습니다. 원인을 분석하고 프롬프트를 튜닝하세요.

**실패한 Task**:
{failed_task}

**Validation Errors**:
{validation_result['errors']}

**이전 시도들**:
{previous_attempts}

**분석 및 튜닝**:
1. 왜 실패했나? (root cause)
2. 어떤 instruction을 추가하면 해결되나?
3. Tool을 바꿔야 하나? (rule ↔ llm)

**출력 형식**:
{{
  "root_cause": "조건 섹션과 정의 섹션의 테이블 구조가 유사해서 오분류됨",
  "instruction": "조건 관련 키워드(가입연령, 보험기간 등)가 있는 섹션은 'condition'으로 분류하세요. 정의는 보험종목 명칭/유형이 있는 것만 해당합니다.",
  "tool_change": null,
  "confidence": 0.85
}}
"""

        response = self.llm.complete(prompt)
        return response
```

#### **4. Validator 강화**

```python
# core/llm_validator.py

class LLMValidator:
    def validate(self, task_type, output, context):
        """
        기존 검증 + 상세한 에러 원인 분석
        """

        if task_type == "classify":
            # 분류 결과 검증
            issues = self._check_classification(output, context)

            if issues:
                return {
                    "is_valid": False,
                    "errors": [
                        {
                            "type": "misclassification",
                            "detail": "섹션 5번이 condition인데 definition_core로 분류됨",
                            "evidence": "섹션 제목: '가입조건', 내용: 연령, 기간",
                            "suggestion": "조건 키워드 명시 필요"
                        }
                    ]
                }

        elif task_type == "extract":
            # 추출 결과 검증
            issues = self._check_extraction(output, context)

            if issues:
                return {
                    "is_valid": False,
                    "errors": [
                        {
                            "type": "incomplete_extraction",
                            "detail": "섹션 내 text 요소가 누락됨",
                            "evidence": "content[1]의 '315형→555형' 주석 미수집",
                            "suggestion": "text 요소도 수집하도록 instruction 추가"
                        }
                    ]
                }
```

---

## 🔧 구현 단계

### Phase 1: 구조 재구성
- [ ] `prototype_5/` 디렉토리 생성 (prototype_4 복사)
- [ ] `core/fixed_workflow.py` 생성
- [ ] `llm_planner.py` → `reflection_planner.py` 리팩토링

### Phase 2: Tool 수정
- [ ] `SectionClassifierTool`에 `instruction` 파라미터 추가
- [ ] `DefinitionExtractToolV2`에 `instruction` 파라미터 추가
- [ ] `LLMCartesianTool`에 `instruction` 파라미터 추가 (기존에 있음)

### Phase 3: Validator 강화
- [ ] Error 타입 세분화 (misclassification, incomplete_extraction, 등)
- [ ] 각 에러에 대한 `evidence`, `suggestion` 추가

### Phase 4: Reflection Loop 구현
- [ ] `reflect_and_tune()` 메서드 구현
- [ ] Instruction 히스토리 관리
- [ ] Agent 통합

### Phase 5: 주석 처리 문제 해결
- [ ] `DefinitionExtractToolV2` 내부 로직 수정
  - table 뿐만 아니라 text 요소도 수집
  - instruction으로 제어 가능하도록

---

## 🎯 예상 실행 흐름

```
[초기 실행]
Task 1: section_classifier (instruction="")
  → 조건 섹션을 정의로 오분류

Validator: ❌ "섹션 5가 condition인데 definition_core로 분류됨"

Planner.reflect_and_tune():
  → root_cause: "테이블 구조 유사"
  → instruction: "조건 키워드 확인 필수"

[재시도 1]
Task 1: section_classifier (instruction="조건 관련 키워드가 있으면...")
  → ✅ 성공!

Task 2: definition_extract_v2 (instruction="")
  → text 요소 누락

Validator: ❌ "주석(315형→555형) 미수집"

Planner.reflect_and_tune():
  → instruction: "섹션 내 모든 content (table + text) 수집"

[재시도 2]
Task 2: definition_extract_v2 (instruction="table + text 모두...")
  → ✅ 성공!

Task 3: rule_cartesian (instruction="")
  → 구분자 오판

Validator: ❌ "남성/여성생식기암 잘못 분리"

Planner.reflect_and_tune():
  → tool_change: "llm_cartesian"
  → instruction: "컬럼별 주 구분자 파악"

[재시도 3]
Task 3: llm_cartesian (instruction="주 구분자...")
  → ✅ 성공!
```

---

## 🤔 해결 가능성 분석

### Q: "주석 처리 불가" 문제가 4번 방식으로 해결 가능한가?

**A: 부분적으로 가능, 하지만 Tool 내부 로직 수정도 필요**

#### 현재 상황
```python
# DefinitionExtractToolV2._extract_from_cores()
for item in section.content:
    if item["type"] == "table":  # ← table만 처리
        data = RuleExtractTool().execute(...)
    # text는 무시됨!
```

#### 해결 방안

**옵션 A: instruction만으로 해결 (이상적)**
```python
# Tool 내부에서 instruction 해석
instruction = params.get("instruction", "")

if "text" in instruction or "주석" in instruction:
    # text 요소도 처리
    for item in section.content:
        if item["type"] == "text":
            collect_annotation(item)
```
- 장점: Tool 로직은 그대로, instruction으로만 제어
- 단점: instruction 파싱 로직 복잡해짐

**옵션 B: Tool 로직 수정 + instruction 튜닝 (현실적)**
```python
# 기본적으로 text도 수집하도록 로직 변경
for item in section.content:
    if item["type"] == "table":
        process_table(item)
    elif item["type"] == "text":
        process_text(item, instruction)  # instruction으로 세부 제어
```
- 장점: 더 명확한 분리
- 단점: Tool 수정 필요

**→ 확정: 옵션 B**

---

## 🛠️ 구체적 구현 상세

### 1. Instruction 누적 메커니즘

```python
# core/reflection_planner.py

class ReflectionPlanner:
    def __init__(self):
        self.instruction_history = {}  # {task_id: [inst1, inst2, ...]}

    def reflect_and_tune(self, failed_task, validation_result, previous_attempts):
        task_id = failed_task["task_id"]

        # 이전 instructions 가져오기
        prev_instructions = self.instruction_history.get(task_id, [])

        # LLM에게 새 instruction 생성 요청
        new_instruction = self._generate_instruction(
            failed_task,
            validation_result,
            prev_instructions  # 이전 것들 전달
        )

        # 누적
        updated_instructions = prev_instructions + [new_instruction]
        self.instruction_history[task_id] = updated_instructions

        # 합쳐서 반환
        combined = "\n".join([f"- {inst}" for inst in updated_instructions])

        return {
            "tool_name": failed_task["tool_name"],
            "parameters": {
                **failed_task["parameters"],
                "instruction": combined  # 누적된 전체
            }
        }
```

### 2. DefinitionExtractToolV2 개선

```python
# tools/hybrid_tools.py

class DefinitionExtractToolV2:
    def _extract_from_cores(self, sections, core_indices, instruction=""):
        """
        개선: table뿐 아니라 text도 기본 수집
        """
        all_data = []
        annotations = []

        for idx in core_indices:
            section = sections[idx]

            for item in section["content"]:
                # TABLE 처리
                if item["type"] == "table":
                    table_data = self._extract_table(item)
                    all_data.append(table_data)

                # TEXT 처리 (NEW!)
                elif item["type"] == "text":
                    text_content = item.get("content", "")

                    # instruction으로 세부 제어
                    if self._should_collect_text(text_content, instruction):
                        annotations.append({
                            "section_idx": idx,
                            "text": text_content,
                            "type": "annotation"
                        })

        return {
            "header": merged_header,
            "data": merged_data,
            "annotations": annotations  # NEW!
        }

    def _should_collect_text(self, text, instruction):
        """
        instruction 기반으로 text 수집 여부 결정
        """
        # 기본: 주석 형태는 모두 수집
        if any(marker in text for marker in ["※", "주:", "주)", "주의", "참고"]):
            return True

        # instruction에 특정 키워드 있으면 추가 수집
        if "모든 text" in instruction or "전체 text" in instruction:
            return True

        if "변경" in instruction and "변경" in text:
            return True

        return False
```

### 3. SectionClassifierTool instruction 지원

```python
class SectionClassifierTool:
    def execute(self, doc, params):
        sections = params["sections"]
        instruction = params.get("instruction", "")

        # 기본 프롬프트
        base_prompt = """다음 섹션들을 4가지 카테고리로 분류하세요:
- definition_core: 핵심 정의 테이블 (보험종목, 명칭 등)
- definition_annotation: 정의 주석/설명
- condition: 계약조건 섹션 (가입연령, 보험기간 등)
- other: 기타
"""

        # instruction 추가
        if instruction:
            full_prompt = f"""{base_prompt}

**추가 지시사항**:
{instruction}

섹션 목록:
{sections_summary}
"""
        else:
            full_prompt = f"""{base_prompt}

섹션 목록:
{sections_summary}
"""

        response = self.llm.complete(full_prompt)
        return response
```

---

## 📋 Critical Files to Read/Modify

### 읽을 파일
- [ ] `prototype_4/agent.py` - 전체 실행 로직
- [ ] `prototype_4/core/llm_planner.py` - 현재 planner 구조
- [ ] `prototype_4/core/llm_validator.py` - 검증 로직
- [ ] `prototype_4/tools/hybrid_tools.py` - 도구 구현

### 수정할 파일
- [ ] `prototype_5/core/fixed_workflow.py` (NEW)
- [ ] `prototype_5/core/reflection_planner.py` (RENAMED)
- [ ] `prototype_5/core/llm_validator.py` (ENHANCED)
- [ ] `prototype_5/tools/hybrid_tools.py` (ADD instruction params)
- [ ] `prototype_5/agent.py` (SIMPLIFY)

---

## ✅ 확정된 설계 결정

1. **Tool 내부 로직 수정 범위**: **옵션 B**
   - Tool 기본 로직 개선 (table + text 모두 수집)
   - instruction으로 세부 제어 ("어떤 text를 수집할지" 등)

2. **Instruction 누적 방식**: **누적**
   - 이전 instruction에 새로운 것 추가
   - 학습 히스토리 유지

3. **Reflection 횟수 제한**: **6회 유지**
   - `max_replan_per_task = 6`
