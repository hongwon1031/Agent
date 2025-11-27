"""
Prototype Tools for Insurance Definition Extraction.

이 모듈은 정의(보종명/유형 계층)의 모든 경우의 수를 생성하기 위한
여러 종류의 Tool 들을 제공합니다.

- 단일 스텝 도구:
  - simple_split
  - column_cartesian
  - row_aware_cartesian
  - llm_cartesian

- 다단계 파이프라인 도구 (state 공유):
  - extract_definition_rows
  - normalize_definition_rows
  - enumerate_definitions
"""

from typing import Dict, Any, List
from pydantic import BaseModel
import json


class ToolResult(BaseModel):
    """Result of a single tool execution."""

    success: bool
    data: Any
    error: str = ""


class SimpleTool:
    """Base Tool Interface.

    모든 Tool 은 동일한 인터페이스를 따릅니다.

    - doc:   원본 parsed 문서 (mutate 해도 되지만, 가능한 한 읽기 전용으로 사용)
    - state: 한 번의 plan 실행 동안 공유되는 mutable dict
    - params: planner 가 결정한 tool‑specific 파라미터
    """

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:  # pragma: no cover - interface
        raise NotImplementedError


# ==================== Tool 1: Simple Split ====================
class SimpleSplitTool(SimpleTool):
    """
    매우 단순한 분리만 수행하는 baseline Tool.

    - params: {"section_index": int, "paragraph_index": int}
    - 반환: {"parsed": [...], "note": "..."} (Cartesian Product 미구현)
    """

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            section = doc[0]["elements"][params["section_index"]]
            paragraph = section["paragraphs"][params["paragraph_index"]]

            if paragraph.get("type") != "table":
                return ToolResult(success=False, data=None, error="Not a table paragraph")

            table_elements = paragraph.get("table", {}).get("table_elements", [])
            if not table_elements:
                return ToolResult(success=False, data=None, error="Empty table")

            first_row = table_elements[0]

            result = []
            for key, value in first_row.items():
                if not isinstance(value, str):
                    result.append({key: [value]})
                    continue

                if "/" in value:
                    parts = [v.strip() for v in value.split("/") if v.strip()]
                    result.append({key: parts})
                else:
                    result.append({key: [value.strip()]})

            return ToolResult(
                success=True,
                data={"parsed": result, "note": "No cartesian product applied"},
            )
        except Exception as e:  # pragma: no cover - 보호용
            return ToolResult(success=False, data=None, error=f"SimpleSplitTool error: {e}")


# ==================== Tool 2: Column-based Cartesian ====================
class ColumnCartesianTool(SimpleTool):
    """
    컬럼 기반으로 '/' 및 줄바꿈을 split 해서 Cartesian Product 생성.

    - params: {"section_index": int, "paragraph_index": int}
    - 스키마:
        - "명칭"        -> "보종명"
        - "보험종목"    -> "유형1"
        - "보험종목_1*" -> "유형2"
    - 반환: {"definitions": [{보종명, 유형1, 유형2}, ...]}
    """

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            section = doc[0]["elements"][params["section_index"]]
            paragraph = section["paragraphs"][params["paragraph_index"]]

            if paragraph.get("type") != "table":
                return ToolResult(success=False, data=None, error="Not a table paragraph")

            table_elements = paragraph.get("table", {}).get("table_elements", [])
            if not table_elements:
                return ToolResult(success=False, data=None, error="Empty table")

            all_combinations: List[Dict[str, Any]] = []

            for row in table_elements:
                schema_mapping = {"보종명": None, "유형1": None, "유형2": None}

                for key, value in row.items():
                    if not isinstance(value, str):
                        continue
                    if "명칭" in key:
                        schema_mapping["보종명"] = value
                    elif key == "보험종목":
                        schema_mapping["유형1"] = value
                    elif "보험종목_1" in key:
                        schema_mapping["유형2"] = value

                parsed: Dict[str, List[Any]] = {}

                def _split(v: str) -> List[str]:
                    v = v.replace("\n", "/")
                    return [x.strip() for x in v.split("/") if x.strip()]

                for schema_key, raw_value in schema_mapping.items():
                    if isinstance(raw_value, str) and raw_value.strip():
                        parsed[schema_key] = _split(raw_value)
                    else:
                        parsed[schema_key] = [None]

                combinations = self._cartesian_product(parsed)
                all_combinations.extend(combinations)

            if not all_combinations:
                return ToolResult(success=False, data=None, error="No combinations generated")

            return ToolResult(success=True, data={"definitions": all_combinations})
        except Exception as e:  # pragma: no cover
            return ToolResult(success=False, data=None, error=f"ColumnCartesianTool error: {e}")

    def _cartesian_product(self, parsed: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        from itertools import product

        keys = list(parsed.keys())
        values = [parsed[k] for k in keys]
        combinations: List[Dict[str, Any]] = []

        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations


# ==================== Tool 3: Row-aware Cartesian ====================
class RowAwareCartesianTool(SimpleTool):
    """
    행별로 다른 보종명/유형을 처리하면서 Cartesian Product 생성.

    - params:
        {
          "section_index": int,
          "paragraph_index": int,
          "key_mapping": {"명칭": "보종명", "보험종목": "유형1", "보험종목_1": "유형2"}  # optional
        }
    """

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            section = doc[0]["elements"][params["section_index"]]
            paragraph = section["paragraphs"][params["paragraph_index"]]

            if paragraph.get("type") != "table":
                return ToolResult(success=False, data=None, error="Not a table paragraph")

            table_elements = paragraph.get("table", {}).get("table_elements", [])
            if not table_elements:
                return ToolResult(success=False, data=None, error="Empty table")

            key_mapping = params.get(
                "key_mapping",
                {"명칭": "보종명", "보험종목": "유형1", "보험종목_1": "유형2"},
            )

            all_combinations: List[Dict[str, Any]] = []

            for row in table_elements:
                schema_data: Dict[str, List[Any]] = {}
                for raw_key, schema_key in key_mapping.items():
                    if raw_key in row and isinstance(row[raw_key], str):
                        value = row[raw_key].replace("\n", "/")
                        parts = [v.strip() for v in value.split("/") if v.strip()]
                        schema_data[schema_key] = parts

                for schema_key in ["보종명", "유형1", "유형2"]:
                    if schema_key not in schema_data:
                        schema_data[schema_key] = [None]

                combinations = self._cartesian_product(schema_data)
                all_combinations.extend(combinations)

            if not all_combinations:
                return ToolResult(success=False, data=None, error="No combinations generated")

            return ToolResult(success=True, data={"definitions": all_combinations})
        except Exception as e:  # pragma: no cover
            return ToolResult(success=False, data=None, error=f"RowAwareCartesianTool error: {e}")

    def _cartesian_product(self, parsed: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        from itertools import product

        keys = list(parsed.keys())
        values = [parsed[k] for k in keys]
        combinations: List[Dict[str, Any]] = []

        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations


# ==================== Tool 4: LLM-based Cartesian ====================
class LLMCartesianTool(SimpleTool):
    """
    LLM 을 사용해 테이블 전체에서 보종명/유형1/유형2 모든 조합을 추출.

    - params: {"section_index": int, "paragraph_index": int}
    - 반환: {"definitions": [...]}  (LLM 출력 그대로)
    """

    def __init__(self) -> None:
        from openai import OpenAI  # type: ignore
        import os
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=r"c:\\Users\\NT-165\\Desktop\\Project\\Toy\\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            section = doc[0]["elements"][params["section_index"]]
            paragraph = section["paragraphs"][params["paragraph_index"]]

            if paragraph.get("type") != "table":
                return ToolResult(success=False, data=None, error="Not a table paragraph")

            table_elements = paragraph.get("table", {}).get("table_elements", [])
            if not table_elements:
                return ToolResult(success=False, data=None, error="Empty table")

            prompt = f"""
다음 보험 정의 테이블에서 모든 보종명/유형1/유형2 조합을 추출해 주세요.

# 테이블 데이터 (JSON)
{json.dumps(table_elements, ensure_ascii=False, indent=2)}

# 규칙
1. 보종명: "명칭" 컬럼의 값을 그대로 사용 (줄바꿈 포함 가능)
2. 유형1: "보험종목" 컬럼의 값
3. 유형2: "보험종목_1" 컬럼의 값을 "/" 또는 줄바꿈 기준으로 split
4. 가능한 모든 조합에 대해 Cartesian Product 생성

# 출력 형식 (JSON)
{{
  "definitions": [
    {{"보종명": "...", "유형1": "...", "유형2": "..." }},
    ...
  ]
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                max_tokens=3000,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction expert. Extract all combinations from the table and return valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            result = json.loads(response.choices[0].message.content)

            if "definitions" not in result:
                return ToolResult(
                    success=False,
                    data=None,
                    error="LLM did not return 'definitions' key",
                )

            return ToolResult(success=True, data=result)
        except Exception as e:  # pragma: no cover
            return ToolResult(success=False, data=None, error=f"LLMCartesianTool error: {e}")


# ==================== Multi‑step helper tools (stateful) ====================
class ExtractDefinitionRowsTool(SimpleTool):
    """단계 1: 정의 섹션의 table_elements 를 state에 저장."""

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            section = doc[0]["elements"][params["section_index"]]
            paragraph = section["paragraphs"][params["paragraph_index"]]

            if paragraph.get("type") != "table":
                return ToolResult(success=False, data=None, error="Not a table paragraph")

            table_elements = paragraph.get("table", {}).get("table_elements", [])
            if not table_elements:
                return ToolResult(success=False, data=None, error="Empty table")

            return ToolResult(success=True, data={"definition_rows": table_elements})
        except Exception as e:  # pragma: no cover
            return ToolResult(
                success=False, data=None, error=f"ExtractDefinitionRowsTool error: {e}"
            )


class NormalizeDefinitionRowsTool(SimpleTool):
    """단계 2: raw definition_rows 를 보종명/유형1/유형2 리스트 구조로 정규화."""

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            rows: List[Dict[str, Any]] = state.get("definition_rows") or []
            if not rows:
                return ToolResult(
                    success=False, data=None, error="No definition_rows in state"
                )

            normalized_rows: List[Dict[str, List[Any]]] = []

            def _split(value: str) -> List[str]:
                value = value.replace("\n", "/")
                return [v.strip() for v in value.split("/") if v.strip()]

            for row in rows:
                schema_row: Dict[str, List[Any]] = {
                    "보종명": [],
                    "유형1": [],
                    "유형2": [],
                }

                raw_name = row.get("명칭") or row.get("상품명") or ""
                if isinstance(raw_name, str) and raw_name.strip():
                    schema_row["보종명"] = [raw_name.strip()]

                raw_type1 = row.get("보험종목") or ""
                raw_type2 = None
                for key in row.keys():
                    if "보험종목_1" in key:
                        raw_type2 = row[key]
                        break

                if isinstance(raw_type1, str) and raw_type1.strip():
                    schema_row["유형1"] = _split(raw_type1)
                if isinstance(raw_type2, str) and raw_type2.strip():
                    schema_row["유형2"] = _split(raw_type2)

                if not schema_row["보종명"]:
                    schema_row["보종명"] = [None]
                if not schema_row["유형1"]:
                    schema_row["유형1"] = [None]
                if not schema_row["유형2"]:
                    schema_row["유형2"] = [None]

                normalized_rows.append(schema_row)

            return ToolResult(success=True, data={"normalized_rows": normalized_rows})
        except Exception as e:  # pragma: no cover
            return ToolResult(
                success=False, data=None, error=f"NormalizeDefinitionRowsTool error: {e}"
            )


class EnumerateDefinitionsFromStateTool(SimpleTool):
    """단계 3: normalized_rows 에서 Cartesian Product 로 모든 경우의 수 출력."""

    def execute(
        self, doc: List[Dict], state: Dict[str, Any], params: Dict
    ) -> ToolResult:
        try:
            normalized_rows: List[Dict[str, List[Any]]] = state.get("normalized_rows") or []
            if not normalized_rows:
                return ToolResult(
                    success=False, data=None, error="No normalized_rows in state"
                )

            from itertools import product

            all_definitions: List[Dict[str, Any]] = []

            for row in normalized_rows:
                keys = ["보종명", "유형1", "유형2"]
                values = [row.get(k, [None]) for k in keys]
                for combo in product(*values):
                    all_definitions.append(dict(zip(keys, combo)))

            if not all_definitions:
                return ToolResult(success=False, data=None, error="No combinations generated")

            return ToolResult(success=True, data={"definitions": all_definitions})
        except Exception as e:  # pragma: no cover
            return ToolResult(
                success=False,
                data=None,
                error=f"EnumerateDefinitionsFromStateTool error: {e}",
            )


# ==================== Tool Registry ====================
TOOL_REGISTRY: Dict[str, SimpleTool] = {
    # 단일‑스텝 도구들
    "simple_split": SimpleSplitTool(),
    "column_cartesian": ColumnCartesianTool(),
    "row_aware_cartesian": RowAwareCartesianTool(),
    "llm_cartesian": LLMCartesianTool(),
    # 상태를 공유하는 다단계 파이프라인용 도구들
    "extract_definition_rows": ExtractDefinitionRowsTool(),
    "normalize_definition_rows": NormalizeDefinitionRowsTool(),
    "enumerate_definitions": EnumerateDefinitionsFromStateTool(),
}

