from pathlib import Path
import json
import re
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict

# =============================
# CONFIG
# =============================
schema_fields = [
    "보종명","유형1","유형2","보험기간","납입기간",
    "주피보험자최소가입연령","주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드","주피보험자최대가입연령구분코드",
    "주피보험자가입성별",
]

block_primary = ["보종명","유형1","유형2","보험기간","납입기간","주피보험자가입성별"]
block_fallback = ["보종명","유형1","유형2","보험기간","납입기간"]

weights = {
    "보종명": 3.0,
    "유형1": 2.0,
    "유형2": 2.0,
    "보험기간": 2.0,
    "납입기간": 2.0,
    "주피보험자가입성별": 2.0,
    "주피보험자최소가입연령": 1.0,
    "주피보험자최대가입연령": 1.0,
    "주피보험자최소가입연령구분코드": 1.0,
    "주피보험자최대가입연령구분코드": 1.0,
}

MATCH_THRESHOLD = 0.85

# gt_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\GT\추가데이터_정답\008.신한놀라운종신보험(무배당, 해약환급금 일부지급형)_가입가능조건.json")
# pred_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\추가데이터_pred\008.사업방법서_신한놀라운종신보험(무배당__해약환급금_일부지급형)_250401_parsed_new_result.json")

# gt_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\GT\추가데이터_정답\056.신한(간편가입)종신보험 세븐Plus(무배당, 해약환급금 일부지급형)_가입가능조건.json")
# pred_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\추가데이터_pred\056.사업방법서_신한(간편가입)종신보험세븐Plus(무배당__해약환급금_일부지급형)_20250401_parsed_new_result.json")

gt_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o\GT\추가데이터_정답\114.(간편)일반암진단특약(무배당, 해약환급금 미지급형)_가입가능조건.json")
pred_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o\추가데이터_pred\114.사업방법서_(간편)일반암진단특약(무배당__해약환급금_미지급형)_250401_parsed_new_result.json")

# gt_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\GT\추가데이터_정답\286.(N)남녀특정암진단특약(무배당, 해약환급금 미지급형)_가입가능조건.json")
# pred_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\추가데이터_pred\286.사업방법서_(N)남녀특정암진단특약(무배당__해약환급금_미지급형)_250401_v2_parsed_new_result.json")

# gt_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\GT\추가데이터_정답\423.(간편)암주요치료비특약(무배당, 해약환급금 미지급형)_가입가능조건.json")
# pred_path = Path(r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8_4o_backup\추가데이터_pred\423.사업방법서_(간편)암주요치료비특약(무배당__해약환급금_미지급형)_250401_parsed_new_result.json")


# -----------------------------
# 1) Normalization
# -----------------------------
def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"\s+", "", s)
    s = s.replace(" ,", ",").replace(", ", ",")
    return s.casefold()

def norm_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    if isinstance(v, str):
        vv = norm_text(v)
        if vv.isdigit():
            return int(vv)
        return vv
    return v

def normalize_row(row: Dict[str, Any], fields: Optional[List[str]] = None) -> Dict[str, Any]:
    row_norm = {norm_text(k): norm_value(v) for k, v in row.items()}
    if fields is None:
        return row_norm
    out = {}
    for f in fields:
        nf = norm_text(f)
        out[f] = row_norm.get(nf)
    return out


# -----------------------------
# 2) Similarity (field-wise)
# -----------------------------
def field_equal(a: Any, b: Any) -> bool:
    return norm_value(a) == norm_value(b)

def record_similarity(gt: Dict[str, Any], pr: Dict[str, Any], weights: Dict[str, float]) -> float:
    if not weights:
        return 0.0
    total_w = 0.0
    hit_w = 0.0
    for f, w in weights.items():
        total_w += w
        if field_equal(gt.get(f), pr.get(f)):
            hit_w += w
    return hit_w / total_w if total_w > 0 else 0.0


# -----------------------------
# 3) Blocking candidates
# -----------------------------
def make_block_key(row: Dict[str, Any], block_fields: List[str]) -> Tuple:
    return tuple(norm_value(row.get(f)) for f in block_fields)

def build_blocks(rows: List[Dict[str, Any]], block_fields: List[str]) -> Dict[Tuple, List[int]]:
    blocks = defaultdict(list)
    for i, r in enumerate(rows):
        blocks[make_block_key(r, block_fields)].append(i)
    return blocks


# -----------------------------
# 4) Assignment (Hungarian if available, else greedy)
# -----------------------------
def try_hungarian(cost_matrix: List[List[float]]) -> Optional[List[Tuple[int, int]]]:
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        cm = np.array(cost_matrix)
        r_ind, c_ind = linear_sum_assignment(cm)
        return list(zip(r_ind.tolist(), c_ind.tolist()))
    except Exception:
        return None

def greedy_assignment(score_matrix: List[List[float]]) -> List[Tuple[int, int]]:
    n_gt = len(score_matrix)
    n_pr = len(score_matrix[0]) if n_gt > 0 else 0
    pairs = []
    used_gt = set()
    used_pr = set()

    candidates = []
    for i in range(n_gt):
        for j in range(n_pr):
            candidates.append((score_matrix[i][j], i, j))
    candidates.sort(reverse=True, key=lambda x: x[0])

    for s, i, j in candidates:
        if i in used_gt or j in used_pr:
            continue
        used_gt.add(i)
        used_pr.add(j)
        pairs.append((i, j))
    return pairs


# -----------------------------
# 5) Evaluate (문서 1개)
# -----------------------------
def evaluate_records(
    gt_rows: List[Dict[str, Any]],
    pred_rows: List[Dict[str, Any]],
    schema_fields: List[str],
    block_fields_primary: List[str],
    block_fields_fallback: Optional[List[str]] = None,
    weights: Optional[Dict[str, float]] = None,
    match_threshold: float = 0.85,
):
    schema_fields = [f.strip() for f in schema_fields]
    gt_norm = [normalize_row(r, schema_fields) for r in gt_rows]
    pr_norm = [normalize_row(r, schema_fields) for r in pred_rows]

    # extra key 비율
    extra_count = 0
    schema_set = set(schema_fields)
    for r in pred_rows:
        extra_keys = [k for k in r.keys() if k not in schema_set]
        if extra_keys:
            extra_count += 1
    extra_keys_rate = extra_count / max(len(pred_rows), 1)

    if weights is None:
        weights = {f: 1.0 for f in schema_fields}

    gt_blocks = build_blocks(gt_norm, block_fields_primary)
    pr_blocks = build_blocks(pr_norm, block_fields_primary)

    n_gt = len(gt_norm)
    n_pr = len(pr_norm)
    score_matrix = [[0.0 for _ in range(n_pr)] for _ in range(n_gt)]

    common_keys = set(gt_blocks.keys()) & set(pr_blocks.keys())
    for k in common_keys:
        for gi in gt_blocks[k]:
            for pj in pr_blocks[k]:
                score_matrix[gi][pj] = record_similarity(gt_norm[gi], pr_norm[pj], weights)

    if block_fields_fallback:
        nonzero = sum(1 for i in range(n_gt) for j in range(n_pr) if score_matrix[i][j] > 0)
        if nonzero < max(1, int(0.05 * n_gt * n_pr)):
            gt_blocks2 = build_blocks(gt_norm, block_fields_fallback)
            pr_blocks2 = build_blocks(pr_norm, block_fields_fallback)
            common2 = set(gt_blocks2.keys()) & set(pr_blocks2.keys())
            for k in common2:
                for gi in gt_blocks2[k]:
                    for pj in pr_blocks2[k]:
                        score_matrix[gi][pj] = max(
                            score_matrix[gi][pj],
                            record_similarity(gt_norm[gi], pr_norm[pj], weights)
                        )

    cost_matrix = [[1.0 - s for s in row] for row in score_matrix]
    pairs = try_hungarian(cost_matrix)
    if pairs is None:
        pairs = greedy_assignment(score_matrix)

    matches = []
    matched_gt = set()
    matched_pr = set()

    for gi, pj in pairs:
        s = score_matrix[gi][pj]
        if s >= match_threshold:
            matches.append((gi, pj, s))
            matched_gt.add(gi)
            matched_pr.add(pj)

    fn_gt = [i for i in range(n_gt) if i not in matched_gt]
    fp_pr = [j for j in range(n_pr) if j not in matched_pr]

    tp = len(matches)
    fp = len(fp_pr)
    fn = len(fn_gt)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "record_metrics": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "match_threshold": match_threshold
        },
        "extra_keys_rate": round(extra_keys_rate, 4),
        "matches": matches,
        "fn_gt_indices": fn_gt,
        "fp_pred_indices": fp_pr,
    }


def evaluate_single_document(gt_path: Path, pred_path: Path) -> dict:
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    if isinstance(gt_data, list):
        gt_rows = gt_data
    elif isinstance(gt_data, dict):
        for k in ["data", "가입가능조건", "rows", "items"]:
            if k in gt_data and isinstance(gt_data[k], list):
                gt_rows = gt_data[k]
                break
        else:
            raise ValueError("GT JSON에서 rows(list) 못 찾음")
    else:
        raise ValueError("GT JSON 구조 이상")

    with open(pred_path, "r", encoding="utf-8") as f:
        pred_data = json.load(f)

    if "final_data" in pred_data and "definitions" in pred_data["final_data"]:
        pred_rows = pred_data["final_data"]["definitions"]
    elif "definitions" in pred_data:
        pred_rows = pred_data["definitions"]
    else:
        raise ValueError("Pred JSON에서 definitions list 못 찾음")

    report = evaluate_records(
        gt_rows=gt_rows,
        pred_rows=pred_rows,
        schema_fields=schema_fields,
        block_fields_primary=block_primary,
        block_fields_fallback=block_fallback,
        weights=weights,
        match_threshold=MATCH_THRESHOLD,
    )

    # 🔥 pred_rows를 같이 넘김
    report["_pred_rows"] = pred_rows
    report["_gt_rows"] = gt_rows
    return report

def best_match_indices(
    query_row: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    schema_fields: List[str],
    weights: Dict[str, float],
    top_k: int = 1,
):
    qn = normalize_row(query_row, schema_fields)
    scored = []
    for idx, r in enumerate(candidates):
        rn = normalize_row(r, schema_fields)
        s = record_similarity(qn, rn, weights)
        scored.append((idx, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

def main():
    report = evaluate_single_document(gt_path, pred_path)

    print("📄 Document:", gt_path.name)
    print("F1:", report["record_metrics"]["f1"])
    print("Precision:", report["record_metrics"]["precision"])
    print("Recall:", report["record_metrics"]["recall"])
    print("TP / FP / FN:",
          report["record_metrics"]["tp"],
          report["record_metrics"]["fp"],
          report["record_metrics"]["fn"])
    print("extra_keys_rate:", report["extra_keys_rate"])

    gt_rows = report["_gt_rows"]
    pred_rows = report["_pred_rows"]

    # --------------------------
    # FP 샘플: Pred row + 가장 가까운 GT Top-1
    # --------------------------
    print("\n==============================")
    print("FP samples (Pred extra) + nearest GT")
    print("==============================")

    for pi in report["fp_pred_indices"][:5]:
        pred_row = pred_rows[pi]
        best = best_match_indices(pred_row, gt_rows, schema_fields, weights, top_k=1)
        gi, score = best[0] if best else (-1, 0.0)

        print(f"\n[FP pred index {pi}]  nearest_GT={gi}  score={score:.4f}")
        print("  PRED:", pred_row)
        if gi >= 0:
            print("  GT  :", gt_rows[gi])

    # --------------------------
    # FN 샘플: GT row + 가장 가까운 Pred Top-1
    # --------------------------
    print("\n==============================")
    print("FN samples (GT missed) + nearest Pred")
    print("==============================")

    for gi in report["fn_gt_indices"][:5]:
        gt_row = gt_rows[gi]
        best = best_match_indices(gt_row, pred_rows, schema_fields, weights, top_k=1)
        pi, score = best[0] if best else (-1, 0.0)

        print(f"\n[FN gt index {gi}]  nearest_PRED={pi}  score={score:.4f}")
        print("  GT  :", gt_row)
        if pi >= 0:
            print("  PRED:", pred_rows[pi])

if __name__ == "__main__":
    main()
