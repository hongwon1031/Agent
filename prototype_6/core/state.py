"""
Graph State Definition
"""
from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    """
    Represents the state of our agent.

    Attributes:
        original_doc: The original input document.
        sections: Parsed sections from the document.
        initial_strategy: High-level strategy determined by the planner at the beginning.
        current_instruction: An instruction for the current task, potentially updated by the replan node.
        
        # Results from each step
        classification_result: Optional[Dict]
        extraction_result: Optional[Dict]
        combination_result: Optional[Dict]
        
        # Metadata for control flow
        validation_feedback: Optional[Dict]
        replan_count: int
        last_executed_task: Optional[str]
        execution_log: Optional[List]
        
        # Final result
        final_data: Optional[Any]
        error: Optional[str]
"""
    # Inputs
    original_doc: Any
    sections: List[Dict]
    initial_strategy: Optional[Dict]
    current_instruction: Optional[str]
    tool_override: Optional[str]

    # Intermediate results
    classification_result: Optional[Dict]
    extraction_result: Optional[Dict]
    combination_result: Optional[Dict]

    # Control flow and metadata
    validation_feedback: Optional[Dict]
    replan_count: int
    last_executed_task: Optional[str]
    execution_log: Optional[List]

    # Final outputs
    final_data: Optional[Any]
    error: Optional[str]
