# test_generate_combinations.py
import os
import re
from itertools import product
from typing import Any, Dict, List, Optional
from tools.formula_utils import parse_age,evaluate_formula,parse_period
# -----------------------------
# Minimal stubs (your code depends on these)
# -----------------------------


# -----------------------------
# The function under test (copied, unchanged)
# -----------------------------
def _generate_combinations(
        self,
        def_header: List[str],
        def_data: List[List[str]],
        cond_header: List[str],
        cond_data: List[List[str]],
        grouping_logic: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        final_definitions = []
        column_mapping = grouping_logic.get("column_mapping", {})
        value_columns = column_mapping.get("value_columns", [])
        groups = grouping_logic.get("groups", [])
        join_keys = set(column_mapping.get("join_keys", []))

        def _fallback_num(value: Any) -> Optional[int]:
            if value is None:
                return None
            match = re.search(r"(\d+)", str(value))
            return int(match.group(1)) if match else None
        
        def _pick_formula_line(raw: Any, *, has_semangi: bool, has_yeonmangi: bool) -> Any:
            """
            raw가 멀티라인이면(\\n) 보험기간 컨텍스트에 맞는 라인을 선택해서 반환.
            - 세만기 컨텍스트면 '세만기' 포함 라인 우선
            - 년만기 컨텍스트면 '년만기' 포함 라인 우선
            - 둘 다 없거나 못찾으면 첫 줄
            """
            if not isinstance(raw, str):
                return raw

            s = raw.strip()
            if "\n" not in s:
                return s

            lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
            if not lines:
                return s

            # 우선순위: 컨텍스트에 맞는 키워드 포함 라인
            if has_yeonmangi:
                for ln in lines:
                    if "년만기" in ln:
                        return ln
                # 어떤 문서는 '년 만기'로 표현될 수도 있어 방어
                for ln in lines:
                    if "년 만기" in ln or "년만" in ln:
                        return ln

            if has_semangi:
                for ln in lines:
                    if "세만기" in ln:
                        return ln
                for ln in lines:
                    if "세 만기" in ln or "세만" in ln:
                        return ln

            # fallback
            return lines[0]




        try:
            whole_life_semangi_default = int(os.getenv("P8_WHOLE_LIFE_SEMANGI", "99"))
        except ValueError:
            whole_life_semangi_default = 99

        for group in groups:
            definition_indices = group.get("definition_indices", [])
            matched_list_items = group.get("matched_list_items", [])

            condition_indices = group.get("condition_indices", [])
            if not condition_indices:
                condition_index = group.get("condition_index")
                if condition_index is not None:
                    condition_indices = [condition_index]

            if not condition_indices:
                print(f"[WARNING] Group {group.get('id')} has no condition_indices")
                continue

            valid_condition_indices = []
            for cond_idx in condition_indices:
                if cond_idx is None or cond_idx >= len(cond_data):
                    print(f"[WARNING] Group {group.get('id')} has invalid condition_index: {cond_idx}")
                else:
                    valid_condition_indices.append(cond_idx)

            if not valid_condition_indices:
                print(f"[WARNING] Group {group.get('id')} has no valid condition_indices")
                continue

            # Get join_mappings for this group (replaces old match_condition)
            join_mappings = group.get("join_mappings", [])

            for condition_index in valid_condition_indices:
                condition_row = cond_data[condition_index]
                cond_row = {}
                for i, col in enumerate(cond_header):
                    cond_row[col] = condition_row[i] if i < len(condition_row) else None

                보험기간_list = cond_row.get("보험기간", [])
                if not isinstance(보험기간_list, list):
                    보험기간_list = [보험기간_list] if 보험기간_list else [None]

                납입기간_list = cond_row.get("납입기간", [])
                if not isinstance(납입기간_list, list):
                    납입기간_list = [납입기간_list] if 납입기간_list else [None]

                성별_list = cond_row.get("주피보험자가입성별", [])
                if not isinstance(성별_list, list):
                    성별_list = [성별_list] if 성별_list else [None]

                for idx, def_idx in enumerate(definition_indices):
                    if def_idx >= len(def_data):
                        print(f"[WARNING] Invalid definition_index: {def_idx}")
                        continue

                    definition_row = def_data[def_idx]

                    # ✅ NEW: matched_list_items element can be:
                    # - None
                    # - dict: {"유형2": [0,1,2], "유형3": 4, ...}
                    # - (legacy) int or list[int]  <-- if old prompt output still comes sometimes
                    matched_item = matched_list_items[idx] if idx < len(matched_list_items) else None

                    selection_map = {}
                    if matched_item is None:
                        selection_map = {}
                    elif isinstance(matched_item, dict):
                        selection_map = matched_item
                    else:
                        # legacy fallback: int or list[int]
                        # ⚠️ ambiguous which column it refers to, so we apply it ONLY to list-columns in join_keys if possible,
                        # else apply to the first list column we find.
                        legacy_indices = matched_item if isinstance(matched_item, list) else [matched_item]
                        legacy_indices = [x for x in legacy_indices if isinstance(x, int)]
                        target_cols = [c for c in def_header if c in join_keys]  # prefer join_key list columns
                        # find first list col among target_cols
                        chosen_col = None
                        for c in target_cols:
                            ci = def_header.index(c)
                            if ci < len(definition_row) and isinstance(definition_row[ci], list):
                                chosen_col = c
                                break
                        if chosen_col is None:
                            # fallback: any first list column
                            for c in def_header:
                                ci = def_header.index(c)
                                if ci < len(definition_row) and isinstance(definition_row[ci], list):
                                    chosen_col = c
                                    break
                        if chosen_col is not None:
                            selection_map = {chosen_col: legacy_indices}
                        else:
                            selection_map = {}

                    # ✅ 1) build options per column
                    options_by_col = {}
                    for i, col in enumerate(def_header):
                        value = definition_row[i] if i < len(definition_row) else None

                        if isinstance(value, list):
                            # 선택 지정이 있으면 그 인덱스만
                            if col in selection_map:
                                sel = selection_map[col]
                                sel_indices = sel if isinstance(sel, list) else [sel]
                                sel_indices = [x for x in sel_indices if isinstance(x, int)]
                                opts = []
                                for si in sel_indices:
                                    if 0 <= si < len(value):
                                        opts.append(value[si])
                                if not opts:
                                    opts = [value[0]] if value else [None]
                                options_by_col[col] = opts
                            else:
                                # 선택 지정이 없으면 전체 펼침
                                options_by_col[col] = value if value else [None]
                        else:
                            options_by_col[col] = [value]

                    # ✅ 2) expand definition row itself (cartesian product across list columns)
                    cols_in_order = def_header
                    option_lists = [options_by_col[c] for c in cols_in_order]

                    for chosen_values in product(*option_lists):
                        processed_def_row = dict(zip(cols_in_order, chosen_values))

                        # ✅ 3) now expand by condition lists (보험기간/납입기간/성별)
                        for 보험기간, 납입기간, 성별 in product(보험기간_list, 납입기간_list, 성별_list):
                            # --- 이하 기존 로직 그대로 (formula_context/age eval/merged 생성) ---
                            # (여기부터는 네 기존 코드 유지)
                            보험기간_숫자 = parse_period(보험기간) if 보험기간 else None
                            if 보험기간_숫자 is None:
                                보험기간_숫자 = _fallback_num(보험기간)
                            납입기간_숫자 = parse_period(납입기간) if 납입기간 else None
                            if 납입기간_숫자 is None:
                                납입기간_숫자 = _fallback_num(납입기간)

                            세만기 = None
                            년만기 = None
                            if 보험기간_숫자 is not None:
                                if "세" in str(보험기간):
                                    세만기 = 보험기간_숫자
                                elif "년" in str(보험기간):
                                    년만기 = 보험기간_숫자
                                else:
                                    세만기 = 보험기간_숫자

                            if 보험기간 and "종신" in str(보험기간) and 세만기 is None:
                                세만기 = whole_life_semangi_default

                            년납 = 납입기간_숫자
                            납입기간_년 = 납입기간_숫자

                            formula_context = {}
                            if 세만기 is not None:
                                formula_context["세만기"] = 세만기
                            if 년만기 is not None:
                                formula_context["년만기"] = 년만기
                            if 년납 is not None:
                                formula_context["년납"] = 년납
                                formula_context["납입기간"] = 년납
                            if 납입기간_년 is not None:
                                formula_context["납입기간_년"] = 납입기간_년

                            최소나이_raw = cond_row.get("주피보험자최소가입연령", "")
                            최대나이_raw = cond_row.get("주피보험자최대가입연령", "")

                            has_semangi = (세만기 is not None)
                            has_yeonmangi = (년만기 is not None)

                            최소나이_raw = _pick_formula_line(최소나이_raw, has_semangi=has_semangi, has_yeonmangi=has_yeonmangi)
                            최대나이_raw = _pick_formula_line(최대나이_raw, has_semangi=has_semangi, has_yeonmangi=has_yeonmangi)


                            최소나이 = parse_age(최소나이_raw) if 최소나이_raw else None
                            if 최소나이 is None and 최소나이_raw:
                                최소나이 = evaluate_formula(최소나이_raw, **formula_context)
                                if 최소나이 is None and formula_context:
                                    print(f"[WARN] Rule-based eval failed for 최소나이: '{최소나이_raw}', trying LLM fallback")
                                    최소나이 = self._llm_evaluate_age_formula(최소나이_raw, formula_context)

                            최대나이 = parse_age(최대나이_raw) if 최대나이_raw else None
                            if 최대나이 is None and 최대나이_raw:
                                최대나이 = evaluate_formula(최대나이_raw, **formula_context)
                                if 최대나이 is None and formula_context:
                                    print(f"[WARN] Rule-based eval failed for 최대나이: '{최대나이_raw}', trying LLM fallback")
                                    최대나이 = self._llm_evaluate_age_formula(최대나이_raw, formula_context)

                            merged = {}
                            # 1) Copy definition columns
                            for col, value in processed_def_row.items():
                                merged[col] = value

                            # 3) Add condition value columns (expanded)
                            merged["보험기간"] = 보험기간
                            merged["납입기간"] = 납입기간
                            merged["주피보험자최소가입연령"] = 최소나이
                            merged["주피보험자최대가입연령"] = 최대나이
                            merged["주피보험자최소가입연령구분코드"] = cond_row.get("주피보험자최소가입연령구분코드")
                            merged["주피보험자최대가입연령구분코드"] = cond_row.get("주피보험자최대가입연령구분코드")
                            merged["주피보험자가입성별"] = 성별

                            for col in value_columns:
                                if col in ("가입나이_남", "가입나이_여"):
                                    continue
                                if col not in merged and col in cond_row:
                                    merged[col] = cond_row[col]

                            final_definitions.append(merged)

        unmatched_def_indices = grouping_logic.get("unmatched", {}).get("definition_indices", [])
        for def_idx in unmatched_def_indices:
            if def_idx >= len(def_data):
                continue
            definition_row = def_data[def_idx]
            merged = {}
            for i, col in enumerate(def_header):
                merged[col] = definition_row[i] if i < len(definition_row) else None
            for col in value_columns:
                if col in ("가입나이_남", "가입나이_여"):
                    continue
                merged[col] = None
            final_definitions.append(merged)

        return final_definitions
# -----------------------------
# Test data (your example, simplified)
# -----------------------------
def main():
    def_header = ["보종명", "유형1", "유형2", "유형3"]
    def_data = [
        [
            "통합암(전이포함)진단특약TC (무배당, 해약환급금 미지급형)",
            "해약환급금 미지급형",
            ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형", "일반심사형"],
            [
                "두경부암(전이포함)",
                "위암 및 식도암(전이포함)",
                "소장·대장·항문암 및 기타암(전이포함)",
                "간·담낭·담도암 및 췌장암(전이포함)",
                "폐암(전이포함)",
                "흉곽내기관·중피성암 및 연조직암(전이포함)",
                "골·피부 등 전신부위암(전이포함)",
                "유방·비뇨기관·부신암 및 내분비선암(전이포함)",
                "남성/여성생식기암(전이포함)",
                "뇌암 및 중추신경계통암(전이포함)",
                "혈액암(전이포함)",
            ],
        ],
        [
            "통합암(전이포함)진단특약TC (무배당)",
            "일반형",
            ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형", "일반심사형"],
            [
                "두경부암(전이포함)",
                "위암 및 식도암(전이포함)",
                "소장·대장·항문암 및 기타암(전이포함)",
                "간·담낭·담도암 및 췌장암(전이포함)",
                "폐암(전이포함)",
                "흉곽내기관·중피성암 및 연조직암(전이포함)",
                "골·피부 등 전신부위암(전이포함)",
                "유방·비뇨기관·부신암 및 내분비선암(전이포함)",
                "남성/여성생식기암(전이포함)",
                "뇌암 및 중추신경계통암(전이포함)",
                "혈액암(전이포함)",
            ],
        ],
    ]

    cond_header = [
          "유형1",
          "유형2",
          "유형3",
          "보험기간",
          "납입기간",
          "주피보험자최소가입연령",
          "주피보험자최대가입연령",
          "주피보험자최소가입연령구분코드",
          "주피보험자최대가입연령구분코드",
          "주피보험자가입성별"
        ]
    cond_data = [
          [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "가입가능 조건",
            "해약환급금 미지급형",
            [
              "80세 만기",
              "90세 만기",
              "100세 만기",
              "종신"
            ],
            [
              "10년납",
              "15년납",
              "20년납",
              "25년납",
              "30년납"
            ],
            "만 15세",
            "min[세만기 - 년납, 90 - 년납, 80] 세",
            "(2)만연령",
            "(1)보험연령",
            [
              "(1)남자",
              "(2)여자"
            ]
          ],
          [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "가입가능 조건",
            "해약환급금 미지급형",
            [
              "80세 만기",
              "90세 만기",
              "100세 만기",
              "종신"
            ],
            [
              "10년납",
              "15년납",
              "20년납",
              "25년납",
              "30년납"
            ],
            "만 15세",
            "min[세만기 - 년납, 90 - 년납, 70] 세",
            "(2)만연령",
            "(1)보험연령",
            [
              "(1)남자",
              "(2)여자"
            ]
          ],
          [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "가입가능 조건",
            "일반형",
            [
              "25년 만기",
              "30년 만기",
              "80세 만기",
              "90세 만기",
              "100세 만기",
              "종신"
            ],
            [
              "5년납",
              "7년납",
              "10년납",
              "15년납",
              "20년납",
              "25년납",
              "30년납"
            ],
            "만 15세",
            "min[세만기 - 년납, 90 - 년납, 80] 세\nmin[100 - 년만기, 90 - 년납, 80] 세",
            "(2)만연령",
            "(1)보험연령",
            [
              "(1)남자",
              "(2)여자"
            ]
          ],
          [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "가입가능 조건",
            "일반형",
            [
              "25년 만기",
              "30년 만기",
              "80세 만기",
              "90세 만기",
              "100세 만기",
              "종신"
            ],
            [
              "5년납",
              "7년납",
              "10년납",
              "15년납",
              "20년납",
              "25년납",
              "30년납"
            ],
            "만 15세",
            "min[세만기 - 년납, 90 - 년납, 80] 세\nmin[100 - 년만기, 90 - 년납, 80] 세",
            "(2)만연령",
            "(1)보험연령",
            [
              "(1)남자",
              "(2)여자"
            ]
          ]
        ]

    data = {
        "column_mapping": {
          "join_keys": [
            "유형1",
            "유형2"
          ],
          "value_columns": [
            "보험기간",
            "납입기간",
            "주피보험자최소가입연령",
            "주피보험자최대가입연령",
            "주피보험자최소가입연령구분코드",
            "주피보험자최대가입연령구분코드",
            "주피보험자가입성별"
          ]
        },
        "groups": [
          {
            "id": 0,
            "join_mappings": [
              {
                "def_col": "유형1",
                "cond_col": "유형1",
                "value": "해약환급금 미지급형"
              },
              {
                "def_col": "유형2",
                "cond_col": "유형2",
                "value": "간편심사형"
              }
            ],
            "definition_indices": [
              0
            ],
            "matched_list_items": [
              [
                0,
                1,
                2
              ]
            ],
            "condition_indices": [
              0
            ],
            "reasoning": "유형1과 유형2가 일치하며, '간편심사형'은 '간편심사(315)형', '간편심사(335)형', '간편심사(355)형'과 fuzzy 매칭됩니다."
          },
          {
            "id": 1,
            "join_mappings": [
              {
                "def_col": "유형1",
                "cond_col": "유형1",
                "value": "해약환급금 미지급형"
              },
              {
                "def_col": "유형2",
                "cond_col": "유형2",
                "value": "일반심사형"
              }
            ],
            "definition_indices": [
              0
            ],
            "matched_list_items": [
              3
            ],
            "condition_indices": [
              1
            ],
            "reasoning": "유형1과 유형2가 일치하며, '일반심사형'은 '일반심사형'과 정확히 매칭됩니다."
          },
          {
            "id": 2,
            "join_mappings": [
              {
                "def_col": "유형1",
                "cond_col": "유형1",
                "value": "일반형"
              },
              {
                "def_col": "유형2",
                "cond_col": "유형2",
                "value": "간편심사형"
              }
            ],
            "definition_indices": [
              1
            ],
            "matched_list_items": [
              [
                0,
                1,
                2
              ]
            ],
            "condition_indices": [
              2
            ],
            "reasoning": "유형1과 유형2가 일치하며, '간편심사형'은 '간편심사(315)형', '간편심사(335)형', '간편심사(355)형'과 fuzzy 매칭됩니다."
          },
          {
            "id": 3,
            "join_mappings": [
              {
                "def_col": "유형1",
                "cond_col": "유형1",
                "value": "일반형"
              },
              {
                "def_col": "유형2",
                "cond_col": "유형2",
                "value": "일반심사형"
              }
            ],
            "definition_indices": [
              1
            ],
            "matched_list_items": [
              3
            ],
            "condition_indices": [
              3
            ],
            "reasoning": "유형1과 유형2가 일치하며, '일반심사형'은 '일반심사형'과 정확히 매칭됩니다."
          }
        ],
        "unmatched": {
          "definition_indices": [],
          "condition_indices": []
        },
        "summary": {
          "total_definitions": 2,
          "total_conditions": 4,
          "total_groups": 4,
          "matched_definition_count": 2,
          "unmatched_definition_count": 0,
          "coverage_ratio": 1.0
        }
      }


    class Dummy:
        def _llm_evaluate_age_formula(self, raw: str, ctx: dict):
            return None
        def _llm_evaluate_age_formula(self, formula_str: str, context: Dict[str, Any]) -> Optional[int]:
            """
            LLM-based fallback for formula evaluation (with caching)

            Args:
                formula_str: Age formula (e.g., "만15세 ~ min{80-년만기, 70}세")
                context: Variable context (e.g., {"년만기": 20, "세만기": 80})

            Returns:
                Evaluated age or None if LLM fails
            """
            # CRITICAL: Check cache first to avoid repeated API calls
            cache_key = (formula_str, frozenset(context.items()))
            if cache_key in self._formula_cache:
                cached_value = self._formula_cache[cache_key]
                print(f"[LLM FORMULA EVAL] [CACHED] '{formula_str}' → {cached_value}")
                return cached_value

            try:
                import json as json_module

                prompt = f"""다음 나이 조건 수식을 해석하여 정수 값을 반환하세요.

    **수식**: {formula_str}
    **컨텍스트**: {json_module.dumps(context, ensure_ascii=False)}

    **예시**:
    - "만15세" → 15
    - "min{{80-년만기, 70}}세" + {{"년만기": 20}} → min{{80-20, 70}} = 60
    - "만20세 ~ 65세" (최소나이 요청) → 20
    - "만20세 ~ 65세" (최대나이 요청) → 65

    **중요**:
    - 수식에 "~"가 있으면 범위 표현입니다. 최소값만 추출하세요 (앞부분).
    - min, max, 사칙연산을 올바르게 계산하세요.
    - 결과는 반드시 정수여야 합니다.

    **JSON 형식으로만 반환**:
    {{
    "value": <정수>
    }}"""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_output_tokens=200
                )

                result = json_module.loads(response.output_text)
                value = result.get("value")

                # Sanity check
                if value is not None and isinstance(value, (int, float)):
                    value = int(value)
                    if 0 <= value <= 120:  # Valid age range
                        print(f"[LLM FORMULA EVAL] '{formula_str}' → {value}")
                        # CRITICAL: Store in cache for future reuse
                        self._formula_cache[cache_key] = value
                        return value
                    else:
                        print(f"[LLM FORMULA EVAL] Invalid age range: {value}")
                        # Cache None for invalid results too (avoid repeated failures)
                        self._formula_cache[cache_key] = None
                        return None
                else:
                    print(f"[LLM FORMULA EVAL] Failed: {formula_str} → {result}")
                    # Cache None for failed results
                    self._formula_cache[cache_key] = None
                    return None

            except Exception as e:
                print(f"[LLM FORMULA EVAL] Error: {e}")
                # Cache None for errors too
                self._formula_cache[cache_key] = None
                return None

    dummy = Dummy()

    out = _generate_combinations(dummy, def_header, def_data, cond_header, cond_data, data)

    print("="*80)
    print("TOTAL:", len(out))
    print("SAMPLE 5:")
    for r in out[:5]:
        print({k: r.get(k) for k in ["보종명","유형1","유형2","유형3","보험기간","납입기간","주피보험자가입성별","주피보험자최대가입연령"]})

    # 유형3 펼쳐졌는지 확인
    type3_vals = [r.get("유형3") for r in out]
    print("-"*80)
    print("유형3 unique count:", len(set(type3_vals)))
    print("유형3 example uniques:", list(dict.fromkeys(type3_vals))[:10])
    for r in out:
        if r["보험기간"] in ("25년 만기", "30년 만기"):
            print("보험기간:", r["보험기간"])
            print("최대가입연령:", r["주피보험자최대가입연령"])
            print("납입기간:", r["납입기간"])
            break
    # 1) 년만기 + 큰 년납
    for r in out:
        if r["보험기간"] in ("25년 만기","30년 만기") and r["납입기간"] == "30년납":
            print("보험기간:", r["보험기간"], "납입기간:", r["납입기간"], "최대:", r["주피보험자최대가입연령"])
            break

    # 2) 세만기 케이스
    for r in out:
        if "세 만기" in r["보험기간"] and r["납입기간"] == "10년납":
            print("보험기간:", r["보험기간"], "납입기간:", r["납입기간"], "최대:", r["주피보험자최대가입연령"])
            break


if __name__ == "__main__":
    main()
