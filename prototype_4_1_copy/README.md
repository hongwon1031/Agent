# Prototype 4.1 Copy: 선형 Multi‑Agent 파이프라인 (Baseline)

`prototype_4_1_copy`는 **보험 상품 정의(보종명/유형 계층)**를 추출하고 Cartesian 조합을 생성하는
기존의 **선형 Multi‑Agent 파이프라인 버전**입니다.

`prototype_4_1`이 LangGraph 기반의 **상태 기계(State Machine)** 버전이라면,
`prototype_4_1_copy`는 그 이전 단계인 **직선형(Sequential) Planner + Validator + Tools 구조**를
보존한 “Baseline” 레퍼런스입니다.

---

## 1. 폴더 구조

- `agent.py`  
  - 메인 에이전트 `Prototype3Agent` 구현 (선형 파이프라인).
- `main.py`  
  - CLI 엔트리 포인트. JSON 파일/디렉터리를 받아 `Prototype3Agent`를 실행하고
    결과를 `prototype_4_1/results/`에 저장.
- `core/`  
  - `document_accessor.py` : 원본 JSON 문서에서 섹션 구조를 추출.
  - `llm_planner.py`       : LLM 기반 플래너 (plan / replan).
  - `llm_validator.py`     : 각 단계 출력에 대한 LLM 기반 Validator.
- `tools/`  
  - `hybrid_tools.py`      : 실제 일을 하는 도구들 집합  
    (`SectionClassifierTool`, `DefinitionExtractToolV2`,
     `RuleCartesianTool`, `LLMCartesianTool` 등).
- `results/`  
  - `main.py`를 통해 실행했을 때 생성되는 결과 JSON
    (경로는 `prototype_4_1/results`로 고정).
- `WORKFLOW.md`  
  - 이 버전에서 사용하는 워크플로우·실험 기록.

---

## 2. 전체 파이프라인 개요

이 버전의 에이전트는 **“계획 → 실행 → 검증 → 리플랜(replan)”** 루프를
선형으로 돌리면서 최종 정의 조합을 만듭니다.

### 2.1 실행 흐름 (high‑level)

1. **문서 로딩 (`main.py`)**
   - 입력: 보험 약관 JSON 파일 (또는 JSON이 여러 개 있는 디렉터리).
   - `load_document()`로 JSON을 읽고 `Prototype3Agent.run(doc)` 호출.

2. **섹션 추출 (`DocumentAccessor`)**
   - `agent.run()`에서:
     - `DocumentAccessor(doc)`를 생성하고 `get_all_sections()` 호출.
     - 각 Section 객체를 다음 형태의 dict로 변환해서 `sections` 리스트 구성:
       ```python
       {
         "index": section.index,
         "title": section.title,
         "content": section.content_items,
         "raw": section.metadata.get("original_element")
                or section.metadata.get("original_section")
                or section.metadata,
       }
       ```

3. **LLM Planner로 Plan 생성 (`LLMPlanner.create_plan`)**
   - 입력: `doc` (원본 JSON).
   - 출력: `plan = {"tasks": [...]}`  
   - 기본 V2 워크플로우 예시:
     - Task 1: `section_classifier` (type: `classify`)
     - Task 2: `definition_extract_v2` (type: `extract`, depends_on: 1)
     - Task 3: `rule_cartesian` (type: `transform`, depends_on: 2, fallback: `llm_cartesian`)

4. **Task 실행 루프 (`Prototype3Agent.run`)**
   - 각 Task에 대해 `_execute_task_with_replan(...)` 호출:
     1. 파라미터 해석 (`_resolve_parameters`)
        - `"{{task1.definition_core}}"` 같은 템플릿을
          `previous_results[1]["definition_core"]`로 치환.
        - `$sections`는 `DocumentAccessor`에서 만든 섹션 리스트로 치환.
     2. 도구 실행 (`tool.execute(doc, params)`)
     3. Validator 호출 → 결과 검증 (`LLMValidator.validate(...)`)
     4. 실패 시 `LLMPlanner.replan(...)` 호출 → 새로운 tool/parameters/instruction으로 교체
     5. 최대 `max_replan_per_task` 회까지 재시도

5. **최종 결과 반환**
   - 모든 Task 성공 시:
     - `previous_results` 중 마지막 Task의 결과를 `final_data`에 넣어 반환.
   - 실패 시:
     - `success = False`, `error` 메시지와 함께 `execution_log` 전체를 반환.
   - `main.py`에서 이 결과를
     `prototype_4_1/results/<stem>_prototype4_1_result.json`으로 저장.

---

## 3. 사용 도구 (Tools)

모든 도구는 `tools/hybrid_tools.py` 안에 구현되어 있고,
`Prototype3Agent.__init__`에서 등록됩니다.

```python
self.tools = {
    "section_classifier": SectionClassifierTool(),
    "definition_extract_v2": DefinitionExtractToolV2(),
    "rule_cartesian": RuleCartesianTool(),
    "llm_cartesian": LLMCartesianTool(),
}
```

### 3.1 SectionClassifierTool

- 역할: **문서의 모든 섹션을 의미 기반으로 4가지로 분류**
  - `definition_core`         : 상품 정의/명칭/보험종목 구조 테이블
  - `definition_annotation`   : 정의에 대한 주석/예외/보충 설명
  - `condition`               : 보험기간/가입나이/납입기간/납입주기 등 조건 테이블
  - `other`                   : 그 외 섹션
- 구현:
  - 각 섹션의 제목/내용 프리뷰를 LLM 프롬프트로 보내서
    JSON 형태의 분류 결과를 받습니다.

### 3.2 DefinitionExtractToolV2

- 입력:
  - `sections`: 전체 섹션 리스트
  - `core_indices`: `definition_core` 섹션 인덱스들
  - `annotation_indices`: `definition_annotation` 섹션 인덱스들
  - (옵션) `instruction`: Validator/Planner에서 넘긴 추가 지시사항
- 동작:
  1. `core_indices`에 해당하는 섹션에서 **base 테이블** 추출
     - 우선 Rule 기반(`RuleExtractTool`)으로 table_elements 파싱 시도.
     - 실패 시 LLM 기반(`LLMExtractTool`) 텍스트 파싱 시도.
  2. `annotation_indices`에 해당하는 섹션들의 텍스트를 모두 모아
     - base 테이블과 함께 LLM에 넘겨 **정의 테이블을 보정/병합**.
     - 예: “A형과 B형은 동일 취급한다” → A/B 통합,
       “특수형 제외” → 해당 행 제거 등.
- 출력:
  - `{"header": [...], "data": [...], "extraction_method": "v2_classifier_based"}`

### 3.3 RuleCartesianTool / LLMCartesianTool

- `RuleCartesianTool`
  - 슬래시(`/`), 쉼표(`,`) 등을 기준으로 셀 값을 분리하고,
    `itertools.product`로 **수학적으로 정확한 Cartesian product** 생성.
  - 규칙 기반이라 빠르고 예측 가능함.

- `LLMCartesianTool`
  - 먼저 LLM이 각 셀 값을 의미 단위 옵션 리스트로 파싱 (`parsed_rows`),
    그 후 Python에서 Cartesian product를 생성.
  - 컬럼별 primary delimiter 추론, 복잡한 값 분리/정규화에 강함.
  - Rule 버전이 실패하거나 Validator가 지적했을 때 fallback/대체로 사용.

---

## 4. Planner / Validator / Replan 구조

### 4.1 LLMPlanner (`core/llm_planner.py`)

- `create_plan(doc)`
  - 문서 설명/요약을 기반으로 어떤 Task를 어떤 순서로 실행할지 JSON plan 생성.
  - 현재는 사실상 **고정된 3단계 워크플로우**를 권장:
    - classify → extract → transform

- `replan(current_task, error_message, validation_result, attempts)`
  - 도구 실행 실패 또는 Validator 실패 시 호출.
  - 역할:
    - 같은 도구를 그대로 쓰되 `instruction`를 강화해서 재시도  
      (예: “주석 행을 데이터로 포함하지 말 것”,
      “원본 행 수와 일치하도록 추출할 것” 등).
    - transform 단계에서 `rule_cartesian` → `llm_cartesian` 전환 등 도구 교체.

### 4.2 LLMValidator (`core/llm_validator.py`)

- `validate(task_type, task_output, context)`
  - `task_type`에 따라 서로 다른 프롬프트로 결과를 검증:
    - `"classify"`  → 섹션 분류가 합리적인지 확인.
    - `"extract"`   → DefinitionExtractV2가 원본 테이블/주석을 잘 반영했는지 확인.
    - `"transform"` → Cartesian 결과에서 보종명/유형 조합의 중복, 잘린 값,
                     비정상 조합 등을 체크.
  - 반환:
    - `{"is_valid": bool, "confidence": float, "errors": [...], "suggestions": [...], "reasoning": "..."}`  
- Agent 쪽에서는:
  - `is_valid == False` 이면 `planner.replan(...)`에 이 정보를 넘겨서
    다음 시도에 사용할 `instruction`를 만들게 합니다.

---

## 5. `prototype_4_1` (LangGraph 버전)과의 차이

`prototype_4_1` 폴더에는 같은 도메인 로직을 **LangGraph 기반 상태 기계**로 옮긴 버전이 있습니다.
두 버전의 핵심 차이는 “**오케스트레이션 구조**”입니다.

| 항목                       | `prototype_4_1_copy`                              | `prototype_4_1` (LangGraph)                        |
|--------------------------|---------------------------------------------------|---------------------------------------------------|
| 에이전트 클래스              | `Prototype3Agent`                                | `Prototype4_1Agent`                               |
| 실행 방식                   | for 루프로 Task 순차 처리                         | LangGraph `StateGraph(AgentState)`               |
| 상태 관리                   | `previous_results` + 로컬 변수                    | `AgentState` TypedDict로 상태 공유               |
| replan 처리                | `_execute_task_with_replan` 내부에서 planner 호출  | 그래프의 `replan_or_finish` 노드에서 분기         |
| 백트래킹(이전 단계로 회귀)      | 논리적으로는 가능하나, 코드상은 “앞으로만 진행”       | 특정 노드로 점프하는 형태의 백트래킹 설계 가능          |
| 실행 로그                   | `execution_log` (task/attempt 단위)              | LangGraph 실행 로그 + state 변화 추적              |
| 사용 도구/플래너/밸리데이터      | 동일한 모듈 (`core/`, `tools/`) 공유               | 동일 (오케스트레이션만 다름)                             |

요약하자면:
- `prototype_4_1_copy`  : 선형 Multi‑Agent + Planner/Validator 루프 (현재 코드와 가장 직접적으로 매핑).
- `prototype_4_1`       : 같은 로직을 LangGraph로 옮겨
  **상태 기반 제어/시각화/백트래킹**을 할 수 있게 만든 버전.

두 버전의 결과 JSON은 형식이 유사하므로,
실험 결과를 비교할 때 서로 참고용으로 사용할 수 있습니다.

---

## 6. 실행 방법

```bash
cd Toy/prototype_4_1_copy

# 단일 파일
python main.py path/to/input.json

# 디렉터리 전체 (.json만)
python main.py path/to/input_dir
```

- 결과는 **항상**  
  `C:\Users\NT-165\Desktop\Project\Toy\prototype_4_1\results` 아래에  
  `<원본파일명>_prototype4_1_result.json` 형식으로 저장됩니다.

---

## 7. TODO / 개선 아이디어

- Planner / Validator 프롬프트를 정리하고, 공통 템플릿 모듈로 분리.
- DefinitionExtractV2의 annotation 병합 규칙을 더 명시적으로 다듬기  
  (equivalence / merge / exclude / informational 패턴 정교화).
- `prototype_4_1` LangGraph 버전과 동일한 테스트 셋으로 결과 비교 리포트 만들기.
- 장기적으로는 이 폴더의 로직을 점진적으로 LangGraph 버전에 통합하고,
  여기 폴더는 “실험용/역사적 레퍼런스”로 유지할지 여부 결정.

