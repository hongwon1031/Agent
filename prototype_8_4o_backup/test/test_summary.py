import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _pretty_name(name: str) -> str:
    return (name or "unknown").replace("_", " ").strip()


def extract_task_runs(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    event_history 기반으로 "백트래킹 반영된" 최종 실행 시퀀스를 복원합니다.

    - task_execute_end: 실행된 task 결과를 1개 추가 (state.task_results.append와 동일 단위)
    - backtrack_applied: kept_task_results_count 기준으로 결과를 잘라냄 (state.task_results = [:min_idx] 반영)
    - 동일 task_id가 2회 이상 실행되면 (replan됨) 표시
    """
    events = result.get("event_history") or []

    effective: List[Dict[str, Any]] = []
    execution_counts: Dict[str, int] = {}

    for e in events:
        if not isinstance(e, dict):
            continue

        ev = e.get("event")

        if ev == "task_execute_end":
            task_id = e.get("task_id") or ""
            tool = e.get("tool_used") or e.get("tool_name") or e.get("task_type") or "unknown"
            task_name = _pretty_name(tool)

            if task_id:
                execution_counts[task_id] = execution_counts.get(task_id, 0) + 1
                if execution_counts[task_id] > 1:
                    task_name = f"{task_name}(replan됨)"

            effective.append({"orig_task_id": task_id, "task_name": task_name})

        elif ev == "backtrack_applied":
            kept = e.get("kept_task_results_count")
            if isinstance(kept, int) and kept >= 0:
                effective = effective[:kept]

    return [
        {"task_id": idx, "orig_task_id": r["orig_task_id"], "task_name": r["task_name"]}
        for idx, r in enumerate(effective, start=1)
    ]


def extract_full_timeline(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    event_history를 '있는 그대로' 타임라인으로 뽑습니다.
    (백트래킹으로 버려진 가지 포함, 실제 실행 순서 그대로)
    """
    events = result.get("event_history") or []

    scheduled_by_task_id: Dict[str, Dict[str, Any]] = {}
    execution_counts: Dict[str, int] = {}
    timeline: List[Dict[str, Any]] = []

    for e in events:
        if not isinstance(e, dict):
            continue

        ev = e.get("event")

        if ev == "task_scheduled":
            task_id = e.get("task_id") or ""
            if task_id:
                scheduled_by_task_id[task_id] = {
                    "dependencies": e.get("dependencies") or [],
                }

        if ev == "task_execute_end":
            task_id = e.get("task_id") or ""
            tool = e.get("tool_used") or e.get("tool_name") or e.get("task_type") or "unknown"
            task_name = _pretty_name(tool)

            if task_id:
                execution_counts[task_id] = execution_counts.get(task_id, 0) + 1
                if execution_counts[task_id] > 1:
                    task_name = f"{task_name}(replan됨)"

            deps = scheduled_by_task_id.get(task_id, {}).get("dependencies", [])
            timeline.append(
                {
                    "kind": "task",
                    "orig_task_id": task_id,
                    "task_name": task_name,
                    "success": bool(e.get("success")),
                    "dependencies": deps,
                }
            )

        if ev == "backtrack_applied":
            timeline.append(
                {
                    "kind": "backtrack",
                    "backtrack_to_task_id": e.get("backtrack_to_task_id"),
                    "tasks_to_rerun": e.get("tasks_to_rerun") or [],
                    "kept_task_results_count": e.get("kept_task_results_count"),
                }
            )

    return timeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_json", type=str)
    parser.add_argument("--mode", choices=["effective", "full"], default="effective")
    parser.add_argument("--show-deps", action="store_true", help="(full mode) dependencies 출력")
    args = parser.parse_args()

    result_path = Path(args.result_json)
    data = json.loads(result_path.read_text(encoding="utf-8"))

    if args.mode == "effective":
        for r in extract_task_runs(data):
            print(f"task_id = {r['task_id']}, task명 : {r['task_name']}")
        return 0

    step = 0
    for item in extract_full_timeline(data):
        if item["kind"] == "task":
            step += 1
            ok = "OK" if item.get("success") else "FAIL"
            deps = item.get("dependencies") or []
            deps_str = f" deps={deps}" if args.show_deps and deps else ""
            print(f"{step}. {item['orig_task_id']} {item['task_name']} [{ok}]{deps_str}")
        else:
            print(
                f"-- BACKTRACK to={item.get('backtrack_to_task_id')} "
                f"kept={item.get('kept_task_results_count')} rerun={item.get('tasks_to_rerun')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
