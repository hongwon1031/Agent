"""
Graph State Definition
"""
from typing import TypedDict, List, Dict, Any, Optional

class TaskDefinition(TypedDict):
    """
    Single task in execution plan for Prototype 7 dynamic architecture.

    Attributes:
        task_id: Unique identifier like "task0", "task1", etc.
        task_type: Type of task (e.g., "extract_definitions", "normalize_definitions")
        description: Human-readable description of what this task does
        tool_name: Primary tool to use for this task
        fallback_tool: Fallback tool if primary fails (optional)
        parameters: Dict of parameters to pass to tool (may contain templates like "{{task0.field}}")
        dependencies: List of task_ids that must complete successfully before this task
        output_key: Key name where result will be stored in task_results
    """
    task_id: str
    task_type: str
    description: str
    tool_name: str
    fallback_tool: Optional[str]
    parameters: Dict[str, Any]
    dependencies: List[str]
    output_key: str


class TaskResult(TypedDict):
    """
    Result of a single task execution in Prototype 7.

    Attributes:
        task_id: Which task this result is for
        success: Whether the task completed successfully
        data: The actual output data from the tool
        tool_used: Which tool was actually used (primary or fallback)
        execution_time: How long the task took in seconds
        error: Error message if task failed (None if successful)
    """
    task_id: str
    success: bool
    data: Any
    tool_used: str
    execution_time: float
    error: Optional[str]


class AgentState(TypedDict):
    """
    Represents the state of our agent.

    Attributes:
        original_doc: The original input document.
        sections: Parsed sections from the document.
        initial_strategy: High-level strategy determined by the planner at the beginning.
        current_instruction: An instruction for the current task, potentially updated by the replan node.

        # ===== PROTOTYPE 7: Dynamic Execution Fields =====
        plan: Optional[Dict]                       # Full plan from LLMPlanner (tasks, total_tasks, reasoning)
        current_task_index: int                    # Which task we're currently executing (0-based)
        task_results: List[TaskResult]             # Results of all completed tasks
        current_task: Optional[TaskDefinition]     # The task being executed now
        current_task_output: Optional[Any]         # Raw output from current task's tool
        max_replans: int                           # Maximum allowed replans (default: 3)
        backtrack_to_task_id: Optional[str]        # If set, backtrack to this task_id

        # ===== LEGACY: Prototype 6 Results (kept for tool compatibility) =====
        classification_result: Optional[Dict]
        extraction_result: Optional[Dict]
        condition_result: Optional[Dict]
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

    # ===== PROTOTYPE 7 v2: 1-Task-at-a-Time Dynamic Execution =====
    task_results: List[TaskResult]                # All completed task results
    current_task: Optional[TaskDefinition]        # Current task being executed
    current_task_output: Optional[Any]            # Raw output from current task
    is_complete: bool                             # All tasks done (planner returned END)
    backtrack_to_task_id: Optional[str]           # If set, backtrack target
    backtrack_reasoning: str                      # CRITICAL: Why we're backtracking (root cause analysis)
    retry_counts: Dict[str, int]                  # Per-task retry counters
    last_validation_feedback: Optional[Dict]      # Last validation feedback
    error_type: Optional[str]                     # Type of error: "task_definition_error" or "execution_error"
    error_suggestion: Optional[str]               # Suggestion for fixing the error
    failed_task_id: Optional[str]                 # ID of task that failed
    event_history: List[Dict[str, Any]]           # Persistent event log (not truncated on backtracking)

    # NEW: Dependency-aware backtracking and recoverable errors
    all_task_definitions: Dict[str, Any]          # Store all task definitions for dependency tracking
    task_definition_failed: bool                  # Recoverable task definition error flag
    task_definition_error: Optional[str]          # Error message for task definition

    # DEPRECATED (kept for backward compatibility, not used in v2)
    plan: Optional[Dict]                          # [DEPRECATED] Not used in 1-task-at-a-time
    current_task_index: int                       # [DEPRECATED] Not used in 1-task-at-a-time
    max_replans: int                              # [DEPRECATED] Not used in 1-task-at-a-time

    # ===== LEGACY: Prototype 6 Intermediate Results =====
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
