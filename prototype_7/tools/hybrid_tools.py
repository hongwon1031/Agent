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
    build_section_classifier_prompt,
    build_intelligent_condition_extract_prompt, # NEW IMPORT
    build_grouping_extraction_prompt, # NEW IMPORT for grouping logic
)

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
            print(f'❗result : {result}')
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

            if not isinstance(sections, list) or not sections:
                return ToolResult(
                    success=False,
                    error=f"No sections provided or wrong type (expected list, got {type(sections).__name__})",
                    tool_name=self.name
                )
            if not all(isinstance(section, dict) for section in sections):
                return ToolResult(
                    success=False,
                    error="Sections must be a list of dict objects",
                    tool_name=self.name
                )

            if isinstance(core_indices, str):
                return ToolResult(
                    success=False,
                    error="core_indices not resolved (string received, template likely unresolved)",
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
            params: {"header": [...], "data": [[...], ...]},

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
            params: {"header": [...], "data": [[...], ...]},

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

            if not isinstance(sections, list) or not sections:
                return ToolResult(
                    success=False,
                    error=f"No sections provided or wrong type (expected list, got {type(sections).__name__})",
                    tool_name=self.name
                )

            if not all(isinstance(section, dict) for section in sections):
                return ToolResult(
                    success=False,
                    error="Sections must be a list of dict objects",
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

class IntelligentConditionExtractTool:
    """
    Extracts and enriches the insurable condition table from classified sections using an LLM.

    - Identifies the specific "insurable conditions" table.
    - Ignores "uninsurable conditions" tables.
    - Analyzes preceding titles to extract hierarchical context (e.g., "Rider", "Non-cancellable type").
    - Adds the hierarchical context as new columns to the table.
    - Normalizes column names.
    """

    def __init__(self):
        self.name = "intelligent_condition_extract"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Extracts and enriches the insurable condition table using an LLM.

        Args:
            params:
                sections: list[dict] - All sections from DocumentAccessor.
                condition_indices: list[int] - Indices of sections classified as 'condition'.
                instruction: str (optional) - Additional instruction for the LLM.

        Returns:
            ToolResult with the enriched header and data.
        """
        try:
            all_sections = params.get("sections", [])
            condition_indices = params.get("condition_indices", [])
            instruction = params.get("instruction", "")

            if not all_sections:
                return ToolResult(success=False, error="No sections provided", tool_name=self.name)

            if not condition_indices:
                return ToolResult(
                    success=True,
                    data={"header": [], "data": [], "reasoning": "No condition sections found."},
                    tool_name=self.name
                )

            # Filter for condition sections
            condition_sections = [s for s in all_sections if s.get("index") in condition_indices]

            if not condition_sections:
                 return ToolResult(
                    success=True,
                    data={"header": [], "data": [], "reasoning": "Condition indices provided, but no matching sections found."}, 
                    tool_name=self.name
                )

            # Build the prompt for the LLM
            prompt = build_intelligent_condition_extract_prompt(
                condition_sections=condition_sections,
                instruction=instruction
            )

            # Call the LLM
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4095
            )

            result_data = json.loads(response.choices[0].message.content)

            # Basic validation of the LLM response
            if "header" not in result_data or "data" not in result_data:
                return ToolResult(
                    success=False,
                    error="LLM response is missing required keys: 'header' or 'data'.",
                    tool_name=self.name
                )
            
            return ToolResult(
                success=True,
                data=result_data,
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"IntelligentConditionExtractTool error: {str(e)}",
                tool_name=self.name
            )


# class DefinitionConditionMergeTool:
#     """
#     LLM-based Intelligent Merge Tool.
#     Merges definition combinations with raw condition data using flexible,
#     semantic matching powered by an LLM.
#     """

#     def __init__(self):
#         self.name = "definition_condition_merge"
#         load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
#         self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

#     def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
#         """
#         Merges definition combinations with raw condition data using an LLM.

#         Args:
#             params:
#                 definitions: list[dict] - Expanded definition combinations.
#                 condition_header: list[str] - Header of the raw condition table.
#                 condition_data: list[list[str]] - Data of the raw condition table.
#                 instruction: str (optional) - Additional instruction for the merge.

#         Returns:
#             ToolResult with data from the LLM, including the merged definitions
#             and join statistics.
#         """
#         try:
#             definitions = params.get("definitions", [])
#             condition_header = params.get("condition_header", [])
#             condition_data = params.get("condition_data", [])
#             instruction = params.get("instruction", "")

#             if not definitions:
#                 return ToolResult(
#                     success=False, error="No definitions provided", tool_name=self.name
#                 )
            
#             # If no condition data, return definitions as is.
#             if not condition_header or not condition_data:
#                 return ToolResult(
#                     success=True,
#                     data={
#                         "definitions": definitions,
#                         "total_count": len(definitions),
#                         "join_stats": {"status": "skipped", "reason": "no_condition_data"}
#                     },
#                     tool_name=self.name
#                 )

#             # Build the intelligent merge prompt
#             prompt = build_llm_intelligent_merge_prompt(
#                 definitions=definitions,
#                 condition_header=condition_header,
#                 condition_data=condition_data,
#                 instruction=instruction,
#             )

#             # Call the LLM
#             response = self.client.chat.completions.create(
#                 model="gpt-4o",
#                 messages=[{"role": "user", "content": prompt}],
#                 response_format={"type": "json_object"},
#                 temperature=0,
#                 max_tokens=12000
#             )
#             raw = response.choices[0].message.content
#             print("=== MERGE RAW RESPONSE ===")
#             print(raw)
#             result_data = json.loads(response.choices[0].message.content)

#             # Basic validation of the LLM response
#             if "definitions" not in result_data or "join_stats" not in result_data:
#                 return ToolResult(
#                     success=False,
#                     error="LLM response is missing required keys: 'definitions' or 'join_stats'.",
#                     tool_name=self.name
#                 )

#             return ToolResult(
#                 success=True,
#                 data=result_data,
#                 tool_name=self.name
#             )

#         except Exception as e:
#             return ToolResult(
#                 success=False,
#                 error=f"DefinitionConditionMergeTool error: {str(e)}",
#                 tool_name=self.name
#             )


# ================================================================================================
# NEW: Grouping-based Combination Generation Tools
# ================================================================================================

class GroupingLogicExtractorTool:
    """
    LLM 기반 그룹핑 로직 추출 도구

    Definition과 Condition 원시 테이블을 분석하여 매칭 그룹을 추출합니다.
    LLM은 "어떤 Definition들이 어떤 Condition과 매칭되는지" 논리만 출력하며,
    실제 조합 생성은 CombinationGeneratorTool이 담당합니다.

    장점:
    - LLM 출력이 그룹 수에만 비례 (보통 5~20개) → 트렁케이션 불가능
    - Fuzzy matching, wildcard 처리 등 복잡한 논리를 LLM이 처리
    - 전체 구조를 한눈에 파악하여 일관된 그룹핑
    """

    def __init__(self):
        self.name = "grouping_logic_extractor"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Definition-Condition 매칭 그룹 추출

        Args:
            params:
                definition_header: list[str] - Definition 테이블 헤더
                definition_data: list[list[str]] - Definition 테이블 데이터
                condition_header: list[str] - Condition 테이블 헤더
                condition_data: list[list[str]] - Condition 테이블 데이터
                instruction: str (optional) - 추가 지시사항

        Returns:
            ToolResult with grouping logic data:
            {
                "column_mapping": {
                    "join_keys": ["유형1", "유형2"],
                    "value_columns": ["보험기간", "납입기간", ...]
                },
                "groups": [
                    {
                        "id": 0,
                        "match_condition": {"유형1": "일반형", ...},
                        "definition_indices": [0, 3, 7],
                        "condition_index": 0,
                        "fuzzy_matches": {...},
                        "reasoning": "..."
                    }
                ],
                "unmatched": {
                    "definition_indices": [...],
                    "condition_indices": [...]
                },
                "summary": {...}
            }
        """
        try:
            definition_header = params.get("definition_header", [])
            definition_data = params.get("definition_data", [])
            condition_header = params.get("condition_header", [])
            condition_data = params.get("condition_data", [])
            instruction = params.get("instruction", "")

            if not definition_header or not definition_data:
                return ToolResult(
                    success=False,
                    error="No definition data provided",
                    tool_name=self.name
                )

            if not condition_header or not condition_data:
                return ToolResult(
                    success=False,
                    error="No condition data provided",
                    tool_name=self.name
                )

            print(f"\n[GROUPING] Extracting grouping logic...")
            print(f"  - Definitions: {len(definition_data)} rows")
            print(f"  - Conditions: {len(condition_data)} rows")

            # Build prompt
            prompt = build_grouping_extraction_prompt(
                definition_header=definition_header,
                definition_data=definition_data,
                condition_header=condition_header,
                condition_data=condition_data,
                instruction=instruction
            )

            # Call LLM
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000  # 그룹 수만큼만 출력되므로 충분
            )

            raw = response.choices[0].message.content
            print("=== GROUPING RAW RESPONSE ===")
            print(raw[:500] + "..." if len(raw) > 500 else raw)

            grouping_logic = json.loads(raw)

            # Validation
            if "groups" not in grouping_logic:
                return ToolResult(
                    success=False,
                    error="LLM response missing 'groups' key",
                    tool_name=self.name
                )

            if "column_mapping" not in grouping_logic:
                return ToolResult(
                    success=False,
                    error="LLM response missing 'column_mapping' key",
                    tool_name=self.name
                )

            # Basic range validation
            for group in grouping_logic.get("groups", []):
                for def_idx in group.get("definition_indices", []):
                    if def_idx < 0 or def_idx >= len(definition_data):
                        return ToolResult(
                            success=False,
                            error=f"Invalid definition_index {def_idx} (out of range 0-{len(definition_data)-1})",
                            tool_name=self.name
                        )

                cond_idx = group.get("condition_index")
                if cond_idx < 0 or cond_idx >= len(condition_data):
                    return ToolResult(
                        success=False,
                        error=f"Invalid condition_index {cond_idx} (out of range 0-{len(condition_data)-1})",
                        tool_name=self.name
                    )

            num_groups = len(grouping_logic.get("groups", []))
            matched_defs = sum(len(g.get("definition_indices", [])) for g in grouping_logic.get("groups", []))
            coverage = matched_defs / len(definition_data) if definition_data else 0

            print(f"\n[GROUPING] [OK] Extracted {num_groups} groups")
            print(f"  - Matched definitions: {matched_defs}/{len(definition_data)} ({coverage:.1%})")
            print(f"  - JOIN keys: {grouping_logic.get('column_mapping', {}).get('join_keys', [])}")
            print(f"  - Value columns: {grouping_logic.get('column_mapping', {}).get('value_columns', [])}")

            return ToolResult(
                success=True,
                data=grouping_logic,
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"GroupingLogicExtractorTool error: {str(e)}",
                tool_name=self.name
            )


class CombinationGeneratorTool:
    """
    Python 기반 조합 생성 도구

    GroupingLogicExtractorTool이 추출한 그룹핑 로직을 바탕으로
    실제 Definition+Condition 조합을 프로그래매틱하게 생성합니다.

    장점:
    - LLM 토큰 제한 무관 → 수만 개 조합도 처리 가능
    - Deterministic → 재현성 보장
    - 빠름 → 순수 Python 로직
    """

    def __init__(self):
        self.name = "combination_generator"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        그룹핑 로직 기반 최종 조합 생성

        Args:
            params:
                definition_header: list[str] - Definition 테이블 헤더
                definition_data: list[list[str]] - Definition 테이블 데이터
                condition_header: list[str] - Condition 테이블 헤더
                condition_data: list[list[str]] - Condition 테이블 데이터
                grouping_logic: dict - 그룹핑 로직 (GroupingLogicExtractorTool 출력)

        Returns:
            ToolResult with final combinations:
            {
                "definitions": [
                    {
                        "보종명": "암보험",
                        "유형1": "일반형",
                        "유형2": "-",
                        "보험기간": "10년",
                        "납입기간": "10년",
                        ...
                    },
                    ...
                ],
                "total_count": 1000,
                "generation_stats": {
                    "groups_processed": 10,
                    "matched_definitions": 950,
                    "unmatched_definitions": 50,
                    "total_generated": 1000
                }
            }
        """
        try:
            definition_header = params.get("definition_header", [])
            definition_data = params.get("definition_data", [])
            condition_header = params.get("condition_header", [])
            condition_data = params.get("condition_data", [])
            grouping_logic = params.get("grouping_logic", {})

            if not definition_header or not definition_data:
                return ToolResult(
                    success=False,
                    error="No definition data provided",
                    tool_name=self.name
                )

            if not grouping_logic or "groups" not in grouping_logic:
                return ToolResult(
                    success=False,
                    error="Invalid grouping_logic (missing 'groups')",
                    tool_name=self.name
                )

            print(f"\n[GENERATE] Generating final combinations...")

            # Generate combinations
            final_definitions = self._generate_combinations(
                definition_header, definition_data,
                condition_header, condition_data,
                grouping_logic
            )

            # Calculate stats
            groups = grouping_logic.get("groups", [])
            matched_def_count = sum(len(g.get("definition_indices", [])) for g in groups)
            unmatched_def_count = len(grouping_logic.get("unmatched", {}).get("definition_indices", []))

            stats = {
                "groups_processed": len(groups),
                "matched_definitions": matched_def_count,
                "unmatched_definitions": unmatched_def_count,
                "total_generated": len(final_definitions)
            }

            print(f"\n[GENERATE] [OK] Generated {len(final_definitions)} final definitions")
            print(f"  - From {len(groups)} groups")
            print(f"  - Matched: {matched_def_count}, Unmatched: {unmatched_def_count}")

            return ToolResult(
                success=True,
                data={
                    "definitions": final_definitions,
                    "total_count": len(final_definitions),
                    "generation_stats": stats
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"CombinationGeneratorTool error: {str(e)}",
                tool_name=self.name
            )

    def _generate_combinations(
        self,
        def_header: List[str],
        def_data: List[List[str]],
        cond_header: List[str],
        cond_data: List[List[str]],
        grouping_logic: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        그룹핑 로직에 따라 조합 생성

        Args:
            def_header: Definition 헤더
            def_data: Definition 데이터
            cond_header: Condition 헤더
            cond_data: Condition 데이터
            grouping_logic: 그룹핑 로직

        Returns:
            최종 definition 리스트 (dict 형태)
        """
        final_definitions = []
        column_mapping = grouping_logic.get("column_mapping", {})
        value_columns = column_mapping.get("value_columns", [])
        groups = grouping_logic.get("groups", [])

        # Process each group
        for group in groups:
            definition_indices = group.get("definition_indices", [])
            condition_index = group.get("condition_index")

            if condition_index is None or condition_index >= len(cond_data):
                print(f"[WARNING] Group {group.get('id')} has invalid condition_index: {condition_index}")
                continue

            condition_row = cond_data[condition_index]

            # For each definition in this group
            for def_idx in definition_indices:
                if def_idx >= len(def_data):
                    print(f"[WARNING] Invalid definition_index: {def_idx}")
                    continue

                definition_row = def_data[def_idx]
                match_condition = group.get("match_condition", {})

                # Create merged definition
                merged = {}

                # Add all definition columns
                # CRITICAL: JOIN key 컬럼은 match_condition 값으로 치환
                for i, col in enumerate(def_header):
                    if i < len(definition_row):
                        # JOIN key 컬럼은 match_condition의 필터링된 값 사용
                        if col in match_condition:
                            merged[col] = match_condition[col]
                        else:
                            merged[col] = definition_row[i]
                    else:
                        merged[col] = None

                # Add condition value columns
                for col in value_columns:
                    if col in cond_header:
                        col_idx = cond_header.index(col)
                        if col_idx < len(condition_row):
                            merged[col] = condition_row[col_idx]
                        else:
                            merged[col] = None
                    else:
                        merged[col] = None

                final_definitions.append(merged)

        # Process unmatched definitions (condition 값은 null)
        unmatched_def_indices = grouping_logic.get("unmatched", {}).get("definition_indices", [])
        for def_idx in unmatched_def_indices:
            if def_idx >= len(def_data):
                continue

            definition_row = def_data[def_idx]
            merged = {}

            # Add definition columns
            for i, col in enumerate(def_header):
                if i < len(definition_row):
                    merged[col] = definition_row[i]
                else:
                    merged[col] = None

            # Add condition columns as null
            for col in value_columns:
                merged[col] = None

            final_definitions.append(merged)

        return final_definitions
