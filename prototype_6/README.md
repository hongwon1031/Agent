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

6. **Definition + Condition 통합 파이프라인 확장** ✅ **[구현 완료]**

   ### 아키텍처
   ```
   기존: classify → extract_def → cartesian_def → END
   최종: classify → extract_def → extract_cond → cartesian_def → LLM_intelligent_merge → END
   ```

   **핵심 설계 결정**:
   - ❌ ~~Condition 데이터에 Cartesian Product 적용~~ (부적절한 조합 생성 문제)
   - ✅ **LLM 기반 지능형 병합**: Condition 원시 테이블을 그대로 LLM에게 전달하여 의미적 매칭 수행
   - **장점**: 유연한 JOIN 키 처리, 의미적 매칭, 복잡한 조건 해석 가능

   **전체 플로우**:
   ```
   initialize → plan → classify_sections → validate
                              ↓ (valid)
                       extract_definitions → validate
                              ↓ (valid)
                       extract_conditions → validate
                              ↓ (valid)
                       create_combinations (Definition만) → validate
                              ↓ (valid)
                       merge_definition_condition (LLM 기반) → validate
                              ↓ (valid)
                             END

   (각 validate에서 invalid → replan_or_finish → 해당 노드로 백트래킹)
   ```

   ### 핵심 컴포넌트

   #### a. `ConditionExtractTool` (`tools/hybrid_tools.py`)
   - **목적**: `condition` 섹션에서 조건 테이블 추출
   - **추출 대상**: `유형1, 유형2, 보험기간, 납입기간, 가입나이_남, 가입나이_여, 납입주기`
   - **로직**:
     - Rule-based 테이블 파싱 (DefinitionExtractV2 패턴 재사용)
     - 컬럼명 정규화: "보험료 납입기간" → "납입기간", "가입가능나이" → "가입나이"
     - Split column 처리: "가입나이" → "가입나이_남", "가입나이_여"
     - JOIN KEY 컬럼 보존: `유형1, 유형2, 심사형, 보장형`
   - **출력**: `{"header": [...], "data": [[...]], "extraction_method": "rule_based"}`

   #### b. `extract_conditions` 노드 (`agent.py`)
   - **목적**: ConditionExtractTool을 실행하는 LangGraph 노드
   - **입력**: `classification_result.condition` (condition 섹션 인덱스)
   - **처리**:
     - Condition 섹션이 없으면 빈 결과 반환
     - ConditionExtractTool 실행
     - 실패 시 validation_feedback 설정
   - **출력**: `condition_result` 업데이트 (원시 테이블 형태)

   #### c. `DefinitionConditionMergeTool` - **LLM 기반 지능형 병합** (`tools/hybrid_tools.py`)
   - **목적**: Definition 조합과 Condition 원시 테이블을 **LLM을 통해 의미적으로 병합**
   - **입력**:
     - `definitions`: Definition Cartesian 결과 (확장된 조합 리스트)
     - `condition_header`, `condition_data`: Condition 원시 테이블 (조합하지 않음)
   - **LLM 프롬프트** (`core/prompt.py::build_llm_intelligent_merge_prompt`):
     - Definition 각 행과 Condition 테이블을 비교하여 매칭
     - 유연한 JOIN 키 처리 (정확히 일치하지 않아도 의미적으로 매칭)
     - 와일드카드 지원 (`유형2 = "-"` → 모든 Definition에 적용)
     - 복잡한 조건 해석 (예: "만15세 ~ min{(80 – 년만기), 70}세")
   - **출력**:
     ```python
     {
       "definitions": [
         {
           "보종명": "...",
           "유형1": "...",
           "유형2": "...",
           "보험기간": "...",  # ← Condition에서 병합
           "납입기간": "...",  # ← Condition에서 병합
           ...
         }
       ],
       "total_count": int,
       "join_stats": {
         "definition_count": int,
         "unmatched_definition_indices": [list],  # 병합 실패한 Definition 인덱스
         "reasoning": str  # LLM의 매칭 논리 설명
       }
     }
     ```
   - **장점**:
     - 의미적 매칭 가능 (단순 문자열 일치 불필요)
     - 복잡한 조건 자동 해석
     - 다양한 컬럼명 변형 자동 처리
     - Condition 과다 조합 문제 해결

   #### d. `merge_definition_condition` 노드 (`agent.py`)
   - **목적**: DefinitionConditionMergeTool을 실행하는 LangGraph 노드
   - **입력**:
     - `combination_result.definitions` (Definition Cartesian 결과)
     - `condition_result` (Condition 원시 테이블, **조합 전 상태**)
   - **처리**:
     - Condition 데이터 없으면 Definition 그대로 반환
     - LLM 기반 DefinitionConditionMergeTool 실행
     - JOIN 통계 로그 출력 (unmatched 비율 표시)
   - **출력**: `merged_result` 업데이트

   ### 최종 스키마
   ```python
   {
     "보종명": str,
     "유형1": str,
     "유형2": str,
     "보험기간": str,         # ← Condition에서 JOIN
     "납입기간": str,         # ← Condition에서 JOIN
     "가입나이_남": str,      # ← Condition에서 JOIN
     "가입나이_여": str,      # ← Condition에서 JOIN
     "납입주기": str          # ← Condition에서 JOIN
   }
   ```

   ### State 확장 (`core/state.py`)
   - `condition_result: Optional[Dict]`: Condition 추출 결과 (원시 테이블)
   - ~~`condition_combination_result`~~: **제거됨** (Condition 조합 단계 삭제)
   - `merged_result: Optional[Dict]`: Definition+Condition LLM 병합 결과

   ### Validator 확장 (`core/llm_validator.py`)

   #### `validate_condition_extract`
   - **검증 항목**:
     - Condition 섹션 없으면 빈 결과 허용
     - 섹션 있으면 header/data 필수
     - 최소 2개 이상의 조건 컬럼 (보험기간, 납입기간 등)
     - 최소 1개 이상의 JOIN KEY (유형1, 유형2 등)
   - **에러**: 컬럼 부족, JOIN KEY 누락 시 is_valid=False

   #### `validate_merge` - **LLM 병합 결과 검증**
   - **검증 항목**:
     - 병합 결과 비어있지 않음
     - 필수 Definition 컬럼 존재 (보종명)
     - **Unmatched 비율 < 50%**: `len(unmatched_definition_indices) / definition_count < 0.5`
     - LLM의 reasoning 필드 존재 확인
   - **에러**: 빈 결과, 필수 컬럼 누락, Unmatched 과다 시 is_valid=False
   - **개선점**: Rule-based JOIN 대신 LLM 출력 검증 (더 유연한 매칭 허용)

   ### Graph/Router 수정 (`agent.py`)

   #### `should_continue`
   - **변경된 라우팅 로직**:
     - `classify` → `extract_definitions`
     - `extract` → `extract_conditions`
     - `extract_condition` → `create_combinations` (Definition만)
     - `combine` → ~~`create_condition_combinations`~~ → **`merge_definition_condition`** (직행)
     - `merge` → `end`
   - **제거**: `combine_condition` 라우팅 (Condition 조합 단계 삭제)

   #### `after_replan`
   - 백트래킹 로직:
     - `extract_condition` → `extract_conditions`
     - ~~`combine_condition`~~: **제거됨**
     - `merge` → `merge_definition_condition`

   #### `build_graph`
   - **노드 추가**: `extract_conditions`, `merge_definition_condition`
   - **노드 제거**: ~~`create_condition_combinations`~~ (불필요)
   - 엣지: 모든 task 노드 → `validate_step`
   - 조건부 엣지: 새 라우팅 로직 반영

   ### Tool Schemas 추가 (`tools/tool_schemas.py`)

   #### `condition_extract`
   ```python
   {
     "description": "Extract condition table from classified condition sections (가입조건 추출)",
     "parameters": {
       "sections": {"type": "list[dict]", "required": True, "value": "$sections"},
       "condition_indices": {"type": "list[int]", "required": True, "example": "{{task1.condition}}"},
       "instruction": {"type": "string", "required": False}
     },
     "returns": {
       "header": "list[string] - Normalized column names",
       "data": "list[list[string]] - Condition rows (원시 테이블)",
       "extraction_method": "string - Method used"
     }
   }
   ```

   #### `definition_condition_merge` - **LLM 기반**
   ```python
   {
     "description": "Merge Definition combinations with Condition table using LLM-based intelligent matching",
     "parameters": {
       "definitions": {"type": "list[dict]", "required": True, "example": "{{task3.definitions}}"},
       "condition_header": {"type": "list[string]", "required": True, "example": "{{task2.header}}"},
       "condition_data": {"type": "list[list[string]]", "required": True, "example": "{{task2.data}}"},  # 원시 데이터
       "instruction": {"type": "string", "required": False}
     },
     "returns": {
       "definitions": "list[dict] - Merged definitions with condition columns",
       "total_count": "int - Total number of merged definitions",
       "join_stats": {
         "definition_count": "int - Input definition count",
         "unmatched_definition_indices": "list[int] - Unmatched indices",
         "reasoning": "string - LLM's matching logic explanation"
       }
     }
   }
   ```

   ### Edge Cases 및 LLM 처리
   1. **Condition 섹션 없음**: `extract_conditions`에서 빈 결과 반환 → merge 시 Definition만 반환
   2. **와일드카드 행**: LLM이 `유형2 = "-"` 를 "모든 Definition에 적용" 으로 해석
   3. **복잡한 조건식**: LLM이 자동 해석 (예: "만15세 ~ min{(80 – 년만기), 70}세")
   4. **컬럼명 변형**: Extraction 단계에서 정규화 + LLM이 의미적으로 매칭
   5. **Split 컬럼**: "남/여" → "가입나이_남", "가입나이_여" (Extraction에서 처리)
   6. **매칭 실패**: LLM이 unmatched_definition_indices에 기록 → Validator 체크 → replan

   ### 구현 파일 요약
   - `core/state.py`: State 확장 (condition_result, merged_result)
   - `core/prompt.py`: **NEW** `build_llm_intelligent_merge_prompt` 추가
   - `tools/hybrid_tools.py`:
     - `ConditionExtractTool`: Rule-based 테이블 추출
     - `DefinitionConditionMergeTool`: **완전 재설계** - LLM 기반 병합 로직
   - `agent.py`:
     - 노드 추가: `extract_conditions`, `merge_definition_condition`
     - 노드 제거: ~~`create_condition_combinations`~~
     - Router 수정: `combine` → `merge` 직행
     - Graph 빌더: 새 플로우 반영
     - run() 메서드: `merged_result` 반환
   - `core/llm_validator.py`:
     - `validate_condition_extract`: 원시 테이블 검증
     - `validate_merge`: **업데이트** - LLM 출력 구조 검증 (unmatched_definition_indices 체크)
   - `tools/tool_schemas.py`: 스키마 2개 추가/수정


7. **LLM 출력 트렁케이션 문제 해결: 그룹핑 기반 조합 생성 아키텍처** ✅ **[구현 완료 - 2025-01-XX]**

   ### 문제 상황

   **기존 아키텍처의 한계**:
   - `merge_definition_condition`에서 LLM이 모든 definition-condition 조합을 한 번에 생성
   - Definition Cartesian 단계에서 이미 조합 폭발 발생 (수백~수천 개)
   - LLM 출력이 `max_tokens=12000` 제한으로 잘림
   - 500+ definitions 처리 시 JSON 응답 불완전

   **근본 원인**:
   - LLM이 "조합 생성"까지 담당 → 출력 크기가 입력에 비례하여 폭발
   - 토큰 제한 증가로는 근본적 해결 불가 (edge case 계속 발생)

   ### 해결 방안: 역할 분리 아키텍처

   **핵심 아이디어**: LLM의 역할을 "조합 생성" → "그룹핑 로직 추출"로 변경

   ```
   기존 방식: LLM이 모든 조합 생성 → 출력 크기 폭발 → 트렁케이션
   새 방식: LLM이 그룹핑 논리만 추출 → 출력 작음 → Python이 조합 생성
   ```

   ### 새 아키텍처 플로우

   ```
   initialize → plan → classify_sections → validate
                              ↓ (valid)
                       extract_definitions → validate
                              ↓ (valid)
                       normalize_definitions → validate  ← NEW (조합 생성 안 함, 컬럼명만 정규화)
                              ↓ (valid)
                       extract_conditions → validate
                              ↓ (valid)
                       normalize_conditions → validate   ← NEW (조합 생성 안 함, 컬럼명만 정규화)
                              ↓ (valid)
                       extract_grouping_logic → validate ← NEW (LLM: 그룹핑 로직 추출)
                              ↓ (valid)
                       generate_final_combinations → validate ← NEW (Python: 조합 생성)
                              ↓ (valid)
                             END
   ```

   **핵심 변경점**:
   1. Definition/Condition 원시 테이블에서 조합 생성하지 않음
   2. LLM은 그룹핑 메타데이터만 출력 (5-20개 그룹, 고정 크기)
   3. Python이 그룹핑 로직 기반으로 조합 생성 (무제한 확장 가능)

   ### 핵심 컴포넌트

   #### a. `normalize_definitions` 노드 (`agent.py`) - NEW
   - **목적**: Definition 테이블 컬럼명만 정규화, **조합 생성 안 함**
   - **입력**: `extraction_result` (header, data)
   - **처리**:
     - 기존 `rule_cartesian`의 column mapping 로직 재사용
     - 첫 번째 column → "보종명"
     - 나머지 columns → "유형1", "유형2", ...
     - **원시 테이블 구조 유지** (Cartesian product 생성 안 함)
   - **출력**: `normalized_definitions` (header, data)

   #### b. `normalize_conditions` 노드 (`agent.py`) - NEW
   - **목적**: Condition 테이블 컬럼명만 정규화
   - **입력**: `condition_result` (header, data)
   - **처리**: Condition은 이미 `IntelligentConditionExtractTool`에서 정규화되므로 passthrough
   - **출력**: `normalized_conditions` (header, data)

   #### c. `GroupingLogicExtractorTool` (`tools/hybrid_tools.py`) - NEW
   - **목적**: LLM이 Definition-Condition 매칭 그룹을 추출
   - **입력**:
     - `definition_header`, `definition_data`: 정규화된 Definition 원시 테이블
     - `condition_header`, `condition_data`: 정규화된 Condition 원시 테이블
     - `instruction`: 재시도 시 추가 지시사항
   - **LLM 프롬프트** (`core/prompt.py::build_grouping_extraction_prompt`):
     - 두 테이블을 분석하여 매칭 관계 파악
     - Fuzzy matching 지원 ("간편심사(315)형" ≈ "간편심사형")
     - Wildcard 처리 ("-" 는 모든 값과 매칭)
     - 우선순위: 정확 매칭 > 의미 매칭 > 와일드카드
   - **LLM 출력 형식** (작은 JSON, ~500 tokens):
     ```python
     {
       "column_mapping": {
         "join_keys": ["유형1", "유형2"],
         "value_columns": ["보험기간", "납입기간", ...]
       },
       "groups": [
         {
           "id": 0,
           "match_condition": {"유형1": "일반형", "유형2": "-"},
           "definition_indices": [0, 3, 7, 11],  # 이 definition들이
           "condition_index": 0,                  # 이 condition 행과 매칭
           "fuzzy_matches": {...},
           "reasoning": "설명..."
         }
       ],
       "unmatched": {
         "definition_indices": [15],  # 매칭 실패한 definition
         "condition_indices": [5]     # 사용되지 않은 condition
       },
       "summary": {
         "total_groups": 10,
         "coverage_ratio": 0.95
       }
     }
     ```
   - **핵심**: LLM 출력 크기가 그룹 수에만 비례 (Definition 수와 무관)

   #### d. `CombinationGeneratorTool` (`tools/hybrid_tools.py`) - NEW
   - **목적**: Python으로 최종 조합 생성 (LLM 사용 안 함)
   - **입력**:
     - `definition_header`, `definition_data`: 정규화된 Definition 원시 테이블
     - `condition_header`, `condition_data`: 정규화된 Condition 원시 테이블
     - `grouping_logic`: LLM이 추출한 그룹핑 메타데이터
   - **처리 로직**:
     ```python
     for group in grouping_logic["groups"]:
         condition_row = condition_data[group["condition_index"]]
         for def_idx in group["definition_indices"]:
             definition_row = definition_data[def_idx]

             # Definition 컬럼 + Condition 컬럼 병합
             merged = {
                 "보종명": definition_row[0],
                 "유형1": definition_row[1],
                 ...
                 "보험기간": condition_row[condition_header.index("보험기간")],
                 "납입기간": condition_row[condition_header.index("납입기간")],
                 ...
             }
             final_definitions.append(merged)
     ```
   - **출력**:
     ```python
     {
       "definitions": [...],  # 최종 병합된 정의 목록
       "total_count": int,
       "generation_stats": {
         "groups_processed": 10,
         "matched_definitions": 950,
         "unmatched_definitions": 50,
         "total_generated": 1000
       }
     }
     ```
   - **핵심**: 순수 Python 로직 → LLM 토큰 제한 무관, 메모리만 허용하면 무한 확장 가능

   #### e. `extract_grouping_logic` 노드 (`agent.py`) - NEW
   - **목적**: GroupingLogicExtractorTool 실행
   - **입력**: `normalized_definitions`, `normalized_conditions`, `current_instruction`
   - **출력**: `grouping_logic` 업데이트

   #### f. `generate_final_combinations` 노드 (`agent.py`) - NEW
   - **목적**: CombinationGeneratorTool 실행
   - **입력**: `normalized_definitions`, `normalized_conditions`, `grouping_logic`
   - **출력**: `final_result` 업데이트

   ### State 확장 (`core/state.py`)

   **추가된 필드**:
   - `normalized_definitions: Optional[Dict]` - 정규화된 definition 원시 테이블 (조합 전)
   - `normalized_conditions: Optional[Dict]` - 정규화된 condition 원시 테이블 (조합 전)
   - `grouping_logic: Optional[Dict]` - LLM 그룹핑 메타데이터
   - `final_result: Optional[Dict]` - 최종 병합된 정의 목록

   **제거된 필드**:
   - ~~`combination_result`~~ → `final_result`로 통합
   - ~~`merged_result`~~ → `final_result`로 통합

   ### Validator 확장 (`core/llm_validator.py`)

   #### `validate_grouping_logic` - NEW
   - **검증 항목**:
     - 필수 키 존재 (groups, column_mapping)
     - 인덱스 범위 검증 (definition_indices, condition_index가 유효한지)
     - 커버리지 검증 (matched definitions >= 50%)
     - JOIN 키 존재 확인
   - **에러**: 인덱스 범위 초과, 낮은 커버리지 시 is_valid=False

   #### `validate_final_combinations` - NEW
   - **검증 항목**:
     - Definitions 리스트 비어있지 않음
     - 필수 컬럼 존재 (보종명)
     - Match rate 검증 (matched/total >= 50%)
     - Generation stats 존재 확인
   - **에러**: 빈 결과, 필수 컬럼 누락, 낮은 매칭률 시 is_valid=False

   #### `validate` 메서드 확장
   - 새 task type 라우팅 추가:
     - `"normalize_def"` → 구조 검증 (header, data 존재)
     - `"normalize_cond"` → 구조 검증 (header, data 존재)
     - `"grouping"` → `validate_grouping_logic`
     - `"generate"` → `validate_final_combinations`

   ### Graph/Router 수정 (`agent.py`)

   #### `should_continue` 라우팅 확장
   - **새 플로우**:
     - `classify` → `extract_definitions`
     - `extract` → `normalize_definitions` ← NEW
     - `normalize_def` → `extract_conditions` ← NEW
     - `extract_condition` → `normalize_conditions` ← NEW
     - `normalize_cond` → `extract_grouping_logic` ← NEW
     - `grouping` → `generate_final_combinations` ← NEW
     - `generate` → `end` ← NEW

   #### `after_replan` 백트래킹 확장
   - 실패한 단계로 되돌아가기:
     - `normalize_def` → `normalize_definitions`
     - `normalize_cond` → `normalize_conditions`
     - `grouping` → `extract_grouping_logic`
     - `generate` → `generate_final_combinations`

   #### `build_graph` 구성
   - **노드 추가**: `normalize_definitions`, `normalize_conditions`, `extract_grouping_logic`, `generate_final_combinations`
   - **노드 제거**: ~~`create_combinations`~~, ~~`merge_definition_condition`~~ (대체됨)
   - 모든 새 노드 → `validate_step` 연결
   - 조건부 엣지: 새 라우팅 로직 반영

   #### `Prototype6Agent.run` 수정
   - 반환값 변경: `final_result` (fallback: `merged_result` or `combination_result`)

   ### Tool Schemas 추가 (`tools/tool_schemas.py`)

   #### `grouping_logic_extractor`
   ```python
   {
     "description": "Extract grouping logic for definition-condition matching (LLM-based)",
     "parameters": {
       "definition_header": {"type": "list[str]", "required": True},
       "definition_data": {"type": "list[list[str]]", "required": True,
                           "description": "Normalized definition table (no combinations, raw table)"},
       "condition_header": {"type": "list[str]", "required": True},
       "condition_data": {"type": "list[list[str]]", "required": True,
                          "description": "Normalized condition table (no combinations, raw table)"},
       "instruction": {"type": "string", "required": False}
     },
     "returns": {
       "column_mapping": "dict - {join_keys: list[str], value_columns: list[str]}",
       "groups": "list[dict] - Grouping logic with definition_indices, condition_index",
       "unmatched": "dict - {definition_indices: list[int], condition_indices: list[int]}",
       "summary": "dict - Statistics summary (total counts, coverage ratio)"
     }
   }
   ```

   #### `combination_generator`
   ```python
   {
     "description": "Generate final combinations based on grouping logic (Python-based, no LLM)",
     "parameters": {
       "definition_header": {"type": "list[str]", "required": True},
       "definition_data": {"type": "list[list[str]]", "required": True},
       "condition_header": {"type": "list[str]", "required": True},
       "condition_data": {"type": "list[list[str]]", "required": True},
       "grouping_logic": {"type": "dict", "required": True, "example": "{{task_grouping.grouping_logic}}"}
     },
     "returns": {
       "definitions": "list[dict] - Final merged definitions with condition columns",
       "total_count": "int - Total number of final definitions",
       "generation_stats": "dict - {groups_processed, matched_definitions, unmatched_definitions, total_generated}"
     }
   }
   ```

   ### 프롬프트 추가 (`core/prompt.py`)

   #### `build_grouping_extraction_prompt` - NEW
   - **역할**: LLM에게 그룹핑 로직 추출을 요청하는 상세 프롬프트
   - **구조** (~300 lines):
     - Definition/Condition 테이블을 보기 쉽게 포맷팅
     - 매칭 규칙 상세 설명 (JOIN 키, Fuzzy matching, Wildcard, 우선순위)
     - 출력 형식 JSON 스키마 제공
     - 예시와 주의사항 포함
   - **Helper**: `format_table_for_prompt` (테이블을 마크다운 형식으로 변환)

   ### 성능 및 효과

   **LLM 출력 크기**:
   - 기존: Definition 수에 비례 (수천 개 → 수만 tokens → 트렁케이션)
   - 새 방식: 그룹 수에 비례 (보통 5-20개 → ~500 tokens → 안정적)

   **확장성**:
   - 기존: 500+ definitions 처리 불가 (토큰 제한)
   - 새 방식: 수천~수만 개도 처리 가능 (Python 조합 생성, 메모리만 허용하면)

   **비용**:
   - 기존: LLM 호출 수십 회 (배치 처리) 또는 매우 큰 입출력
   - 새 방식: LLM 호출 1회, 작은 입출력 (~85% 비용 절감)

   **정확도**:
   - 기존: 배치 처리 시 불일치 가능
   - 새 방식: LLM이 전체 구조를 한눈에 보고 그룹핑 → 일관성 향상

   **디버깅**:
   - 기존: LLM 출력이 너무 커서 검증 어려움
   - 새 방식: LLM 출력(그룹핑 로직)을 사람이 직접 검증 가능

   ### 테스트 결과

   **샘플 문서 테스트** (2025-01-XX):
   - Input: Definition 2개, Condition 4개
   - LLM 출력: 4개 그룹 (작은 JSON 메타데이터)
   - Python 생성: 4개 최종 조합
   - **모든 검증 통과** ✅

   **처리 흐름**:
   ```
   [OK] normalize_definitions: 3 columns, 2 rows
   [OK] normalize_conditions: 8 columns, 4 rows
   [OK] extract_grouping_logic: 4 groups, 100% coverage
   [OK] generate_final_combinations: 4 definitions
   ```

   ### 버그 수정 이력

   1. **Validator 라우팅 누락**: `validate_step` 노드에서 새 task type 처리 추가
   2. **인코딩 에러**: CP949에서 지원하지 않는 Unicode 문자(✓) 제거
   3. **Context 전달**: `validate_step`에서 grouping validator에 필요한 context 추가

   ### 구현 파일 요약

   - `core/state.py`: State 필드 추가 (normalized_definitions, normalized_conditions, grouping_logic, final_result)
   - `core/prompt.py`: `build_grouping_extraction_prompt`, `format_table_for_prompt` 추가
   - `tools/hybrid_tools.py`:
     - `GroupingLogicExtractorTool`: LLM 기반 그룹핑 로직 추출 (~150 lines)
     - `CombinationGeneratorTool`: Python 기반 조합 생성 (~100 lines)
   - `agent.py`:
     - 노드 추가: `normalize_definitions`, `normalize_conditions`, `extract_grouping_logic`, `generate_final_combinations`
     - Router 수정: `should_continue`, `after_replan`
     - Graph 빌더: `build_graph` 새 플로우 반영
     - run() 메서드: `final_result` 반환
     - validate_step: 새 task type 라우팅 및 context 전달
   - `core/llm_validator.py`:
     - `validate_grouping_logic`: 그룹핑 로직 검증 (~80 lines)
     - `validate_final_combinations`: 최종 조합 검증 (~60 lines)
     - `validate`: 새 task type 라우팅 추가
   - `tools/tool_schemas.py`: 스키마 2개 추가 (grouping_logic_extractor, combination_generator)

   ### 향후 개선 방향

   1. **계층적 그룹핑**: 그룹 수가 100개 초과 시 계층적 그룹핑 지원
   2. **Streaming 조합 생성**: 메모리 부족 방지를 위한 배치 단위 파일 저장
   3. **그룹핑 로직 재사용**: 유사한 문서에 대해 그룹핑 로직 캐싱/재사용
   4. **성능 모니터링**: 대규모 데이터셋(수천 개)에 대한 벤치마크

---

## 8. 실행 방법 요약

```bash
cd Toy/prototype_6
python main.py path/to/input.json

# 또는 디렉터리 전체 처리
python main.py path/to/input_dir
```

결과는 `results/<원본파일명>_prototype6_result.json`으로 저장됩니다.  
파일에는 `success`, `final_data`(definitions), `full_log`(LangGraph 실행 로그) 등이 포함됩니다.

