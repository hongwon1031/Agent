"""
LLM Usage Statistics Viewer

기존 결과 파일들의 LLM 사용량 및 비용을 확인하는 유틸리티
"""

import json
import sys
from pathlib import Path
from typing import Dict, List


def load_result_file(file_path: Path) -> dict:
    """Load a result JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path.name}: {e}")
        return {}


def extract_llm_stats_from_tasks(task_list: List[dict], result: dict = None) -> dict:
    """
    Extract and aggregate LLM stats from task_history or task_results
    (for backward compatibility with files that don't have llm_usage_summary)
    Also includes planner and validator stats if available.
    """
    aggregated = {}

    # Extract tool stats from task list
    for task in task_list:
        if not isinstance(task, dict):
            continue

        if not task.get("success"):
            continue

        task_data = task.get("data", {})
        llm_stats = task_data.get("llm_usage_stats", {})

        if not llm_stats:
            continue

        # Try both "tool_name" and "tool_used" (agent.py uses "tool_used")
        tool_name = task.get("tool_name") or task.get("tool_used", "unknown")

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

            # For cache_hits
            if "cache_hits" in stats:
                if "cache_hits" not in agg:
                    agg["cache_hits"] = 0
                agg["cache_hits"] += stats.get("cache_hits", 0)

    # Add planner stats if available
    if result:
        planner_stats = result.get("planner_llm_stats", {})
        if planner_stats:
            aggregated["planner"] = planner_stats

        # Add validator stats if available
        validator_stats = result.get("validator_llm_stats", {})
        if validator_stats:
            aggregated["validator"] = validator_stats

    # Calculate totals and averages
    total_cost = 0
    total_time = 0
    total_calls = 0
    
    for tool_name, operations in aggregated.items():
        for operation, stats in operations.items():
            if stats["call_count"] > 0:
                stats["average_time_ms"] = round(stats["total_time_ms"] / stats["call_count"], 2)
                input_cost = (stats["total_prompt_tokens"] / 1_000_000) * 2.5
                output_cost = (stats["total_completion_tokens"] / 1_000_000) * 10.0
                stats["estimated_cost_usd"] = round(input_cost + output_cost, 6)
            else:
                stats["average_time_ms"] = 0
                stats["estimated_cost_usd"] = 0

            total_cost += stats["estimated_cost_usd"]
            total_time += stats["total_time_ms"]
            total_calls += stats["call_count"]

    if not aggregated:
        return {}
    total_input_tokens = 0
    total_output_tokens = 0

    for tool_name, operations in aggregated.items():
        for operation, stats in operations.items():
            total_input_tokens += stats.get("total_prompt_tokens", 0)
            total_output_tokens += stats.get("total_completion_tokens", 0)

    total_tokens = total_input_tokens + total_output_tokens
    return {
        "total_llm_calls": total_calls,
        "total_time_ms": total_time,
        "total_time_seconds": round(total_time / 1000, 2),
        "total_estimated_cost_usd": round(total_cost, 6),

        # --- ADD: totals ---
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        # --- END ADD ---

        "by_tool": aggregated
    }


def format_time(ms: float) -> str:
    """Format milliseconds to human-readable string"""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.2f}s"
    else:
        minutes = int(ms / 60000)
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"


def print_summary(file_path: Path, summary: dict):
    """Print LLM usage summary for a single file"""
    print(f"\n{'='*80}")
    print(f"📄 File: {file_path.name}")
    print(f"{'='*80}")

    if not summary:
        print("❌ No LLM usage data found")
        return

    print(f"\n📊 Overall Statistics:")
    print(f"  💰 Total Cost:     ${summary['total_estimated_cost_usd']:.6f}")
    print(f"  ⏱️  Total Time:     {format_time(summary['total_time_ms'])}")
    print(f"  📞 Total Calls:    {summary['total_llm_calls']}")

    print(f"  🧾 Total Input Tokens:  {summary.get('total_input_tokens', 0):,}")
    print(f"  🧾 Total Output Tokens: {summary.get('total_output_tokens', 0):,}")
    print(f"  🧾 Total Tokens:        {summary.get('total_tokens', 0):,}")
    by_tool = summary.get('by_tool', {})
    if not by_tool:
        return

    print(f"\n🔧 By Tool & Operation:")
    print(f"{'Tool':<30} {'Operation':<20} {'Calls':<8} {'Input':<12} {'Output':<12} {'Total':<12} {'Time':<12} {'Cost':<12}")

    print("-" * 94)

    for tool_name, operations in sorted(by_tool.items()):
        for operation, stats in sorted(operations.items()):
            input_tokens = stats.get('total_prompt_tokens', 0)
            output_tokens = stats.get('total_completion_tokens', 0)
            total_tokens = input_tokens + output_tokens
            time_str = format_time(stats.get('total_time_ms', 0))
            cost = stats.get('estimated_cost_usd', 0)
            calls = stats.get('call_count', 0)

            # Add cache info if available
            cache_info = ""
            if 'cache_hits' in stats:
                cache_info = f" (cache: {stats['cache_hits']})"

            print(
    f"{tool_name:<30} {operation:<20} {calls:<8} "
    f"{input_tokens:<12,} {output_tokens:<12,} {total_tokens:<12,} "
    f"{time_str:<12} ${cost:<11.6f}"
)

            if cache_info:
                print(f"{'':>50} {cache_info}")


def print_aggregated_summary(all_summaries: List[tuple]):
    """Print aggregated summary across all files"""
    if not all_summaries:
        return

    print(f"\n{'='*80}")
    print(f"📈 AGGREGATED SUMMARY (All Files)")
    print(f"{'='*80}")

    total_cost = sum(s['total_estimated_cost_usd'] for _, s in all_summaries if s)
    total_time = sum(s['total_time_ms'] for _, s in all_summaries if s)
    total_calls = sum(s['total_llm_calls'] for _, s in all_summaries if s)

    print(f"\n💰 Total Cost:     ${total_cost:.6f}")
    print(f"⏱️  Total Time:     {format_time(total_time)}")
    print(f"📞 Total Calls:    {total_calls}")
    print(f"📁 Files Analyzed: {len([s for _, s in all_summaries if s])}")

    # Aggregate by tool
    aggregated_by_tool = {}
    for _, summary in all_summaries:
        if not summary:
            continue
        by_tool = summary.get('by_tool', {})
        for tool_name, operations in by_tool.items():
            if tool_name not in aggregated_by_tool:
                aggregated_by_tool[tool_name] = {}
            for operation, stats in operations.items():
                if operation not in aggregated_by_tool[tool_name]:
                    aggregated_by_tool[tool_name][operation] = {
                        'call_count': 0,
                        'total_tokens': 0,
                        'total_time_ms': 0,
                        'estimated_cost_usd': 0
                    }
                agg = aggregated_by_tool[tool_name][operation]
                agg['call_count'] += stats.get('call_count', 0)
                agg['total_tokens'] += stats.get('total_tokens', 0)
                agg['total_time_ms'] += stats.get('total_time_ms', 0)
                agg['estimated_cost_usd'] += stats.get('estimated_cost_usd', 0)

                if 'cache_hits' in stats:
                    if 'cache_hits' not in agg:
                        agg['cache_hits'] = 0
                    agg['cache_hits'] += stats.get('cache_hits', 0)

    if aggregated_by_tool:
        print(f"\n🔧 Aggregated By Tool & Operation:")
        print(f"{'Tool':<30} {'Operation':<20} {'Calls':<8} {'Input':<12} {'Output':<12} {'Total':<12} {'Time':<12} {'Cost':<12}")
        print("-" * 94)

        for tool_name in sorted(aggregated_by_tool.keys()):
            operations = aggregated_by_tool[tool_name]
            for operation in sorted(operations.keys()):
                stats = operations[operation]
                input_tokens = stats.get('total_prompt_tokens', 0)
                output_tokens = stats.get('total_completion_tokens', 0)
                total_tokens = input_tokens + output_tokens

                time_str = format_time(stats['total_time_ms'])
                cost = stats['estimated_cost_usd']
                calls = stats['call_count']

                cache_info = ""
                if 'cache_hits' in stats:
                    cache_info = f" (cache: {stats['cache_hits']})"

                print(
                f"{tool_name:<30} {operation:<20} {calls:<8} "
                f"{input_tokens:<12,} {output_tokens:<12,} {total_tokens:<12,} "
                f"{time_str:<12} ${cost:<11.6f}"
)

                if cache_info:
                    print(f"{'':>50} {cache_info}")


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        # Specific file or directory provided
        path = Path(sys.argv[1])
    else:
        # Default to new_results directory
        #path = Path(r"E:\work\work\Agent\prototype_8_4o\4o")
        path = Path(r'C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\추가데이터_pred\423.사업방법서_(간편)암주요치료비특약(무배당__해약환급금_미지급형)_250401_parsed_new_result.json')

    if not path.exists():
        print(f"❌ Path not found: {path}")
        sys.exit(1)

    all_summaries = []

    if path.is_file():
        # Single file mode
        result = load_result_file(path)
        summary = result.get('llm_usage_summary')

        # If no summary, try to extract from task_history or task_results
        if not summary:
            task_history = result.get('task_history', [])
            if not task_history:
                task_history = result.get('task_results', [])

            if task_history:
                summary = extract_llm_stats_from_tasks(task_history, result)

        print_summary(path, summary if summary else {})
    else:
        # Directory mode
        json_files = sorted(path.glob("*.json"))
        if not json_files:
            print(f"❌ No JSON files found in {path}")
            sys.exit(1)

        print(f"🔍 Found {len(json_files)} JSON files")

        for file_path in json_files:
            result = load_result_file(file_path)
            summary = result.get('llm_usage_summary')

            # If no summary, try to extract from task_history or task_results
            if not summary:
                task_history = result.get('task_history', [])
                if not task_history:
                    task_history = result.get('task_results', [])

                if task_history:
                    summary = extract_llm_stats_from_tasks(task_history, result)

            all_summaries.append((file_path, summary if summary else {}))
            print_summary(file_path, summary if summary else {})

        # Print aggregated summary
        print_aggregated_summary(all_summaries)

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()
