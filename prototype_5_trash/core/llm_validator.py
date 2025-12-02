"""
LLM-based Validator for Prototype 5

역할
------
- Task 타입별 결과를 검증하고,
- 에러/문제 원인을 사람이 읽기 쉬운 형태로 정리해서
  ReflectionPlanner가 그대로 instruction으로 쓸 수 있게 해준다.

Prototype 5에서 실제로 사용하는 Task 타입은 다음 세 가지뿐이다.

1) classify  : section_classifier
2) extract   : definition_extract_v2
3) transform : rule_cartesian / llm_cartesian

이 파일은 이 세 가지에만 집중하도록 정리되어 있다.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI


class LLMValidator:
    """
    LLM 기반 Task 결과 검증기 (Prototype 5 전용)

    - classify  : section_classifier 출력 구조 검증
    - extract   : definition_extract_v2 출력(header/data) 구조 검증
    - transform : Cartesian 결과(definitions) 품질 검증
    """

    def __init__(self) -> None:
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def validate(
        self,
        task_type: str,
        task_output: Dict[str, Any],
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Task 타입에 따라 적절한 검증 로직을 호출한다.

        Args:
            task_type: "classify" | "search" | "extract" | "transform"
            task_output: 해당 task 의 출력 데이터 (tool result.data)
            context: 이전 task 결과 등 부가 정보
        """
        if context is None:
            context = {}

        if task_type in ("search", "classify"):
            return self._validate_classify(task_output, context)
        if task_type == "extract":
            return self._validate_extract(task_output, context)
        if task_type == "transform":
            return self._validate_transform(task_output, context)

        # 그 외 타입은 현재 워크플로우에서 사용하지 않으므로 통과 처리
        return {
            "is_valid": True,
            "confidence": 1.0,
            "errors": [],
            "suggestions": [],
            "reasoning": f"Unknown task type '{task_type}' – skipped validation in Prototype 5",
        }

    # ------------------------------------------------------------------
    # 1) classify: section_classifier 전용 검증
    # ------------------------------------------------------------------
    def _validate_classify(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        section_classifier 결과 검증

        기대 형식::
            {
              "definition_core": [int, ...],
              "definition_annotation": [int, ...],
              "condition": [int, ...],
              "other": [int, ...],
              "reasoning": "..." (optional)
            }
        """
        required_keys = ["definition_core", "definition_annotation", "condition", "other"]

        # section_classifier 가 아닌 legacy search 결과라면 가볍게 통과
        if not isinstance(task_output, dict) or not all(
            key in task_output for key in required_keys
        ):
            return {
                "is_valid": True,
                "confidence": 0.9,
                "errors": [],
                "suggestions": [],
                "reasoning": "Output does not look like section_classifier result; "
                             "skipping structural validation (Prototype 5 expects classifier).",
            }

        errors: List[str] = []
        suggestions: List[str] = []

        # 각 키가 list[int] 인지 확인
        all_indices: List[int] = []
        for key in required_keys:
            value = task_output.get(key)
            if not isinstance(value, list):
                errors.append(f"'{key}' must be a list of section indices")
                continue

            non_int = [v for v in value if not isinstance(v, int)]
            if non_int:
                sample = ", ".join(str(v) for v in non_int[:5])
                errors.append(f"'{key}' contains non-integer values: {sample}")
            all_indices.extend(v for v in value if isinstance(v, int))

        # definition_core 가 비어 있으면 사실상 정의 섹션을 못 찾은 것
        definition_core = task_output.get("definition_core") or []
        if not definition_core:
            errors.append("No definition_core sections found by classifier")
            suggestions.append(
                "Classifier may have misclassified sections or the document may not "
                "contain explicit definition tables."
            )

        # 인덱스 중복 여부 확인 (한 섹션이 여러 카테고리에 들어가면 문제)
        if all_indices:
            counter = Counter(all_indices)
            duplicated = [idx for idx, cnt in counter.items() if cnt > 1]
            if duplicated:
                errors.append(
                    f"Some sections are assigned to multiple categories: {duplicated}"
                )
                suggestions.append(
                    "Ensure each section index belongs to exactly one of "
                    "definition_core / definition_annotation / condition / other."
                )

        # 인덱스 범위 체크 (context 에 sections 가 있으면)
        sections = context.get("sections") or context.get("all_sections")
        if isinstance(sections, list) and all_indices:
            max_index = max(all_indices)
            if max_index >= len(sections) or any(idx < 0 for idx in all_indices):
                errors.append(
                    "Some section indices are out of range for the current document"
                )
                suggestions.append(
                    f"Valid section indices are 0~{len(sections) - 1}, "
                    f"but got up to {max_index}."
                )

        if errors:
            return {
                "is_valid": False,
                "confidence": 0.6,
                "errors": errors,
                "suggestions": suggestions,
                "reasoning": "section_classifier output failed structural validation",
            }

        return {
            "is_valid": True,
            "confidence": 0.95,
            "errors": [],
            "suggestions": [],
            "reasoning": (
                f"section_classifier produced valid indices: "
                f"{len(definition_core)} core, "
                f"{len(task_output.get('definition_annotation') or [])} annotation, "
                f"{len(task_output.get('condition') or [])} condition, "
                f"{len(task_output.get('other') or [])} other sections"
            ),
        }

    # ------------------------------------------------------------------
    # 2) extract: definition_extract_v2 결과 검증
    # ------------------------------------------------------------------
    def _validate_extract(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        definition_extract_v2 결과 검증.

        기대 형식::
            {
              "header": [...],
              "data": [[...], ...],
              "extraction_method": "v2_classifier_based" | "...",
              "used_sections": {...}
            }
        """
        if not isinstance(task_output, dict):
            return {
                "is_valid": False,
                "confidence": 0.8,
                "errors": ["Extractor output must be a dict"],
                "suggestions": ["Check tool implementation for definition_extract_v2"],
                "reasoning": "Unexpected extractor output type",
            }

        header = task_output.get("header") or []
        data = task_output.get("data") or []

        if not header:
            return {
                "is_valid": False,
                "confidence": 0.9,
                "errors": ["Header is empty"],
                "suggestions": ["Ensure core definition sections contain a usable table"],
                "reasoning": "definition_extract_v2 returned empty header",
            }

        if not data:
            return {
                "is_valid": False,
                "confidence": 0.9,
                "errors": ["Data rows are empty"],
                "suggestions": ["Check that at least one row was extracted from core sections"],
                "reasoning": "definition_extract_v2 returned no data rows",
            }

        # 각 행이 list 이고 header 길이와 맞는지 확인
        invalid_rows: List[int] = []
        for idx, row in enumerate(data):
            if not isinstance(row, list) or len(row) != len(header):
                invalid_rows.append(idx)

        if invalid_rows:
            return {
                "is_valid": False,
                "confidence": 0.7,
                "errors": [
                    "Some rows do not match header length "
                    f"(invalid row indices: {invalid_rows})"
                ],
                "suggestions": [
                    "Ensure that every extracted row has the same number of columns "
                    "as the header."
                ],
                "reasoning": "definition_extract_v2 produced inconsistent table shape",
            }

        method = task_output.get("extraction_method", "")
        return {
            "is_valid": True,
            "confidence": 0.95 if method == "v2_classifier_based" else 0.9,
            "errors": [],
            "suggestions": [],
            "reasoning": (
                f"definition_extract_v2 produced a {len(header)}-column table "
                f"with {len(data)} rows (method='{method}')"
            ),
        }

    # ------------------------------------------------------------------
    # 3) transform: Cartesian Product 결과 검증
    # ------------------------------------------------------------------
    def _validate_transform(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Cartesian Product (rule_cartesian / llm_cartesian) 결과 검증.

        여기서는 **구조적인 품질**에 집중한다.
        - definitions 리스트가 비어 있지 않은지
        - 각 definition 이 동일한 키 집합(보종명 + 유형축들)을 갖는지
        - 중복된 (보종명 + 유형1..N) 조합이 있는지
        - total_count 와 실제 개수가 크게 어긋나지 않았는지
        """
        if not isinstance(task_output, dict):
            return {
                "is_valid": False,
                "confidence": 0.9,
                "errors": ["Transform output must be a dict"],
                "suggestions": ["Check Cartesian tool implementation"],
                "reasoning": "Unexpected transform output type",
            }

        definitions = task_output.get("definitions")
        total_count = task_output.get("total_count", 0)

        if not isinstance(definitions, list) or not definitions:
            return {
                "is_valid": False,
                "confidence": 1.0,
                "errors": ["No definitions generated"],
                "suggestions": ["Check input header/data or Cartesian tool behaviour"],
                "reasoning": "Transform result is empty",
            }

        errors: List[str] = []
        suggestions: List[str] = []

        # 기대 키 집합 추론: "보종명" + "유형1..N"
        first_def = definitions[0]
        if not isinstance(first_def, dict):
            return {
                "is_valid": False,
                "confidence": 0.8,
                "errors": ["First definition must be a dict"],
                "suggestions": ["Check Cartesian tool output schema"],
                "reasoning": "definitions[0] is not a dict",
            }

        # 보종명 필드는 필수
        if "보종명" not in first_def:
            errors.append("Key '보종명' is missing in definitions")
            suggestions.append(
                "Cartesian tool should map the product name column to '보종명'."
            )

        # 유형 축 키들 추론 ("유형1", "유형2", ...) – 헤더 길이를 참고할 수 있으면 사용
        extracted_data = context.get("extracted_data", {})
        header = extracted_data.get("header") or []

        expected_type_keys: List[str] = []
        if header and len(header) >= 2:
            # 첫 번째 컬럼은 명칭 → 나머지 컬럼 수만큼 유형 축이 있다고 가정
            expected_type_keys = [f"유형{i}" for i in range(1, len(header))]
        else:
            # 헤더 정보가 없으면 현재 definition 에 존재하는 유형 키들만 기준
            expected_type_keys = sorted(
                key for key in first_def.keys() if key.startswith("유형")
            )

        # 모든 definition 이 동일한 키들을 갖는지 확인
        missing_keys: Dict[str, List[int]] = {}
        for idx, d in enumerate(definitions):
            if not isinstance(d, dict):
                errors.append(f"Definition at index {idx} is not a dict")
                continue

            # 필수 키(보종명 + 유형축) 체크
            for key in ["보종명"] + expected_type_keys:
                if key not in d or d[key] in (None, ""):
                    missing_keys.setdefault(key, []).append(idx)

        if missing_keys:
            for key, rows in missing_keys.items():
                errors.append(f"Key '{key}' missing/empty in rows: {rows}")
            suggestions.append(
                "Ensure that every definition has '보종명' and all 유형축(유형1, 유형2, ...) filled."
            )

        # (보종명 + 유형1..N) 조합 중복 여부 확인
        if not errors and expected_type_keys:
            combo_counter: Counter = Counter()
            for d in definitions:
                if not isinstance(d, dict):
                    continue
                combo = tuple(
                    [d.get("보종명", "").strip()]
                    + [str(d.get(k, "")).strip() for k in expected_type_keys]
                )
                combo_counter[combo] += 1

            duplicated_combos = [combo for combo, cnt in combo_counter.items() if cnt > 1]
            if duplicated_combos:
                sample = [
                    {
                        "보종명": c[0],
                        **{f"유형{i+1}": c[i + 1] for i in range(len(expected_type_keys))},
                    }
                    for c in duplicated_combos[:5]
                ]
                errors.append(
                    f"Found duplicated (보종명 + 유형들) combinations: {len(duplicated_combos)}"
                )
                suggestions.append(
                    "Remove duplicated definition rows so that each combination appears only once."
                )
                suggestions.append(f"Example duplicated combinations: {json.dumps(sample, ensure_ascii=False)}")

        # total_count 와 실제 개수 비교 (심각하게 어긋날 때만 에러)
        actual_count = len(definitions)
        if not errors and isinstance(total_count, int) and total_count > 0:
            if actual_count == total_count:
                pass  # OK
            elif actual_count == 0:
                errors.append("definitions is empty while total_count is positive")
            else:
                # 허용 오차 없이 단순 불일치만 보고
                errors.append(
                    f"total_count ({total_count}) does not match actual definitions count ({actual_count})"
                )
                suggestions.append(
                    "Ensure Cartesian tool sets total_count to the number of generated combinations."
                )

        if errors:
            return {
                "is_valid": False,
                "confidence": 0.7,
                "errors": errors,
                "suggestions": suggestions,
                "reasoning": "Cartesian Product output failed structural validation",
                "actual_count": actual_count,
            }

        return {
            "is_valid": True,
            "confidence": 0.95,
            "errors": [],
            "suggestions": [],
            "reasoning": (
                f"Cartesian Product generated {actual_count} unique combinations "
                f"with keys ['보종명'] + {expected_type_keys}."
            ),
            "actual_count": actual_count,
        }

