"""
Restructure agent result JSON to show plan→execute→validate cycles chronologically
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def restructure_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Restructure result to show chronological plan→execute→validate cycles

    Args:
        result: Original agent output

    Returns:
        Restructured result with cycles
    """
    event_history = result.get("event_history", [])
    task_results = result.get("task_results", [])
    task_history = result.get("task_history", [])

    # Build lookup tables
    task_results_map = {r["task_id"]: r for r in task_results}
    task_history_map = {}
    for r in task_history:
        task_id = r["task_id"]
        if task_id not in task_history_map:
            task_history_map[task_id] = []
        task_history_map[task_id].append(r)

    cycles = []
    current_cycle = {}
    cycle_number = 0

    # Process events chronologically
    for event in event_history:
        event_type = event.get("event")

        # PLAN: planner_response
        if event_type == "planner_response":
            # Save previous cycle if complete
            if current_cycle and "execute" in current_cycle:
                cycles.append(current_cycle)

            cycle_number += 1
            action = event.get("action")

            if action == "next_task":
                current_cycle = {
                    "cycle_number": cycle_number,
                    "plan": {
                        "action": "next_task",
                        "reasoning": event.get("reasoning_preview", ""),
                        "task_results_count": event.get("task_results_count", 0)
                    }
                }
            elif action == "end":
                current_cycle = {
                    "cycle_number": cycle_number,
                    "plan": {
                        "action": "end",
                        "reasoning": event.get("reasoning_preview", "")
                    }
                }
                cycles.append(current_cycle)
                current_cycle = {}

        # PLAN: task_definition_created
        elif event_type == "task_definition_created":
            if "plan" in current_cycle:
                task_id = event.get("task_id")
                current_cycle["plan"].update({
                    "task_id": task_id,
                    "task_type": event.get("task_type"),
                    "tool": event.get("tool_name"),
                    "dependencies": event.get("dependencies", []),
                    "description": event.get("description", "")
                })

        # PLAN: backtrack
        elif event_type == "backtrack_requested":
            if current_cycle and "execute" in current_cycle:
                cycles.append(current_cycle)

            cycle_number += 1
            current_cycle = {
                "cycle_number": cycle_number,
                "plan": {
                    "action": "backtrack",
                    "backtrack_to_task_id": event.get("backtrack_to_task_id"),
                    "backtrack_reasoning": event.get("backtrack_reasoning", ""),
                    "task_results_count_before": event.get("task_results_count_before", 0)
                }
            }

        elif event_type == "backtrack_applied":
            if "plan" in current_cycle and current_cycle["plan"].get("action") == "backtrack":
                current_cycle["plan"]["tasks_to_rerun"] = event.get("tasks_to_rerun", [])
                current_cycle["plan"]["kept_task_results_count"] = event.get("kept_task_results_count", 0)

        # EXECUTE: task_execute_start
        elif event_type == "task_execute_start":
            task_id = event.get("task_id")
            if "plan" in current_cycle:
                current_cycle["execute"] = {
                    "task_id": task_id,
                    "task_type": event.get("task_type"),
                    "tool": event.get("tool_name"),
                    "started": True
                }

        # EXECUTE: task_execute_end
        elif event_type == "task_execute_end":
            task_id = event.get("task_id")
            if "execute" in current_cycle:
                # Get full task result data
                task_result = task_history_map.get(task_id, [{}])[-1]  # Get latest attempt

                current_cycle["execute"].update({
                    "success": event.get("success"),
                    "execution_time": event.get("execution_time"),
                    "input_params": event.get("resolved_params_preview", ""),
                    "output": event.get("output_preview", "") if event.get("success") else None,
                    "error": event.get("error_preview", "") if not event.get("success") else None,
                    "full_output": task_result.get("data") if event.get("success") else None,
                    "full_error": task_result.get("error") if not event.get("success") else None
                })

        # VALIDATE: validation_complete
        elif event_type == "validation_complete":
            task_id = event.get("task_id")
            if "execute" in current_cycle:
                current_cycle["validate"] = {
                    "task_id": task_id,
                    "is_valid": event.get("is_valid"),
                    "confidence": event.get("confidence"),
                    "errors": event.get("errors_preview", ""),
                    "suggestions": event.get("suggestions_preview", ""),
                    "root_cause_task_id": event.get("root_cause_task_id"),
                    "root_cause_reasoning": event.get("root_cause_reasoning_preview", "")
                }

    # Add last cycle if exists
    if current_cycle and "execute" in current_cycle:
        cycles.append(current_cycle)

    # Build summary
    successful_tasks = [r for r in task_results if r.get("success")]
    failed_tasks = [r for r in task_history if not r.get("success")]

    summary = {
        "overall_success": result.get("success"),
        "final_error": result.get("error"),
        "total_cycles": len(cycles),
        "total_tasks_executed": len(task_history),
        "successful_tasks": len(successful_tasks),
        "failed_tasks": len(failed_tasks),
        "backtrack_count": sum(1 for c in cycles if c.get("plan", {}).get("action") == "backtrack"),
        "planner_calls": result.get("planner_llm_stats", {}).get("generate_next_task", {}).get("call_count", 0),
        "total_cost_usd": result.get("llm_usage_summary", {}).get("total_estimated_cost_usd", 0),
        "total_time_seconds": result.get("llm_usage_summary", {}).get("total_time_seconds", 0)
    }

    return {
        "summary": summary,
        "cycles": cycles,
        "final_data": result.get("final_data"),
        "llm_usage_summary": result.get("llm_usage_summary"),
        "original_task_results": result.get("task_results"),  # For reference
        "original_task_history": result.get("task_history")   # For reference
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python restructure_result.py <input_json_path> [output_json_path]")
        print("If output path not specified, will use <input>_restructured.json")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.parent / f"{input_path.stem}_restructured.json"

    # Load original result
    print(f"Loading: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        result = json.load(f)

    # Restructure
    print("Restructuring...")
    restructured = restructure_result(result)

    # Save
    print(f"Saving: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(restructured, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for key, value in restructured["summary"].items():
        print(f"{key}: {value}")
    print(f"\nTotal cycles: {len(restructured['cycles'])}")
    print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
