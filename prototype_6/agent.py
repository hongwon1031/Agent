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
)

# Initialize tools and core components once
planner = LLMPlanner()
validator = LLMValidator()
tools = {
    "section_classifier": SectionClassifierTool(),
    "definition_extract_v2": DefinitionExtractToolV2(),
    "rule_cartesian": RuleCartesianTool(),
    "llm_cartesian": LLMCartesianTool(),
}
MAX_REPLAN_COUNT = 5

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
    return {
        "extraction_result": result.data, 
        "last_executed_task": "extract", 
        "execution_log": log,
        "current_instruction": None # Clear instruction after use
    }

def create_combinations(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Create combinations using a Cartesian tool.
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
    return {
        "combination_result": result.data, 
        "last_executed_task": "combine", 
        "execution_log": log,
        "current_instruction": None, # Clear instruction after use
        "tool_override": None # Clear override after use
    }

def validate_step(state: AgentState) -> Dict[str, Any]:
    """
    Node 6: Validate the output of the previous step.
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
    elif last_task == 'combine':
        output_to_validate = state.get('combination_result')
        task_type_for_validator = 'transform'
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
    elif last_task == 'combine':
        context["extracted_data"] = state.get('extraction_result')

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
    """
    if state.get("error"):
        return "end"
        
    validation_result = state.get("validation_feedback", {})
    last_task = state['last_executed_task']

    if validation_result.get("is_valid", False):
        if last_task == "classify":
            return "extract_definitions"
        elif last_task == "extract":
            return "create_combinations"
        elif last_task == "combine":
            # This was the last step, so we are done
            return "end"
        else:
            return "end" # Should not happen
    else:
        # If validation fails, go to replan
        return "replan_or_finish"

def after_replan(state: AgentState) -> str:
    """
    Router: After replanning, decide which node to backtrack to.
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
    elif last_executed_task == "combine":
        return "create_combinations"
    else:
        return "end"


# ============================================================================ 
# GRAPH BUILDER
# ============================================================================ 

def build_graph():
    """
    Builds the LangGraph agent graph.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("initialize_state", initialize_state)
    workflow.add_node("plan_initial_strategy", plan_initial_strategy)
    workflow.add_node("classify_sections", classify_sections)
    workflow.add_node("extract_definitions", extract_definitions)
    workflow.add_node("create_combinations", create_combinations)
    workflow.add_node("validate_step", validate_step)
    workflow.add_node("replan_or_finish", replan_or_finish)

    # Set entry point
    workflow.set_entry_point("initialize_state")

    # Add edges
    workflow.add_edge("initialize_state", "plan_initial_strategy")
    workflow.add_edge("plan_initial_strategy", "classify_sections")

    workflow.add_edge("classify_sections", "validate_step")
    workflow.add_edge("extract_definitions", "validate_step")
    workflow.add_edge("create_combinations", "validate_step")

    # Conditional edge after validation
    workflow.add_conditional_edges(
        "validate_step",
        should_continue,
        {
            "extract_definitions": "extract_definitions",
            "create_combinations": "create_combinations",
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
            "create_combinations": "create_combinations",
            "end": END
        }
    )

    # Compile the graph
    app = workflow.compile()
    return app

class Prototype4_1Agent:
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

        for step in self.graph.stream(inputs):
            full_log.append(step)
            # The last key in the dictionary is the node that just ran
            last_node = list(step.keys())[-1]
            final_state.update(step[last_node])

        if final_state.get("error"):
            return {"success": False, "error": final_state["error"], "full_log": full_log}
        
        return {
            "success": True,
            "final_data": final_state.get("combination_result"),
            "full_log": full_log,
            "error": None
        }