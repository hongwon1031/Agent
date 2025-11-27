import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOC_PLAN_DIR = BASE_DIR / "data" / "토이프로젝트_데이터" / "test" / "plan_no_cot"

def main():
    files = sorted(DOC_PLAN_DIR.glob("*no_cot.json"))
    if not files:
        print("NO_FILES")
        return

    agg = {
        "count": 0,
        "latency_seconds_sum": 0.0,
        "input_tokens_sum": 0,
        "output_tokens_sum": 0,
        "total_tokens_sum": 0,
        "input_cost_sum": 0.0,
        "output_cost_sum": 0.0,
        "total_cost_sum": 0.0,
    }

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        meta = data.get("_metadata") or {}
        agg["count"] += 1
        agg["latency_seconds_sum"] += float(meta.get("latency_seconds", 0.0))

        tu = meta.get("token_usage") or {}
        agg["input_tokens_sum"] += int(tu.get("input_tokens", 0))
        agg["output_tokens_sum"] += int(tu.get("output_tokens", 0))
        agg["total_tokens_sum"] += int(tu.get("total_tokens", 0))

        cost = meta.get("cost_usd") or {}
        agg["input_cost_sum"] += float(cost.get("input_cost", 0.0))
        agg["output_cost_sum"] += float(cost.get("output_cost", 0.0))
        agg["total_cost_sum"] += float(cost.get("total_cost", 0.0))

    count = agg["count"]
    avg = {
        "latency_seconds_avg": agg["latency_seconds_sum"] / count,
        "input_tokens_avg": agg["input_tokens_sum"] / count,
        "output_tokens_avg": agg["output_tokens_sum"] / count,
        "total_tokens_avg": agg["total_tokens_sum"] / count,
        "input_cost_avg": agg["input_cost_sum"] / count,
        "output_cost_avg": agg["output_cost_sum"] / count,
        "total_cost_avg": agg["total_cost_sum"] / count,
    }

    print(f"FILES: {count}")
    print("\n=== SUM ===")
    for k, v in agg.items():
        print(f"{k}: {v}")
    print("\n=== AVG ===")
    for k, v in avg.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
