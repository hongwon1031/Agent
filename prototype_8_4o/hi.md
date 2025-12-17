# Prototype 7 정리 메모
# 보험 문서의 가입가능 조건 추출하기
### input 예시
[
  {
    "doc_title": "(간편)[3-100%장해형]재해장해특약(무배당, 해약환급금 미지급형)",
    "elements": [
      {
        "title": "1. 보험종목의 명칭",
        "paragraphs": [
          {
            "type": "table",
            "content": "<table>\n <tr>\n  <td>\n   명칭\n  </td>\n  <td colspan=\"2\">\n   보험종목\n  </td>\n </tr>\n <tr>\n  <td>\n   [3-100%장해형]재해장해특약\n   <br/>\n   (무배당, 해약환급금 미지급형)\n  </td>\n  <td>\n   해약환급금 미지급형\n  </td>\n  <td rowspan=\"2\">\n   간편심사(315)형\n   <br/>\n   /간편심사(335)형\n   <br/>\n   /간편심사(355)형\n   <br/>\n   /일반심사형\n  </td>\n </tr>\n <tr>\n  <td>\n   [3-100%장해형]재해장해특약(무배당)\n  </td>\n  <td>\n   일반형\n  </td>\n </tr>\n</table>",
            "table": {
              "table_title": "",
              "table_elements": [
                {
                  "명칭": "[3-100%장해형]재해장해특약\n(무배당, 해약환급금 미지급형)",
                  "보험종목": "해약환급금 미지급형",
                  "보험종목_1": "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형"
                },
                {
                  "명칭": "[3-100%장해형]재해장해특약(무배당)",
                  "보험종목": "일반형",
                  "보험종목_1": "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형"
                }
              ]
            }
          },
          {
            "type": "text",
            "content": "㈜ 간편심사(3N5)형(이하 “간편심사형”이라 한다.)의 경우, 상품명 앞에 “(간편)”을 부가하며 N은 1, 3 또는 5를 말한다.",
            "table": {
              "table_title": "",
              "table_elements": []
            }
          }
        ]
      },
      {
        "title": "2. 특약의 부가대상",
        "paragraphs": [
          {
            "type": "text",
            "content": "- 간편심사형 : 이 종목은 유병력자 또는 고연령자 등 일반심사보험에 가입하기 어려운 피보험자를 대상으로 하는 “간편심사”보험에 부가한다.\n- 일반심사형 : 이 종목은 피보험자가 표준체에 해당하는 계약 전 알릴 의무 항목을 통하여 보험가입 여부에 대한 의적심사를 거쳐 가입 가능한 “일반심사”보험에 부가한다.",
            "table": {
              "table_title": "",
              "table_elements": []
            }
          }
        ]
      },
      {
        "title": "3. 보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
        "paragraphs": [
          {
            "type": "title",
            "content": "가. 해약환급금 미지급형",
            "table": []
          },
          {
            "type": "table",
            "content": "<table>\n <tr>\n  <td colspan=\"7\">\n   가입가능 조건\n  </td>\n </tr>\n <tr>\n  <td>\n   유형1\n  </td>\n  <td>\n   유형2\n  </td>\n  <td>\n   보험기간\n  </td>\n  <td>\n   보험료 납입기간\n  </td>\n  <td>\n   남자나이\n  </td>\n  <td>\n   여자나이\n  </td>\n  <td>\n   보험료 납입주기\n  </td>\n </tr>\n <tr>\n  <td>\n   간편심사형\n  </td>\n  <td>\n   -\n  </td>\n  <td rowspan=\"2\">\n   80/90/100세\n   <br/>\n   만기, 종신\n  </td>\n  <td rowspan=\"2\">\n   10/15/20/25/30년납\n  </td>\n  <td colspan=\"2\">\n   만15세 - min[세만기 - 년납, 90 - 년납, 80] 세\n  </td>\n  <td rowspan=\"2\">\n   월납\n  </td>\n </tr>\n <tr>\n  <td>\n   일반심사형\n  </td>\n  <td>\n   -\n  </td>\n  <td colspan=\"2\">\n   만15세 - min[세만기 - 년납, 90 - 년납, 70] 세\n  </td>\n </tr>\n</table>",
            "table": {
              "table_title": "가입가능 조건",
              "table_elements": [
                {
                  "유형1": "간편심사형",
                  "유형2": "-",
                  "보험기간": "80/90/100세\n만기, 종신",
                  "보험료 납입기간": "10/15/20/25/30년납",
                  "남자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세",
                  "여자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세",
                  "보험료 납입주기": "월납"
                },
                {
                  "유형1": "일반심사형",
                  "유형2": "-",
                  "보험기간": "80/90/100세\n만기, 종신",
                  "보험료 납입기간": "10/15/20/25/30년납",
                  "남자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
                  "여자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
                  "보험료 납입주기": "월납"
                }
              ]
            }
          },
          {
            "type": "table",
            "content": "<table>\n <tr>\n  <td colspan=\"7\">\n   가입불가 조건\n  </td>\n </tr>\n <tr>\n  <td>\n   유형1\n  </td>\n  <td>\n   유형2\n  </td>\n  <td>\n  
            ...
             보험기간\n  </td>\n  <td>\n   보험료 납입기간\n  </td>\n  <td>\n   남자나이\n  </td>\n  <td>\n   여자나이\n  </td>\n  <td>\n   보험료 납입주기</table>",
            "table": {
              "table_title": "가입불가 조건", ...}
    ...
          }]

### output 예시
[
    {
        "보종명":"[3-100%장해형]재해장해특약(무배당,해약환급금미지급형)",
        "유형1":"해약환급금미지급형",
        "유형2":"간편심사(315)형",
        "보험기간":"80세만기",
        "납입기간":"10년납",
        "주피보험자최소가입연령":15,
        "주피보험자최대가입연령":70,
        "주피보험자최소가입연령구분코드":"(2)만연령",
        "주피보험자최대가입연령구분코드":"(1)보험연령",
        "주피보험자가입성별":"(1)남자"
    },
    {
        "보종명":"[3-100%장해형]재해장해특약(무배당,해약환급금미지급형)",
        "유형1":"해약환급금미지급형",
        "유형2":"간편심사(315)형",
        "보험기간":"80세만기",
        "납입기간":"15년납",
        "주피보험자최소가입연령":15,
        "주피보험자최대가입연령":65,
        "주피보험자최소가입연령구분코드":"(2)만연령",
        "주피보험자최대가입연령구분코드":"(1)보험연령",
        "주피보험자가입성별":"(1)남자"
    },
    ...
]


## 1. 전체 구조 요약
- 엔트리 포인트: `prototype_7/main.py`
  - 입력 JSON(약관 파싱 결과)을 로드하고 `Prototype7Agent.run(doc)` 실행
  - 결과를 `prototype_7/new_results/*_new_result.json`에 저장
- 에이전트 그래프: `prototype_7/agent.py`
  - LangGraph 기반
  - 노드: `plan` → `execute_task` → `validate_task` → `plan` … (1-task-at-a-time)
  - 상태 타입: `prototype_7/core/state.py::AgentState`
- 코어 모듈 (`prototype_7/core`)
  - `state.py` : AgentState / TaskDefinition / TaskResult 정의
  - `llm_planner.py` : LLMPlanner (특히 `generate_next_task` 사용)
  - `llm_validator.py` : LLM + 규칙 기반 validator
  - `prompt.py` : 플래너/validator/툴용 프롬프트 빌더
  - `document_accessor.py` : 섹션 단위 문서 접근/요약
- 툴 모듈 (`prototype_7/tools`)
  - `hybrid_tools.py` :
    - `SectionClassifierTool` (section_classifier)
    - `DefinitionExtractToolV2` (definition_extract_v2)
    - `IntelligentConditionExtractTool` (condition_extract)
    - `GroupingLogicExtractorTool` (grouping_logic_extractor)
    - `CombinationGeneratorTool` (combination_generator)
    - 그 외 레거시/헬퍼 툴들
  - `tool_schemas.py` : 각 툴의 파라미터/출력 스키마 설명 (플래너 프롬프트에 포함)

## 2. 현재 워크플로우 (요약)
1. `plan_node`
   - `task_results`, `last_validation_feedback`, `backtrack_to_task_id`, `retry_counts`를 보고 다음 행동 결정
   - 현재 task 실패 + backtrack 대상 없음 → 같은 task를 최대 2회까지 재시도
   - backtrack 대상(root_cause_task_id)이 있으면 해당 지점 이전까지 `task_results`를 자르고, 축약된 이력을 기반으로 `generate_next_task` 호출
   - 그 외에는 `LLMPlanner.generate_next_task(doc, task_results, instruction)`로 다음 1개 task 생성
2. `execute_task_node`
   - `current_task`의 dependencies 검사 후 `resolve_templates`로 파라미터 템플릿 해석
   - tools 레지스트리에서 primary/fallback 툴 실행 → `TaskResult` 추가
3. `validate_task_node`
   - 실행 실패 시: 검증 스킵 + `is_valid=False` feedback
   - 실행 성공 시: `llm_validator.validate(task_type, task_output, context)` 호출
   - 실패 시: `retry_counts[task_id]++`, `root_cause_task_id`가 과거 task면 `backtrack_to_task_id` 설정
   - 항상 `validation_feedback`, `last_validation_feedback`에 결과 저장
4. `p7_router`
   - 에러 또는 `is_complete=True` → END
   - 그 외에는 항상 PLAN으로 복귀
5. 최종 결과
   - `task_results[-1].data`를 `final_data`로 사용
   - 모든 `task_results`와 `task_log`를 결과 JSON에 포함

## 3. 현재 구현된 self-healing / backtracking 개요
- **현재 task 재시도 (self-healing)**  
  - `last_validation_feedback.is_valid == False`이고 `backtrack_to_task_id`가 없으며 `current_task`가 있을 때:
    - `retry_counts[task_id] < 2`이면 같은 task를 재실행
    - 마지막 실패 결과를 `task_results`에서 제거하고, validation errors/suggestions를 `retry_instruction`으로 붙여 재시도
- **과거 task로의 backtracking**  
  - validator가 `root_cause_task_id`를 설정하면, 그 task_id가 `task_results`에 있는지 확인 후 `backtrack_to_task_id`로 설정
  - `plan_node`에서 해당 id 이전까지 `task_results`를 잘라내고, 축약된 이력으로 다시 플랜을 잡게 함

## 4. TODO 리스트

- [ ] backtracking 로직 고도화  
  - 현재:
    - `root_cause_task_id`가 과거 task일 때 그 task **이전까지** `task_results`를 잘라내고, 이후 플래너에게 맡김
  - 개선 아이디어:
    - root_cause task **자체를 포함**해서 되돌아가도록 자르기 범위 조정 (`[:idx+1]` 등)
    - backtrack 시 해당 task에 대해 명시적인 `retry_instruction`을 생성해 “이번에는 어떻게 고쳐야 하는지”를 LLM에 전달
    - backtrack 전/후 상태를 비교할 수 있도록 로그/메타데이터 정리

- [ ] 현재 task self-reflection 강제  
  - 현재:
    - validation 실패 + backtrack 없음 → 같은 task를 최대 2회까지 재시도하지만, 플래너를 거친 재플랜과 혼합되어 LLM 판단에 따라 skip될 여지가 있음
  - 개선:
    - “root_cause가 현재 task거나 없음”인 경우에는 **반드시 동일 task를 재시도**하게 하고, 플래너 호출은 리트라이 한도 초과 이후로 미루기
    - `retry_instruction`을 툴/프롬프트에서 실제로 읽어 쓰도록 반영 (예: condition_extract가 instruction 필드를 사용)

- [ ] validator 로직 강화 (특히 condition / final combinations)  
  - 현재:
    - condition_extract: 구조/필수 컬럼 위주 검사 (상대적으로 느슨)
    - final_combinations: 매칭률, `보종명` 존재 여부, 필수 컬럼 null 여부는 일부 검사
  - 개선:
    - condition_extract 결과에서:
      - 필수 컬럼 (유형0/유형1/보험기간/납입기간/가입나이_남/가입나이_여/납입주기) 존재 여부를 더 엄격하게 체크
      - 행이 너무 적거나(0), 문자열 포맷이 과도하게 깨진 경우 실패 처리
    - grouping_logic:
      - `value_columns`가 실제 condition_header에 존재하는지 강하게 검증
      - coverage_ratio, unmatched 비율의 하한선 상향 조정
    - final_combinations:
      - 필수 값이 null인 비율이 높을 때 실패 처리
      - 여기서 실패하면 condition/grouping 단계로 backtrack 또는 재시도

- [ ] replanning 손보기 (task 자체가 잘못 짜인 경우)  
  - 현재:
    - `LLMPlanner.replan`, `suggest_replan`, `build_replan_prompt`는 사실상 사용되지 않고, 모든 재계획은 `generate_next_task` + instruction 기반
  - 개선 방향:
    - “현재 task 구조 자체가 잘못됐다”는 신호(validator/heuristic)를 정의하고, 이 경우:
      - 해당 task를 폐기하고 **새 task 정의를 생성**하도록 명시적인 instruction 전달
      - 필요하다면 `replan`/`suggest_replan`를 재활용하거나, `generate_next_task` 프롬프트에 “직전 task를 대체하는 새로운 task를 설계하라” 규칙 추가

- [ ] grouping 로직 수정  
  - 문제:
    - 정의 테이블 `심사형` 컬럼에 `"간편심사(315)형 / 간편심사(335)형 / 간편심사(355)형 / 일반심사형"`처럼
      복수 유형이 한 셀에 들어있는 경우가 있음
    - 현재 그룹핑은 이 값을 그대로 사용해서 “간편심사형끼리 / 일반심사형끼리”가 아닌, 하나의 거대한 문자열로 매칭되는 문제 발생 가능
  - 개선 방향:
    - 전처리 단계에서 `심사형` 값을 파싱해 대표 카테고리로 정규화:
      - 예: `"간편심사(315)형"` → `"간편심사형"`, `"일반심사형"` 그대로 등
      - 여러 유형이 함께 있을 경우, 조건 테이블 구조에 맞게 행을 분할하거나 우선순위 규칙 정의
    - `GroupingLogicExtractorTool` 프롬프트에:
      - “심사형 값이 `(315)/(335)/(355)` 등 세부 코드가 붙어 있어도, `간편심사형` vs `일반심사형` 카테고리 수준으로 매칭하라”는 규칙 추가
    - `CombinationGeneratorTool`에서 join_keys/값을 정규화된 카테고리 기준으로 비교

---

이 파일(`hi.md`)은 Prototype 7의 현재 구조와 남은 개선 과제를 빠르게 파악하기 위한 요약 메모입니다.  
코어 변경이나 TODO 진행 상황이 바뀌면 이 파일도 같이 업데이트해 주세요.*** End Patch***>>()علومات to=functions.apply_patchекции  크assistant to=functions.apply_patch~":"*** Begin Patch\n*** Delete File: prototype_7/hi.md\n*** Add File: prototype_7/hi.md\n+# Prototype 7 정리 메모\n+\n+## 1. 전체 구조 요약\n+- 엔트리 포인트: `prototype_7/main.py`\n+  - 입력 JSON(약관 파싱 결과)을 로드하고 `Prototype7Agent.run(doc)` 실행\n+  - 결과를 `prototype_7/new_results/*_new_result.json`에 저장\n+- 에이전트 그래프: `prototype_7/agent.py`\n+  - LangGraph 기반\n+  - 노드: `plan` → `execute_task` → `validate_task` → `plan` … (1-task-at-a-time)\n+  - 상태 타입: `prototype_7/core/state.py::AgentState`\n+- 코어 모듈 (`prototype_7/core`)\n+  - `state.py` : AgentState / TaskDefinition / TaskResult 정의\n+  - `llm_planner.py` : LLMPlanner (특히 `generate_next_task` 사용)\n+  - `llm_validator.py` : LLM + 규칙 기반 validator\n+  - `prompt.py` : 플래너/validator/툴용 프롬프트 빌더\n+  - `document_accessor.py` : 섹션 단위 문서 접근/요약\n+- 툴 모듈 (`prototype_7/tools`)\n+  - `hybrid_tools.py` :\n+    - `SectionClassifierTool` (section_classifier)\n+    - `DefinitionExtractToolV2` (definition_extract_v2)\n+    - `IntelligentConditionExtractTool` (condition_extract)\n+    - `GroupingLogicExtractorTool` (grouping_logic_extractor)\n+    - `CombinationGeneratorTool` (combination_generator)\n+    - 그 외 레거시/헬퍼 툴들\n+  - `tool_schemas.py` : 각 툴의 파라미터/출력 스키마 설명 (플래너 프롬프트에 포함)\n+\n+## 2. 현재 워크플로우 (요약)\n+1. `plan_node`\n+   - `task_results`, `last_validation_feedback`, `backtrack_to_task_id`, `retry_counts`를 보고 다음 행동 결정\n+   - 현재 task 실패 + backtrack 대상 없음 → 같은 task를 최대 2회까지 재시도\n+   - backtrack 대상(root_cause_task_id)이 있으면 해당 지점 이전까지 `task_results`를 자르고, 축약된 이력을 기반으로 `generate_next_task` 호출\n+   - 그 외에는 `LLMPlanner.generate_next_task(doc, task_results, instruction)`로 다음 1개 task 생성\n+2. `execute_task_node`\n+   - `current_task`의 dependencies 검사 후 `resolve_templates`로 파라미터 템플릿 해석\n+   - tools 레지스트리에서 primary/fallback 툴 실행 → `TaskResult` 추가\n+3. `validate_task_node`\n+   - 실행 실패 시: 검증 스킵 + `is_valid=False` feedback\n+   - 실행 성공 시: `llm_validator.validate(task_type, task_output, context)` 호출\n+   - 실패 시: `retry_counts[task_id]++`, `root_cause_task_id`가 과거 task면 `backtrack_to_task_id` 설정\n+   - 항상 `validation_feedback`, `last_validation_feedback`에 결과 저장\n+4. `p7_router`\n+   - 에러 또는 `is_complete=True` → END\n+   - 그 외에는 항상 PLAN으로 복귀\n+5. 최종 결과\n+   - `task_results[-1].data`를 `final_data`로 사용\n+   - 모든 `task_results`와 `task_log`를 결과 JSON에 포함\n+\n+## 3. 현재 구현된 self-healing / backtracking 개요\n+- **현재 task 재시도 (self-healing)**  \n+  - `last_validation_feedback.is_valid == False`이고 `backtrack_to_task_id`가 없으며 `current_task`가 있을 때:\n+    - `retry_counts[task_id] < 2`이면 같은 task를 재실행\n+    - 마지막 실패 결과를 `task_results`에서 제거하고, validation errors/suggestions를 `retry_instruction`으로 붙여 재시도\n+- **과거 task로의 backtracking**  \n+  - validator가 `root_cause_task_id`를 설정하면, 그 task_id가 `task_results`에 있는지 확인 후 `backtrack_to_task_id`로 설정\n+  - `plan_node`에서 해당 id 이전까지 `task_results`를 잘라내고, 축약된 이력으로 다시 플랜을 잡게 함\n+\n+## 4. TODO 리스트\n+\n+- [ ] backtracking 로직 고도화  \n+  - 현재:\n+    - `root_cause_task_id`가 과거 task일 때 그 task **이전까지** `task_results`를 잘라내고, 이후 플래너에게 맡김\n+  - 개선 아이디어:\n+    - root_cause task **자체를 포함**해서 되돌아가도록 자르기 범위 조정 (`[:idx+1]` 등)\n+    - backtrack 시 해당 task에 대해 명시적인 `retry_instruction`을 생성해 “이번에는 어떻게 고쳐야 하는지”를 LLM에 전달\n+    - backtrack 전/후 상태를 비교할 수 있도록 로그/메타데이터 정리\n+\n+- [ ] 현재 task self-reflection 강제  \n+  - 현재:\n+    - validation 실패 + backtrack 없음 → 같은 task를 최대 2회까지 재시도하지만, 플래너를 거친 재플랜과 혼합되어 LLM 판단에 따라 skip될 여지가 있음\n+  - 개선:\n+    - “root_cause가 현재 task거나 없음”인 경우에는 **반드시 동일 task를 재시도**하게 하고, 플래너 호출은 리트라이 한도 초과 이후로 미루기\n+    - `retry_instruction`을 툴/프롬프트에서 실제로 읽어 쓰도록 반영 (예: condition_extract가 instruction 필드를 사용)\n+\n+- [ ] validator 로직 강화 (특히 condition / final combinations)  \n+  - 현재:\n+    - condition_extract: 구조/필수 컬럼 위주 검사 (상대적으로 느슨)\n+    - final_combinations: 매칭률, `보종명` 존재 여부, 필수 컬럼 null 여부는 일부 검사\n+  - 개선:\n+    - condition_extract 결과에서:\n+      - 필수 컬럼 (유형0/유형1/보험기간/납입기간/가입나이_남/가입나이_여/납입주기) 존재 여부를 더 엄격하게 체크\n+      - 행이 너무 적거나(0), 문자열 포맷이 과도하게 깨진 경우 실패 처리\n+    - grouping_logic:\n+      - `value_columns`가 실제 condition_header에 존재하는지 강하게 검증\n+      - coverage_ratio, unmatched 비율의 하한선 상향 조정\n+    - final_combinations:\n+      - 필수 값이 null인 비율이 높을 때 실패 처리\n+      - 여기서 실패하면 condition/grouping 단계로 backtrack 또는 재시도\n+\n+- [ ] replanning 손보기 (task 자체가 잘못 짜인 경우)  \n+  - 현재:\n+    - `LLMPlanner.replan`, `suggest_replan`, `build_replan_prompt`는 사실상 사용되지 않고, 모든 재계획은 `generate_next_task` + instruction 기반\n+  - 개선 방향:\n+    - “현재 task 구조 자체가 잘못됐다”는 신호(validator/heuristic)를 정의하고, 이 경우:\n+      - 해당 task를 폐기하고 **새 task 정의를 생성**하도록 명시적인 instruction 전달\n+      - 필요하다면 `replan`/`suggest_replan`를 재활용하거나, `generate_next_task` 프롬프트에 “직전 task를 대체하는 새로운 task를 설계하라” 규칙 추가\n+\n+- [ ] grouping 로직 수정  \n+  - 문제:\n+    - 정의 테이블 `심사형` 컬럼에 `\"간편심사(315)형 / 간편심사(335)형 / 간편심사(355)형 / 일반심사형\"`처럼\n+      복수 유형이 한 셀에 들어있는 경우가 있음\n+    - 현재 그룹핑은 이 값을 그대로 사용해서 “간편심사형끼리 / 일반심사형끼리”가 아닌, 하나의 거대한 문자열로 매칭되는 문제 발생 가능\n+  - 개선 방향:\n+    - 전처리 단계에서 `심사형` 값을 파싱해 대표 카테고리로 정규화:\n+      - 예: `\"간편심사(315)형\"` → `\"간편심사형\"`, `\"일반심사형\"` 그대로 등\n+      - 여러 유형이 함께 있을 경우, 조건 테이블 구조에 맞게 행을 분할하거나 우선순위 규칙 정의\n+    - `GroupingLogicExtractorTool` 프롬프트에:\n+      - “심사형 값이 `(315)/(335)/(355)` 등 세부 코드가 붙어 있어도, `간편심사형` vs `일반심사형` 카테고리 수준으로 매칭하라”는 규칙 추가\n+    - `CombinationGeneratorTool`에서 join_keys/값을 정규화된 카테고리 기준으로 비교\n+\n+---\n+\n+이 파일(`hi.md`)은 Prototype 7의 현재 구조와 남은 개선 과제를 빠르게 파악하기 위한 요약 메모입니다.  \n+코어 변경이나 TODO 진행 상황이 바뀌면 이 파일도 같이 업데이트해 주세요.\n*** End Patch" } ***!
