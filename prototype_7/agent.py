"""
Prototype 4.1: LangGraph-based Agent

This agent uses LangGraph to create a robust, stateful, and cyclic workflow,
allowing for dynamic backtracking and replanning.
"""
from typing import Dict, Any

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
    IntelligentConditionExtractTool, # MODIFIED: Replaced ConditionExtractTool
    DefinitionConditionMergeTool,
    GroupingLogicExtractorTool,  # NEW: Grouping logic extractor
    CombinationGeneratorTool,    # NEW: Combination generator
)

# Initialize tools and core components once
planner = LLMPlanner()
validator = LLMValidator()
tools = {
    "section_classifier": SectionClassifierTool(),
    "definition_extract_v2": DefinitionExtractToolV2(),
    "rule_cartesian": RuleCartesianTool(),
    "llm_cartesian": LLMCartesianTool(),
    "condition_extract": IntelligentConditionExtractTool(), # MODIFIED: Replaced ConditionExtractTool
    "definition_condition_merge": DefinitionConditionMergeTool(),  # Legacy tool
    "grouping_logic_extractor": GroupingLogicExtractorTool(),      # NEW
    "combination_generator": CombinationGeneratorTool(),            # NEW
}
MAX_REPLAN_COUNT = 5

# ============================================================================
# PROTOTYPE 7: TEMPLATE RESOLUTION
# ============================================================================

def resolve_templates(params: Dict[str, Any], task_results: list, document: Any) -> Dict[str, Any]:
    """
    Resolve template placeholders in task parameters (Prototype 7).

    Supports:
    - {{document}} → full document string
    - {{taskN.output_key.field}} → nested field access from task results

    Example:
        Input: {"header": "{{task0.definition_core.header}}"}
        Output: {"header": ["보종명", "유형1", "유형2"]}

    Args:
        params: Parameter dict with potential template strings
        task_results: List of TaskResult dicts from previous tasks
        document: Original document

    Returns:
        Resolved parameter dict
    """
    import re
    import json

    def resolve_value(value: Any) -> Any:
        """Recursively resolve a single value"""
        if isinstance(value, str):
            # Match {{template}} patterns
            template_pattern = r'\{\{([^}]+)\}\}'
            matches = re.findall(template_pattern, value)

            if not matches:
                return value

            # Replace each template
            result = value
            for match in matches:
                match = match.strip()

                # Handle {{document}}
                if match == "document":
                    # Convert document to string if needed
                    if isinstance(document, dict) or isinstance(document, list):
                        doc_str = json.dumps(document, ensure_ascii=False)
                    else:
                        doc_str = str(document)
                    result = result.replace(f"{{{{{match}}}}}", doc_str)

                # Handle {{taskN.field.subfield...}}
                elif match.startswith("task"):
                    try:
                        parts = match.split(".")
                        task_id = parts[0]  # e.g., "task0"
                        field_path = parts[1:]  # e.g., ["definition_core", "header"]

                        # Find the task result
                        task_result = None
                        for tr in task_results:
                            if tr.get("task_id") == task_id:
                                task_result = tr
                                break

                        if not task_result:
                            print(f"[WARN] Template resolution: task '{task_id}' not found in results")
                            continue

                        # Navigate through nested fields
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
                            # If the entire value is a template, return the actual type
                            if result == f"{{{{{match}}}}}":
                                return current
                            # Otherwise, convert to string and replace
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
    PROTOTYPE 7: Generate initial execution plan using LLMPlanner.

    Calls LLMPlanner.create_plan() to generate a dynamic 3-7 task plan
    based on document complexity.

    Args:
        state: Current agent state

    Returns:
        Updated state with plan and initialization
    """
    print("\n[P7 NODE] plan_node: Creating dynamic execution plan...")

    doc = state.get('original_doc')
    instruction = state.get('current_instruction', '')

    # Call LLMPlanner to generate dynamic plan
    plan = planner.create_plan(doc=doc, goal=instruction)

    if plan.get("error"):
        print(f"[FAIL] Planning failed: {plan['error']}")
        return {"error": f"Planning failed: {plan['error']}"}

    # Validate plan has required Prototype 7 structure
    if "total_tasks" not in plan or "tasks" not in plan:
        print(f"[FAIL] Plan missing required fields (total_tasks, tasks)")
        return {"error": "Invalid plan structure: missing total_tasks or tasks"}

    num_tasks = plan.get("total_tasks", 0)
    print(f"[OK] Plan created with {num_tasks} tasks")
    print(f"  - Reasoning: {plan.get('reasoning', 'N/A')[:100]}...")

    # Initialize execution state
    return {
        "plan": plan,
        "current_task_index": 0,
        "task_results": [],
        "replan_count": 0,
        "max_replans": 3,  # Default max replans
        "backtrack_to_task_id": None,
    }


def execute_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Execute the current task from the plan.

    Logic:
    1. Get current task from plan
    2. Check dependencies completed successfully
    3. Resolve template parameters
    4. Execute primary tool (with fallback if fails)
    5. Record TaskResult
    6. Populate legacy fields for compatibility

    Args:
        state: Current agent state

    Returns:
        Updated state with task result
    """
    import time

    print("\n[P7 NODE] execute_task_node: Executing current task...")

    plan = state.get('plan')
    current_task_index = state.get('current_task_index', 0)
    task_results = state.get('task_results', [])
    document = state.get('original_doc')

    # Get current task
    tasks = plan.get('tasks', [])
    if current_task_index >= len(tasks):
        return {"error": f"Task index {current_task_index} out of range (total: {len(tasks)})"}

    current_task = tasks[current_task_index]
    task_id = current_task.get('task_id')

    print(f"[INFO] Executing {task_id}: {current_task.get('description', 'N/A')}")

    # Check dependencies
    dependencies = current_task.get('dependencies', [])
    for dep_id in dependencies:
        dep_result = next((r for r in task_results if r.get('task_id') == dep_id), None)
        if not dep_result or not dep_result.get('success'):
            return {
                "error": f"Dependency {dep_id} not completed successfully",
                "current_task": current_task
            }

    # Resolve template parameters
    raw_params = current_task.get('parameters', {})
    try:
        resolved_params = resolve_templates(raw_params, task_results, document)
        print(f"[INFO] Parameters resolved: {len(str(resolved_params))} chars")
    except Exception as e:
        return {
            "error": f"Template resolution failed: {str(e)}",
            "current_task": current_task
        }

    # Get tool
    tool_name = current_task.get('tool_name')
    fallback_tool_name = current_task.get('fallback_tool')

    if tool_name not in tools:
        return {
            "error": f"Tool '{tool_name}' not found in tools registry",
            "current_task": current_task
        }

    # Execute primary tool
    tool = tools[tool_name]
    start_time = time.time()

    print(f"[INFO] Using primary tool: {tool_name}")
    result = tool.execute(doc=document, params=resolved_params)

    # Try fallback if primary fails
    if not result.success and fallback_tool_name and fallback_tool_name in tools:
        print(f"[INFO] Primary tool failed. Trying fallback: {fallback_tool_name}")
        tool = tools[fallback_tool_name]
        result = tool.execute(doc=document, params=resolved_params)
        tool_name = fallback_tool_name  # Update tool name used

    execution_time = time.time() - start_time

    # Record TaskResult
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
    else:
        print(f"[FAIL] Task {task_id} failed: {result.error}")

    # Populate legacy fields for backward compatibility
    legacy_fields = {}
    task_type = current_task.get('task_type', '')
    output_key = current_task.get('output_key', '')

    # Map output_key to legacy fields
    if result.success and result.data:
        if output_key == 'classification_result' or task_type == 'classify_sections':
            legacy_fields['classification_result'] = result.data
        elif output_key == 'extraction_result' or task_type == 'extract_definitions':
            legacy_fields['extraction_result'] = result.data
        elif output_key == 'condition_result' or task_type == 'extract_conditions':
            legacy_fields['condition_result'] = result.data
        elif output_key == 'normalized_definitions' or task_type == 'normalize_definitions':
            legacy_fields['normalized_definitions'] = result.data
        elif output_key == 'normalized_conditions' or task_type == 'normalize_conditions':
            legacy_fields['normalized_conditions'] = result.data
        elif output_key == 'grouping_logic' or task_type == 'extract_grouping_logic':
            legacy_fields['grouping_logic'] = result.data
        elif output_key == 'final_result' or task_type == 'generate_combinations':
            legacy_fields['final_result'] = result.data

    return {
        "task_results": task_results,
        "current_task": current_task,
        "current_task_output": result.data,
        **legacy_fields
    }


def validate_task_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Validate the current task output.

    Logic:
    1. Build context with previous_results for root cause analysis
    2. Call LLMValidator.validate()
    3. Validator includes root_cause_task_id if failure
    4. Store in validation_feedback

    Args:
        state: Current agent state

    Returns:
        Updated state with validation feedback
    """
    print("\n[P7 NODE] validate_task_node: Validating current task...")

    current_task = state.get('current_task')
    current_task_output = state.get('current_task_output')
    task_results = state.get('task_results', [])

    if not current_task:
        return {"error": "No current_task to validate"}

    if current_task_output is None:
        # Task failed during execution, skip validation
        print("[INFO] Task execution failed, skipping validation")
        return {
            "validation_feedback": {
                "is_valid": False,
                "errors": [state.get('error', 'Unknown execution error')],
                "confidence": 0.0,
                "suggestions": [],
                "reasoning": "Task execution failed"
            }
        }

    task_type = current_task.get('task_type')
    task_id = current_task.get('task_id')

    print(f"[INFO] Validating {task_id} ({task_type})...")

    # Build context for validator
    context = {
        "previous_results": task_results  # Include all previous task results for root cause analysis
    }

    # Run validation with root cause analysis support
    validation_result = validator.validate(
        task_type=task_type,
        task_output=current_task_output,
        context=context
    )

    if validation_result.get("is_valid"):
        print(f"[OK] Validation passed (confidence: {validation_result.get('confidence', 0):.2f})")
    else:
        print(f"[FAIL] Validation failed: {validation_result.get('errors', [])}")
        root_cause = validation_result.get("root_cause_task_id")
        if root_cause:
            print(f"  - Root cause identified: {root_cause}")

    return {"validation_feedback": validation_result}


def replan_node(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Replan after task failure.

    Logic:
    1. Check replan_count < max_replans
    2. Call LLMPlanner.suggest_replan()
    3. Handle 3 replan types:
       - adjust_parameters: Update current task params
       - insert_task: Add new task to plan
       - full_replan: Generate completely new plan
    4. Increment replan_count

    Args:
        state: Current agent state

    Returns:
        Updated state with new plan/parameters
    """
    print("\n[P7 NODE] replan_node: Analyzing failure and replanning...")

    replan_count = state.get('replan_count', 0)
    max_replans = state.get('max_replans', 3)

    if replan_count >= max_replans:
        print(f"[FAIL] Maximum replan limit reached ({max_replans})")
        return {"error": f"Maximum replan limit ({max_replans}) reached"}

    current_plan = state.get('plan')
    current_task = state.get('current_task')
    validation_feedback = state.get('validation_feedback', {})
    task_results = state.get('task_results', [])

    if not current_task:
        return {"error": "No current_task to replan"}

    # Call LLMPlanner to suggest replan action
    replan_action = planner.suggest_replan(
        current_plan=current_plan,
        failed_task=current_task,
        validation_feedback=validation_feedback,
        task_results=task_results
    )

    if replan_action.get("error"):
        return {"error": f"Replan suggestion failed: {replan_action['error']}"}

    replan_type = replan_action.get("type")
    reasoning = replan_action.get("reasoning", "N/A")

    print(f"[INFO] Replan strategy: {replan_type}")
    print(f"  - Reasoning: {reasoning[:100]}...")

    # Handle different replan types
    updated_state = {
        "replan_count": replan_count + 1
    }

    if replan_type == "adjust_parameters":
        # Update current task's parameters
        new_params = replan_action.get("new_parameters", {})
        current_task_index = state.get('current_task_index', 0)
        tasks = current_plan.get('tasks', [])

        if current_task_index < len(tasks):
            tasks[current_task_index]['parameters'] = new_params
            print(f"[OK] Adjusted parameters for {current_task.get('task_id')}")
            updated_state["plan"] = current_plan
        else:
            return {"error": "Task index out of range for parameter adjustment"}

    elif replan_type == "insert_task":
        # Insert new task before current task
        new_task = replan_action.get("new_task", {})
        current_task_index = state.get('current_task_index', 0)
        tasks = current_plan.get('tasks', [])

        # Insert at current position (before current failing task)
        tasks.insert(current_task_index, new_task)

        # Update total_tasks count
        current_plan['total_tasks'] = len(tasks)

        # Re-index task_ids (task0, task1, ...)
        for i, task in enumerate(tasks):
            task['task_id'] = f"task{i}"

        print(f"[OK] Inserted new task at index {current_task_index}: {new_task.get('task_type')}")
        updated_state["plan"] = current_plan
        # Don't increment current_task_index - we'll execute the newly inserted task

    elif replan_type == "full_replan":
        # Generate completely new plan
        new_instruction = replan_action.get("new_instruction", "")
        doc = state.get('original_doc')

        print(f"[INFO] Generating completely new plan with instruction: {new_instruction[:100]}...")
        new_plan = planner.create_plan(doc=doc, goal=new_instruction)

        if new_plan.get("error"):
            return {"error": f"Full replan failed: {new_plan['error']}"}

        # Reset execution state
        updated_state["plan"] = new_plan
        updated_state["current_task_index"] = 0
        updated_state["task_results"] = []
        updated_state["current_task"] = None
        updated_state["current_task_output"] = None
        print(f"[OK] New plan created with {new_plan.get('total_tasks')} tasks")

    else:
        return {"error": f"Unknown replan type: {replan_type}"}

    # Clear validation feedback
    updated_state["validation_feedback"] = None

    return updated_state


def prepare_next_task(state: AgentState) -> Dict[str, Any]:
    """
    PROTOTYPE 7: Prepare the next task for execution.

    Handles:
    - Normal progression: Increment current_task_index
    - Backtracking: Set current_task_index to backtrack target and clear results after that point

    Args:
        state: Current agent state

    Returns:
        Updated state with next task index
    """
    backtrack_to_task_id = state.get('backtrack_to_task_id')
    current_task_index = state.get('current_task_index', 0)
    task_results = state.get('task_results', [])

    if backtrack_to_task_id:
        # Backtracking mode
        print(f"\n[P7 ROUTER] Backtracking to {backtrack_to_task_id}...")

        # Find the index of the backtrack target
        backtrack_index = int(backtrack_to_task_id.replace('task', ''))

        # Clear all task results after the backtrack point
        task_results = [r for r in task_results if int(r['task_id'].replace('task', '')) < backtrack_index]

        print(f"[INFO] Cleared {current_task_index - backtrack_index + 1} task results from index {backtrack_index}")

        return {
            "current_task_index": backtrack_index,
            "task_results": task_results,
            "backtrack_to_task_id": None  # Clear backtrack flag
        }
    else:
        # Normal progression: move to next task
        next_index = current_task_index + 1
        print(f"\n[P7 ROUTER] Moving to task index {next_index}")

        return {
            "current_task_index": next_index
        }


def p7_router(state: AgentState) -> str:
    """
    PROTOTYPE 7: Router after validation.

    Decision tree:
    1. If error exists → end
    2. If validation passed:
       - If all tasks done → end
       - Else → execute_task
    3. If validation failed:
       - If root_cause_task_id exists → backtrack (set flag, then execute_task)
       - Elif replan_count < max_replans → replan
       - Else → end (max replans exceeded)

    Args:
        state: Current agent state

    Returns:
        Next node name
    """
    if state.get("error"):
        print("[P7 ROUTER] Error detected → END")
        return "end"

    validation_feedback = state.get("validation_feedback", {})
    plan = state.get('plan', {})
    current_task_index = state.get('current_task_index', 0)
    replan_count = state.get('replan_count', 0)
    max_replans = state.get('max_replans', 3)
    total_tasks = plan.get('total_tasks', 0)

    if validation_feedback.get("is_valid"):
        # Task passed validation
        next_index = current_task_index + 1

        if next_index >= total_tasks:
            print(f"[P7 ROUTER] All {total_tasks} tasks complete → END")
            return "end"
        else:
            print(f"[P7 ROUTER] Task {current_task_index} passed → NEXT TASK ({next_index})")
            return "prepare_next_task"
    else:
        # Task failed validation
        root_cause_task_id = validation_feedback.get("root_cause_task_id")

        if root_cause_task_id:
            # Backtracking to root cause
            print(f"[P7 ROUTER] Root cause identified: {root_cause_task_id} → BACKTRACK")
            # Set backtrack flag (prepare_next_task will handle it)
            state["backtrack_to_task_id"] = root_cause_task_id
            return "prepare_next_task"

        elif replan_count < max_replans:
            # Replan
            print(f"[P7 ROUTER] Validation failed, replan {replan_count + 1}/{max_replans} → REPLAN")
            return "replan"
        else:
            # Max replans exceeded
            print(f"[P7 ROUTER] Max replans ({max_replans}) exceeded → END")
            return "end"


def build_p7_graph():
    """
    PROTOTYPE 7: Build the dynamic task execution graph.

    Graph Flow:
    ┌─────────────────────────────────────────────────┐
    │  PLAN (Generate 3-7 tasks dynamically)         │
    └───────────────────┬─────────────────────────────┘
                        ↓
    ┌─────────────────────────────────────────────────┐
    │  EXECUTE_TASK (Generic executor)                │
    │  - Check dependencies                           │
    │  - Resolve templates                            │
    │  - Execute tool (+ fallback)                    │
    └───────────────────┬─────────────────────────────┘
                        ↓
    ┌─────────────────────────────────────────────────┐
    │  VALIDATE_TASK (With root cause analysis)       │
    └───────────────────┬─────────────────────────────┘
                        ↓
                   [ROUTER]
                        ├─→ All tasks done? → END
                        ├─→ Valid? → PREPARE_NEXT_TASK → EXECUTE_TASK
                        ├─→ Root cause? → PREPARE_NEXT_TASK (backtrack) → EXECUTE_TASK
                        ├─→ Can replan? → REPLAN → EXECUTE_TASK
                        └─→ Max replans? → END

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(AgentState)

    # Add Prototype 7 nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("validate_task", validate_task_node)
    workflow.add_node("replan", replan_node)
    workflow.add_node("prepare_next_task", prepare_next_task)

    # Set entry point
    workflow.set_entry_point("plan")

    # Add edges
    workflow.add_edge("plan", "execute_task")
    workflow.add_edge("execute_task", "validate_task")

    # Conditional edge after validation (router decides next step)
    workflow.add_conditional_edges(
        "validate_task",
        p7_router,
        {
            "prepare_next_task": "prepare_next_task",
            "replan": "replan",
            "end": END
        }
    )

    # After prepare_next_task, go back to execute_task
    workflow.add_edge("prepare_next_task", "execute_task")

    # After replan, go back to execute_task
    workflow.add_edge("replan", "execute_task")

    # Compile the graph
    return workflow.compile()


class Prototype7Agent:
    """
    PROTOTYPE 7: Dynamic Task Execution Agent

    Key Features:
    - Dynamic planning: 3-7 tasks based on document complexity
    - Template-based dependencies: {{taskN.field}} resolution
    - True backtracking: Re-execute earlier tasks when identified as root cause
    - Replan strategies: adjust_parameters, insert_task, full_replan
    - Generic nodes: No hardcoded workflow
    """

    def __init__(self):
        """Initialize Prototype 7 agent with dynamic graph"""
        self.graph = build_p7_graph()

    def run(self, doc: Any) -> Dict[str, Any]:
        """
        Run the Prototype 7 agent on a document.

        Args:
            doc: Input document (parsed JSON)

        Returns:
            Dict with:
            - success: bool
            - final_data: Final task result
            - task_log: List of task execution summaries
            - error: Error message if failed
        """
        print("\n" + "="*80)
        print("PROTOTYPE 7: Dynamic Task Execution Agent")
        print("="*80)

        inputs = {"original_doc": doc}
        final_state = {}

        try:
            # Stream execution steps
            for step in self.graph.stream(inputs, config={"recursion_limit": 100}):
                last_node = list(step.keys())[-1]
                node_state = step[last_node]

                # Skip END node or None
                if not isinstance(node_state, dict):
                    continue

                final_state.update(node_state)

            # Check for errors
            if final_state.get("error"):
                return {
                    "success": False,
                    "error": final_state["error"],
                    "task_log": self._build_task_log(final_state),
                    "final_data": None
                }

            # Extract final data
            task_results = final_state.get("task_results", [])
            final_data = None

            # Get the last successful task's data
            if task_results:
                last_result = task_results[-1]
                final_data = last_result.get("data")

            # Build task log
            task_log = self._build_task_log(final_state)

            print("\n" + "="*80)
            print(f"PROTOTYPE 7 COMPLETE: {len(task_results)} tasks executed")
            print("="*80)

            return {
                "success": True,
                "final_data": final_data,
                "task_log": task_log,
                "error": None
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Execution exception: {str(e)}",
                "task_log": [],
                "final_data": None
            }

    def _build_task_log(self, state: Dict) -> list:
        """
        Build a human-readable task execution log from state.

        Args:
            state: Final agent state

        Returns:
            List of task execution summaries
        """
        task_results = state.get("task_results", [])
        task_log = []

        for idx, result in enumerate(task_results, start=1):
            task_log.append({
                "step": idx,
                "task_id": result.get("task_id"),
                "success": result.get("success"),
                "tool_used": result.get("tool_used"),
                "execution_time": round(result.get("execution_time", 0), 2),
                "error": result.get("error")
            })

        return task_log

# ============================================================================
# NODE DEFINITIONS
# ============================================================================ 

def initialize_state(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Initialize the state by parsing the document into sections.
    This is the entry point of the graph.
    """
    print("\n[NODE] initialize_state: Parsing document...")
    doc = state['original_doc']
    accessor = DocumentAccessor(doc)
    sections_raw = accessor.get_all_sections()

    sections = [
        {
            "index": section.index,
            "title": section.title,
            "content": section.content_items,
            "raw": section.metadata.get("original_element") or section.metadata.get("original_section") or section.metadata
        }
        for section in sections_raw
    ]
    print(f"[OK] Found and converted {len(sections)} sections.")
    return {"sections": sections, "replan_count": 0, "execution_log": []}


def plan_initial_strategy(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Create an initial plan/strategy using the LLMPlanner.
    """
    print("\n[NODE] plan_initial_strategy: Creating initial plan...")
    plan = planner.create_plan(doc=state['original_doc'])
    
    if plan.get("error"):
        print(f"[FAIL] Planner failed: {plan['error']}")
        return {"error": f"Initial planning failed: {plan['error']}"}
        
    print(f"[OK] Initial strategy planned. Reasoning: {plan.get('reasoning')}")
    return {"initial_strategy": plan}

def classify_sections(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Classify sections using SectionClassifierTool.
    """
    print("\n[NODE] classify_sections: Executing...")
    tool = tools["section_classifier"]
    
    # Prepare params
    params = {"sections": state['sections']}
    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution (sections 제거한 버전만 기록)
    log = state.get("execution_log") or []
    log_params = dict(params)
    log_params.pop("sections", None)
    log.append({"type": "classify", "tool": tool.name, "params": log_params})

    # 실제 툴 실행은 full params로
    result = tool.execute(doc=None, params=params)
    
    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]}, 
            "last_executed_task": "classify",
            "execution_log": log
        }
    # 실행 결과 요약 ======================
    try:
        data = result.data or {}
        output_summary = {
            "definition_core": data.get("definition_core", []),
            "definition_annotation": data.get("definition_annotation", []),
            "condition": data.get("condition", []),
            "other": data.get("other", []),
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass
    # ==================================

    print("[OK] Sections classified.")
    return {
        "classification_result": result.data, 
        "last_executed_task": "classify", 
        "execution_log": log,
        "current_instruction": None # Clear instruction after use
    }

def extract_definitions(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Extract definitions using DefinitionExtractToolV2.
    """
    print("\n[NODE] extract_definitions: Executing...")
    tool = tools["definition_extract_v2"]
    classification = state['classification_result']
    
    params = {
        "sections": state['sections'],
        "core_indices": classification.get("definition_core", []),
        "annotation_indices": classification.get("definition_annotation", []),
    }
    


    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution (sections 제거한 버전만 기록)
    log = state.get("execution_log") or []
    log_params = dict(params)
    log_params.pop("sections", None)
    log.append({"type": "extract", "tool": tool.name, "params": log_params})

    # 실제 툴 실행은 full params로
    result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]}, 
            "last_executed_task": "extract",
            "execution_log": log
        }

    print("[OK] Definitions extracted.")
    # 결과 요약 =====================
    try:
        data = result.data or {}
        header = data.get("header", [])
        rows = data.get("data", [])
        output_summary = {
            "header": header,
            #"row_count": len(rows),
            "data": rows,
            "extraction_method": data.get("extraction_method", ""),
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass
    # 결과 요약 =====================

    return {
        "extraction_result": result.data, 
        "last_executed_task": "extract", 
        "execution_log": log,
        "current_instruction": None # Clear instruction after use
    }

def create_combinations(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Create combinations using a Cartesian tool (for Definition).
    """
    print("\n[NODE] create_combinations: Executing...")

    tool_override = state.get("tool_override")
    if tool_override and tool_override in tools:
        print(f"[INFO] Using tool override: {tool_override}")
        tool = tools[tool_override]
    else:
        # Default strategy: try rule-based first, then LLM.
        tool = tools.get("rule_cartesian", tools["llm_cartesian"])

    extraction = state['extraction_result']

    params = {
        "header": extraction.get("header", []),
        "data": extraction.get("data", []),
    }
    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # # Log execution
    # log = state.get("execution_log") or []
    # log.append({"type": "combine", "tool": tool.name, "params": params})

    # result = tool.execute(doc=None, params=params)
    # Log execution (sections 제거한 버전만 기록)
    log = state.get("execution_log") or []
    log_params = dict(params)
    log_params.pop("sections", None)
    log.append({"type": "combine", "tool": tool.name, "params": log_params})

    # 실제 툴 실행은 full params로
    result = tool.execute(doc=None, params=params)

    # Fallback logic only if no override was used
    if not tool_override and not result.success and tool.name == "rule_cartesian":
        print("[INFO] Rule-based combination failed. Trying LLM-based...")
        tool = tools["llm_cartesian"]
        log.append({"type": "combine", "tool": tool.name, "params": params})
        result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "combine",
            "execution_log": log
        }

    print(f"[OK] Combinations created using {tool.name}.")
    
    # 결과 요약 ==============
    try:
        data = result.data or {}
        defs = data.get("definitions", []) or data.get("rows", [])
        output_summary = {
            "total_count": data.get("total_count", len(defs)),
            "sample": defs[:3],  # 처음 3개만 로그에
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass
    
    # 결과 요약 ==============

    return {
        "combination_result": result.data,
        "last_executed_task": "combine",
        "execution_log": log,
        "current_instruction": None, # Clear instruction after use
        "tool_override": None # Clear override after use
    }

def extract_conditions(state: AgentState) -> Dict[str, Any]:
    """
    Node 6: Extract conditions using ConditionExtractTool.
    """
    print("\n[NODE] extract_conditions: Executing...")
    tool = tools["condition_extract"]
    classification = state['classification_result']

    # Get condition section indices
    condition_indices = classification.get("condition", [])

    # If no condition sections found, return empty result
    if not condition_indices:
        print("[INFO] No condition sections found. Skipping condition extraction.")
        return {
            "condition_result": {"header": [], "data": []},
            "last_executed_task": "extract_condition",
            "execution_log": state.get("execution_log", [])
        }

    params = {
        "sections": state['sections'],
        "condition_indices": condition_indices,
    }

    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution (sections 제거한 버전만 기록)
    log = state.get("execution_log") or []
    log_params = dict(params)
    log_params.pop("sections", None)
    log.append({"type": "extract_condition", "tool": tool.name, "params": log_params})

    # 실제 툴 실행은 full params로
    result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "extract_condition",
            "execution_log": log
        }

    print("[OK] Conditions extracted.")
    # 결과 요약을 execution_log 마지막 항목에 추가
    try:
        data = result.data or {}
        header = data.get("header", [])
        rows = data.get("data", [])
        output_summary = {
            "header": header,
            #"row_count": len(rows),
            "data": rows,
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass

    return {
        "condition_result": result.data,
        "last_executed_task": "extract_condition",
        "execution_log": log,
        "current_instruction": None # Clear instruction after use
    }

def create_condition_combinations(state: AgentState) -> Dict[str, Any]:
    """
    Node 7: Create combinations for Condition using a Cartesian tool.
    """
    print("\n[NODE] create_condition_combinations: Executing...")

    condition_data = state.get('condition_result', {})

    # If no condition data, skip this step
    if not condition_data.get("header") or not condition_data.get("data"):
        print("[INFO] No condition data to combine. Skipping condition cartesian.")
        return {
            "condition_combination_result": {"header": [], "data": []},
            "last_executed_task": "combine_condition",
            "execution_log": state.get("execution_log", [])
        }

    tool_override = state.get("tool_override")
    if tool_override and tool_override in tools:
        print(f"[INFO] Using tool override: {tool_override}")
        tool = tools[tool_override]
    else:
        # Default strategy: try rule-based first, then LLM.
        tool = tools.get("rule_cartesian", tools["llm_cartesian"])

    params = {
        "header": condition_data.get("header", []),
        "data": condition_data.get("data", []),
    }
    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution (sections 제거한 버전만 기록)
    log = state.get("execution_log") or []
    log_params = dict(params)
    log_params.pop("sections", None)
    log.append({"type": "combine_condition", "tool": tool.name, "params": log_params})

    # 실제 툴 실행은 full params로
    result = tool.execute(doc=None, params=params)

    # Fallback logic only if no override was used
    if not tool_override and not result.success and tool.name == "rule_cartesian":
        print("[INFO] Rule-based condition combination failed. Trying LLM-based...")
        tool = tools["llm_cartesian"]
        log.append({"type": "combine_condition", "tool": tool.name, "params": params})
        result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "combine_condition",
            "execution_log": log
        }

    print(f"[OK] Condition combinations created using {tool.name}.")

    # 결과 요약을 execution_log 마지막 항목에 추가
    try:
        data = result.data or {}
        defs = data.get("definitions", []) or data.get("rows", [])
        output_summary = {
            "total_count": data.get("total_count", len(defs)),
            "sample": defs[:3],
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass

    return {
        "condition_combination_result": result.data,
        "last_executed_task": "combine_condition",
        "execution_log": log,
        "current_instruction": None, # Clear instruction after use
        "tool_override": None # Clear override after use
    }

def merge_definition_condition(state: AgentState) -> Dict[str, Any]:
    """
    Node 8: Merge Definition and Condition combinations using LEFT JOIN.
    """
    print("\n[NODE] merge_definition_condition: Executing...")
    tool = tools["definition_condition_merge"]

    definition_result = state.get('combination_result', {})
    # [MODIFIED] Use raw condition_result, not condition_combination_result
    condition_result = state.get('condition_result', {})

    # If no condition data, return definitions as-is
    if not condition_result.get("header") or not condition_result.get("data"):
        print("[INFO] No condition data to merge. Returning definitions as-is.")
        return {
            "merged_result": definition_result,
            "last_executed_task": "merge",
            "execution_log": state.get("execution_log", [])
        }

    params = {
        "definitions": definition_result.get("definitions", []),
        "condition_header": condition_result.get("header", []),
        "condition_data": condition_result.get("data", []),
    }

    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution
    log = state.get("execution_log") or []
    log_params = dict(params)
    log.append({"type": "merge", "tool": tool.name, "params": log_params})

    # 실제 툴 실행
    result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "merge",
            "execution_log": log
        }

    print(f"[OK] Definition and Condition merged. Total: {result.data.get('total_count')}, "
          f"Matched: {result.data.get('join_stats', {}).get('matched', 0)}")

    # 결과 요약을 execution_log 마지막 항목에 추가
    try:
        data = result.data or {}
        output_summary = {
            "total_count": data.get("total_count"),
            "join_stats": data.get("join_stats", {}),
            "sample": data.get("definitions", [])[:3],
        }
        log[-1]["output_summary"] = output_summary
    except Exception:
        pass

    return {
        "merged_result": result.data,
        "last_executed_task": "merge",
        "execution_log": log,
        "current_instruction": None # Clear instruction after use
    }


# ============================================================================
# NEW NODES: Grouping-based Architecture
# ============================================================================

def normalize_definitions(state: AgentState) -> Dict[str, Any]:
    """
    Node 9 (NEW): Normalize definition table column names without creating combinations.

    Uses rule_cartesian's column mapping logic to normalize column names
    (first column → "보종명", rest → "유형1", "유형2", ...) but does NOT
    create Cartesian product. Keeps the raw table structure.
    """
    print("\n[NODE] normalize_definitions: Normalizing column names...")

    extraction = state.get('extraction_result')
    if not extraction or not extraction.get("header") or not extraction.get("data"):
        return {
            "validation_feedback": {"is_valid": False, "errors": ["No extraction_result to normalize"]},
            "last_executed_task": "normalize_def",
            "execution_log": state.get("execution_log", [])
        }

    header = extraction.get("header", [])
    data = extraction.get("data", [])

    # Column mapping logic (from RuleCartesianTool)
    # First column → "보종명", rest → "유형1", "유형2", ...
    normalized_header = []
    if header:
        normalized_header.append("보종명")  # First column
        for i in range(1, len(header)):
            normalized_header.append(f"유형{i}")

    print(f"[OK] Normalized {len(header)} columns: {header} → {normalized_header}")
    print(f"  - Data rows: {len(data)}")

    # Log execution
    log = state.get("execution_log") or []
    log.append({
        "type": "normalize_def",
        "tool": "rule_based_column_mapping",
        "params": {"original_header": header},
        "output_summary": {
            "normalized_header": normalized_header,
            "row_count": len(data)
        }
    })

    return {
        "normalized_definitions": {
            "header": normalized_header,
            "data": data  # Keep raw data as-is
        },
        "last_executed_task": "normalize_def",
        "execution_log": log,
        "current_instruction": None
    }


def normalize_conditions(state: AgentState) -> Dict[str, Any]:
    """
    Node 10 (NEW): Normalize condition table column names.

    Condition columns are already normalized by IntelligentConditionExtractTool,
    so this node just passes through the data. Kept for consistency and
    future enhancements.
    """
    print("\n[NODE] normalize_conditions: Normalizing condition columns...")

    condition_result = state.get('condition_result')

    # If no condition data, return empty
    if not condition_result or not condition_result.get("header"):
        print("[INFO] No condition data to normalize.")
        log = state.get("execution_log") or []
        log.append({
            "type": "normalize_cond",
            "tool": "passthrough",
            "output_summary": {"status": "no_condition_data"}
        })
        return {
            "normalized_conditions": {"header": [], "data": []},
            "last_executed_task": "normalize_cond",
            "execution_log": log
        }

    header = condition_result.get("header", [])
    data = condition_result.get("data", [])

    print(f"[OK] Condition columns: {header}")
    print(f"  - Data rows: {len(data)}")

    # Log execution
    log = state.get("execution_log") or []
    log.append({
        "type": "normalize_cond",
        "tool": "passthrough",
        "params": {"header": header},
        "output_summary": {
            "header": header,
            "row_count": len(data)
        }
    })

    return {
        "normalized_conditions": {
            "header": header,
            "data": data
        },
        "last_executed_task": "normalize_cond",
        "execution_log": log,
        "current_instruction": None
    }


def extract_grouping_logic(state: AgentState) -> Dict[str, Any]:
    """
    Node 11 (NEW): Extract grouping logic using LLM.

    LLM analyzes Definition and Condition tables to determine which
    definition rows match with which condition rows. Returns grouping
    metadata (not actual combinations).
    """
    print("\n[NODE] extract_grouping_logic: Executing...")
    tool = tools["grouping_logic_extractor"]

    normalized_defs = state.get('normalized_definitions', {})
    normalized_conds = state.get('normalized_conditions', {})

    if not normalized_defs.get("header") or not normalized_defs.get("data"):
        return {
            "validation_feedback": {"is_valid": False, "errors": ["No normalized_definitions"]},
            "last_executed_task": "grouping",
            "execution_log": state.get("execution_log", [])
        }

    if not normalized_conds.get("header") or not normalized_conds.get("data"):
        return {
            "validation_feedback": {"is_valid": False, "errors": ["No normalized_conditions"]},
            "last_executed_task": "grouping",
            "execution_log": state.get("execution_log", [])
        }

    params = {
        "definition_header": normalized_defs.get("header", []),
        "definition_data": normalized_defs.get("data", []),
        "condition_header": normalized_conds.get("header", []),
        "condition_data": normalized_conds.get("data", []),
    }

    instruction = state.get("current_instruction")
    if instruction:
        params["instruction"] = instruction

    # Log execution
    log = state.get("execution_log") or []
    log_params = {
        "definition_rows": len(normalized_defs.get("data", [])),
        "condition_rows": len(normalized_conds.get("data", [])),
    }
    if instruction:
        log_params["instruction"] = instruction
    log.append({"type": "grouping", "tool": tool.name, "params": log_params})

    # Execute tool
    result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "grouping",
            "execution_log": log
        }

    grouping_logic = result.data
    num_groups = len(grouping_logic.get("groups", []))
    summary = grouping_logic.get("summary", {})

    print(f"[OK] Extracted {num_groups} groups")
    print(f"  - Coverage: {summary.get('coverage_ratio', 0):.1%}")

    # Add output summary to log
    try:
        log[-1]["output_summary"] = {
            "num_groups": num_groups,
            "matched_definitions": summary.get("matched_definition_count", 0),
            "unmatched_definitions": summary.get("unmatched_definition_count", 0),
            "coverage_ratio": summary.get("coverage_ratio", 0),
        }
    except Exception:
        pass

    return {
        "grouping_logic": grouping_logic,
        "last_executed_task": "grouping",
        "execution_log": log,
        "current_instruction": None
    }


def generate_final_combinations(state: AgentState) -> Dict[str, Any]:
    """
    Node 12 (NEW): Generate final combinations using Python.

    Takes grouping logic from LLM and programmatically generates
    all definition+condition combinations. This is pure Python logic,
    no LLM calls, so it can handle unlimited combinations.
    """
    print("\n[NODE] generate_final_combinations: Executing...")
    tool = tools["combination_generator"]

    normalized_defs = state.get('normalized_definitions', {})
    normalized_conds = state.get('normalized_conditions', {})
    grouping_logic = state.get('grouping_logic', {})

    if not grouping_logic or "groups" not in grouping_logic:
        return {
            "validation_feedback": {"is_valid": False, "errors": ["No grouping_logic"]},
            "last_executed_task": "generate",
            "execution_log": state.get("execution_log", [])
        }

    params = {
        "definition_header": normalized_defs.get("header", []),
        "definition_data": normalized_defs.get("data", []),
        "condition_header": normalized_conds.get("header", []),
        "condition_data": normalized_conds.get("data", []),
        "grouping_logic": grouping_logic,
    }

    # Log execution
    log = state.get("execution_log") or []
    log_params = {
        "definition_rows": len(normalized_defs.get("data", [])),
        "condition_rows": len(normalized_conds.get("data", [])),
        "num_groups": len(grouping_logic.get("groups", [])),
    }
    log.append({"type": "generate", "tool": tool.name, "params": log_params})

    # Execute tool
    result = tool.execute(doc=None, params=params)

    if not result.success:
        print(f"[FAIL] {result.error}")
        return {
            "validation_feedback": {"is_valid": False, "errors": [result.error]},
            "last_executed_task": "generate",
            "execution_log": log
        }

    final_result = result.data
    stats = final_result.get("generation_stats", {})

    print(f"[OK] Generated {final_result.get('total_count', 0)} final definitions")
    print(f"  - From {stats.get('groups_processed', 0)} groups")
    print(f"  - Matched: {stats.get('matched_definitions', 0)}, Unmatched: {stats.get('unmatched_definitions', 0)}")

    # Add output summary to log
    try:
        log[-1]["output_summary"] = {
            "total_count": final_result.get("total_count", 0),
            "generation_stats": stats,
            "sample": final_result.get("definitions", [])[:3],
        }
    except Exception:
        pass

    return {
        "final_result": final_result,
        "last_executed_task": "generate",
        "execution_log": log
    }


def validate_step(state: AgentState) -> Dict[str, Any]:
    """
    Node 9: Validate the output of the previous step.
    This is a generic validation node.
    """
    feedback = state.get("validation_feedback") or {}
    if feedback.get("is_valid") is False:
        print(f"[INFO] Skipping validation for '{state.get('last_executed_task')}' as failure is already reported.")
        return {}

    last_task = state['last_executed_task']
    print(f"\n[NODE] validate_step: Validating '{last_task}'...")

    # Determine which output to validate based on the last task
    output_to_validate = None
    if last_task == 'classify':
        output_to_validate = state.get('classification_result')
        task_type_for_validator = 'classify'
    elif last_task == 'extract':
        output_to_validate = state.get('extraction_result')
        task_type_for_validator = 'extract'
    elif last_task == 'extract_condition':
        output_to_validate = state.get('condition_result')
        task_type_for_validator = 'extract_condition'
    elif last_task == 'combine':
        output_to_validate = state.get('combination_result')
        task_type_for_validator = 'transform'
    elif last_task == 'merge':
        output_to_validate = state.get('merged_result')
        task_type_for_validator = 'merge'
    elif last_task == 'normalize_def':
        output_to_validate = state.get('normalized_definitions')
        task_type_for_validator = 'normalize_def'
    elif last_task == 'normalize_cond':
        output_to_validate = state.get('normalized_conditions')
        task_type_for_validator = 'normalize_cond'
    elif last_task == 'grouping':
        output_to_validate = state.get('grouping_logic')
        task_type_for_validator = 'grouping'
    elif last_task == 'generate':
        output_to_validate = state.get('final_result')
        task_type_for_validator = 'generate'
    else:
        return {"validation_feedback": {"is_valid": False, "errors": [f"Unknown task to validate: {last_task}"]}}

    # Prepare context for the validator
    context = {}
    if last_task == 'classify':
        context["all_sections"] = state.get('sections', [])
    elif last_task == 'extract':
        core_indices = state.get("classification_result", {}).get("definition_core", [])
        annotation_indices = state.get("classification_result", {}).get("definition_annotation", [])
        all_sections = state.get('sections', [])
        context["core_sections"] = [s for s in all_sections if s['index'] in core_indices]
        context["annotation_sections"] = [s for s in all_sections if s['index'] in annotation_indices]
        context["definition_sections"] = [s for s in all_sections if s['index'] in core_indices or s['index'] in annotation_indices]
    elif last_task == 'extract_condition':
        condition_indices = state.get("classification_result", {}).get("condition", [])
        all_sections = state.get('sections', [])
        context["condition_sections"] = [s for s in all_sections if s['index'] in condition_indices]
    elif last_task == 'combine':
        context["extracted_data"] = state.get('extraction_result')
    elif last_task == 'merge':
        context["definition_result"] = state.get('combination_result')
        # [MODIFIED] Pass raw condition_result to validator
        context["condition_result"] = state.get('condition_result')
    elif last_task == 'grouping':
        # Grouping logic validator needs definition and condition data for index validation
        normalized_def = state.get('normalized_definitions', {})
        normalized_cond = state.get('normalized_conditions', {})
        context["definition_data"] = normalized_def.get('data', [])
        context["condition_data"] = normalized_cond.get('data', [])
    # normalize_def, normalize_cond, generate don't need special context

    # Run validation
    validation_result = validator.validate(
        task_type=task_type_for_validator,
        task_output=output_to_validate,
        context=context
    )

    if validation_result["is_valid"]:
        print(f"[OK] Validation passed for '{last_task}'.")
    else:
        print(f"[FAIL] Validation failed for '{last_task}': {validation_result.get('errors')}")

    return {"validation_feedback": validation_result}

def replan_or_finish(state: AgentState) -> Dict[str, Any]:
    """
    Node 7: The replan node. If validation fails, this node is called.
    It calls the planner to decide on the next step.
    """
    print("\n[NODE] replan_or_finish: Analyzing failure and replanning...")
    replan_count = state.get('replan_count', 0)

    if replan_count >= MAX_REPLAN_COUNT:
        print("[FAIL] Maximum replan limit reached. Aborting.")
        return {"error": "Maximum replan limit reached."}

    last_task_name = state['last_executed_task']
    execution_log = state.get('execution_log', [])
    validation_feedback = state.get('validation_feedback', {})

    # Find the last attempt for the failed task
    failed_task_attempt = None
    for attempt in reversed(execution_log):
        if attempt.get('type') == last_task_name:
            failed_task_attempt = attempt
            break
    
    if not failed_task_attempt:
        return {"error": f"Could not find execution log for failed task: {last_task_name}"}

    # Call the planner to get a new strategy
    new_plan = planner.replan(
        failed_task=failed_task_attempt,
        error_message=validation_feedback.get('errors', ['Unknown error'])[0],
        validation_result=validation_feedback
    )

    if new_plan.get("error"):
        return {"error": f"Replanning failed: {new_plan['error']}"}

    # For now, we only use the new instruction. A more advanced router
    # could use other info from the new_plan, like 'tool_name' or a 'next_node' field.
    new_instruction = new_plan.get("parameters", {}).get("instruction")
    tool_override = new_plan.get("tool_name")

    print(f"[INFO] Replanning attempt {replan_count + 1}/{MAX_REPLAN_COUNT}.")
    if new_instruction:
        print(f"  - New Instruction: {new_instruction}")
    if tool_override:
        print(f"  - Tool Override: {tool_override}")
    
    return {
        "replan_count": replan_count + 1,
        "current_instruction": new_instruction,
        "tool_override": tool_override,
        "validation_feedback": None # Clear feedback after replan
    }


# ============================================================================ 
# CONDITIONAL EDGES
# ============================================================================ 

def should_continue(state: AgentState) -> str:
    """
    Router: After validation, decide where to go next.
    - If valid, proceed to the next step.
    - If invalid, go to the replan node.

    NEW FLOW (grouping-based):
    classify → extract → normalize_def → extract_condition → normalize_cond
           → grouping → generate → end
    """
    if state.get("error"):
        return "end"

    validation_result = state.get("validation_feedback", {})
    last_task = state['last_executed_task']

    if validation_result.get("is_valid", False):
        if last_task == "classify":
            return "extract_definitions"
        elif last_task == "extract":
            # NEW: Go to normalize_definitions instead of extract_conditions
            return "normalize_definitions"
        elif last_task == "normalize_def":
            # NEW: After normalizing definitions, extract conditions
            return "extract_conditions"
        elif last_task == "extract_condition":
            # NEW: After extracting conditions, normalize them
            return "normalize_conditions"
        elif last_task == "normalize_cond":
            # NEW: After normalizing conditions, extract grouping logic
            return "extract_grouping_logic"
        elif last_task == "grouping":
            # NEW: After grouping logic, generate final combinations
            return "generate_final_combinations"
        elif last_task == "generate":
            # NEW: After generating combinations, we're done
            return "end"
        # Legacy paths (for backward compatibility if needed)
        elif last_task == "combine":
            return "merge_definition_condition"
        elif last_task == "merge":
            return "end"
        else:
            return "end" # Should not happen
    else:
        # If validation fails, go to replan
        return "replan_or_finish"

def after_replan(state: AgentState) -> str:
    """
    Router: After replanning, decide which node to backtrack to.

    Backtracking strategy: Retry the last failed step.
    """
    if state.get("error"):
        return "end"

    # Advanced: Here, planner.replan() would return the node to go to.
    # Simple version: always retry the last failed step.
    last_executed_task = state['last_executed_task']
    print(f"[ROUTE] Backtracking to '{last_executed_task}'.")

    if last_executed_task == "classify":
        return "classify_sections"
    elif last_executed_task == "extract":
        return "extract_definitions"
    elif last_executed_task == "normalize_def":
        # NEW: Backtrack to normalize_definitions
        return "normalize_definitions"
    elif last_executed_task == "extract_condition":
        return "extract_conditions"
    elif last_executed_task == "normalize_cond":
        # NEW: Backtrack to normalize_conditions
        return "normalize_conditions"
    elif last_executed_task == "grouping":
        # NEW: Backtrack to extract_grouping_logic
        return "extract_grouping_logic"
    elif last_executed_task == "generate":
        # NEW: Backtrack to generate_final_combinations
        return "generate_final_combinations"
    # Legacy paths
    elif last_executed_task == "combine":
        return "create_combinations"
    elif last_executed_task == "merge":
        return "merge_definition_condition"
    else:
        return "end"


# ============================================================================ 
# GRAPH BUILDER
# ============================================================================ 

def build_graph():
    """
    Builds the LangGraph agent graph.

    NEW FLOW (grouping-based architecture):
    initialize → plan → classify → validate
                                    ↓
                         extract_definitions → validate
                                    ↓
                         normalize_definitions → validate
                                    ↓
                         extract_conditions → validate
                                    ↓
                         normalize_conditions → validate
                                    ↓
                         extract_grouping_logic → validate
                                    ↓
                         generate_final_combinations → validate
                                    ↓
                                   END

    (validate can trigger replan → backtrack to failed node)
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("initialize_state", initialize_state)
    workflow.add_node("plan_initial_strategy", plan_initial_strategy)
    workflow.add_node("classify_sections", classify_sections)
    workflow.add_node("extract_definitions", extract_definitions)
    workflow.add_node("extract_conditions", extract_conditions)
    workflow.add_node("create_combinations", create_combinations)  # Legacy
    workflow.add_node("merge_definition_condition", merge_definition_condition)  # Legacy
    # NEW: Grouping-based nodes
    workflow.add_node("normalize_definitions", normalize_definitions)
    workflow.add_node("normalize_conditions", normalize_conditions)
    workflow.add_node("extract_grouping_logic", extract_grouping_logic)
    workflow.add_node("generate_final_combinations", generate_final_combinations)
    # Control nodes
    workflow.add_node("validate_step", validate_step)
    workflow.add_node("replan_or_finish", replan_or_finish)

    # Set entry point
    workflow.set_entry_point("initialize_state")

    # Add edges
    workflow.add_edge("initialize_state", "plan_initial_strategy")
    workflow.add_edge("plan_initial_strategy", "classify_sections")

    # All task nodes go to validation
    workflow.add_edge("classify_sections", "validate_step")
    workflow.add_edge("extract_definitions", "validate_step")
    workflow.add_edge("extract_conditions", "validate_step")
    workflow.add_edge("create_combinations", "validate_step")  # Legacy
    workflow.add_edge("merge_definition_condition", "validate_step")  # Legacy
    # NEW edges
    workflow.add_edge("normalize_definitions", "validate_step")
    workflow.add_edge("normalize_conditions", "validate_step")
    workflow.add_edge("extract_grouping_logic", "validate_step")
    workflow.add_edge("generate_final_combinations", "validate_step")

    # Conditional edge after validation
    workflow.add_conditional_edges(
        "validate_step",
        should_continue,
        {
            "extract_definitions": "extract_definitions",
            "extract_conditions": "extract_conditions",
            "create_combinations": "create_combinations",  # Legacy
            "merge_definition_condition": "merge_definition_condition",  # Legacy
            # NEW routes
            "normalize_definitions": "normalize_definitions",
            "normalize_conditions": "normalize_conditions",
            "extract_grouping_logic": "extract_grouping_logic",
            "generate_final_combinations": "generate_final_combinations",
            "replan_or_finish": "replan_or_finish",
            "end": END,
        },
    )

    # Conditional edge after replanning (for backtracking)
    workflow.add_conditional_edges(
        "replan_or_finish",
        after_replan,
        {
            "classify_sections": "classify_sections",
            "extract_definitions": "extract_definitions",
            "extract_conditions": "extract_conditions",
            "create_combinations": "create_combinations",  # Legacy
            "merge_definition_condition": "merge_definition_condition",  # Legacy
            # NEW backtrack routes
            "normalize_definitions": "normalize_definitions",
            "normalize_conditions": "normalize_conditions",
            "extract_grouping_logic": "extract_grouping_logic",
            "generate_final_combinations": "generate_final_combinations",
            "end": END
        }
    )

    # Compile the graph
    app = workflow.compile()
    return app

class Prototype6Agent:
    """
    The new LangGraph-based agent.
    The `run` method is now a simple call to the compiled graph.
    """
    def __init__(self):
        self.graph = build_graph()

    def run(self, doc: Any) -> Dict[str, Any]:
        """
        Run the agent graph and stream intermediate steps.
        """
        inputs = {"original_doc": doc}
        full_log = []
        final_state = {}

        # LangGraph 기본 recursion_limit(25)을 넘지 않도록 여유를 둔다.
        # replan 루프가 여러 번 돌 수 있으므로 recursion_limit을 넉넉하게 올려준다.
        for step in self.graph.stream(inputs, config={"recursion_limit": 100}):
            full_log.append(step)
            last_node = list(step.keys())[-1]
            node_state = step[last_node]

            # END 노드 / None 등은 건너뛰기
            if not isinstance(node_state, dict):
                continue

            final_state.update(node_state)
            
        if final_state.get("error"):
            return {"success": False, "error": final_state["error"], "full_log": full_log}

        # NEW: Return final_result from grouping-based architecture
        # Fallback: merged_result or combination_result for legacy
        final_data = (
            final_state.get("final_result") or
            final_state.get("merged_result") or
            final_state.get("combination_result")
        )

        # execution_log를 기반으로 한 간단한 task 로그 생성
        execution_log = final_state.get("execution_log", [])
        task_log = []
        for idx, entry in enumerate(execution_log, start=1):
            task_log.append({
                "step": idx,
                "type": entry.get("type"),
                "tool": entry.get("tool"),
                "input": entry.get("params"),
                # output_summary는 없을 수도 있으니 기본값 None
                "output": entry.get("output_summary"),
            })

        return {
            "success": True,
            "final_data": final_data,
            "task_log": task_log,
            "full_log": full_log,
            "error": None
        }
