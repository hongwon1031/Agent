"""
Hybrid Tools: Rule-based + LLM-based

각 기능별로 Rule/LLM 버전 제공:
- Search: 정의 섹션 찾기
- Extract: 데이터 추출
- Transform: Cartesian Product 생성
"""

import json
import os
import re
from typing import Dict, Any, List, Optional
from itertools import product
from openai import OpenAI
from dotenv import load_dotenv
from core.prompt import (
    build_llm_extract_prompt,
    build_llm_merge_prompt,
    build_llm_cartesian_prompt,
    build_section_classifier_prompt)

class ToolResult:
    """도구 실행 결과"""

    def __init__(self, success: bool, data: Any = None, error: str = None, tool_name: str = ""):
        self.success = success
        self.data = data
        self.error = error
        self.tool_name = tool_name

    def to_dict(self):
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tool_name": self.tool_name
        }


# ============================================================================
# SEARCH TOOLS
# ============================================================================

class DefinitionExtractToolV2:
    """
    V2: Works with SectionClassifierTool output

    Extracts definition tables from classified sections:
    - Uses core_indices (definition_core) as primary source
    - Merges with annotation_indices (definition_annotation) if present
    - Handles both table and text-only cases
    """

    def __init__(self):
        self.name = "definition_extract_v2"
        # Initialize OpenAI client for LLM helper
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _rule_extract_helper(self, content: Dict, content_type: str) -> tuple:
        """
        Private helper for rule-based extraction (replaces RuleExtractTool)

        Args:
            content: Table object or text string
            content_type: "table" or "text"

        Returns:
            (header, rows, extraction_method) or ([], [], "") on failure
        """
        try:
            if content_type == "text":
                return self._extract_from_text_helper(content)
            else:  # "table"
                return self._extract_from_table_helper(content)
        except Exception:
            return [], [], ""

    def _extract_from_table_helper(self, content: Dict) -> tuple:
        """Extract data from table (helper for _rule_extract_helper)"""
        try:
            table_elements = content.get("table_elements", [])
            if not table_elements:
                return [], [], ""

            # Dict format (already parsed)
            if isinstance(table_elements[0], dict) and "cells" not in table_elements[0]:
                header = list(table_elements[0].keys())
                data = []
                for row in table_elements:
                    data.append([str(row.get(col, "")) for col in header])
                return header, data, "table_parsing"

            # Cells format
            else:
                rows = []
                for row in table_elements:
                    cells = row.get("cells", [])
                    if not cells:
                        continue

                    # Filter annotation rows
                    first_cell = cells[0].get("text", "").strip()
                    if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                        continue

                    row_data = [cell.get("text", "").strip() for cell in cells]
                    rows.append(row_data)

                if len(rows) < 2:
                    return [], [], ""

                header = rows[0]
                data = rows[1:]
                return header, data, "table_parsing"

        except Exception:
            return [], [], ""

    def _extract_from_text_helper(self, text_content: str) -> tuple:
        """Extract data from text (helper for _rule_extract_helper)"""
        try:
            lines = text_content.split("\n")
            groups = []
            current_group = None

            for line in lines:
                line = line.strip()
                if not line or line.startswith("※") or line.startswith("주"):
                    continue

                # Group header (1), 2), ...)
                if re.match(r"^\d+\)", line):
                    group_name = line.split(")", 1)[1].strip()
                    current_group = {"name": group_name, "items": []}
                    groups.append(current_group)
                # Items (-, *, •)
                elif current_group and re.match(r"^[-*•]\s+", line):
                    item = re.sub(r"^[-*•]\s+", "", line).strip()
                    current_group["items"].append(item)

            if not groups:
                return [], [], ""

            header = ["보종명"]
            max_items = max(len(g["items"]) for g in groups) if groups else 0
            if max_items > 0:
                header.append("유형1")

            data = []
            for group in groups:
                if group["items"]:
                    row = [group["name"], "/".join(group["items"])]
                else:
                    row = [group["name"]]
                data.append(row)

            return header, data, "text_parsing"

        except Exception:
            return [], [], ""

    def _llm_extract_helper(self, content: Any, content_type: str, instruction: str = "") -> tuple:
        """
        Private helper for LLM-based extraction (replaces LLMExtractTool)

        Args:
            content: Content to extract from
            content_type: "table", "text", or "mixed"
            instruction: Additional extraction instruction

        Returns:
            (header, rows, notes) or ([], [], "") on failure
        """
        try:
            # Convert content to string
            if isinstance(content, str):
                content_str = content
            else:
                content_str = json.dumps(content, ensure_ascii=False)

            prompt = build_llm_extract_prompt(content_str, content_type, instruction)

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=3000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("header") or not result.get("data"):
                return [], [], ""

            return result["header"], result["data"], result.get("notes", "")

        except Exception:
            return [], [], ""

    def _llm_merge_helper(self, content: Any, instruction: str = "") -> tuple:
        """
        Private helper for LLM-based merging of table and annotations.
        """
        try:
            content_str = json.dumps(content, ensure_ascii=False)

            
            prompt = build_llm_merge_prompt(content_str, instruction)

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=3000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("header") or not result.get("data"):
                return [], [], ""

            return result["header"], result["data"], result.get("notes", "")

        except Exception:
            return [], [], ""

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Extract definition table from classified sections

        Args:
            params:
                sections: list[dict] - All sections
                core_indices: list[int] - Indices of definition_core sections
                annotation_indices: list[int] - Indices of definition_annotation sections (optional)
                instruction: str (optional) - Additional instruction for extraction

        Returns:
            ToolResult with data:
                {
                    "header": list[str],
                    "data": list[list[str]],
                    "extraction_method": str
                }
        """
        try:
            sections = params.get("sections", [])
            core_indices = params.get("core_indices", [])
            annotation_indices = params.get("annotation_indices", [])
            instruction = params.get("instruction", "")

            if not sections:
                return ToolResult(
                    success=False,
                    error="No sections provided",
                    tool_name=self.name
                )

            if not core_indices:
                return ToolResult(
                    success=False,
                    error="No core_indices provided - classification may have failed",
                    tool_name=self.name
                )

            # Step 1: Extract base table from core sections
            header, rows = self._extract_from_cores(sections, core_indices, doc, instruction)

            if not header and not rows:
                return ToolResult(
                    success=False,
                    error="Failed to extract base table from core sections",
                    tool_name=self.name
                )

            # Step 2: If annotations exist, merge them
            merge_indices = sorted(set(annotation_indices + core_indices))
            if merge_indices:
                header, rows = self._merge_with_annotations(
                    sections, merge_indices, header, rows, doc, instruction
                )

            return ToolResult(
                success=True,
                data={
                    "header": header,
                    "data": rows,
                    "extraction_method": "v2_classifier_based"
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"DefinitionExtractToolV2 error: {str(e)}",
                tool_name=self.name
            )

    def _extract_from_cores(
        self, sections: List[Dict], core_indices: List[int], doc: Any, instruction: str = ""
    ) -> tuple[List[str], List[List[str]]]:
        """
        Extract base table from core sections

        Args:
            instruction: Additional instruction for extraction

        Returns:
            (header, rows)
        """
        # Try each core section until we get a valid table
        for idx in core_indices:
            if idx < 0 or idx >= len(sections):
                continue

            section = sections[idx]
            content = section.get("content", [])

            # Look for table in content
            for item in content:
                if not isinstance(item, dict):
                    continue

                if "table" in item:
                    table = item["table"]

                    # Try rule-based extraction first (using private helper)
                    header, rows, _ = self._rule_extract_helper(table, "table")
                    if header and rows:
                        return header, rows

        # If no table found, try text-based extraction
        text_fragments = []
        for idx in core_indices:
            if idx < 0 or idx >= len(sections):
                continue

            section = sections[idx]
            content = section.get("content", [])

            for item in content:
                if isinstance(item, dict):
                    text = item.get("content", "") or item.get("text", "")
                    if text and isinstance(text, str):
                        text_fragments.append(text.strip())
                elif isinstance(item, str):
                    text_fragments.append(item.strip())

        if text_fragments:
            combined = "\n\n".join(text_fragments)

            # Use private LLM helper
            header, rows, _ = self._llm_extract_helper(combined, "text", instruction)
            if header and rows:
                return header, rows

        return [], []

    def _merge_with_annotations(
        self,
        sections: List[Dict],
        annotation_indices: List[int],
        base_header: List[str],
        base_rows: List[List[str]],
        doc: Any,
        instruction: str = ""
    ) -> tuple[List[str], List[List[str]]]:
        """
        Merge annotation text with base table using LLM

        Args:
            instruction: Additional instruction for merging

        Returns:
            (merged_header, merged_rows)
        """
        # Collect annotation texts
        annotation_texts = []
        for idx in annotation_indices:
            if idx < 0 or idx >= len(sections):
                continue

            section = sections[idx]
            content = section.get("content", [])

            for item in content:
                if isinstance(item, dict):
                    text = item.get("content", "") or item.get("text", "")
                    if text and isinstance(text, str):
                        annotation_texts.append(text.strip())
                elif isinstance(item, str):
                    annotation_texts.append(item.strip())

        if not annotation_texts:
            return base_header, base_rows

        # Use LLM to merge
        combined_content = {
            "base_table": {
                "header": base_header,
                "data": base_rows
            },
            "annotations": "\n\n".join(annotation_texts)
        }

        # Use the new merge helper
        merged_header, merged_rows, _ = self._llm_merge_helper(
            combined_content,
            instruction
        )

        if merged_header and merged_rows:
            return merged_header, merged_rows

        # Fallback to base if LLM merge fails
        return base_header, base_rows


class RuleCartesianTool:
    """
    Rule-based Cartesian Product: 수학적으로 정확한 조합 생성

    장점: 빠르고 정확
    단점: 컬럼명 매핑 못함
    """

    def __init__(self):
        self.name = "rule_cartesian"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Cartesian Product 생성

        Args:
            doc: 문서
            params: {"header": [...], "data": [[...], ...]}

        Returns:
            ToolResult with data = {
                "definitions": [...],
                "total_count": int
            }
        """
        try:
            header = params.get("header", [])
            data = params.get("data", [])

            if not header or not data:
                return ToolResult(
                    success=False,
                    error="Header or data is empty",
                    tool_name=self.name
                )

            definitions = []

            for row in data:
                # 각 셀을 슬래시(/) 또는 쉼표(,)로 분리
                options = []
                for cell in row:
                    cell_clean = cell.replace('\n', '').strip()
                    # 먼저 슬래시로 분리
                    slash_parts = cell_clean.split('/')
                    # 각 슬래시 part를 다시 쉼표로 분리
                    values = []
                    for part in slash_parts:
                        comma_parts = [v.strip() for v in part.split(',') if v.strip()]
                        values.extend(comma_parts)
                    options.append(values)

                # 조합 생성
                for combo in product(*options):
                    definition = {}

                    type_counter = 1  # 유형 번호 카운터 (첫 컬럼 제외)
                    for i, col_name in enumerate(header):
                        if i == 0 or "명칭" in col_name:
                            # 첫 번째 컬럼 또는 "명칭"이 포함된 컬럼은 보종명
                            definition["보종명"] = combo[i]
                        else:
                            # 나머지는 순서대로 유형1, 유형2, ...
                            definition[f"유형{type_counter}"] = combo[i]
                            type_counter += 1
                    definitions.append(definition)

            return ToolResult(
                success=True,
                data={
                    "definitions": definitions,
                    "total_count": len(definitions)
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"RuleCartesianTool error: {str(e)}",
                tool_name=self.name
            )


class LLMCartesianTool:
    """
    LLM-based Cartesian: 컬럼명 지능적 매핑 포함

    장점: 컬럼명 자동 매핑
    단점: 느리고 비쌈
    """

    def __init__(self):
        self.name = "llm_cartesian"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        LLM으로 값 분리 + Python으로 Cartesian product 생성

        Step 1 (LLM): 각 셀의 값을 의미적으로 분리하여 리스트로 변환
        Step 2 (Python): itertools.product로 정확한 Cartesian product 생성

        Args:
            doc: 문서
            params: {"header": [...], "data": [[...], ...]}

        Returns:
            ToolResult
        """
        try:
            header = params.get("header", [])
            data = params.get("data", [])
            instruction = params.get("instruction", "").strip()

            if not header or not data:
                return ToolResult(
                    success=False,
                    error="Header or data is empty",
                    tool_name=self.name
                )

            # Step 1: LLM으로 값 분리
            
            prompt = build_llm_cartesian_prompt(header, data, instruction)

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )

            llm_result = json.loads(response.choices[0].message.content)

            if not llm_result.get("parsed_rows"):
                return ToolResult(
                    success=False,
                    error="LLM failed to parse values",
                    tool_name=self.name
                )

            # Step 2: Python으로 Cartesian product 생성
            from itertools import product

            parsed_rows = llm_result["parsed_rows"]
            all_definitions = []

            for row in parsed_rows:
                # row = [["보종명"], ["유형값"], ["옵션1", "옵션2"], ["암1", "암2", ...]]
                # 각 셀이 옵션 리스트를 가지고 있음
                # Cartesian product로 모든 조합 생성

                if not row:
                    continue

                # Cartesian product 생성
                for combo in product(*row):
                    definition = {"보종명": combo[0]}
                    for i, value in enumerate(combo[1:], start=1):
                        definition[f"유형{i}"] = value
                    all_definitions.append(definition)

            return ToolResult(
                success=True,
                data={
                    "definitions": all_definitions,
                    "total_count": len(all_definitions),
                    "notes": f"LLM parsing + Python Cartesian. {llm_result.get('notes', '')}"
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"LLMCartesianTool error: {str(e)}",
                tool_name=self.name
            )


class SectionClassifierTool:
    """
    LLM-based multi-class section classifier

    Performs 4-way classification of ALL sections:
    - definition_core: Core definition tables (보험종목, 명칭 등)
    - definition_annotation: Text annotations/explanations for definitions
    - condition: Condition tables (가입조건, 계약조건 등)
    - other: Unrelated sections

    This ensures 100% recall - no sections are missed.
    """

    def __init__(self):
        self.name = "section_classifier"
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Classify all sections into 4 categories

        Args:
            params:
                sections: list[dict] - All sections from DocumentAccessor
                instruction: str (optional) - Additional instruction for classification

        Returns:
            ToolResult with data:
                {
                    "definition_core": [int] - Section indices,
                    "definition_annotation": [int] - Section indices,
                    "condition": [int] - Section indices,
                    "other": [int] - Section indices
                }
        """
        try:
            sections = params.get("sections", [])
            instruction = params.get("instruction", "")

            if not sections:
                return ToolResult(
                    success=False,
                    error="No sections provided",
                    tool_name=self.name
                )

            # Step 1: Create section summaries
            summaries = []
            for section in sections:
                summary = {
                    "index": section.get("index"),
                    "title": section.get("title", ""),
                    "preview": self._get_preview(section),
                    "has_table": self._has_table(section),
                    "has_text": self._has_text(section)
                }
                summaries.append(summary)

            # Step 2: Build classification prompt
            prompt = self._build_classification_prompt(summaries, instruction)

            # Step 3: Call LLM
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )

            result = json.loads(response.choices[0].message.content)

            # Step 4: Validate structure
            required_keys = ["definition_core", "definition_annotation", "condition", "other"]
            for key in required_keys:
                if key not in result:
                    return ToolResult(
                        success=False,
                        error=f"LLM response missing key: {key}",
                        tool_name=self.name
                    )
                if not isinstance(result[key], list):
                    return ToolResult(
                        success=False,
                        error=f"Invalid type for {key}: expected list, got {type(result[key])}",
                        tool_name=self.name
                    )

            # Step 5: Return classification
            return ToolResult(
                success=True,
                data={
                    "definition_core": result["definition_core"],
                    "definition_annotation": result["definition_annotation"],
                    "condition": result["condition"],
                    "other": result["other"],
                    "reasoning": result.get("reasoning", "")
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"SectionClassifierTool error: {str(e)}",
                tool_name=self.name
            )

    def _get_preview(self, section: Dict, max_chars: int = 300) -> str:
        """
        Extract content preview from section

        Args:
            section: Section dict from DocumentAccessor
            max_chars: Maximum characters to preview

        Returns:
            str: Preview text
        """
        content = section.get("content", [])

        if not content:
            return ""

        # Collect text from content items
        texts = []
        for item in content[:3]:  # Only first 3 items
            if isinstance(item, dict):
                if "table" in item:
                    # Table preview: show headers + first row
                    table = item["table"]
                    if isinstance(table, dict):
                        headers = table.get("header", [])
                        data = table.get("data", [])
                        if headers:
                            texts.append(f"[Table: {', '.join(headers[:3])}")
                            if data:
                                texts.append(f" | {', '.join(str(x) for x in data[0][:3])}]")
                            else:
                                texts.append("]")
                elif "text" in item:
                    texts.append(str(item["text"]))
            elif isinstance(item, str):
                texts.append(item)

        preview = " ".join(texts)

        if len(preview) > max_chars:
            return preview[:max_chars] + "..."

        return preview

    def _has_table(self, section: Dict) -> bool:
        """Check if section contains table"""
        content = section.get("content", [])
        for item in content:
            if isinstance(item, dict) and "table" in item:
                return True
        return False

    def _has_text(self, section: Dict) -> bool:
        """Check if section contains text"""
        content = section.get("content", [])
        for item in content:
            if isinstance(item, dict) and "text" in item:
                return True
            elif isinstance(item, str):
                return True
        return False

    def _build_classification_prompt(self, summaries: List[Dict], instruction: str = "") -> str:
        """
        Build LLM prompt for section classification

        Args:
            summaries: List of section summaries
            instruction: Additional instruction for classification (optional)

        Returns:
            str: Classification prompt
        """
        
        return build_section_classifier_prompt(summaries, instruction)


# ============================================================================
# NEW: CONDITION TOOLS
# ============================================================================

class ConditionExtractTool:
    """
    Extract condition table from classified condition sections

    Similar to DefinitionExtractToolV2 but specialized for condition tables:
    - Extracts from condition sections (not definition)
    - Normalizes column names (보험료 납입기간 → 납입기간)
    - Handles split columns (가입나이 → 가입나이_남, 가입나이_여)
    """

    def __init__(self):
        self.name = "condition_extract"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Extract condition table from classified sections

        Args:
            params:
                sections: list[dict] - All sections
                condition_indices: list[int] - Indices of condition sections
                instruction: str (optional) - Additional instruction

        Returns:
            ToolResult with data:
                {
                    "header": list[str],
                    "data": list[list[str]],
                    "extraction_method": str
                }
        """
        try:
            sections = params.get("sections", [])
            condition_indices = params.get("condition_indices", [])
            instruction = params.get("instruction", "")

            if not sections:
                return ToolResult(
                    success=False,
                    error="No sections provided",
                    tool_name=self.name
                )

            # If no condition sections, return empty (not an error)
            if not condition_indices:
                return ToolResult(
                    success=True,
                    data={
                        "header": [],
                        "data": [],
                        "extraction_method": "no_condition_sections"
                    },
                    tool_name=self.name
                )

            # Extract condition table
            header, rows = self._extract_from_condition_sections(
                sections, condition_indices, instruction
            )

            if not header or not rows:
                return ToolResult(
                    success=True,
                    data={
                        "header": [],
                        "data": [],
                        "extraction_method": "extraction_failed"
                    },
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "header": header,
                    "data": rows,
                    "extraction_method": "rule_based"
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"ConditionExtractTool error: {str(e)}",
                tool_name=self.name
            )

    def _extract_from_condition_sections(
        self, sections: List[Dict], condition_indices: List[int], instruction: str = ""
    ) -> tuple[List[str], List[List[str]]]:
        """
        Extract condition table from condition sections

        Returns:
            (header, rows)
        """
        # Try each condition section
        for idx in condition_indices:
            if idx < 0 or idx >= len(sections):
                continue

            section = sections[idx]
            content = section.get("content", [])

            # Look for table in content
            for item in content:
                if not isinstance(item, dict):
                    continue

                if "table" in item:
                    table = item["table"]

                    # Try rule-based extraction
                    header, rows = self._parse_condition_table(table)
                    if header and rows:
                        # Normalize column names
                        header = self._normalize_condition_headers(header)
                        return header, rows

        return [], []

    def _parse_condition_table(self, table: Dict) -> tuple[List[str], List[List[str]]]:
        """
        Parse condition table (reuse DefinitionExtractV2 logic)
        """
        try:
            table_elements = table.get("table_elements", [])
            if not table_elements:
                return [], []

            # Dict format
            if isinstance(table_elements[0], dict) and "cells" not in table_elements[0]:
                header = list(table_elements[0].keys())
                data = []
                for row in table_elements:
                    data.append([str(row.get(col, "")) for col in header])
                return header, data

            # Cells format
            else:
                rows = []
                for row in table_elements:
                    cells = row.get("cells", [])
                    if not cells:
                        continue

                    # Filter annotation rows
                    first_cell = cells[0].get("text", "").strip()
                    if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                        continue

                    row_data = [cell.get("text", "").strip() for cell in cells]
                    rows.append(row_data)

                if len(rows) < 2:
                    return [], []

                header = rows[0]
                data = rows[1:]
                return header, data

        except Exception:
            return [], []

    def _normalize_condition_headers(self, headers: List[str]) -> List[str]:
        """
        Normalize condition column names

        Mapping:
        - "보험기간" → "보험기간"
        - "보험료 납입기간" → "납입기간"
        - "가입나이" / "남자나이" / "여자나이" → "가입나이_남", "가입나이_여"
        - "보험료 납입주기" → "납입주기"
        - "유형1", "유형2" → keep as is (JOIN keys)
        """
        normalized = []

        for h in headers:
            h_clean = h.strip().replace("\n", "").replace(" ", "")

            # JOIN KEY columns - keep as is
            if h_clean in ["유형1", "유형2", "심사형", "보장형"]:
                normalized.append(h_clean)

            # Condition columns - normalize
            elif "보험기간" in h_clean:
                normalized.append("보험기간")
            elif "납입기간" in h_clean or "보험료납입기간" in h_clean:
                normalized.append("납입기간")
            elif "남자나이" in h_clean or "남자" in h_clean and "나이" in h_clean:
                normalized.append("가입나이_남")
            elif "여자나이" in h_clean or "여자" in h_clean and "나이" in h_clean:
                normalized.append("가입나이_여")
            elif "납입주기" in h_clean or "보험료납입주기" in h_clean:
                normalized.append("납입주기")
            else:
                # Unknown column - keep as is
                normalized.append(h)

        return normalized


class DefinitionConditionMergeTool:
    """
    Merge Definition combinations with Condition combinations (LEFT JOIN)

    JOIN strategy:
    - JOIN KEY: 유형1 + 유형2 (auto-detected)
    - JOIN TYPE: LEFT JOIN (Definition is primary)
    - Wildcard: 유형2 = "-" matches all Definitions
    """

    def __init__(self):
        self.name = "definition_condition_merge"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Merge Definition and Condition combinations

        Args:
            params:
                definitions: list[dict] - Definition Cartesian result
                condition_definitions: list[dict] - Condition Cartesian result
                instruction: str (optional)

        Returns:
            ToolResult with data:
                {
                    "definitions": list[dict] - Merged combinations,
                    "total_count": int,
                    "join_stats": dict
                }
        """
        try:
            definitions = params.get("definitions", [])
            condition_definitions = params.get("condition_definitions", [])

            # If no condition data, return definitions as is
            if not condition_definitions:
                return ToolResult(
                    success=True,
                    data={
                        "definitions": definitions,
                        "total_count": len(definitions),
                        "join_stats": {"skipped": "no_condition_data"}
                    },
                    tool_name=self.name
                )

            if not definitions:
                return ToolResult(
                    success=False,
                    error="No definitions provided",
                    tool_name=self.name
                )

            # Step 1: Determine JOIN keys
            join_keys = self._determine_join_keys(definitions, condition_definitions)

            # Step 2: Build condition lookup dict
            condition_lookup = self._build_condition_lookup(
                condition_definitions, join_keys
            )

            # Step 3: LEFT JOIN
            merged = self._perform_left_join(
                definitions, condition_lookup, join_keys
            )

            # Step 4: Calculate stats
            stats = self._calculate_join_stats(definitions, condition_definitions, merged)

            return ToolResult(
                success=True,
                data={
                    "definitions": merged,
                    "total_count": len(merged),
                    "join_stats": stats
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"DefinitionConditionMergeTool error: {str(e)}",
                tool_name=self.name
            )

    def _determine_join_keys(
        self, definitions: List[Dict], conditions: List[Dict]
    ) -> List[str]:
        """
        Auto-detect JOIN keys

        Strategy:
        - Find common keys between definitions and conditions
        - Prioritize type-related keys (유형1, 유형2, etc.)

        Returns:
            list of join key names (e.g., ["유형1", "유형2"])
        """
        if not definitions or not conditions:
            return []

        def_keys = set(definitions[0].keys())
        cond_keys = set(conditions[0].keys())

        # Find common keys
        common_keys = def_keys & cond_keys

        # Filter for type-related keys
        type_keys = [k for k in common_keys if "유형" in k or "형" in k]

        # Prioritize: 유형1 > 유형2 > others
        priority = ["유형1", "유형2", "심사형", "보장형"]
        join_keys = [k for k in priority if k in type_keys]

        # Add remaining type keys
        join_keys.extend([k for k in type_keys if k not in join_keys])

        return join_keys[:2]  # Max 2 keys

    def _build_condition_lookup(
        self, conditions: List[Dict], join_keys: List[str]
    ) -> Dict[tuple, Dict]:
        """
        Build condition lookup dict for fast JOIN

        Returns:
            {
                (유형1값, 유형2값): {보험기간: ..., 납입기간: ...},
                ("-", "-"): {wildcard condition},
                ...
            }
        """
        lookup = {}

        # Condition columns (exclude JOIN keys)
        cond_cols = set(conditions[0].keys()) - set(join_keys) if conditions else set()

        for cond in conditions:
            # Extract JOIN key values
            key = tuple(cond.get(k, "") for k in join_keys)

            # Extract condition values
            cond_values = {k: cond.get(k, "") for k in cond_cols}

            lookup[key] = cond_values

        return lookup

    def _perform_left_join(
        self, definitions: List[Dict], condition_lookup: Dict[tuple, Dict], join_keys: List[str]
    ) -> List[Dict]:
        """
        LEFT JOIN definitions with conditions

        Strategy:
        1. For each definition:
           a. Extract JOIN key values
           b. Lookup condition (exact match)
           c. If not found, try wildcard (all keys = "-")
           d. If still not found, fill with NULL
        2. Merge definition + condition
        """
        merged = []
        wildcard_key = tuple("-" for _ in join_keys)

        for defn in definitions:
            # Extract JOIN key values
            key = tuple(defn.get(k, "") for k in join_keys)

            # Lookup condition (exact match)
            cond = condition_lookup.get(key)

            # Wildcard fallback
            if cond is None and wildcard_key in condition_lookup:
                cond = condition_lookup[wildcard_key]

            # Merge
            if cond:
                merged_item = {**defn, **cond}
            else:
                # No match - fill with NULL
                merged_item = defn.copy()
                # Add NULL for condition columns
                if condition_lookup:
                    sample_cond = next(iter(condition_lookup.values()))
                    for col in sample_cond.keys():
                        merged_item.setdefault(col, None)

            merged.append(merged_item)

        return merged

    def _calculate_join_stats(
        self, definitions: List[Dict], conditions: List[Dict], merged: List[Dict]
    ) -> Dict:
        """
        Calculate JOIN statistics
        """
        unmatched = len([m for m in merged if any(v is None for v in m.values())])

        return {
            "definition_count": len(definitions),
            "condition_count": len(conditions),
            "merged_count": len(merged),
            "unmatched_definitions": unmatched
        }
