from pathlib import Path
import json
import re
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict

# schema_fields = [
#     "보종명","유형1","유형2","보험기간","납입기간",
#     "주피보험자최소가입연령","주피보험자최대가입연령",
#     "주피보험자최소가입연령구분코드","주피보험자최대가입연령구분코드",
#     "주피보험자가입성별",
# ]

schema_fields = [
    "보종명","유형1","유형2","유형3","보험기간","납입기간",
    "주피보험자최소가입연령","주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드","주피보험자최대가입연령구분코드",
    "주피보험자가입성별",
]

block_primary = ["보종명","유형1","유형2","유형3","보험기간","납입기간","주피보험자가입성별"]
#block_primary = ["보종명","유형1","유형2","보험기간","납입기간","주피보험자가입성별"]
block_fallback = ["보종명","유형1","유형2","유형3","보험기간","납입기간"]
#block_fallback = ["보종명","유형1","유형2","보험기간","납입기간"]

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



# -----------------------------
# 1) Normalization
# -----------------------------
def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"\s+", "", s)
    s = s.replace(" ,", ",").replace(", ", ",")
    return s.casefold()  # ✅ 영문 대소문자 통일 (TC/tc)

def norm_value(v: Any) -> Any:
    if v is None:
        return None
    # 숫자면 int로
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    # 숫자 문자열도 int 가능하면 int로
    if isinstance(v, str):
        vv = norm_text(v)
        if vv.isdigit():
            return int(vv)
        return vv
    return v

def normalize_row(row: Dict[str, Any], fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    - row는 key/value 모두 정규화해서 lookup 가능하게 만들고
    - fields가 있으면 결과 dict의 key는 '원본 fields 이름'을 유지한다 (중요!)
    """
    # row key 정규화 -> value 정규화
    row_norm = {norm_text(k): norm_value(v) for k, v in row.items()}

    if fields is None:
        return row_norm  # (여기서도 정규화 키로 반환하니, 보통은 fields를 주는 쪽이 안전)

    out = {}
    for f in fields:
        nf = norm_text(f)          # lookup용
        out[f] = row_norm.get(nf)  # ✅ key는 원본 필드명 유지
    return out

def evaluate_em_and_field_metrics(
    gt_rows: List[Dict[str, Any]],
    pred_rows: List[Dict[str, Any]],
    schema_fields: List[str],
    block_fields_primary: List[str],
    block_fields_fallback: Optional[List[str]] = None,
    weights_for_pairing: Optional[Dict[str, float]] = None,
    min_pair_score: float = 0.0,  # ⭐ 추가: 매칭 점수가 이거보다 낮으면 unmatched로 처리
):
    """
    - 헝가리/그리디로 1:1 매칭 후보를 만들되
    - GT 기준으로:
      1) row-wise EM (all fields exact)
      2) field accuracy (FN 포함, GT 전체 기준)
      3) row-wise field-hit ratio (각 row에서 맞춘 필드 비율)
      4) macro row accuracy (= row-wise field-hit ratio 평균)
    """

    schema_fields = [f.strip() for f in schema_fields]

    gt_norm = [normalize_row(r, schema_fields) for r in gt_rows]
    pr_norm = [normalize_row(r, schema_fields) for r in pred_rows]

    if weights_for_pairing is None:
        weights_for_pairing = {f: 1.0 for f in schema_fields}

    n_gt = len(gt_norm)
    n_pr = len(pr_norm)

    # 1) blocking 후보 만들기
    gt_blocks = build_blocks(gt_norm, block_fields_primary)
    pr_blocks = build_blocks(pr_norm, block_fields_primary)

    score_matrix = [[0.0 for _ in range(n_pr)] for _ in range(n_gt)]

    common_keys = set(gt_blocks.keys()) & set(pr_blocks.keys())
    for k in common_keys:
        for gi in gt_blocks[k]:
            for pj in pr_blocks[k]:
                score_matrix[gi][pj] = record_similarity(
                    gt_norm[gi], pr_norm[pj], weights_for_pairing
                )

    # fallback 확장
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
                            record_similarity(gt_norm[gi], pr_norm[pj], weights_for_pairing)
                        )

    # 2) 1:1 최적 매칭
    cost_matrix = [[1.0 - s for s in row] for row in score_matrix]
    pairs = try_hungarian(cost_matrix)
    if pairs is None:
        pairs = greedy_assignment(score_matrix)

    # 3) GT->Pred 매핑(단, min_pair_score 미만이면 unmatched)
    gt_to_pred = {}
    for gi, pj in pairs:
        if gi >= n_gt or pj >= n_pr:
            continue
        if score_matrix[gi][pj] < min_pair_score:
            continue
        gt_to_pred[gi] = pj

    # 4) Metrics 계산
    field_hits = defaultdict(int)
    field_total = defaultdict(int)

    row_results = []
    em_count = 0
    macro_row_acc_sum = 0.0  # row별 필드정확도 평균을 위한 합

    for gi in range(n_gt):
        g = gt_norm[gi]
        pj = gt_to_pred.get(gi)

        # GT 전체 기준이므로 total은 무조건 증가
        for f in schema_fields:
            field_total[f] += 1

        if pj is None:
            # unmatched: field hit은 0, row_acc도 0
            row_results.append({
                "gt_index": gi,
                "pred_index": None,
                "pair_score": None,
                "is_em": False,
                "row_field_acc": 0.0,
                "diff": {f: {"gt": g.get(f), "pred": None} for f in schema_fields if g.get(f) is not None}
            })
            continue

        p = pr_norm[pj]
        pair_score = score_matrix[gi][pj]

        diff = {}
        is_exact = True
        hit_cnt = 0

        for f in schema_fields:
            if field_equal(g.get(f), p.get(f)):
                field_hits[f] += 1
                hit_cnt += 1
            else:
                is_exact = False
                diff[f] = {"gt": g.get(f), "pred": p.get(f)}

        row_field_acc = hit_cnt / max(len(schema_fields), 1)
        macro_row_acc_sum += row_field_acc

        if is_exact:
            em_count += 1

        row_results.append({
            "gt_index": gi,
            "pred_index": pj,
            "pair_score": round(pair_score, 4),
            "is_em": is_exact,
            "row_field_acc": round(row_field_acc, 4),
            "diff": diff
        })

    em_rate = em_count / max(n_gt, 1)
    field_accuracy = {f: round(field_hits[f] / field_total[f], 4) for f in schema_fields}
    macro_row_accuracy = round(macro_row_acc_sum / max(n_gt, 1), 4)

    return {
        "em_count": em_count,
        "gt_total": n_gt,
        "em_rate": round(em_rate, 4),
        "field_accuracy_gt_based": field_accuracy,  # ✅ FN 포함 전체 기준
        "macro_row_accuracy": macro_row_accuracy,   # ✅ row별 필드정확도 평균
        "row_metrics": row_results,                 # ✅ GT index 기준 상세
    }


# -----------------------------
# 2) Similarity (field-wise)
# -----------------------------
def field_equal(a: Any, b: Any) -> bool:
    return norm_value(a) == norm_value(b)

def record_similarity(
    gt: Dict[str, Any],
    pr: Dict[str, Any],
    weights: Dict[str, float],
    ignore_extra_pred_keys: bool = True,
) -> float:
    """
    가중치 기반 필드 일치 점수 (0~1).
    - weights에 있는 필드만 평가 대상으로 삼는 것을 권장
    """
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
    """
    block_fields로 구성한 키. 값은 정규화된 형태로.
    """
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
    """
    scipy가 있으면 Hungarian으로 최소비용(=최대유사도) 매칭.
    cost_matrix: (n_gt x n_pred) 비용행렬
    return: (gt_idx, pred_idx) pairs
    """
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
        cm = np.array(cost_matrix)
        r_ind, c_ind = linear_sum_assignment(cm)
        return list(zip(r_ind.tolist(), c_ind.tolist()))
    except Exception:
        return None

def greedy_assignment(score_matrix: List[List[float]]) -> List[Tuple[int, int]]:
    """
    단순 greedy 최대점 매칭(1:1)
    score_matrix: (n_gt x n_pred) 유사도 행렬
    """
    n_gt = len(score_matrix)
    n_pr = len(score_matrix[0]) if n_gt > 0 else 0

    pairs = []
    used_gt = set()
    used_pr = set()

    # 모든 후보를 점수로 정렬해서 높은 것부터 배정
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
# 5) Main evaluate
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
    """
    반환:
      - matches: [(gt_i, pr_j, score)]
      - tp_gt, fp_pred, fn_gt
      - field_accuracy (TP 매칭된 것 기준)
      - mismatch_samples
      - extra_keys_rate
    """
    schema_fields = [f.strip() for f in schema_fields]

    # 0) 스키마 기준으로만 정규화 (예측의 extra key는 평가에서 제외)
    gt_norm = [normalize_row(r, schema_fields) for r in gt_rows]
    pr_norm = [normalize_row(r, schema_fields) for r in pred_rows]

    # extra key 비율(품질 지표)
    extra_count = 0
    for r in pred_rows:
        extra_keys = [k for k in r.keys() if k not in set(schema_fields)]
        if extra_keys:
            extra_count += 1
    extra_keys_rate = extra_count / max(len(pred_rows), 1)

    # weights 기본값: schema 전부 1.0
    if weights is None:
        weights = {f: 1.0 for f in schema_fields}

    # 1) blocking 후보 만들기
    gt_blocks = build_blocks(gt_norm, block_fields_primary)
    pr_blocks = build_blocks(pr_norm, block_fields_primary)

    # 2) 같은 block key끼리만 점수 계산 (없으면 fallback으로 확장)
    # score_matrix는 전체(gt x pred)를 만들되, 후보 아니면 0점 처리
    n_gt = len(gt_norm)
    n_pr = len(pr_norm)
    score_matrix = [[0.0 for _ in range(n_pr)] for _ in range(n_gt)]

    common_keys = set(gt_blocks.keys()) & set(pr_blocks.keys())
    for k in common_keys:
        for gi in gt_blocks[k]:
            for pj in pr_blocks[k]:
                score_matrix[gi][pj] = record_similarity(gt_norm[gi], pr_norm[pj], weights)

    # fallback: primary block에서 매칭 후보가 거의 안 생기면, 더 느슨한 block으로 확장
    if block_fields_fallback:
        # 후보가 거의 없으면 확장 (경험적으로 5% 미만이면 확장)
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

    # 3) 최적 1:1 배정 (Hungarian 가능하면 사용)
    # Hungarian은 "비용 최소화"라서 cost=1-score 로 변환
    cost_matrix = [[1.0 - s for s in row] for row in score_matrix]
    pairs = try_hungarian(cost_matrix)
    if pairs is None:
        pairs = greedy_assignment(score_matrix)

    # 4) threshold로 TP/미매칭 분리
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

    # 5) 필드별 정확도(TP 매칭된 레코드들 기준)
    field_hits = defaultdict(int)
    field_total = defaultdict(int)
    exact_pairs = []
    non_exact_pairs = []
    mismatch_samples = []  # 디버깅용
    for gi, pj, s in matches:
        g = gt_norm[gi]
        p = pr_norm[pj]
        diff = {}
        is_exact = True
        for f in schema_fields:
            field_total[f] += 1
            if field_equal(g.get(f), p.get(f)):
                field_hits[f] += 1
            else:
                diff[f] = {"gt": g.get(f), "pred": p.get(f)}
                is_exact = False
        if is_exact:
            exact_pairs.append((gi, pj, s))
        else:
            non_exact_pairs.append((gi, pj, s))

        if diff:
            mismatch_samples.append({
                "gt_index": gi,
                "pred_index": pj,
                "score": round(s, 4),
                "diff": diff
            })

    field_accuracy = {}
    for f in schema_fields:
        tot = field_total.get(f, 0)
        field_accuracy[f] = (field_hits.get(f, 0) / tot) if tot else None  # TP가 없으면 None

    # 6) record-level metrics
    tp = len(matches)
    fp = len(fp_pr)
    fn = len(fn_gt)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    
    non_exact_pairs.sort(key=lambda x: x[2])  # score 오름차순 (worst first)
    exact_tp = len(exact_pairs)
    exact_precision = exact_tp / (exact_tp + fp) if (exact_tp + fp) else 0.0
    exact_recall = exact_tp / (exact_tp + fn) if (exact_tp + fn) else 0.0

    return {
        "record_metrics": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "match_threshold": match_threshold
        },
        "matches": matches,          # (gt_i, pred_j, score)
        "fn_gt_indices": fn_gt,
        "fp_pred_indices": fp_pr,
        "field_accuracy": field_accuracy,
        "mismatch_samples": mismatch_samples[:10],  # 샘플 10개만
        "extra_keys_rate": round(extra_keys_rate, 4),
        "exact_metrics": {
            "exact_tp": exact_tp,
            "exact_rate_in_matches": round(exact_tp / max(len(matches), 1), 4),
            "exact_precision": round(exact_precision, 4),
            "exact_recall": round(exact_recall, 4),
        },

        "exact_pairs": exact_pairs[:50],
        "non_exact_pairs": non_exact_pairs[:50],
    }

def evaluate_field_accuracy_gt_based(
    gt_rows: List[Dict[str, Any]],
    pred_rows: List[Dict[str, Any]],
    schema_fields: List[str],
    block_fields_primary: List[str],
    block_fields_fallback: Optional[List[str]] = None,
    weights_for_pairing: Optional[Dict[str, float]] = None,
):
    schema_fields = [f.strip() for f in schema_fields]

    gt_norm = [normalize_row(r, schema_fields) for r in gt_rows]
    pr_norm = [normalize_row(r, schema_fields) for r in pred_rows]

    if weights_for_pairing is None:
        weights_for_pairing = {f: 1.0 for f in schema_fields}

    n_gt = len(gt_norm)
    n_pr = len(pr_norm)

    # --- 1) score_matrix (blocking) ---
    gt_blocks = build_blocks(gt_norm, block_fields_primary)
    pr_blocks = build_blocks(pr_norm, block_fields_primary)

    score_matrix = [[0.0 for _ in range(n_pr)] for _ in range(n_gt)]

    common_keys = set(gt_blocks.keys()) & set(pr_blocks.keys())
    for k in common_keys:
        for gi in gt_blocks[k]:
            for pj in pr_blocks[k]:
                score_matrix[gi][pj] = record_similarity(gt_norm[gi], pr_norm[pj], weights_for_pairing)

    # fallback 확장
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
                            record_similarity(gt_norm[gi], pr_norm[pj], weights_for_pairing)
                        )

    # --- 2) 1:1 matching ---
    cost_matrix = [[1.0 - s for s in row] for row in score_matrix]
    pairs = try_hungarian(cost_matrix) or greedy_assignment(score_matrix)

    gt_to_pred = {gi: pj for gi, pj in pairs if gi < n_gt and pj < n_pr}

    # --- 3) Field accuracy (GT-based) ---
    field_hits = {f: 0 for f in schema_fields}
    field_total = {f: n_gt for f in schema_fields}  # ✅ 분모는 GT 전체 row

    for gi in range(n_gt):
        pj = gt_to_pred.get(gi, None)
        g = gt_norm[gi]

        if pj is None:
            continue  # 매칭 실패면 그 row의 모든 필드는 hit 못 함

        p = pr_norm[pj]
        for f in schema_fields:
            if field_equal(g.get(f), p.get(f)):
                field_hits[f] += 1

    field_acc = {f: round(field_hits[f] / max(field_total[f], 1), 4) for f in schema_fields}

    return {
        "gt_total": n_gt,
        "field_accuracy_gt_based": field_acc
    }


gtpath = r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\추출결과\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_가입가능조건.json"
predpath = r"C:\Users\NT-165\Desktop\Project\Toy\prototype_8\4o\신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed_single_result.json"

gt_path = Path(gtpath)
pred_path = Path(predpath)

with open(gt_path, "r", encoding="utf-8") as f:
    gt_data = json.load(f)

# ✅ GT는 반드시 list[dict] 여야 함
if isinstance(gt_data, list):
    gt_rows = gt_data
elif isinstance(gt_data, dict):
    # wrapper 있는 경우 대비
    for k in ["data", "가입가능조건", "rows", "items"]:
        if k in gt_data and isinstance(gt_data[k], list):
            gt_rows = gt_data[k]
            break
    else:
        raise ValueError("GT JSON에서 list 형태 rows를 찾지 못함")
else:
    raise ValueError("GT JSON 구조 이상")

# agent 출력 결과


with open(pred_path, "r", encoding="utf-8") as f:
    pred_data = json.load(f)

# 👉 agent 출력 구조 처리
# 보통: { "success": true, "final_data": { "definitions": [...] } }

if isinstance(pred_data, dict):
    if "final_data" in pred_data and "definitions" in pred_data["final_data"]:
        pred_rows = pred_data["final_data"]["definitions"]
    elif "definitions" in pred_data and isinstance(pred_data["definitions"], list):
        pred_rows = pred_data["definitions"]
    else:
        raise ValueError("Pred JSON에서 definitions list를 찾지 못함")
else:
    raise ValueError("Pred JSON 구조 이상")


weights = {k.strip(): v for k, v in weights.items()}
block_primary = [f.strip() for f in block_primary]
block_fallback = [f.strip() for f in block_fallback]

# report = evaluate_records(
#     gt_rows=gt_rows,
#     pred_rows=pred_rows,
#     schema_fields=schema_fields,
#     block_fields_primary=block_primary,
#     block_fields_fallback=block_fallback,
#     weights=weights,
#     match_threshold=0.85,
# )

# print(report["record_metrics"])
# print("extra_keys_rate:", report["extra_keys_rate"])
# print("field_accuracy:", report["field_accuracy"])
# print("mismatch_samples:", report["mismatch_samples"])
# print("FP pred indices:", report["fp_pred_indices"])
# print("FN gt indices:", report["fn_gt_indices"])

# # ✅ exact 결과 출력 추가
# print("exact_metrics:", report["exact_metrics"])
# print("exact_pairs (sample):", report["exact_pairs"][:10])
# print("non_exact_pairs (worst sample):", report["non_exact_pairs"][:10])



# report = evaluate_em_and_field_metrics(
#     gt_rows=gt_rows,
#     pred_rows=pred_rows,
#     schema_fields=schema_fields,
#     block_fields_primary=block_primary,
#     block_fields_fallback=block_fallback,
#     weights_for_pairing=weights,
#     min_pair_score=0.0,  # ⭐ 추천: 너무 엉뚱한 매칭은 unmatched 처리
# )

# print("EM:", report["em_count"], "/", report["gt_total"], "=", report["em_rate"])
# print("Macro Row Accuracy:", report["macro_row_accuracy"])
# print("Field Accuracy (GT-based):", report["field_accuracy_gt_based"])

# print("Row-wise (first 20):")
# for r in report["row_metrics"][:20]:
#     print(r["gt_index"], "->", r["pred_index"], "EM:", r["is_em"], "row_acc:", r["row_field_acc"], "pair_score:", r["pair_score"])
#     if not r["is_em"]:
#         print("  diff:", r["diff"])


fa = evaluate_field_accuracy_gt_based(
    gt_rows=gt_rows,
    pred_rows=pred_rows,
    schema_fields=schema_fields,
    block_fields_primary=block_primary,
    block_fields_fallback=block_fallback,
    weights_for_pairing=weights,
)

print("GT total:", fa["gt_total"])
print("Field Accuracy (GT-based):", fa["field_accuracy_gt_based"])
