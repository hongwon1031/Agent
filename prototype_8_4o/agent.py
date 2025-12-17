"""
Prototype 7: LangGraph-based Agent with Dynamic Planning and Pydantic Validation.
Refactored to use a Tool-based architecture, removing legacy Prototype 6 nodes.
"""
import json
import re
import time
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, ValidationError, conlist, field_validator

from langgraph.graph import StateGraph, END

from core.state import AgentState
from core.llm_planner import LLMPlanner
from core.llm_validator import LLMValidator
from core.document_accessor import DocumentAccessor
from tools.hybrid_tools import (
    SectionClassifierTool,
    DefinitionExtractToolV2,
    LLMCartesianTool,
    RuleCartesianTool,
    IntelligentConditionExtractTool,
    LLMTableSplitTool,
    RuleTableSplitTool,
    ConditionTransformTool,
    GroupingLogicExtractorTool,
    CombinationGeneratorTool,
)

# Helper class for tool results
class ToolResult:
    """A simple class to encapsulate the result of a tool execution."""
    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error

# --- [NEW] Refactored Tool Classes ---
class NormalizeDefinitionsTool:
    """
    [NEW] Tool to normalize definition table columns.
    Encapsulates the logic from the old P6 'normalize_definitions' node.
    """
    def __init__(self):
        self.name = "normalize_definitions"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        print(f"\n[TOOL] {self.name}: Normalizing column names...")

        header = params.get("header")
        data = params.get("data")

        if not isinstance(header, list) or data is None:
            return ToolResult(
                success=False,
                error=f"Invalid parameters: 'header' (list) and 'data' are required. Got header={type(header)}, data={type(data)}"
            )

        normalized_header = []
        if header:
            normalized_header.append("보종명")
            for i in range(1, len(header)):
                normalized_header.append(f"유형{i}")
        
        print(f"[OK] Normalized {len(header)} columns: {header} -> {normalized_header}")

        output_data = {
            "header": normalized_header,
            "data": data
        }
        
        return ToolResult(success=True, data=output_data)

class NormalizeConditionsTool:
    """
    [NEW] Tool to normalize condition table columns.
    Encapsulates the logic from the old P6 'normalize_conditions' node.
    """
    def __init__(self):
        self.name = "normalize_conditions"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        print(f"\n[TOOL] {self.name}: Normalizing condition columns...")

        header = params.get("header")
        data = params.get("data")
        
        if header is None or data is None:
            print("[INFO] No condition data to normalize. Passing through empty.")
            return ToolResult(success=True, data={"header": [], "data": []})

        if not isinstance(header, list) or not isinstance(data, list):
            return ToolResult(
                success=False,
                error=f"Invalid parameters: 'header' and 'data' must be lists. Got header={type(header)}, data={type(data)}"
            )

        print(f"[OK] Condition columns passed through: {header}")

        output_data = {
            "header": header,
            "data": data
        }

        return ToolResult(success=True, data=output_data)

# --- Core Components and Tools Initialization ---
planner = LLMPlanner()
validator = LLMValidator()

tools = {
    "section_classifier": SectionClassifierTool(),
    "definition_extract_v2": DefinitionExtractToolV2(),
    "normalize_definitions": NormalizeDefinitionsTool(),
    "normalize_conditions": NormalizeConditionsTool(),
    "rule_cartesian": RuleCartesianTool(),
    "llm_cartesian": LLMCartesianTool(),
    "condition_extract": IntelligentConditionExtractTool(),
    "llm_table_split": LLMTableSplitTool(),
    "rule_table_split": RuleTableSplitTool(),
    "condition_transform": ConditionTransformTool(),

    "grouping_logic_extractor": GroupingLogicExtractorTool(),
    "combination_generator": CombinationGeneratorTool(),
}

# --- [NEW] Pydantic Models for Plan Validation ---
# 개별적인 task 구조
class Task(BaseModel):
    task_id: str # task id
    task_type: str # task 종류
    tool_name: str # 실행 tool
    fallback_tool: Optional[str] = None # main 툴 실패시 대체옵션
    parameters: Dict[str, Any] # 입력값
    dependencies: List[str] # 해당 task 실행 전 완료되어야하는 task(의존성)
    output_key: str # 결과물 state에 저장할 때 사용할 key

    @field_validator('tool_name')
    @classmethod
    def validate_tool_name(cls, v):
        if v not in tools:
            raise ValueError(f"Invalid tool_name: {v}. Available tools: {list(tools.keys())}")
        return v

    @field_validator('fallback_tool')
    @classmethod
    def validate_fallback_tool(cls, v):
        if v is not None and v not in tools:
            raise ValueError(f"Invalid fallback_tool: {v}. Available tools: {list(tools.keys())}")
        return v

class Plan(BaseModel):
    total_tasks: int
    tasks: conlist(Task, min_length=1)
    reasoning: str

MAX_REPLAN_COUNT = 3
MAX_TASK_RETRIES = 3
MAX_TOTAL_TASKS = 15  # Maximum total number of tasks (including retries) to prevent infinite loops
MAX_EVENT_HISTORY = 2000


def _safe_preview(
    value: Any,
    max_str: int = 300,
    max_list: int = 30,
    max_depth: int = 4,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return "<max_depth>"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        s = value.replace("\r\n", "\n")
        return s if len(s) <= max_str else s[:max_str] + "...(truncated)"
    if isinstance(value, list):
        if len(value) > max_list:
            return [_safe_preview(v, max_str, max_list, max_depth, _depth + 1) for v in value[:max_list]] + [
                f"...(+{len(value) - max_list} items)"
            ]
        return [_safe_preview(v, max_str, max_list, max_depth, _depth + 1) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in list(value.items())[:50]:
            out[str(k)] = _safe_preview(v, max_str, max_list, max_depth, _depth + 1)
        if len(value) > 50:
            out["..."] = f"+{len(value) - 50} keys"
        return out
    return str(value)


def _append_event(state: AgentState, event: Dict[str, Any]) -> None:
    history = state.get("event_history")
    if not isinstance(history, list):
        history = []
    event = dict(event)
    event.setdefault("ts", time.time())
    history.append(event)
    if len(history) > MAX_EVENT_HISTORY:
        history[:] = history[-MAX_EVENT_HISTORY:]
    state["event_history"] = history

# ============================================================================
# PROTOTYPE 7: TEMPLATE RESOLUTION
# ============================================================================

def validate_task_definition(current_task: Dict[str, Any], task_results: list) -> Dict[str, Any]:
    """
    범용 Task Definition Validator - 어떤 task에도 적용 가능한 규칙들만 검증

    검증 항목:
    1. Dependency가 실제로 완료됐는지
    2. Template에서 참조하는 task가 존재하는지
    3. Tool이 레지스트리에 있는지

    Args:
        current_task: 검증할 task definition
        task_results: 이미 완료된 task 목록

    Returns:
        {
            "is_valid": bool,
            "error": str (if not valid),
            "error_type": "task_definition_error" (if not valid),
            "suggestion": str (if not valid)
        }
    """
    task_id = current_task.get("task_id", "unknown")

    # Rule 1: Dependency 검증 (성공한 task만)
    dependencies = current_task.get("dependencies", [])
    if dependencies is None or dependencies == "none" or dependencies == ["none"]:
        dependencies = []

    completed_ids = [r.get("task_id") for r in task_results if r.get("success")]

    for dep_id in dependencies:
        if dep_id not in completed_ids:
            return {
                "is_valid": False,
                "error": f"Task {task_id} depends on {dep_id}, but {dep_id} is not completed successfully",
                "error_type": "task_definition_error",
                "suggestion": f"Complete {dep_id} first or remove it from dependencies"
            }

    # Rule 2: Template에서 참조하는 task가 존재하는지 (사전 검증)
    import re
    params_str = str(current_task.get("parameters", {}))
    template_pattern = r'\{\{(task\d+)[.\[]'  # {{task0.data}} or {{task0[
    referenced_tasks = re.findall(template_pattern, params_str)

    for ref_task in set(referenced_tasks):
        if ref_task not in completed_ids:
            return {
                "is_valid": False,
                "error": f"Task {task_id} references {ref_task} in parameters, but {ref_task} is not completed",
                "error_type": "task_definition_error",
                "suggestion": f"Add {ref_task} to dependencies or remove reference"
            }

    # Rule 3: Tool 존재 여부 (이미 plan_node에서 체크하지만 이중 안전장치)
    tool_name = current_task.get("tool_name")
    if tool_name not in tools:
        return {
            "is_valid": False,
            "error": f"Task {task_id} uses unknown tool: {tool_name}",
            "error_type": "task_definition_error",
            "suggestion": f"Use one of available tools: {list(tools.keys())}"
        }

    fallback = current_task.get("fallback_tool")
    if fallback and fallback not in tools:
        return {
            "is_valid": False,
            "error": f"Task {task_id} uses unknown fallback tool: {fallback}",
            "error_type": "task_definition_error",
            "suggestion": f"Use one of available tools: {list(tools.keys())}"
        }

    return {"is_valid": True}


def resolve_templates(params: Dict[str, Any], task_results: list, document: Any, sections: Any = None) -> Dict[str, Any]:
    """
    Resolve template placeholders in task parameters.
    Supports:
      - "$sections"
      - "{{taskN.data.xxx}}"
      - "{taskN.data.xxx}"  (auto-normalized to double braces)
    """
    import re
    import json

    # match double braces like {{ ... }}
    template_pattern = re.compile(r"\{\{([^}]+)\}\}")
    # match single-brace whole-string like { ... }
    single_whole_pattern = re.compile(r"^\{([^{}]+)\}$")

    def resolve_value(value: Any) -> Any:
        if isinstance(value, str):
            v = value.strip()

            # 0) runtime tokens
            if v == "$sections":
                return sections
            if v == "$doc" or v == "$document":
                return document

            # 1) normalize single-brace whole-string -> double brace
            #    ex) "{task8.data.definition_core}" -> "{{task8.data.definition_core}}"
            m = single_whole_pattern.fullmatch(v)
            if m:
                v = "{{" + m.group(1).strip() + "}}"

            # 2) find templates
            matches = template_pattern.findall(v)
            if not matches:
                return value  # return original (not stripped) to preserve formatting

            result = v
            for match in matches:
                match = match.strip()

                # special
                if match == "document":
                    doc_str = json.dumps(document, ensure_ascii=False) if isinstance(document, (dict, list)) else str(document)
                    result = result.replace(f"{{{{{match}}}}}", doc_str)
                    continue

                # task reference
                if match.startswith("task"):
                    try:
                        parts = match.split(".")
                        task_id, field_path = parts[0], parts[1:]

                        # allow both taskN.xxx and taskN.data.xxx
                        if field_path and field_path[0] == "data":
                            field_path = field_path[1:]

                        # remove filters like "| join(',')"
                        clean = []
                        for f in field_path:
                            clean_field = f.split("|", 1)[0].strip()
                            if clean_field:
                                clean.append(clean_field)
                        field_path = clean

                        task_result = next((tr for tr in task_results if tr.get("task_id") == task_id), None)
                        if not task_result:
                            raise KeyError(f"task '{task_id}' not found in task_results")

                        current = task_result.get("data")
                        for field in field_path:
                            if isinstance(current, dict):
                                current = current.get(field)
                            elif isinstance(current, list) and field.isdigit():
                                current = current[int(field)]
                            else:
                                current = None
                                break

                        if current is None:
                            raise KeyError(f"field path not found: {task_id}." + ".".join(field_path))

                        # if the whole string is exactly the template, return raw object (list/dict/int)
                        if result == f"{{{{{match}}}}}":
                            return current

                        # otherwise embed as string (json for non-str)
                        replacement = current if isinstance(current, str) else json.dumps(current, ensure_ascii=False)
                        result = result.replace(f"{{{{{match}}}}}", replacement)

                    except Exception as e:
                        # IMPORTANT: fail fast so we don't pass unresolved string to tools
                        raise ValueError(f"Template resolution failed for '{value}': {e}") from e

            # 3) fail-fast if any template-like residue remains
            if "{{" in result or "}}" in result or single_whole_pattern.fullmatch(result.strip()):
                raise ValueError(f"Unresolved template remains after resolution: {result}")

            return result

        elif isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(v) for v in value]
        else:
            return value

    return resolve_value(params)

# ============================================================================
# PROTOTYPE 7: DYNAMIC NODES
# ============================================================================

def plan_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7 v2: Generate the next single task based on completed tasks.

    This is called:
    1. Initially (task_results empty) - generates first task
    2. After each task validation - generates next task or signals completion
    """
    doc = state.get('original_doc') # 원본 문서
    task_results = state.get('task_results', []) # 수행 완료된 task의 결과들
    task_history = state.get('task_history', []) # 전체 히스토리 (재시도 포함)
    last_feedback = state.get("last_validation_feedback") or {} # 마지막 검증 결과
    backtrack_to = state.get("backtrack_to_task_id") # 백트래킹할곳
    current_task_state = state.get("current_task") # 최근 검증 task
    retry_counts = state.get("retry_counts", {}) # 재시도 횟수

    # Check total planning limit (based on planner call count, not truncated by backtracking)
    planner_stats = planner.get_llm_usage_stats()
    total_planning_calls = planner_stats.get("generate_next_task", {}).get("call_count", 0)

    if total_planning_calls >= MAX_TOTAL_TASKS:
        error_msg = f"Maximum planning limit ({MAX_TOTAL_TASKS}) exceeded. Total planning calls: {total_planning_calls}."
        print(f"[PLAN NODE ERROR] {error_msg}")
        return {
            "error": error_msg,
            "current_task": None  # Ensure conditional edge routes to END
        }

    # 백트래킹
    backtrack_instruction = ""
    backtracking_occurred = False  # NEW: Track if backtracking actually happened
    if backtrack_to:
        _append_event(
            state,
            {
                "event": "backtrack_requested",
                "backtrack_to_task_id": backtrack_to,
                "backtrack_reasoning": state.get("backtrack_reasoning", ""),
                "task_results_count_before": len(task_results),
            },
        )
        ids = [r.get("task_id") for r in task_results]
        if backtrack_to in ids:
            idx = ids.index(backtrack_to)

            # NEW: Dependency-aware backtracking
            # Find all tasks that depend on backtrack_to (directly or indirectly)
            all_task_definitions = state.get("all_task_definitions", {})
            tasks_to_rerun = set([backtrack_to])

            # BFS로 backtrack_to에 의존하는 task들 찾기
            queue = [backtrack_to]
            while queue:
                current = queue.pop(0)
                for completed_id in ids[idx:]:  # Only check tasks after backtrack_to
                    task_def = all_task_definitions.get(completed_id)
                    if task_def:
                        deps = task_def.get("dependencies", [])
                        # Handle both list and string "none"
                        if deps and deps != "none" and deps != ["none"]:
                            if current in deps:
                                if completed_id not in tasks_to_rerun:
                                    tasks_to_rerun.add(completed_id)
                                    queue.append(completed_id)

            # 되돌려야 하는 task들 중 가장 앞쪽 인덱스 서치
            min_idx = idx
            for task_id in tasks_to_rerun:
                if task_id in ids:
                    task_idx = ids.index(task_id)
                    min_idx = min(min_idx, task_idx)

            # task_result를 min_idx 이전까지만 남기고 전부 삭제
            task_results = task_results[:min_idx]
            backtracking_occurred = True  # NEW: Mark that backtracking happened
            _append_event(
                state,
                {
                    "event": "backtrack_applied",
                    "backtrack_to_task_id": backtrack_to,
                    "tasks_to_rerun": sorted(tasks_to_rerun),
                    "kept_task_results_count": len(task_results),
                },
            )

            # NEW: 되돌릴 task들의 retry count 초기화
            retry_counts = dict(state.get("retry_counts", {}))
            for task_id in tasks_to_rerun:
                if task_id in retry_counts:
                    old_count = retry_counts.pop(task_id)
                    print(f"[P7 NODE] Resetting retry count for {task_id} (was {old_count})")
                    _append_event(
                        state,
                        {"event": "retry_reset", "task_id": task_id, "previous_retry_count": old_count},
                    )

            # CRITICAL:backtrack_reasoning 있으면 플래너에게 줄 추가 지시문 생성
            backtrack_reasoning = state.get("backtrack_reasoning", "")
            if backtrack_reasoning:
                backtrack_instruction = f"[BACKTRACK] {backtrack_to}와 그 의존 작업들을 재실행합니다. 실패 원인: {backtrack_reasoning}"
                print(f"[P7 NODE] Dependency-aware backtracking: {sorted(tasks_to_rerun)}")
                print(f"[P7 NODE] Truncating to index {min_idx} (was {len(ids)}, removed {len(ids)-min_idx} tasks)")
                print(f"[P7 NODE] Backtrack reasoning: {backtrack_reasoning[:]}...")
            else:
                print(f"[P7 NODE] Backtracking to {backtrack_to}: trimming results to {len(task_results)} entries")

            # FIX: Reset current_task after backtracking to prevent stale task info
            current_task_state = None
            print(f"[P7 NODE] Cleared current_task after backtracking")
        else:
            print(f"[P7 NODE] Backtrack target {backtrack_to} not found in results; ignoring.")
        # clear backtrack flag
        backtrack_to = None

    num_completed = len(task_results)
    print(f"\n[P7 NODE] plan_node: Generating next task (completed: {num_completed})...")

    # FIXED: Check if we need to force retry due to validation failure
    print(f"[DEBUG] Checking validation status...")
    last_validation = state.get("last_validation_feedback")
    print(f"[DEBUG] last_validation type: {type(last_validation)}, value: {last_validation}")

    if last_validation is None:
        last_validation = {}

    print(f"[DEBUG] backtrack_instruction: {backtrack_instruction}")

    if not last_validation.get("is_valid", True) and not backtrack_instruction:
        # Validation failed and no backtracking scheduled
        # Find the failed task and check if we should retry
        task_results_list = state.get("task_results", [])
        failed_task_id = None

        for result in reversed(task_results_list):
            if result and result.get("validation_failed"):
                failed_task_id = result.get("task_id")
                break

        if failed_task_id:
            retry_counts = state.get("retry_counts", {})
            retries = retry_counts.get(failed_task_id, 0)

            if retries < MAX_TASK_RETRIES:
                # Force retry: reuse previous task definition
                all_task_definitions = state.get("all_task_definitions", {})
                if failed_task_id in all_task_definitions:
                    task_def = all_task_definitions[failed_task_id]
                    print(f"[P7 NODE] FORCE RETRY: {failed_task_id} (attempt {retries + 1}/{MAX_TASK_RETRIES})")
                    print(f"[P7 NODE] Validation errors: {last_validation.get('errors', [])}")
                    print(f"[P7 NODE] Reusing task definition with same parameters")

                    _append_event(
                        state,
                        {
                            "event": "force_retry",
                            "task_id": failed_task_id,
                            "retry_attempt": retries + 1,
                            "max_retries": MAX_TASK_RETRIES,
                            "reason": "validation_failed_without_backtracking",
                        },
                    )

                    return {
                        "current_task": task_def,
                        "is_complete": False,
                        "task_results": task_results,
                        "backtrack_to_task_id": None,
                        "backtrack_reasoning": "",
                        "all_task_definitions": all_task_definitions,
                        "retry_counts": retry_counts,
                        "event_history": state.get("event_history", []),
                    }

    # Call LLM to get next task or end signal
    # instruction 생성 (3가지 우선순위)
    extra_instruction = ""
    feedback_for_planner = last_feedback  # Will be cleared if backtracking

    # PRIORITY 1:백트래킹 instruction
    if backtrack_instruction:
        extra_instruction = backtrack_instruction
        # FIX: Clear last_feedback during backtracking to prevent confusion
        feedback_for_planner = None
        print(f"[P7 NODE] Cleared last_feedback during backtracking to prevent confusion")
    # PRIORITY 2: task 정의 자체가 틀려서 재설계 필요한 경우
    elif last_feedback and last_feedback.get("skip_retry"):
        failed_task_id = state.get("failed_task_id", "unknown")
        errors = last_feedback.get("errors", [])
        suggestions = last_feedback.get("suggestions", [])
        parts = [f"[RE-PLAN] Task {failed_task_id}의 정의가 잘못되었습니다."]
        if errors:
            parts.append("오류: " + "; ".join(map(str, errors))[:400])
        if suggestions:
            parts.append("제안: " + "; ".join(map(str, suggestions))[:400])
        parts.append("완전히 새로운 task를 생성하세요. 이전 task는 폐기하십시오.")
        extra_instruction = " / ".join(parts)
        print(f"[P7 NODE] Re-plan instruction prepared: {extra_instruction[:150]}...")
    # PRIORITY 3: 일반적인 validtion 피드백(오류/개선 지시)
    else:
        last_feedback = state.get("last_validation_feedback") or {}
        if last_feedback and not last_feedback.get("is_valid", True):
            errors = last_feedback.get("errors", [])
            suggestions = last_feedback.get("suggestions", [])
            parts = []
            if errors:
                parts.append("최근 오류: " + "; ".join(map(str, errors))[:400])
            if suggestions:
                parts.append("개선 지시: " + "; ".join(map(str, suggestions))[:400])
            if parts:
                extra_instruction = " / ".join(parts)
    
    # 플래너
    result = planner.generate_next_task(doc=doc,
                                        task_results=task_results,
                                        instruction=extra_instruction,
                                        last_feedback = feedback_for_planner,  # FIX: Use cleared feedback during backtracking
                                        last_task = current_task_state)
    if result.get("error"):
        print(f"[FAIL] Task generation failed: {result['error']}")
        return {"error": f"Task generation failed: {result['error']}"}

    action = result.get("action")
    _append_event(
        state,
        {
            "event": "planner_response",
            "action": action,
            "reasoning_preview": _safe_preview(result.get("reasoning", ""), max_str=400),
            "task_results_count": len(task_results),
        },
    )


    # 종료
    if action == "end":
        # All tasks complete
        print(f"[OK] Planner signals completion")
        print(f"  - Reasoning: {result.get('reasoning', 'N/A')[:100]}...")
        return {
            "is_complete": True,
            "current_task": None,
            "task_results": task_results,
            "backtrack_to_task_id": None,
            "backtrack_reasoning": "",
            "retry_counts": retry_counts,  # Propagate updated retry_counts
            "event_history": state.get("event_history", []),
        }

    # 다음 task 진행
    elif action == "next_task":
        # New task to execute
        task = result.get("task")
        task_id = task.get("task_id")
        print(f"[OK] Next task generated: {task_id}")
        print(f"  - Type: {task.get('task_type')}")
        print(f"  - Tool: {task.get('tool_name')}")
        print(f"  - Reasoning: {result.get('reasoning', 'N/A')[:100]}...")

        # 유효한 tool / fallback_tool인지 체크
        tool_name = task.get("tool_name")
        if tool_name not in tools:
            return {"error": f"Invalid tool_name: {tool_name}. Available: {list(tools.keys())}"}

        # Validate fallback tool if specified
        fallback = task.get("fallback_tool")
        if fallback and fallback not in tools:
            return {"error": f"Invalid fallback_tool: {fallback}"}

        # NEW: 이 task 정의를 all_task_definitions에 저장(나중에 dependency 기반 backtracking용)
        all_task_definitions = state.get("all_task_definitions", {})
        all_task_definitions[task_id] = task
        print(f"[DEBUG] Saved task definition for {task_id} (dependencies: {task.get('dependencies', [])})")
        _append_event(
            state,
            {
                "event": "task_scheduled",
                "task_id": task_id,
                "task_type": task.get("task_type"),
                "tool_name": task.get("tool_name"),
                "fallback_tool": task.get("fallback_tool"),
                "dependencies": task.get("dependencies", []),
                "parameters_preview": _safe_preview(task.get("parameters", {})),
            },
        )

        return {
            "current_task": task,
            "is_complete": False,
            "task_results": task_results,
            "backtrack_to_task_id": None,
            "backtrack_reasoning": "",
            "all_task_definitions": all_task_definitions,  # NEW
            "retry_counts": retry_counts,  # Propagate updated retry_counts
            "event_history": state.get("event_history", []),
        }

    else:
        return {"error": f"Unknown action from planner: {action}"}

# execute node
# 현재 state에 들어있는 current_task를 실제로 실행하고 결과/에러를 task_result에 기록
def execute_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7 v2: Execute the current task.
    """
    print("\n[P7 NODE] execute_task_node: Executing current task...")
    # state에서 현재 상태 꺼냄
    current_task = state.get('current_task')
    task_results = state.get('task_results', [])
    task_history = state.get('task_history', [])  # NEW

    document = state.get('original_doc')
    sections = state.get('sections')

    if not current_task:
        return {"error": "No current_task to execute"}

    task_id = current_task.get('task_id')
    print(f"[INFO] Executing {task_id}: {current_task.get('description', 'N/A')}")
    _append_event(
        state,
        {
            "event": "task_execute_start",
            "task_id": task_id,
            "task_type": current_task.get("task_type"),
            "tool_name": current_task.get("tool_name"),
        },
    )

    # ========== STEP 1: Task Definition Validation ==========
    print(f"[VALIDATE] Checking task definition for {task_id}...")
    definition_check = validate_task_definition(current_task, task_results)

    if not definition_check.get("is_valid"):
        error_msg = definition_check.get("error", "Unknown definition error")
        suggestion = definition_check.get("suggestion", "")
        print(f"[FAIL] Task definition invalid: {error_msg}")
        print(f"[SUGGESTION] {suggestion}")

        # NEW: Use separate flag for recoverable task_definition_error (not "error")
        return {
            "task_definition_failed": True,  # NEW: Recoverable error flag
            "task_definition_error": error_msg,  # NEW: Error message
            "error_type": "task_definition_error",
            "error_suggestion": suggestion,
            "failed_task_id": task_id
            # NOTE: "error" field NOT set → won't trigger END in router
        }

    print(f"🚨[OK] Task definition valid")

    # ========== STEP 2: Template Resolution (with error classification) ==========
    try:
        resolved_params = resolve_templates(current_task.get('parameters', {}), task_results, document, sections)
        print(f"[INFO] Parameters resolved: {len(str(resolved_params))} chars")
    except KeyError as e:
        # Template reference to non-existent task → Task Definition Error
        error_msg = f"Template resolution failed (KeyError): {str(e)}"
        print(f"[FAIL] {error_msg}")
        return {
            "error": error_msg,
            "error_type": "task_definition_error",
            "error_suggestion": f"Task {task_id} references non-existent task or field. Check template syntax and dependencies.",
            "failed_task_id": task_id
        }
    except Exception as e:
        # Other template errors → Execution Error (retry 가능)
        error_msg = f"Template resolution failed: {str(e)}"
        print(f"[FAIL] {error_msg}")
        return {
            "error": error_msg,
            "error_type": "execution_error",
            "error_suggestion": "Check parameter format and try again",
            "failed_task_id": task_id
        }

    # ========== STEP 3: Tool Execution ==========
    tool_name = current_task.get('tool_name')
    tool = tools[tool_name]
    start_time = time.time()
    print(f"[INFO] Using primary tool: {tool_name}")

    try:
        result = tool.execute(doc=document, params=resolved_params)
    except Exception as e:
        # Tool execution exception → Execution Error
        error_msg = f"Tool {tool_name} raised exception: {str(e)}"
        print(f"[FAIL] {error_msg}")
        return {
            "error": error_msg,
            "error_type": "execution_error",
            "error_suggestion": f"Tool {tool_name} execution failed. Check tool implementation or parameters.",
            "failed_task_id": task_id
        }

    # Try fallback if primary fails
    fallback_tool_name = current_task.get('fallback_tool')
    if not result.success and fallback_tool_name:
        print(f"[INFO] Primary tool failed. Trying fallback: {fallback_tool_name}")
        tool = tools[fallback_tool_name]
        try:
            result = tool.execute(doc=document, params=resolved_params)
            tool_name = fallback_tool_name
        except Exception as e:
            error_msg = f"Fallback tool {fallback_tool_name} raised exception: {str(e)}"
            print(f"[FAIL] {error_msg}")
            return {
                "error": error_msg,
                "error_type": "execution_error",
                "error_suggestion": f"Both primary and fallback tools failed.",
                "failed_task_id": task_id
            }

    # Record result
    execution_time = time.time() - start_time
    task_result = {
        "task_id": task_id,
        "success": result.success,
        "data": result.data,
        "tool_used": tool_name,
        "execution_time": execution_time,
        "error": result.error if not result.success else None,
        "validation_result": None,  # FIXED: Will be updated by validate_task_node
        "validation_failed": False  # FIXED: Will be updated by validate_task_node
    }
    task_results.append(task_result)
    task_history.append(task_result)   
    _append_event(
        state,
        {
            "event": "task_execute_end",
            "task_id": task_id,
            "task_type": current_task.get("task_type"),
            "tool_used": tool_name,
            "success": bool(result.success),
            "execution_time": round(execution_time, 4),
            "error_preview": _safe_preview(result.error, max_str=500) if not result.success else None,
            "resolved_params_preview": _safe_preview(resolved_params),
            "output_preview": _safe_preview(result.data),
        },
    )
    
    if result.success:
        print(f"🚨[OK] Task {task_id} completed successfully ({execution_time:.2f}s)")
        print(f"[DEBUG] Output of {tool_name} (Task {task_id}): {result.data}")
    else:
        print(f"🚨[FAIL] Task {task_id} failed: {result.error}")
        print(f"[DEBUG] Failed output of {tool_name} (Task {task_id}): {result.error}")
        print(f"[DEBUG] Params for {tool_name} (Task {task_id}): {resolved_params}")

    return {
        "task_results": task_results,
        "task_history": task_history,
        "current_task_output": result.data,
        "error": result.error if not result.success else None,
        "error_type": "execution_error" if not result.success else None,
        "event_history": state.get("event_history", []),
    }

def validate_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Validate the current task output.
    """
    print("\n[P7 NODE] validate_task_node: Validating current task...")
    current_task = state.get('current_task')
    current_task_output = state.get('current_task_output')
    error_type = state.get('error_type')

    if not current_task:
        return {"error": "No current_task to validate"}

    # CRITICAL: Skip validation if task definition error (validation 무의미)
    if error_type == "task_definition_error":
        error_msg = state.get('error', 'Unknown task definition error')
        suggestion = state.get('error_suggestion', '')
        print(f"[SKIP] Skipping validation due to task_definition_error")
        print(f"[ERROR] {error_msg}")
        print(f"[SUGGESTION] {suggestion}")

        return {
            "validation_feedback": {
                "is_valid": False,
                "errors": [error_msg],
                "suggestions": [suggestion],
                "reasoning": "Task definition is invalid - re-planning required",
                "skip_retry": True  # Signal to not retry this task
            },
            "last_validation_feedback": {
                "is_valid": False,
                "errors": [error_msg],
                "suggestions": [suggestion],
                "reasoning": "Task definition is invalid - re-planning required",
                "skip_retry": True
            }
        }

    if current_task_output is None:
        print("[INFO] Task execution failed, analyzing root cause...")
        error_msg = state.get('error', 'Unknown execution error')
        tool_name = current_task.get('tool_name', 'unknown')
        task_type = current_task.get('task_type', 'unknown')
        task_id = current_task.get('task_id', 'unknown')

        print(f"[ERROR DETAILS] Task: {task_id}, Type: {task_type}, Tool: {tool_name}")
        print(f"[ERROR MESSAGE] {error_msg}")

        # Build context with previous results for root cause analysis
        context = {
            "previous_results": state.get('task_results', []),
            "execution_error": error_msg,
            "failed_task_id": task_id
        }

        # Call validator to analyze root cause even on execution failure
        validation_result = validator.validate(
            task_type=task_type,
            task_output={"error": error_msg, "execution_failed": True},
            context=context
        )

        # If validator doesn't find root cause, provide basic feedback
        if not validation_result.get("root_cause_task_id"):
            validation_result["errors"] = validation_result.get("errors", []) + [f"Tool execution failed: {error_msg}"]
            validation_result["suggestions"] = validation_result.get("suggestions", []) + [
                f"Task {task_id} ({task_type}) failed when executing {tool_name}",
                f"Error: {error_msg}",
                "Check parameters or investigate upstream tasks"
            ]
            validation_result["reasoning"] = validation_result.get("reasoning", "") + " (Tool execution failed)"

        print(f"[VALIDATION] Execution failure analysis: is_valid={validation_result.get('is_valid')}")
        if root_cause := validation_result.get("root_cause_task_id"):
            print(f"[VALIDATION] Root cause identified: {root_cause}")

        return {
            "validation_feedback": validation_result
        }

    task_type = current_task.get('task_type')
    task_id = current_task.get('task_id')
    print(f"[INFO] Validating {task_id} ({task_type})...")

    # Build context with previous results
    context = {"previous_results": state.get('task_results', [])}

    # NEW: For table_split validation, add original definition data
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

    # NEW: For condition_transform validation, add original condition data
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

    # NEW: For extract_condition validation, add condition_sections
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

        # Also get definition sections for annotation reference checking
        definition_core_indices = []
        definition_annotation_indices = []
        for r in state.get("task_results", []):
            if r.get("success") and r.get("tool_used") == "section_classifier":
                data = r.get("data", {})
                definition_core_indices = data.get("definition_core", [])
                definition_annotation_indices = data.get("definition_annotation", [])
                break

        if all_sections and (definition_core_indices or definition_annotation_indices):
            all_definition_indices = definition_core_indices + definition_annotation_indices
            definition_sections = [s for s in all_sections if s.get("index") in all_definition_indices]
            context["definition_sections"] = definition_sections

        print(f"[CONTEXT] Condition extract validation context prepared:")
        print(f"  - all_sections count: {len(all_sections)}")
        print(f"  - condition_indices: {condition_indices}")
        print(f"  - condition_sections count: {len(context.get('condition_sections', []))}")
        print(f"  - definition_sections count: {len(context.get('definition_sections', []))}")

    # CRITICAL: For grouping validation, add definition/condition headers and data
    if task_type == "grouping":
        task_results = state.get("task_results", [])

        def last_success(tool_name: str):
            for r in reversed(task_results):
                if r.get("success") and r.get("tool_used") == tool_name and isinstance(r.get("data"), dict):
                    return r["data"]
            return None

        def_data = last_success("llm_table_split") or last_success("rule_table_split") or last_success("definition_extract_v2")
        cond_data = last_success("condition_transform") or last_success("condition_extract")

        if def_data:
            context["definition_header"] = def_data.get("header", [])
            context["definition_data"] = def_data.get("data", [])
        if cond_data:
            context["condition_header"] = cond_data.get("header", [])
            context["condition_data"] = cond_data.get("data", [])

        print(f"[CONTEXT] Grouping validation context prepared:")
        print(f"  - definition_header: {context.get('definition_header', 'NOT FOUND')}")
        print(f"  - condition_header: {context.get('condition_header', 'NOT FOUND')}")

    validation_result = validator.validate(task_type=task_type, task_output=current_task_output, context=context)
    _append_event(
        state,
        {
            "event": "task_validated",
            "task_id": task_id,
            "task_type": task_type,
            "is_valid": bool(validation_result.get("is_valid")),
            "confidence": validation_result.get("confidence"),
            "errors": _safe_preview(validation_result.get("errors", []), max_str=400),
            "suggestions": _safe_preview(validation_result.get("suggestions", []), max_str=400),
            "root_cause_task_id": validation_result.get("root_cause_task_id"),
            "root_cause_reasoning_preview": _safe_preview(validation_result.get("root_cause_reasoning", ""), max_str=400),
        },
    )

    if validation_result.get("is_valid"):
        print(f"[OK] Validation passed (confidence: {validation_result.get('confidence', 0):.2f})")
    else:
        print(f"[FAIL] Validation failed: {validation_result.get('errors', [])}")
        if root_cause := validation_result.get("root_cause_task_id"):
            print(f"  - Root cause identified: {root_cause}")

    updates: Dict[str, Any] = {
        "validation_feedback": validation_result,
        "last_validation_feedback": validation_result,
    }

    # Track retries and backtrack target
    retry_counts = dict(state.get("retry_counts", {}))
    if not validation_result.get("is_valid", False):
        root_cause = validation_result.get("root_cause_task_id")

        # NEW: Only increment retry if root cause is current task (not a different task)
        if root_cause and root_cause != task_id:
            # Root cause is a different task - don't increment retry for current task
            # Backtracking will handle it
            print(f"[P7 VALIDATE] Root cause is {root_cause} (not {task_id}), skipping retry increment")
        else:
            # Current task's own problem - increment retry
            retry_counts[task_id] = retry_counts.get(task_id, 0) + 1
            print(f"[P7 VALIDATE] {task_id} retry count: {retry_counts[task_id]}/{MAX_TASK_RETRIES}")

        updates["retry_counts"] = retry_counts

        # Set backtrack target if root cause is a different completed task
        if root_cause:
            completed_ids = [r.get("task_id") for r in state.get("task_results", [])]
            if root_cause in completed_ids:
                updates["backtrack_to_task_id"] = root_cause
                # CRITICAL: Save reasoning for why we're backtracking
                root_cause_reasoning = validation_result.get("root_cause_reasoning", "")
                updates["backtrack_reasoning"] = root_cause_reasoning
                print(f"[P7 VALIDATE] Backtrack reasoning saved: {root_cause_reasoning[:]}...")
                _append_event(
                    state,
                    {
                        "event": "backtrack_marked",
                        "from_task_id": task_id,
                        "to_task_id": root_cause,
                        "reasoning_preview": _safe_preview(root_cause_reasoning, max_str=500),
                    },
                )

    # FIXED: Update task_result with validation info for debugging and safety
    task_results = state.get("task_results", [])
    for result in task_results:
        if result.get("task_id") == task_id:
            result["validation_result"] = validation_result
            result["validation_failed"] = not validation_result.get("is_valid", False)
            break

    updates["task_results"] = task_results
    updates["event_history"] = state.get("event_history", [])
    return updates

def p7_router(state: AgentState) -> str:
    """
    PROTOTYPE 7 v2: Router after validation.

    Routes based on error type:
    - Fatal error (state.error) → END
    - task_definition_failed (recoverable) → PLAN (re-plan)
    - Success → PLAN (next task)
    """
    # Check for fatal errors (not recoverable)
    # NOTE: Tool execution errors are recoverable (can retry), not fatal
    error = state.get("error")
    error_type = state.get("error_type")

    # Only treat as fatal if it's NOT a recoverable error type
    if error and error_type not in ["execution_error", "task_definition_error"]:
        # Fatal error: max retries, recursion limit, etc.
        print(f"[P7 ROUTER] Fatal error detected: {error[:100]} -> END")
        return "end"

    if state.get("is_complete"):
        print("[P7 ROUTER] Planner signaled completion -> END")
        return "end"

    # NEW: Check for recoverable errors (task_definition_failed)
    if state.get("task_definition_failed"):
        task_def_error = state.get("task_definition_error", "Unknown")
        failed_task_id = state.get("failed_task_id", "unknown")
        print(f"[P7 ROUTER] Task definition error for {failed_task_id}: {task_def_error[:100]}")
        print(f"[P7 ROUTER] -> PLAN (re-plan to fix definition)")
        # NOTE: Flag will be cleared in state update, not here
        return "plan"

    # FIXED: Check if validation failed without backtracking and max retries reached
    validation_feedback = state.get("last_validation_feedback", {})
    if not validation_feedback.get("is_valid", True):
        backtrack_to = state.get("backtrack_to_task_id")
        if not backtrack_to:
            # Validation failed but no backtracking set - find which task failed
            # Look through task_results in reverse to find the most recent validation failure
            task_results = state.get("task_results", [])
            failed_task_id = None

            for result in reversed(task_results):
                if result and result.get("validation_failed"):
                    failed_task_id = result.get("task_id")
                    break

            if failed_task_id:
                retry_counts = state.get("retry_counts", {})
                retries = retry_counts.get(failed_task_id, 0)

                if retries >= MAX_TASK_RETRIES:
                    # Max retries reached without finding root cause - cannot proceed
                    errors = validation_feedback.get("errors", [])
                    error_summary = "; ".join(str(e) for e in errors[:2])  # First 2 errors
                    print(f"[P7 ROUTER] CRITICAL: {failed_task_id} validation failed after {retries} retries")
                    print(f"[P7 ROUTER] Errors: {error_summary[:200]}")
                    print(f"[P7 ROUTER] Cannot proceed without valid output -> END")
                    return "end"

    # Always go back to planner for next task
    # NOTE: Total task limit is checked in plan_node, not here
    print("[P7 ROUTER] -> PLAN (generate next task)")
    return "plan"

def build_p7_graph():
    """
    PROTOTYPE 7 v2: Build the 1-task-at-a-time execution graph.

    Flow:
    1. plan -> generate next task (or signal END)
    2. execute_task -> execute current task
    3. validate_task -> validate output
    4. router -> check completion or go back to plan

    Cycle: plan -> execute -> validate -> (plan or end)
    """
    workflow = StateGraph(AgentState)

    # 노드 추가
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("validate_task", validate_task_node)

    # 엔트리 포인트 설정(그래프 처음 시작할때 진입노드)
    workflow.set_entry_point("plan")

    # Add edges
    # plan node 실행 후 state를 보고 current_task가 있으면 execute_task로 이동, 없거나 error 있으면 end
    def plan_router(state):
        # Check for fatal errors first
        if state.get("error"):
            return "end"
        # Then check for current_task
        return "execute_task" if state.get("current_task") else "end"

    workflow.add_conditional_edges(
        "plan",
        plan_router,
        {"execute_task": "execute_task", "end": END}
    )
    # execute -> validate
    workflow.add_edge("execute_task", "validate_task")
    # validate -> p7_router를 기반으로 plan/end 결정
    workflow.add_conditional_edges(
        "validate_task",
        p7_router,
        {"plan": "plan", "end": END}
    )

    return workflow.compile()

class Prototype7Agent:
    """
    PROTOTYPE 7: Dynamic Task Execution Agent
    """
    def __init__(self):
        # Create fresh planner and validator instances to avoid stat accumulation
        global planner, validator
        planner = LLMPlanner()
        validator = LLMValidator()
        self.graph = build_p7_graph()

    def run(self, doc: Any) -> Dict[str, Any]:
        print("\n" + "="*80 + "\nPROTOTYPE 7: Dynamic Task Execution Agent\n" + "="*80)
        try:
            # 문서를 section 단위로 파싱
            accessor = DocumentAccessor(doc)
            section_objects = accessor.get_all_sections()
            # section 객체를 dict 형태로 변환해서 langgraph state에 넣을 수 있도록 준비
            sections = [
                {
                    "index": s.index,
                    "title": s.title,
                    "content": s.content_items,
                    "raw": s.metadata.get("original_element") or s.metadata
                }
                for s in section_objects
            ]
        except Exception as e:
            print(f"[ERROR] DocumentAccessor failed: {e}")
            sections = []

        # PROTOTYPE 7 v2: 초기 상태(state) 구성
        inputs = {
            "original_doc": doc, # 원본 문서
            "sections": sections, # 섹션 단위로 분해된 문서
            "task_results": [], # 지금까지 task 결과
            "task_history": [], # 디버깅용
            "event_history": [], # Persistent event log (not truncated on backtracking)
            "current_task": None, # 현재 실행중인 task
            "current_task_output": None, # 현재 task의 결과
            "is_complete": False, # 완료 플래그
            "backtrack_to_task_id": None, # 어느 task로 되돌아갈지
            "backtrack_reasoning": "",  # CRITICAL: Store why we're backtracking
            "retry_counts": {}, 
            "last_validation_feedback": None,
            "error_type": None,  # NEW: Error classification
            "error_suggestion": None,  # NEW: Error fix suggestion
            "failed_task_id": None,  # NEW: Which task failed

            # NEW: Dependency-aware backtracking and recoverable errors
            "all_task_definitions": {},  # Store all task definitions for dependency tracking
            "task_definition_failed": False,  # Recoverable task definition error flag
            "task_definition_error": None,  # Error message for task definition
        }
        # 그래프 실행 중 마지막 상태를 누적할 dictionary
        final_state = {}

        # 그래프 실행
        try:
            # 랭그래프의 스트리밍 실행 함수(graph.stream)
            for step in self.graph.stream(inputs, config={"recursion_limit": 100}):
                if node_state := next(iter(step.values()), None):
                    final_state.update(node_state)

            if error := final_state.get("error"):
                task_results = final_state.get("task_results", [])
                task_history = final_state.get("task_history", [])
                event_history = final_state.get("event_history", [])

                # Collect planner and validator LLM usage stats even on error
                planner_stats = planner.get_llm_usage_stats()
                validator_stats = validator.get_llm_usage_stats()

                return {
                    "success": False,
                    "error": error,
                    "task_log": self._build_task_log(final_state),
                    "final_data": None,
                    "task_results": task_results,
                    "task_history": task_history,
                    "event_history": event_history,
                    "planner_llm_stats": planner_stats,
                    "validator_llm_stats": validator_stats,
                }

            # 성공 case 처리
            task_results = final_state.get("task_results", [])
            task_history = final_state.get("task_history", [])
            event_history = final_state.get("event_history", [])
            # final_data는 마지막 task의 data를 최종 산출물로 가져옴
            final_data = task_results[-1].get("data") if task_results else None
            task_log = self._build_task_log(final_state)
            print("\n" + "="*80 + f"\nPROTOTYPE 7 COMPLETE: {len(task_results)} tasks executed\n" + "="*80)

            # Collect planner and validator LLM usage stats
            planner_stats = planner.get_llm_usage_stats()
            validator_stats = validator.get_llm_usage_stats()

            return {
                "success": True,
                "final_data": final_data,
                "task_log": task_log,
                "task_results": task_results,
                "task_history": task_history,
                "event_history": event_history,
                "error": None,
                "planner_llm_stats": planner_stats,
                "validator_llm_stats": validator_stats,
            }
        except Exception as e:
            # Collect available data even on exception
            task_results = final_state.get("task_results", [])
            task_history = final_state.get("task_history", [])
            event_history = final_state.get("event_history", [])

            # Try to get LLM stats if possible
            try:
                planner_stats = planner.get_llm_usage_stats()
                validator_stats = validator.get_llm_usage_stats()
            except:
                planner_stats = {"total_calls": 0, "total_time_ms": 0}
                validator_stats = {"total_calls": 0, "total_time_ms": 0}

            return {
                "success": False,
                "error": f"Execution exception: {str(e)}",
                "task_log": self._build_task_log(final_state) if final_state else [],
                "final_data": None,
                "task_results": task_results,
                "task_history": task_history,
                "event_history": event_history,
                "planner_llm_stats": planner_stats,
                "validator_llm_stats": validator_stats,
            }

    def _build_task_log(self, state: Dict) -> list:
        return [
            {"step": idx + 1, "task_id": r.get("task_id"), "success": r.get("success"),
             "tool_used": r.get("tool_used"), "execution_time": round(r.get("execution_time", 0), 2),
             "error": r.get("error")}
            for idx, r in enumerate(state.get("task_results", []))
        ]
