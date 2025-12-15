"""
Prototype 7 Main Entry Point

Dynamic Task Execution System with True Backtracking
"""

import json
import sys
import argparse
from pathlib import Path
from agent import  Prototype7Agent


def load_document(doc_path: str):
    """Load JSON document"""
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading document: {e}")
        return None


def aggregate_llm_stats(task_history: list, planner_stats: dict = None, validator_stats: dict = None) -> dict:
    """
    Aggregate LLM usage statistics from task_history, planner, and validator

    Returns a dictionary with aggregated stats by tool and operation
    """
    aggregated = {}

    # Aggregate tool stats from task_history
    for task in task_history:
        if not task.get("success"):
            continue

        task_data = task.get("data", {})
        llm_stats = task_data.get("llm_usage_stats", {})

        tool_name = task.get("tool_name", "unknown")

        if tool_name not in aggregated:
            aggregated[tool_name] = {}

        for operation, stats in llm_stats.items():
            if operation not in aggregated[tool_name]:
                aggregated[tool_name][operation] = {
                    "call_count": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "total_time_ms": 0,
                    "estimated_cost_usd": 0
                }

            agg = aggregated[tool_name][operation]
            agg["call_count"] += stats.get("call_count", 0)
            agg["total_prompt_tokens"] += stats.get("total_prompt_tokens", 0)
            agg["total_completion_tokens"] += stats.get("total_completion_tokens", 0)
            agg["total_tokens"] += stats.get("total_tokens", 0)
            agg["total_time_ms"] += stats.get("total_time_ms", 0)

            # For cache_hits (CombinationGeneratorTool)
            if "cache_hits" in stats:
                if "cache_hits" not in agg:
                    agg["cache_hits"] = 0
                agg["cache_hits"] += stats.get("cache_hits", 0)

    # Add planner stats
    if planner_stats:
        aggregated["planner"] = planner_stats

    # Add validator stats
    if validator_stats:
        aggregated["validator"] = validator_stats

    # Calculate averages and costs for aggregated stats
    total_cost = 0
    total_time = 0
    total_calls = 0

    for tool_name, operations in aggregated.items():
        for operation, stats in operations.items():
            if stats["call_count"] > 0:
                stats["average_time_ms"] = round(stats["total_time_ms"] / stats["call_count"], 2)
                # Cost might already be calculated for planner/validator
                if "estimated_cost_usd" not in stats or stats["estimated_cost_usd"] == 0:
                    input_cost = (stats["total_prompt_tokens"] / 1_000_000) * 2.50
                    output_cost = (stats["total_completion_tokens"] / 1_000_000) * 10.00
                    stats["estimated_cost_usd"] = round(input_cost + output_cost, 6)
            else:
                stats["average_time_ms"] = 0
                if "estimated_cost_usd" not in stats:
                    stats["estimated_cost_usd"] = 0

            total_cost += stats["estimated_cost_usd"]
            total_time += stats["total_time_ms"]
            total_calls += stats["call_count"]

    # Add summary
    summary = {
        "total_llm_calls": total_calls,
        "total_time_ms": total_time,
        "total_time_seconds": round(total_time / 1000, 2),
        "total_estimated_cost_usd": round(total_cost, 6),
        "by_tool": aggregated
    }

    return summary


def save_result(result: dict, output_path: str):
    """Save result to JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nResult saved to: {output_path}")
    except Exception as e:
        print(f"\nError saving result: {e}")

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="Prototype 8 Agent - Dynamic Task Execution")
    parser.add_argument("input_path", type=str, help="Input document path or directory")
    parser.add_argument("--prototype", type=int, choices=[6, 7], default=7,
                        help="Prototype version to use (6=legacy, 7=dynamic) [default: 7]")

    args = parser.parse_args()
    input_path = Path(args.input_path)

    # Select agent

    print("\n🚀 Using Prototype 7: Dynamic Task Execution Agent")
    agent = Prototype7Agent()
    #results_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8\4o")
    results_dir = Path(r"E:\work\work\Agent\prototype_8_cost\4o")


    results_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_dir():
        # 디렉터리 모드: 모든 .json 처리
        json_files = sorted(input_path.glob("*.json"))
        if not json_files:
            print(f"No .json files found in {input_path}")
            return

        for doc_path in json_files:
            print("\n" + "="*80)
            print(f"Processing: {doc_path.name}")
            print("="*80)

            doc = load_document(str(doc_path))
            if doc is None:
                continue

            result = agent.run(doc)
            # 필요 시 task_results를 포함시킴
            if "task_results" not in result and hasattr(agent, "task_results"):
                result["task_results"] = getattr(agent, "task_results", [])
                result["task_history"] = getattr(agent, "task_history", [])
                result["debug_logs"] = agent.debug_logs  # 필요하다면

            # Aggregate LLM usage stats from task_history, planner, and validator
            task_history = getattr(agent, "task_history", [])
            planner_stats = result.get("planner_llm_stats")
            validator_stats = result.get("validator_llm_stats")
            if task_history:
                llm_usage_summary = aggregate_llm_stats(task_history, planner_stats, validator_stats)
                result["llm_usage_summary"] = llm_usage_summary
                print(f"\n💰 Total LLM Cost: ${llm_usage_summary['total_estimated_cost_usd']:.6f}")
                print(f"⏱️  Total LLM Time: {llm_usage_summary['total_time_seconds']:.2f}s")
                print(f"📞 Total LLM Calls: {llm_usage_summary['total_llm_calls']}")

            output_path = results_dir / f"{doc_path.stem}_new_result.json"
            save_result(result, str(output_path))


        print("\nAll files processed.")
    else:
        # 단일 파일 모드 (기존 동작 유지)
        doc_path = input_path
        print(f"\nInput document: {doc_path.name}")

        doc = load_document(str(doc_path))
        if doc is None:
            sys.exit(1)

        result = agent.run(doc)

        # 필요하면 task_results를 result에 넣어줌 (이미 포함돼 있으면 생략)
        if "task_results" not in result and hasattr(agent, "task_results"):
            result["task_results"] = getattr(agent, "task_results", [])
            result["task_history"] = getattr(agent, "task_history", [])
            result["debug_logs"] = agent.debug_logs  # 필요하다면

        # Aggregate LLM usage stats from task_history, planner, and validator
        task_history = getattr(agent, "task_history", [])
        planner_stats = result.get("planner_llm_stats")
        validator_stats = result.get("validator_llm_stats")
        if task_history:
            llm_usage_summary = aggregate_llm_stats(task_history, planner_stats, validator_stats)
            result["llm_usage_summary"] = llm_usage_summary
            print(f"\n💰 Total LLM Cost: ${llm_usage_summary['total_estimated_cost_usd']:.6f}")
            print(f"⏱️  Total LLM Time: {llm_usage_summary['total_time_seconds']:.2f}s")
            print(f"📞 Total LLM Calls: {llm_usage_summary['total_llm_calls']}")

        output_path = results_dir / f"{doc_path.stem}_single_result.json"
        save_result(result, str(output_path))


if __name__ == "__main__":
    main()