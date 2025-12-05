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
        condition_result: Optional[Dict]

        # NEW: Grouping-based architecture results
        normalized_definitions: Optional[Dict]     # Normalized definition table (no combination)
        normalized_conditions: Optional[Dict]      # Normalized condition table (no combination)
        grouping_logic: Optional[Dict]             # LLM-extracted grouping logic
        final_result: Optional[Dict]               # Final combined definitions (Python-generated)

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

    # Intermediate results - Original pipeline
    classification_result: Optional[Dict]
    extraction_result: Optional[Dict]
    condition_result: Optional[Dict]              # Condition extraction result

    # NEW: Grouping-based architecture results
    normalized_definitions: Optional[Dict]        # {header, data} - normalized definition table
    normalized_conditions: Optional[Dict]         # {header, data} - normalized condition table
    grouping_logic: Optional[Dict]                # LLM grouping logic (groups, column_mapping, unmatched)
    final_result: Optional[Dict]                  # {definitions, total_count, generation_stats}

    # Control flow and metadata
    validation_feedback: Optional[Dict]
    replan_count: int
    last_executed_task: Optional[str]
    execution_log: Optional[List]

    # Final outputs
    final_data: Optional[Any]
    error: Optional[str]
