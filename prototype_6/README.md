# Prototype 6: LangGraph-based Definition Extraction Agent

보험 약관/상품 설명서 JSON에서 **보종명/유형 계층 정의를 안정적으로 추출하고, 모든 조합을 생성**하기 위한
LangGraph 기반 Multi-Agent 파이프라인입니다.

Prototype 6은 기존 `prototype_4`의 선형 파이프라인을 **상태(State)를 공유하는 LangGraph 워크플로우**로
재구성한 버전입니다.

---

## 1. 전체 구조 개요

### 1.1 주요 책임

- 문서(JSON)에서 **섹션 구조 추출** (`DocumentAccessor`)
- 섹션을 의미 기반으로 **분류** (`SectionClassifierTool`)
- 분류 결과를 이용해 **정의 테이블 추출** (`DefinitionExtractToolV2`)
- 추출된 테이블에서 **모든 보종/유형 조합 생성** (`RuleCartesianTool` / `LLMCartesianTool`)
- 각 단계 결과를 **LLMValidator**로 검증하고, 문제가 있으면 **재계획(replan)**
- 이 모든 과정을 **LangGraph StateGraph**로 관리 (백트래킹/루프 포함)

### 1.2 주요 모듈

- `core/document_accessor.py`  
  - 원본 문서(JSON)를 다양한 포맷에서 통일된 `sections` 구조로 변환
- `core/state.py`  
  - LangGraph에서 사용하는 `AgentState` 정의 (공유 상태)
- `tools/hybrid_tools.py`  
  - `SectionClassifierTool`, `DefinitionExtractToolV2`, `RuleCartesianTool`, `LLMCartesianTool` 등 도구 구현
- `core/llm_planner.py`  
  - 초기 plan 생성 (`create_plan`) + 실패 시 재계획 (`replan`) 프롬프트/로직
- `core/llm_validator.py`  
  - classify / extract / transform 결과를 LLM으로 검증
- `agent.py`  
  - LangGraph `StateGraph(AgentState)`를 구성하는 노드/엣지 정의
- `main.py`  
  - CLI 엔트리포인트. JSON 파일(또는 디렉터리)을 읽어 agent를 실행하고 결과를 `results/`에 저장.

---

## 2. AgentState (공유 상태)

`core/state.py` 의 `AgentState`는 모든 노드가 공유하는 중앙 상태입니다:

- 입력/전역 정보
  - `original_doc: Any` – 원본 문서(JSON)
  - `sections: List[Dict]` – `DocumentAccessor`로 변환한 섹션 리스트
  - `initial_strategy: Optional[Dict]` – `LLMPlanner.create_plan` 결과 (현재는 참고용)
  - `current_instruction: Optional[str]` – replan 후, 다음 시도에 사용할 instruction
  - `tool_override: Optional[str]` – transform 단계에서 사용할 도구 강제 지정 (`"llm_cartesian"` 등)

- 단계별 출력
  - `classification_result: Optional[Dict]` – `section_classifier` 결과
  - `extraction_result: Optional[Dict]` – `definition_extract_v2` 결과 (`header`, `data`, `extraction_method`)
  - `combination_result: Optional[Dict]` – Cartesian 결과 (`definitions`, `total_count` 등)

- 검증/제어 메타데이터
  - `validation_feedback: Optional[Dict]` – `LLMValidator`의 최신 검증 결과
  - `replan_count: int` – replan 시도 횟수 (무한 루프 방지)
  - `last_executed_task: Optional[str]` – 마지막으로 실행한 Task 타입 (`"classify"`, `"extract"`, `"combine"`)
  - `execution_log: Optional[List]` – 각 노드 실행 기록 (tool, params 등)

- 최종 결과
  - `final_data: Optional[Any]` – 최종 결과 (Prototype6Agent.run에서는 `combination_result`를 반환)
  - `error: Optional[str]` – 치명적 에러 메시지

---

## 3. LangGraph 워크플로우 (agent.py)

### 3.1 노드 개요

`agent.py`에서 LangGraph `StateGraph(AgentState)`를 사용해 다음 노드들을 정의합니다.

1. `initialize_state`
   - `original_doc`를 읽어 `DocumentAccessor`로 `sections` 생성
   - `AgentState`에 `sections`, `replan_count = 0`, `execution_log = []` 설정

2. `plan_initial_strategy`
   - `LLMPlanner.create_plan(doc)` 호출
   - 결과를 `initial_strategy`에 저장  
   - 현재 그래프 흐름에서는 **직접적인 제어에는 사용하지 않고**, 향후 고급 전략/분기용으로 보존

3. `classify_sections`
   - 도구: `SectionClassifierTool`
   - 입력:
     - `sections`
     - (선택) `current_instruction` – replan 에서 내려온 추가 지시
   - 출력:
     - `classification_result` (keys: `definition_core`, `definition_annotation`, `condition`, `other`, `reasoning`)
     - `last_executed_task = "classify"`
     - `execution_log`에 실행 기록 추가
   - 실패 시:
     - `validation_feedback = {"is_valid": False, "errors": [result.error]}` 로 세팅 후, `replan` 경로로 이동

4. `extract_definitions`
   - 도구: `DefinitionExtractToolV2`
   - 입력:
     - `sections`
     - `classification_result.definition_core` / `definition_annotation`
     - (선택) `current_instruction` – replan에서 내려온 추출 기준
   - 출력:
     - `extraction_result` (예: `{"header": [...], "data": [...], "extraction_method": "v2_classifier_based"}`)
     - `last_executed_task = "extract"`
     - `execution_log` 갱신
   - 실패 시: 마찬가지로 `validation_feedback`에 실패 내용 기록

5. `create_combinations`
   - 도구: 기본 `RuleCartesianTool`, fallback `LLMCartesianTool`
   - 입력:
     - `extraction_result.header`, `extraction_result.data`
     - (선택) `current_instruction` – transform 실패 후 재시도 지시
     - (선택) `tool_override` – planner.replan 이 강제로 `"llm_cartesian"` 등을 지정했을 때 사용
   - 동작:
     - `tool_override`가 있으면 해당 도구로 바로 실행
     - 없으면 `rule_cartesian` 먼저 실행, 실패하면 한 번 `llm_cartesian`으로 자동 fallback
   - 출력:
     - `combination_result` (예: `{"definitions": [...], "total_count": ...}`)
     - `last_executed_task = "combine"`
     - `execution_log` 갱신

6. `validate_step`
   - 도구: `LLMValidator`
   - 입력:
     - `last_executed_task` 에 따라 서로 다른 output/context를 구성
       - `classify` → `classification_result` + `all_sections`
       - `extract` → `extraction_result` + `core_sections` / `annotation_sections` / `definition_sections`
       - `combine` → `combination_result` + `extracted_data = extraction_result`
   - 출력:
     - `validation_feedback` (keys: `is_valid`, `confidence`, `errors`, `suggestions`, `reasoning`)

7. `replan_or_finish`
   - 도구: `LLMPlanner.replan`
   - 입력:
     - `failed_task` 정보 (`last_executed_task`와 이전 시도 로그)
     - `error_message` 또는 `validation_result.errors`
     - `previous_attempts` (execution_log 기반)
   - 동작:
     - planner.replan 이 반환한 JSON에서
       - `parameters.instruction` → `current_instruction`로 저장
       - (선택) `tool_name` → `tool_override`로 저장 (transform 단계에서 어떤 도구를 쓸지 강제)
     - `replan_count` 증가
     - `validation_feedback` 초기화
   - 출력:
     - 업데이트된 `replan_count`, `current_instruction`, `tool_override`

### 3.2 엣지(조건부 흐름)

1. `should_continue(state: AgentState) -> str`
   - `validate_step` 이후의 라우터
   - 로직:
     - `error`가 있으면 → `"end"`
     - `validation_feedback.is_valid == True` 이면:
       - `last_executed_task == "classify"` → `"extract_definitions"`
       - `last_executed_task == "extract"` → `"create_combinations"`
       - `last_executed_task == "combine"` → `"end"`
     - 그 외 (검증 실패) → `"replan_or_finish"`

2. `after_replan(state: AgentState) -> str`
   - `replan_or_finish` 이후의 라우터 (백트래킹)
   - 기본 정책: **마지막으로 실패한 단계로 되돌아가기**
     - `"classify"` → `"classify_sections"`
     - `"extract"` → `"extract_definitions"`
     - `"combine"` → `"create_combinations"`
     - 기타/에러 → `"end"`
   - 향후에는 planner.replan이 “어느 단계로 점프해야 할지”까지 반환하도록 확장 가능.

### 3.3 그래프 구성 요약

`build_graph()`:

- 노드 등록:
  - `initialize_state` → `plan_initial_strategy` → `classify_sections`
  - 이후 `classify_sections` / `extract_definitions` / `create_combinations` → 항상 `validate_step`으로 이동
  - `validate_step` → `should_continue` 로 결정 (다음 단계 또는 `replan_or_finish` 또는 `END`)
  - `replan_or_finish` → `after_replan` 로 결정 (백트래킹 또는 `END`)

- `Prototype6Agent.run(doc)`:
  - 입력: `{"original_doc": doc}`
  - `graph.stream(inputs)`로 전체 실행과 intermediate state 로그(`full_log`) 수집
  - 최종 상태의 `combination_result`를 `final_data`로 반환

---

## 4. LLMPlanner 역할 (core/llm_planner.py)

### 4.1 `create_plan`

`create_plan(doc, goal)`은 현재:

- `DocumentAccessor` 요약 + Tool schemas(`tool_schemas.get_schema_prompt()`)를 프롬프트에 넣고
- “3단계 (classify → extract → transform) 계획”을 LLM에 요청합니다.
- 반환된 `tasks` 구조는 현재 LangGraph 흐름에서는 직접 사용하지 않고, 
  `plan_initial_strategy` 노드가 `initial_strategy`에 저장만 합니다.

향후에는:

- `AgentState.initial_strategy`에 담긴 plan을 이용해
  - 특정 문서 유형에서 transform 단계 도구 선택 전략(rule vs llm)
  - 추가적인 검증/보조 노드를 graph에 붙이는 등의 **동적 그래프 구성**에도 활용할 수 있습니다.

### 4.2 `replan`

`replan(failed_task, error_message, validation_result, previous_attempts)`는:

- 실패한 task / validation 피드백 / 이전 시도 로그를 JSON으로 LLM에 넘겨
  - 어떤 도구를 쓸지 (`tool_name`)
  - 어떤 instruction을 추가/수정할지 (`parameters.instruction`)
  - 변경 이유 (`reasoning`, `changes`) 를 생성하게 합니다.

현재 LangGraph 에서는:

- `agent.replan_or_finish` 노드가 `replan`의 결과에서
  - `parameters.instruction` → `state.current_instruction`
  - `tool_name` → `state.tool_override`
  만 사용하고 있습니다.
- 이 값들은 다음 사이클의 노드(`classify_sections` / `extract_definitions` / `create_combinations`)에서
  - tool 파라미터/선택에 반영됩니다.

---

## 5. Validator 역할 (core/llm_validator.py)

### 5.1 validate

`LLMValidator.validate(task_type, task_output, context)`는 task_type에 따라:

- `"classify"` → `validate_section_classifier_llm`
- `"extract"` → `validate_definition_extract_v2_llm` (extraction_method == "v2_classifier_based")
- `"transform"` → `validate_transform`

을 호출하여 구조적/품질 검증을 수행합니다.

### 5.2 DefinitionExtractV2 검증

`validate_definition_extract_v2_llm`는:

- context.definition_sections (core + annotation 섹션들)을 샘플로 보여주고,
- ExtractV2 의 header/data가
  - 비어 있지 않고,
  - 원본 core 섹션 테이블과 크게 어긋나지 않으며,
  - 주석 행이 데이터로 잘못 포함되지 않았는지 등을 LLM으로 체크합니다.

이는 “추출기가 원본을 크게 망가뜨리지 않았는지”를 보는 레벨이며,
annotation 해석에 대한 완전한 정답을 강제하기보다는 **명백한 구조적 오류**를 잡는 데 초점을 둡니다.

### 5.3 Transform 검증

`validate_transform`는 Cartesian 결과에 대해:

- 보종명 잘림, 중복된 (보종명, 유형1, 유형2) 조합,
- 명백한 행 수 이상/이하 여부 등을 체크합니다.

이 피드백은 `replan_or_finish` → `planner.replan`을 통해
다음 시도의 instruction/도구 선택에 반영됩니다.

---

## 6. TODO / 개선 아이디어

이 섹션은 실제 코드/실험을 하면서 발견한 개선 포인트를 기록하는 용도입니다.

1. **LLM 클라이언트/환경 설정 공통화**
   - 현재 여러 곳에서 `load_dotenv` / `OpenAI(api_key=...)`를 반복 호출합니다.
   - `core/llm_client.py` 같은 유틸 모듈로 클라이언트 생성/환경 로딩을 공통화하면
     설정 변경/테스트가 쉬워집니다.

2. **프롬프트 텍스트 분리**
   - 긴 프롬프트들이 `llm_planner.py`, `llm_validator.py`, `tools/hybrid_tools.py` 안에 하드코딩되어 있습니다.
   - `core/prompts/` 디렉터리로 템플릿을 분리하면
     - 프롬프트 실험,
     - 버전 관리,
     - 언어/도메인 변경이 훨씬 관리하기 쉬워집니다.

3. **LangGraph Checkpointer 도입**
   - 현재 `Prototype6Agent.run`은 `graph.stream` 결과만 `full_log`로 반환합니다.
   - LangGraph의 checkpointer(예: `MemorySaver`, `SqliteSaver`)를 붙이면
     - 노드별 state를 run_id 단위로 저장/재현할 수 있어
     - 디버깅/리그레션 테스트가 쉬워집니다.

4. **replan → 그래프 레벨 통합**
   - 지금은 `replan_or_finish` 노드에서 `planner.replan`의 일부 정보만 사용합니다.
   - 향후에는 `replan` 결과에 “다음으로 갈 노드 이름”까지 포함시켜,
     더 유연한 백트래킹/점프(예: extract 실패 → classify로 직접 점프)를 지원할 수 있습니다.

5. **DefinitionExtractV2 / Validator 정교화**
   - annotation 해석 (equivalence / merge / exclude / informational)에 대한 규칙을
     ExtractV2와 Validator 양쪽에 조금 더 명시적으로 나누면,
     - Extract는 “원본 + annotation을 반영한 테이블”
     - Cartesian/Transform는 “조합/계층 구조 확장” 역할에 집중할 수 있습니다.

6. **Definition + Condition 통합 파이프라인 확장**
   - Condition 섹션용 `ConditionExtractTool(V2)` 추가  
     - `condition` 섹션에서 `유형1/유형2/보험기간/납입기간/가입나이/납입주기` 등 조건 테이블을 추출
   - Definition 테이블과 Condition 테이블을 조합하는 Transform 툴 설계  
     - 예: `DefinitionConditionMergeTool`  
     - 정의 쪽 보종명/유형1/유형2와, 조건 쪽 유형 컬럼(유형1/유형2/심사형 등)을 join key로 사용
   - 유형 축 매핑 규칙 정의  
     - 헤더 문자열 규칙(“보험종목”, “유형1”, “심사형” 등)으로 1차 매핑  
     - 애매한 경우 LLM으로 definition/condition 헤더를 정렬(column alignment)
   - 최종 스키마 구조 확정  
     - 한 행이 “정의 + 조건”이 합쳐진 완전한 상품 조합이 되도록  
     - 예: `보종명, 유형1, 유형2, 보험기간, 납입기간, 가입나이_남, 가입나이_여, 납입주기, ...`
   - Validator 확장 (`validate_transform`)  
     - 정의×조건 join 시 보종명/유형/조건 축 누락·중복·잘린 값 검증  
     - 정의 조합 개수 대비 조건 매핑 개수가 비정상적으로 적거나 많은 경우 에러로 보고하여 replan 유도


---

## 7. 실행 방법 요약

```bash
cd Toy/prototype_6
python main.py path/to/input.json

# 또는 디렉터리 전체 처리
python main.py path/to/input_dir
```

결과는 `results/<원본파일명>_prototype6_result.json`으로 저장됩니다.  
파일에는 `success`, `final_data`(definitions), `full_log`(LangGraph 실행 로그) 등이 포함됩니다.

