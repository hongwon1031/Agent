# 🔍 추가

1. Planner는 전체 workflow를 짜지 않습니다!

실제 구조:

# agent.py:68-80

```jsx
def plan_initial_strategy(state: AgentState):
plan = planner.create_plan(doc=state['original_doc'])
return {"initial_strategy": plan}  # ← 저장만 하고 사용 안 함!
```

# agent.py:909-956 (should_continue)

```jsx
def should_continue(state: AgentState) -> str:
# 고정된 7단계 workflow (LangGraph)
if last_task == "classify":
return "extract_definitions"
elif last_task == "extract":
return "normalize_definitions"
# ... (하드코딩된 flow)
```

즉:

- plan_initial_strategy 노드는 호출되지만 결과를 사용하지 않습니다
- 실제 workflow는 LangGraph의 고정된 7단계를 따릅니다
- initial_strategy는 참고용으로만 저장됩니다 (레거시 코드)

---

1. Planner의 진짜 역할: replan() - 실패 시 instruction 생성

# agent.py:850-899 (replan_or_finish)

```jsx
def replan_or_finish(state: AgentState):
# 실패 시 호출됨
new_plan = planner.replan(
failed_task=failed_task_attempt,
error_message=validation_feedback.get('errors')[0],
validation_result=validation_feedback
)
```

```
  # instruction만 추출
  new_instruction = new_plan.get("parameters", {}).get("instruction")

  # state에 저장 → 재시도 시 tool에 전달
  return {
      "current_instruction": new_instruction,
      "replan_count": replan_count + 1
  }

```

Planner의 실제 역할:

- ❌ 전체 workflow 계획 수립 (사용 안 함)
- ✅ 실패 시 복구 instruction 생성
    - Validator 피드백 분석
    - 새로운 instruction 파라미터 생성
    - Tool 재실행 시 이 instruction이 힌트로 전달됨

---

1. 왜 prompt에 3단계만 있는가?

# core/prompt.py:16-57

```jsx
"""
**Task 구성**:
- 정확히 3단계의 Task를 구성하세요 (고정된 워크플로우)
**Step 1: Classify TaskStep 2: Extract TaskStep 3: Transform Task**  # ← Cartesian Product 생성
"""
```

이유:

1. Prompt가 구버전입니다 (3단계 workflow 시절)
2. 현재는 create_plan()을 사용하지 않으므로 업데이트되지 않음
3. 실제 workflow는 agent.py의 should_continue 함수가 정의 (7단계)

---

📊 전체 구조 정리

```jsx
[LangGraph - 고정 7단계 Flow]
initialize_state
↓
plan_initial_strategy  ← create_plan() 호출하지만 결과 무시!
↓
classify_sections
↓
validate_step ──[실패]──→ replan_or_finish ← replan() 호출!
↓ [성공]                      ↓
extract_definitions        instruction 생성
↓                              ↓
validate_step ──[실패]─────────→ backtrack (after_replan)
↓ [성공]                      ↓
normalize_definitions ←─────────┘ (재시도 with instruction)
↓
... (나머지 4단계)
```

---

💡 핵심 정리

| 요소 | 역할 | 실제 사용 여부 |
| --- | --- | --- |
| LangGraph | 7단계 고정 workflow 정의 | ✅ 실제 사용 |
| Planner.create_plan() | 초기 계획 수립 | ❌ 호출하지만 무시 (레거시) |
| Planner.replan() | 실패 시 instruction 생성 | ✅ 진짜 역할! |
| should_continue() | 다음 단계 라우팅 | ✅ 하드코딩된 flow |
| prompt.py의 3단계 | create_plan용 prompt | ❌ 구버전 (사용 안 함) |

---

🔧 결론

질문에 대한 답변:

1. "Planner는 전체 workflow의 plan을 짜는가?"
- ❌ 아닙니다. create_plan()은 호출되지만 결과를 사용하지 않습니다.
- 전체 workflow는 LangGraph가 하드코딩되어 있습니다.
2. "Prompt에 3단계만 있는 이유?"
- 구버전 prompt입니다 (업데이트 안 됨)
- create_plan()을 사용하지 않으므로 문제없습니다.
3. "전체 workflow가 고정되어 있다면 Planner는 뭘 하는가?"
- 진짜 역할: replan() - 실패 시 복구 instruction 생성
- Validator 피드백 → 새 instruction → Tool 재시도

---

📝 README 업데이트 제안

이 내용을 README에 명확히 해야 할 것 같습니다:

## Planner의 역할

### ⚠️ 중요: create_plan()은 현재 사용되지 않습니다

- `plan_initial_strategy` 노드가 `create_plan()`을 호출하지만
- 결과는 `initial_strategy`에 저장만 되고 실제로 사용되지 않습니다
- 실제 workflow는 **LangGraph의 고정된 7단계**를 따릅니다

### ✅ Planner의 실제 역할: replan()

- **실패 시 복구 전략 수립**
- Validator 피드백 분석 → 새 instruction 생성
- 재시도 시 이 instruction이 tool에 전달됨

### 아키텍처

[고정 Flow]         [동적 Recovery]
LangGraph    +      Planner.replan()
(7단계)             (instruction 생성)

이렇게 정리하면 팀원들에게 훨씬 명확하게 설명할 수 있을 것 같습니다!

## 🚀 향후 개선 계획: 진짜 Agentic System으로

### 📋 현재 시스템의 한계

**발견된 문제점:**

1. **❌ 동적 Planning이 아님**
    
    ```python
    # Planner.create_plan() 호출하지만 결과 무시
    plan = planner.create_plan(doc)
    # → initial_strategy에 저장만 하고 사용 안 함
    
    # 실제 workflow는 하드코딩
    def should_continue(state):
        if last_task == "classify":
            return "extract_definitions"  # 고정!
        elif last_task == "extract":
            return "normalize_definitions"  # 고정!
    
    ```
    
2. **❌ 같은 Task만 재시도 (이전 Task로 Backtrack 안 됨)**
    
    ```python
    # agent.py:957-995 (after_replan)
    # Backtracking strategy: Retry the last failed step.
    
    # Task 3 실패 (원인: Task 1 잘못)
    # → Task 3으로만 돌아감 (Task 1로 backtrack 안 함)
    # → 3번 재시도 후 포기
    
    ```
    
3. **❌ LangGraph의 장점을 제대로 활용 안 함**
    - 단순 선형 flow만 구현
    - 복잡한 graph topology 미사용
    - 조건부 backtracking 미구현

**실제로는:**

```
고정 7단계 파이프라인
+ LLM 검증
+ 같은 단계만 재시도 (instruction 추가)

```

---

### ✨ 제안: 동적 루프 기반 Agentic Architecture

### 새로운 구조

```
START
  ↓
┌─────────────────────────────────┐
│  PLAN                           │
│  (Planner.create_plan)          │
│  → N개 task 동적 생성           │
│  → 문서마다 다른 전략           │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│  EXECUTE_TASK                   │ ← Loop!
│  (일반화된 executor)            │
│  - tasks[current_index] 실행    │
│  - 이전 task 결과 자동 주입     │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│  VALIDATE_TASK                  │
│  (LLM 검증)                     │
└─────────────────────────────────┘
  ↓
ROUTER:
  ✅ Success → current_index++, EXECUTE_TASK (다음 task)
  ❌ Fail → REPLAN
  🏁 All done → END
  ↓
┌─────────────────────────────────┐
│  REPLAN                         │
│  - Root cause 분석              │
│  - backtrack_index 결정         │
│  - current_index = backtrack    │
└─────────────────────────────────┘
  ↓
EXECUTE_TASK (재실행)

```

### 핵심 차이점

| 항목 | 현재 (고정 노드) | 제안 (동적 루프) |
| --- | --- | --- |
| **노드 수** | 8개 고정 노드 | 4개 범용 노드 |
| **Planning** | 무시됨 | 실제 사용 ✅ |
| **Workflow** | 모든 문서 동일 (7단계) | 문서별 최적화 (3~7단계) |
| **Backtracking** | 같은 task만 | 이전 task로 가능 ✅ |
| **확장성** | 새 step 추가 시 코드 수정 | plan만 수정 |
| **Tool 선택** | 하드코딩 | Planner가 동적 선택 |

---

### 🏗️ 구현 계획

### 1. State 재설계

```python
class AgentState(TypedDict):
    # 문서
    original_doc: Any
    sections: List[Dict]

    # 🔥 Plan (핵심! 실제로 사용됨)
    plan: Dict[str, Any]  # Planner.create_plan() 결과
    # {
    #   "tasks": [
    #     {"task_id": 0, "type": "classify", "tool_name": "section_classifier",
    #      "parameters": {...}, "fallback": "llm", "depends_on": null},
    #     {"task_id": 1, "type": "extract", "tool_name": "definition_extract_v2",
    #      "parameters": {...}, "depends_on": 0},
    #     {"task_id": 2, "type": "transform", "tool_name": "rule_cartesian",
    #      "parameters": {...}, "fallback": "llm_cartesian", "depends_on": 1},
    #     ...
    #   ],
    #   "reasoning": "테이블 많음 → rule 우선, 실패 시 llm fallback",
    #   "estimated_difficulty": "medium"
    # }

    # 🔥 Execution state (동적 진행 상황)
    current_task_index: int  # 현재 실행 중인 task (0부터 시작)
    task_results: List[Dict]  # 각 task의 결과 저장
    # [
    #   {"task_id": 0, "success": True, "output": {...}, "tool_used": "section_classifier"},
    #   {"task_id": 1, "success": True, "output": {...}, "tool_used": "definition_extract_v2"},
    # ]

    # Validation & Replan
    validation_feedback: Optional[Dict]
    replan_count: int
    current_instruction: Optional[str]

    # Logs
    execution_log: List[Dict]
    error: Optional[str]

```

### 2. PLAN 노드

```python
def plan_node(state: AgentState) -> Dict[str, Any]:
    """
    🔥 Planner가 문서 분석 → N개 task 동적 생성

    문서 특성에 따라:
    - 단순 문서: 3단계 (classify → extract → cartesian)
    - 복잡 문서: 7단계 (classify → extract → normalize → condition → ...)
    - Tool 선택도 동적 (Rule vs LLM)
    """
    print("\\n[PLAN] Analyzing document and creating execution plan...")

    plan = planner.create_plan(doc=state['original_doc'])

    if plan.get("error"):
        return {"error": f"Planning failed: {plan['error']}"}

    num_tasks = len(plan['tasks'])
    print(f"[PLAN] ✅ Created {num_tasks} tasks")
    print(f"[PLAN] Reasoning: {plan.get('reasoning')}")
    print(f"[PLAN] Difficulty: {plan.get('estimated_difficulty')}")

    for task in plan['tasks']:
        print(f"  - Task {task['task_id']}: {task['tool_name']}")
        if task.get('fallback'):
            print(f"    (fallback: {task['fallback']})")

    return {
        "plan": plan,
        "current_task_index": 0,
        "task_results": [],
        "replan_count": 0
    }

```

### 3. EXECUTE_TASK 노드 (일반화된 Executor)

```python
def execute_task_node(state: AgentState) -> Dict[str, Any]:
    """
    🔥 일반화된 Task Executor

    plan의 current_task_index에 해당하는 task 실행
    - Tool 동적 선택
    - 이전 task 결과 자동 주입
    - Fallback 자동 처리
    """
    plan = state['plan']
    current_idx = state['current_task_index']
    tasks = plan['tasks']

    if current_idx >= len(tasks):
        return {"error": "Task index out of range"}

    current_task = tasks[current_idx]
    tool_name = current_task['tool_name']

    print(f"\\n[EXECUTE] Task {current_idx}/{len(tasks)-1}: {tool_name}")

    # Tool 가져오기
    tool = tools.get(tool_name)
    if not tool:
        return {"error": f"Tool not found: {tool_name}"}

    # 🔥 파라미터 준비 (이전 task 결과 자동 주입)
    params = prepare_params(current_task, state)

    # Instruction 추가 (replan에서 온 경우)
    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction
        print(f"[EXECUTE] Using instruction: {instruction[:50]}...")

    # 실행
    result = tool.execute(doc=state.get('original_doc'), params=params)

    # 🔥 Fallback 처리 (실패 시 자동)
    if not result.success and current_task.get('fallback'):
        fallback_tool_name = current_task['fallback']
        print(f"[EXECUTE] Primary tool failed. Trying fallback: {fallback_tool_name}")

        fallback_tool = tools.get(fallback_tool_name)
        if fallback_tool:
            result = fallback_tool.execute(doc=state.get('original_doc'), params=params)
            tool_name = fallback_tool_name  # Update for logging

    # 결과 저장
    task_results = state.get('task_results', []).copy()
    task_results.append({
        "task_id": current_idx,
        "task_type": current_task['type'],
        "tool_name": tool_name,
        "success": result.success,
        "output": result.data,
        "error": result.error
    })

    # Log 기록
    execution_log = state.get('execution_log', []).copy()
    execution_log.append({
        "task_id": current_idx,
        "tool": tool_name,
        "params": sanitize_params(params),
        "success": result.success
    })

    if result.success:
        print(f"[EXECUTE] ✅ Task {current_idx} succeeded")
    else:
        print(f"[EXECUTE] ❌ Task {current_idx} failed: {result.error}")

    return {
        "task_results": task_results,
        "execution_log": execution_log,
        "current_instruction": None  # Clear after use
    }

def prepare_params(current_task: Dict, state: AgentState) -> Dict:
    """
    🔥 이전 task 결과를 현재 task params에 자동 주입

    Task dependency 기반으로 필요한 데이터 찾기
    """
    params = current_task.get('parameters', {}).copy()
    task_results = state.get('task_results', [])
    task_type = current_task['type']

    # Helper: task_id로 결과 찾기
    def find_result(task_id):
        for result in task_results:
            if result['task_id'] == task_id:
                return result
        return None

    # Task type별 자동 주입 로직
    if task_type == 'extract':
        # Extract는 classify 결과 필요
        depends_on = current_task.get('depends_on')
        if depends_on is not None:
            classify_result = find_result(depends_on)
            if classify_result and classify_result['success']:
                output = classify_result['output']
                params['core_indices'] = output.get('definition_core', [])
                params['annotation_indices'] = output.get('definition_annotation', [])

    elif task_type == 'normalize':
        # Normalize는 extract 결과 필요
        depends_on = current_task.get('depends_on')
        if depends_on is not None:
            extract_result = find_result(depends_on)
            if extract_result and extract_result['success']:
                # params에 이미 포함되어 있을 수 있음
                pass

    elif task_type == 'transform':
        # Transform은 normalize 결과 필요
        depends_on = current_task.get('depends_on')
        if depends_on is not None:
            normalize_result = find_result(depends_on)
            if normalize_result and normalize_result['success']:
                output = normalize_result['output']
                params['header'] = output.get('header', [])
                params['data'] = output.get('data', [])

    # sections는 항상 주입
    params['sections'] = state['sections']

    return params

def sanitize_params(params: Dict) -> Dict:
    """Log에서 sections 같은 큰 데이터 제거"""
    sanitized = params.copy()
    sanitized.pop('sections', None)
    return sanitized

```

### 4. VALIDATE_TASK 노드

```python
def validate_task_node(state: AgentState) -> Dict[str, Any]:
    """
    현재 task 결과 검증
    """
    current_idx = state['current_task_index']
    task_results = state.get('task_results', [])

    if current_idx >= len(task_results):
        return {"error": "No task result to validate"}

    current_result = task_results[current_idx]

    print(f"\\n[VALIDATE] Validating task {current_idx}...")

    # Tool 실행 자체가 실패한 경우
    if not current_result['success']:
        return {
            "validation_feedback": {
                "is_valid": False,
                "errors": [current_result.get('error', 'Unknown error')],
                "suggestions": [],
                "reasoning": "Tool execution failed"
            }
        }

    # LLM Validator로 결과 검증
    task_type = current_result['task_type']
    output = current_result['output']

    # Context 준비
    context = prepare_validation_context(state, current_idx)

    validation = validator.validate(
        task_type=task_type,
        task_output=output,
        context=context
    )

    if validation.get("is_valid"):
        print(f"[VALIDATE] ✅ Task {current_idx} validation passed")
    else:
        print(f"[VALIDATE] ❌ Task {current_idx} validation failed")
        print(f"  Errors: {validation.get('errors')}")

    return {"validation_feedback": validation}

def prepare_validation_context(state: AgentState, task_idx: int) -> Dict:
    """Validator에 필요한 context 준비"""
    task_results = state['task_results']
    current_result = task_results[task_idx]
    task_type = current_result['task_type']

    context = {}

    if task_type == 'classify':
        context["all_sections"] = state['sections']

    elif task_type == 'extract':
        # Classification 결과 필요
        for result in task_results:
            if result['task_type'] == 'classify':
                context["classification_result"] = result['output']
                break
        context["all_sections"] = state['sections']

    # 추가 context...

    return context

```

### 5. ROUTER 로직

```python
def router(state: AgentState) -> str:
    """
    🔥 Validation 결과에 따라 다음 action 결정

    - Success: 다음 task 실행
    - Fail: replan
    - All done: end
    """
    if state.get("error"):
        return "end"

    validation = state.get('validation_feedback', {})
    plan = state['plan']
    current_idx = state['current_task_index']
    total_tasks = len(plan['tasks'])

    if validation.get("is_valid", False):
        # ✅ Success: 다음 task로
        next_idx = current_idx + 1

        if next_idx >= total_tasks:
            # 🏁 모든 task 완료!
            print(f"\\n[ROUTER] ✅ All {total_tasks} tasks completed!")
            return "end"
        else:
            # ➡️ 다음 task 실행
            print(f"[ROUTER] ➡️ Moving to task {next_idx}/{total_tasks-1}")
            # current_task_index 증가
            state['current_task_index'] = next_idx
            return "execute_task"
    else:
        # ❌ Fail: replan
        print(f"[ROUTER] ❌ Task {current_idx} failed. Replanning...")
        return "replan"

```

### 6. REPLAN 노드 (진짜 Backtracking!)

```python
def replan_node(state: AgentState) -> Dict[str, Any]:
    """
    🔥 실패 분석 → Backtrack index 결정

    핵심:
    - Root cause 분석
    - 어느 task로 돌아갈지 결정 (현재 or 이전)
    - 해당 task부터 재실행
    """
    print("\\n[REPLAN] Analyzing failure and determining backtrack point...")

    replan_count = state.get('replan_count', 0)
    if replan_count >= MAX_REPLAN_COUNT:
        print(f"[REPLAN] ❌ Maximum replan count ({MAX_REPLAN_COUNT}) reached")
        return {"error": "Maximum replan limit reached"}

    current_idx = state['current_task_index']
    task_results = state['task_results']
    current_result = task_results[current_idx]
    validation = state['validation_feedback']

    # Planner에게 replan 요청
    new_plan = planner.replan(
        failed_task=current_result,
        error_message=validation.get('errors', ['Unknown error'])[0],
        validation_result=validation,
        previous_attempts=state.get('execution_log', [])
    )

    if new_plan.get("error"):
        return {"error": f"Replanning failed: {new_plan['error']}"}

    # 🔥 핵심: backtrack_to_task_id 결정!
    # Planner가 분석 결과:
    # - 현재 task만 문제: backtrack_to = current_idx
    # - 이전 task 문제: backtrack_to < current_idx (진짜 backtracking!)
    backtrack_to = new_plan.get("backtrack_to_task_id", current_idx)
    new_instruction = new_plan.get("parameters", {}).get("instruction")
    tool_override = new_plan.get("tool_name")

    print(f"[REPLAN] Attempt {replan_count + 1}/{MAX_REPLAN_COUNT}")
    print(f"[REPLAN] Current task: {current_idx}")
    print(f"[REPLAN] 🔙 Backtrack to task: {backtrack_to}")

    if backtrack_to < current_idx:
        print(f"[REPLAN] ⚠️ Root cause in earlier task! Backtracking {current_idx - backtrack_to} steps")

    if new_instruction:
        print(f"[REPLAN] 📝 New instruction: {new_instruction[:80]}...")
    if tool_override:
        print(f"[REPLAN] 🔧 Tool override: {tool_override}")

    # 🔥 Task results 정리 (backtrack_to 이후 결과 삭제)
    # 예: backtrack_to=1이면 task 0,1 결과만 유지, 2부터 삭제
    task_results_cleaned = task_results[:backtrack_to]

    return {
        "current_task_index": backtrack_to,
        "task_results": task_results_cleaned,
        "current_instruction": new_instruction,
        "replan_count": replan_count + 1,
        "validation_feedback": None  # Clear
    }

```

### 7. Graph 재구성

```python
def build_graph():
    """
    🔥 새로운 동적 루프 기반 Graph

    구조:
    START → PLAN → (EXECUTE → VALIDATE → ROUTER) 루프 → END
                            ↓ fail
                         REPLAN → EXECUTE (backtrack)
    """
    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("initialize_state", initialize_state)
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("validate_task", validate_task_node)
    workflow.add_node("replan", replan_node)

    # Entry
    workflow.set_entry_point("initialize_state")

    # Linear edges
    workflow.add_edge("initialize_state", "plan")
    workflow.add_edge("plan", "execute_task")
    workflow.add_edge("execute_task", "validate_task")

    # 🔥 Router (핵심 분기점!)
    workflow.add_conditional_edges(
        "validate_task",
        router,
        {
            "execute_task": "execute_task",  # 다음 task 실행 (루프!)
            "replan": "replan",              # 재계획
            "end": END                       # 모든 task 완료
        }
    )

    # 🔥 Replan 후 backtrack (루프로 복귀)
    workflow.add_edge("replan", "execute_task")

    return workflow.compile()

```

---

### 🎁 예상 효과

### 1. 진짜 동적 Planning

**Document A (복잡한 구조):**

```json
{
  "tasks": [
    {"task_id": 0, "tool_name": "section_classifier"},
    {"task_id": 1, "tool_name": "definition_extract_v2"},
    {"task_id": 2, "tool_name": "llm_cartesian", "fallback": null},
    {"task_id": 3, "tool_name": "intelligent_condition_extract"},
    {"task_id": 4, "tool_name": "grouping_logic_extractor"},
    {"task_id": 5, "tool_name": "combination_generator"}
  ],
  "reasoning": "복잡한 구조, LLM 위주 전략"
}

```

**Document B (표준 구조):**

```json
{
  "tasks": [
    {"task_id": 0, "tool_name": "section_classifier"},
    {"task_id": 1, "tool_name": "definition_extract_v2"},
    {"task_id": 2, "tool_name": "rule_cartesian", "fallback": "llm_cartesian"}
  ],
  "reasoning": "표준 구조, Rule 위주로 빠르게"
}

```

### 2. 진짜 Backtracking

**시나리오: Task 3 실패, 근본 원인은 Task 1**

```
[현재 시스템]
Task 1 ✅ (잘못된 추출이지만 통과)
Task 2 ✅
Task 3 ❌ (Task 1 결과가 이상함)
  → replan → Task 3 재시도 ❌ (여전히 실패)
  → replan → Task 3 재시도 ❌
  → 포기

[새 시스템]
Task 1 ✅ (잘못된 추출)
Task 2 ✅
Task 3 ❌
  → Validator: "Task 1의 추출에 문제"
  → replan: backtrack_to_task_id = 1
  → Task 1 재실행 (instruction with) ✅
  → Task 2 재실행 ✅
  → Task 3 재실행 ✅
  → 성공!

```

### 3. 코드 간결화

```python
# 현재: 노드마다 별도 함수
classify_sections()      # 130 lines
extract_definitions()    # 80 lines
normalize_definitions()  # 50 lines
extract_conditions()     # 90 lines
normalize_conditions()   # 50 lines
extract_grouping_logic() # 70 lines
generate_combinations()  # 80 lines
# 총 ~550 lines

# 새 시스템: 일반화된 executor
execute_task_node()      # ~100 lines (모든 task 처리!)
prepare_params()         # ~50 lines
# 총 ~150 lines

# 코드 73% 감소!

```

### 4. 확장성

```python
# 새 Tool 추가 시

# 현재: agent.py 수정 필요
# 1. 새 노드 함수 작성 (80 lines)
# 2. should_continue 수정
# 3. after_replan 수정
# 4. Graph 구조 수정
# → 4개 파일 수정

# 새 시스템: tool_schemas만 추가
# 1. hybrid_tools.py에 새 Tool 클래스 작성
# 2. tool_schemas.py에 schema 추가
# → Planner가 자동으로 활용!
# → agent.py 수정 불필요!

```

---

### ⚠️ 구현 시 주의사항

### 1. Planner Prompt 대폭 업데이트 필요

**현재 (core/prompt.py:16-57):**

```python
"""
**Task 구성**:
   - 정확히 3단계의 Task를 구성하세요 (고정된 워크플로우)
"""

```

**수정 필요:**

```python
"""
**Task 구성 가이드라인**:

1. **동적 단계 수**:
   - 문서 복잡도에 따라 3~7단계 구성
   - 단순 문서: 3단계 (classify → extract → transform)
   - 복잡 문서: 7단계 (전체 workflow)

2. **필수 Task**:
   - task_id: 0부터 순차 증가
   - type: "classify" | "extract" | "normalize" | "transform" | "merge"
   - tool_name: 실제 Tool 이름
   - parameters: Tool에 전달할 고정 파라미터
   - depends_on: 의존하는 이전 task_id (null이면 독립)
   - fallback: (optional) 실패 시 대체 tool

3. **사용 가능한 Tool**:
   {tool_schemas}

4. **예시 Plan**:
   ```json
   {
     "tasks": [
       {
         "task_id": 0,
         "type": "classify",
         "tool_name": "section_classifier",
         "parameters": {},
         "depends_on": null,
         "fallback": null
       },
       {
         "task_id": 1,
         "type": "extract",
         "tool_name": "definition_extract_v2",
         "parameters": {},
         "depends_on": 0,
         "fallback": null
       },
       {
         "task_id": 2,
         "type": "transform",
         "tool_name": "rule_cartesian",
         "parameters": {},
         "depends_on": 1,
         "fallback": "llm_cartesian"
       }
     ],
     "reasoning": "표준 테이블 형식 → Rule 우선",
     "estimated_difficulty": "easy"
   }

```

"""

```

#### 2. Replan Prompt도 업데이트

**추가 필요:**
```python
def build_replan_prompt(...):
    """
    **중요: backtrack_to_task_id 결정**

    실패 원인 분석:
    1. 현재 task의 로직 문제 → backtrack_to = current_task_id
    2. 이전 task의 잘못된 출력 → backtrack_to = 근본 원인 task_id

    예시:
    - Task 3 실패: "normalize_definitions의 header가 이상함"
    - 원인 분석: Task 1 (extract_definitions)이 잘못된 header 추출
    - 결정: backtrack_to_task_id = 1

    **출력 형식**:
    {
      "backtrack_to_task_id": 1,
      "reasoning": "Task 1의 추출에 오류, 재실행 필요",
      "parameters": {
        "instruction": "header의 첫 컬럼은 반드시 '보종명'으로"
      },
      "tool_name": null  # 같은 tool 사용
    }
    """

```

### 3. Validator 강화 필요

**Root cause 힌트 제공:**

```python
# 현재
{
  "is_valid": False,
  "errors": ["데이터가 이상함"],
  "suggestions": ["다시 확인"]
}

# 수정
{
  "is_valid": False,
  "errors": ["normalize_definitions의 header 형식 오류"],
  "suggestions": ["extract_definitions 단계 재확인 필요"],
  "possible_root_cause_task": "extract",  # 🔥 추가!
  "reasoning": "header가 ['명칭', '유형']인데 정규화 후 ['유형1', '유형2']가 됨. 원본 추출 오류로 판단"
}

```

### 4. 하위 호환성

**기존 실행 로그와 호환성 유지:**

- `task_results` 형식은 기존 validator와 호환
- `execution_log`도 동일 형식 유지
- 점진적 마이그레이션 가능

### 5. 테스트 전략

```python
# Phase 1: 단순 케이스 (3단계)
test_doc_simple = {...}  # classify → extract → transform

# Phase 2: 복잡 케이스 (7단계)
test_doc_complex = {...}  # 전체 workflow

# Phase 3: Backtracking
test_doc_need_backtrack = {...}  # Task 1 실패 시나리오

# Phase 4: 기존 문서들
test_all_existing_docs()  # 성공률 유지 확인

```

---

### 📊 예상 소요 시간

| 단계 | 작업 | 예상 시간 |
| --- | --- | --- |
| 1 | State 재설계 + AgentState 수정 | 1시간 |
| 2 | plan_node 구현 | 0.5시간 |
| 3 | execute_task_node + prepare_params 구현 | 2시간 |
| 4 | validate_task_node 수정 | 1시간 |
| 5 | router 구현 | 0.5시간 |
| 6 | replan_node 구현 (backtracking 로직) | 2시간 |
| 7 | Graph 재구성 | 1시간 |
| 8 | Planner prompt 대폭 수정 | 1.5시간 |
| 9 | Replan prompt 수정 | 1시간 |
| 10 | 테스트 (단순 → 복잡 → backtrack) | 3시간 |
| 11 | 디버깅 및 수정 | 2시간 |
| **총** |  | **15.5시간** |

**단계별 진행:**

- **Phase 1** (6시간): 기본 구조 구현 (plan → execute → validate loop)
- **Phase 2** (4시간): Backtracking 구현 (replan → backtrack)
- **Phase 3** (3시간): Prompt 고도화 (동적 planning, root cause)
- **Phase 4** (2.5시간): 테스트 및 최적화

---

### 🎯 마이그레이션 전략

**Option 1: 병렬 개발**

```
prototype_6/
  ├── agent.py (기존)
  ├── agent_v2.py (새 버전)
  ├── main.py → agent.py 사용 (안정)
  └── main_v2.py → agent_v2.py 사용 (실험)

```

**Option 2: Feature Flag**

```python
USE_DYNAMIC_LOOP = os.getenv("USE_DYNAMIC_LOOP", "false") == "true"

if USE_DYNAMIC_LOOP:
    graph = build_dynamic_graph()
else:
    graph = build_graph()  # 기존

```

**Option 3: 직접 교체**

```
- 기존 agent.py 백업
- 새 버전으로 교체
- 전체 테스트

```

**추천: Option 1 (병렬 개발)**

- 안정성 유지
- 비교 테스트 가능
- 점진적 마이그레이션

---

### 🚀 다음 단계

1. **설계 검토**: 팀원들과 새 구조 리뷰
2. **Proof of Concept**: 단순 케이스로 동작 확인
3. **점진적 구현**: Phase별로 단계적 개발
4. **병렬 테스트**: 기존 vs 새 시스템 성능 비교
5. **완전 전환**: 안정성 확인 후 production 적용

---

*작성일: 2024버전: Prototype 6 (7-Step Grouping-based Architecture)다음 버전: Prototype 7 (Dynamic Loop-based Agentic Architecture) - 계획 중파일: E:\work\work\Agent\prototype_6\new_WORKFLOW.md*