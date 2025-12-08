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
            normalized_header.append("보종�?")
            for i in range(1, len(header)):
                normalized_header.append(f"?��?��{i}")
        
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
    
    "grouping_logic_extractor": GroupingLogicExtractorTool(),
    "combination_generator": CombinationGeneratorTool(),
}

# --- [NEW] Pydantic Models for Plan Validation ---

class Task(BaseModel):
    task_id: str
    task_type: str
    tool_name: str
    fallback_tool: Optional[str] = None
    parameters: Dict[str, Any]
    dependencies: List[str]
    output_key: str

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

# ============================================================================
# PROTOTYPE 7: TEMPLATE RESOLUTION
# ============================================================================

def resolve_templates(params: Dict[str, Any], task_results: list, document: Any, sections: Any = None) -> Dict[str, Any]:
    """
    Resolve template placeholders in task parameters.
    """
    import re
    import json

    def resolve_value(value: Any) -> Any:
        if isinstance(value, str):
            template_pattern = r'{{([^}}]+)}}'
            matches = re.findall(template_pattern, value)

            if not matches:
                if value == "$sections":
                    return sections
                return value

            result = value
            for match in matches:
                match = match.strip()

                if match == "document":
                    doc_str = json.dumps(document, ensure_ascii=False) if isinstance(document, (dict, list)) else str(document)
                    result = result.replace(f"{{{{{match}}}}}", doc_str)
                elif match.startswith("task"):
                    try:
                        parts = match.split(".")
                        task_id, field_path = parts[0], parts[1:]
                        if field_path and field_path[0] == "data":
                            field_path = field_path[1:]

                        # 필터 제거
                        clean = []
                        for f in field_path:
                            clean_field = f.split("|", 1)[0].strip()
                            if clean_field:
                                clean.append(clean_field)
                        field_path = clean

                        task_result = next((tr for tr in task_results if tr.get("task_id") == task_id), None)

                        if not task_result:
                            print(f"[WARN] Template resolution: task '{task_id}' not found in results")
                            continue

                        current = task_result.get("data")
                        for field in field_path:
                            if isinstance(current, dict):
                                current = current.get(field)
                            elif isinstance(current, list) and field.isdigit():
                                current = current[int(field)]
                            else:
                                print(f"[WARN] Template resolution: field '{field}' not found in path {'.'.join(field_path)}")
                                current = None
                                break
                        
                        if current is not None:
                            if result == f"{{{{{match}}}}}":
                                return current
                            else:
                                result = result.replace(f"{{{{{match}}}}}", json.dumps(current, ensure_ascii=False) if not isinstance(current, str) else current)
                    except Exception as e:
                        print(f"[WARN] Template resolution error for '{match}': {e}")
                        continue
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
    doc = state.get('original_doc')
    task_results = state.get('task_results', [])

    num_completed = len(task_results)
    print(f"\n[P7 NODE] plan_node: Generating next task (completed: {num_completed})...")

    # Call LLM to get next task or end signal
    result = planner.generate_next_task(doc=doc, task_results=task_results)

    if result.get("error"):
        print(f"[FAIL] Task generation failed: {result['error']}")
        return {"error": f"Task generation failed: {result['error']}"}

    action = result.get("action")

    if action == "end":
        # All tasks complete
        print(f"[OK] Planner signals completion")
        print(f"  - Reasoning: {result.get('reasoning', 'N/A')[:100]}...")
        return {
            "is_complete": True,
            "current_task": None
        }

    elif action == "next_task":
        # New task to execute
        task = result.get("task")
        task_id = task.get("task_id")
        print(f"[OK] Next task generated: {task_id}")
        print(f"  - Type: {task.get('task_type')}")
        print(f"  - Tool: {task.get('tool_name')}")
        print(f"  - Reasoning: {result.get('reasoning', 'N/A')[:100]}...")

        # Validate tool exists
        tool_name = task.get("tool_name")
        if tool_name not in tools:
            return {"error": f"Invalid tool_name: {tool_name}. Available: {list(tools.keys())}"}

        # Validate fallback tool if specified
        fallback = task.get("fallback_tool")
        if fallback and fallback not in tools:
            return {"error": f"Invalid fallback_tool: {fallback}"}

        return {
            "current_task": task,
            "is_complete": False
        }

    else:
        return {"error": f"Unknown action from planner: {action}"}

def execute_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7 v2: Execute the current task.
    """
    print("\n[P7 NODE] execute_task_node: Executing current task...")
    current_task = state.get('current_task')
    task_results = state.get('task_results', [])
    document = state.get('original_doc')
    sections = state.get('sections')

    if not current_task:
        return {"error": "No current_task to execute"}

    task_id = current_task.get('task_id')
    print(f"[INFO] Executing {task_id}: {current_task.get('description', 'N/A')}")

    # Check dependencies
    dependencies = current_task.get('dependencies', [])
    # Handle case where LLM returns "none" as string or null
    if dependencies is None or dependencies == "none" or dependencies == ["none"]:
        dependencies = []

    for dep_id in dependencies:
        if not any(r.get('task_id') == dep_id and r.get('success') for r in task_results):
            return {"error": f"Dependency {dep_id} not completed successfully."}

    # Resolve template parameters
    try:
        resolved_params = resolve_templates(current_task.get('parameters', {}), task_results, document, sections)
        print(f"[INFO] Parameters resolved: {len(str(resolved_params))} chars")
    except Exception as e:
        return {"error": f"Template resolution failed: {str(e)}"}

    # Execute primary tool
    tool_name = current_task.get('tool_name')
    tool = tools[tool_name]
    start_time = time.time()
    print(f"[INFO] Using primary tool: {tool_name}")
    result = tool.execute(doc=document, params=resolved_params)

    # Try fallback if primary fails
    fallback_tool_name = current_task.get('fallback_tool')
    if not result.success and fallback_tool_name:
        print(f"[INFO] Primary tool failed. Trying fallback: {fallback_tool_name}")
        tool = tools[fallback_tool_name]
        result = tool.execute(doc=document, params=resolved_params)
        tool_name = fallback_tool_name

    # Record result
    execution_time = time.time() - start_time
    task_result = {
        "task_id": task_id,
        "success": result.success,
        "data": result.data,
        "tool_used": tool_name,
        "execution_time": execution_time,
        "error": result.error if not result.success else None
    }
    task_results.append(task_result)

    if result.success:
        print(f"[OK] Task {task_id} completed successfully ({execution_time:.2f}s)")
        print(f"[DEBUG] Output of {tool_name} (Task {task_id}): {result.data}")
    else:
        print(f"[FAIL] Task {task_id} failed: {result.error}")
        print(f"[DEBUG] Failed output of {tool_name} (Task {task_id}): {result.error}")
        print(f"[DEBUG] Params for {tool_name} (Task {task_id}): {resolved_params}")
    return {
        "task_results": task_results,
        "current_task_output": result.data
    }

def validate_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Validate the current task output.
    """
    print("\n[P7 NODE] validate_task_node: Validating current task...")
    current_task = state.get('current_task')
    current_task_output = state.get('current_task_output')

    if not current_task:
        return {"error": "No current_task to validate"}

    if current_task_output is None:
        print("[INFO] Task execution failed, skipping validation")
        return {"validation_feedback": {"is_valid": False, "errors": [state.get('error', 'Unknown execution error')], "reasoning": "Task execution failed"}}

    task_type = current_task.get('task_type')
    task_id = current_task.get('task_id')
    print(f"[INFO] Validating {task_id} ({task_type})...")

    context = {"previous_results": state.get('task_results', [])}
    validation_result = validator.validate(task_type=task_type, task_output=current_task_output, context=context)

    if validation_result.get("is_valid"):
        print(f"[OK] Validation passed (confidence: {validation_result.get('confidence', 0):.2f})")
    else:
        print(f"[FAIL] Validation failed: {validation_result.get('errors', [])}")
        if root_cause := validation_result.get("root_cause_task_id"):
            print(f"  - Root cause identified: {root_cause}")

    return {"validation_feedback": validation_result}

def p7_router(state: AgentState) -> str:
    """
    PROTOTYPE 7 v2: Router after validation.

    In the new 1-task-at-a-time design:
    - Always return to planner (whether validation passed or failed)
    - Planner will see validation results and decide next step
    - Check if planner already signaled completion
    """
    if state.get("error"):
        print("[P7 ROUTER] Error detected -> END")
        return "end"

    if state.get("is_complete"):
        print("[P7 ROUTER] Planner signaled completion -> END")
        return "end"

    # Always go back to planner for next task
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

    # Add nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("validate_task", validate_task_node)

    # Set entry point
    workflow.set_entry_point("plan")

    # Add edges
    workflow.add_conditional_edges(
        "plan",
        lambda state: "execute_task" if state.get("current_task") else "end",
        {"execute_task": "execute_task", "end": END}
    )
    workflow.add_edge("execute_task", "validate_task")
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
        self.graph = build_p7_graph()

    def run(self, doc: Any) -> Dict[str, Any]:
        print("\n" + "="*80 + "\nPROTOTYPE 7: Dynamic Task Execution Agent\n" + "="*80)
        try:
            accessor = DocumentAccessor(doc)
            section_objects = accessor.get_all_sections()
            # Convert Section objects to dict
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

        # PROTOTYPE 7 v2: Initialize state for 1-task-at-a-time execution
        inputs = {
            "original_doc": doc,
            "sections": sections,
            "task_results": [],
            "current_task": None,
            "current_task_output": None,
            "is_complete": False
        }
        final_state = {}

        try:
            for step in self.graph.stream(inputs, config={"recursion_limit": 100}):
                if node_state := next(iter(step.values()), None):
                    final_state.update(node_state)

            if error := final_state.get("error"):
                return {
                    "success": False,
                    "error": error,
                    "task_log": self._build_task_log(final_state),
                    "final_data": None,
                    "task_results": final_state.get("task_results", []),
                }

            task_results = final_state.get("task_results", [])
            final_data = task_results[-1].get("data") if task_results else None
            task_log = self._build_task_log(final_state)
            print("\n" + "="*80 + f"\nPROTOTYPE 7 COMPLETE: {len(task_results)} tasks executed\n" + "="*80)
            return {
                "success": True,
                "final_data": final_data,
                "task_log": task_log,
                "task_results": task_results,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution exception: {str(e)}",
                "task_log": [],
                "final_data": None,
                "task_results": final_state.get("task_results", []),
            }

    def _build_task_log(self, state: Dict) -> list:
        return [
            {"step": idx + 1, "task_id": r.get("task_id"), "success": r.get("success"),
             "tool_used": r.get("tool_used"), "execution_time": round(r.get("execution_time", 0), 2),
             "error": r.get("error")}
            for idx, r in enumerate(state.get("task_results", []))
        ]


# ============================================================================
# LEGACY PROTOTYPE 6 (Stub for backward compatibility)
# ============================================================================

class Prototype6Agent:
    """
    Legacy Prototype 6 Agent - Not fully implemented in Prototype 7 directory.
    Use prototype_6 directory for full P6 functionality.
    """
    def __init__(self):
        print("[WARN] Prototype6Agent is a stub in prototype_7. Use --prototype 7 instead.")

    def run(self, doc: Any) -> Dict[str, Any]:
        """
        Stub implementation - directs users to use Prototype 7 or switch to prototype_6 directory.
        """
        return {
            "success": False,
            "error": "Prototype 6 is not fully implemented in prototype_7 directory. Use --prototype 7 or run from prototype_6 directory.",
            "final_data": None,
            "task_log": []
        }

# ============================================================================
# LEGACY PROTOTYPE 6 (Stub for backward compatibility)
# ============================================================================

class Prototype6Agent:
    """
    Legacy Prototype 6 Agent - Not fully implemented in Prototype 7 directory.
    Use prototype_6 directory for full P6 functionality.
    """
    def __init__(self):
        print("[WARN] Prototype6Agent is a stub in prototype_7. Use --prototype 7 instead.")

    def run(self, doc: Any) -> Dict[str, Any]:
        """
        Stub implementation - directs users to use Prototype 7 or switch to prototype_6 directory.
        """
        return {
            "success": False,
            "error": "Prototype 6 is not fully implemented in prototype_7 directory. Use --prototype 7 or run from prototype_6 directory.",
            "final_data": None,
            "task_log": []
        }
