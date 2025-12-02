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
# EXTRACT TOOLS
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

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Extract definition table from classified sections

        Args:
            params:
                sections: list[dict] - All sections
                core_indices: list[int] - Indices of definition_core sections
                annotation_indices: list[int] - Indices of definition_annotation sections (optional)
                instruction: str (optional) - Additional extraction instruction

        Returns:
            ToolResult with data:
                {
                    "header": list[str],
                    "data": list[list[str]],
                    "extraction_method": str,
                    "annotations": list[dict] (optional)
                }
        """
        try:
            sections = params.get("sections", [])
            core_indices = params.get("core_indices", [])
            annotation_indices = params.get("annotation_indices", [])
            instruction = params.get("instruction", "")  # NEW: instruction parameter

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

            # Step 1: Extract base table from core sections (with text annotations)
            header, rows, annotations = self._extract_from_cores(sections, core_indices, doc, instruction)

            if not header and not rows:
                return ToolResult(
                    success=False,
                    error="Failed to extract base table from core sections",
                    tool_name=self.name
                )

            # Step 2: If annotations exist, merge them
            if annotation_indices:
                header, rows = self._merge_with_annotations(
                    sections, annotation_indices, header, rows, doc
                )

            result_data = {
                "header": header,
                "data": rows,
                "extraction_method": "v2_classifier_based"
            }

            # Add annotations if collected
            if annotations:
                result_data["annotations"] = annotations

            return ToolResult(
                success=True,
                data=result_data,
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
    ) -> tuple[List[str], List[List[str]], List[Dict]]:
        """
        Extract base table from core sections + collect text annotations

        Args:
            sections: All sections
            core_indices: Indices of core sections
            doc: Original document
            instruction: Additional instruction

        Returns:
            (header, rows, annotations)
        """
        header = []
        rows = []
        annotations = []

        # Try each core section until we get a valid table
        for idx in core_indices:
            if idx < 0 or idx >= len(sections):
                continue

            section = sections[idx]
            content = section.get("content", [])

            # Process all content items in this section
            for item in content:
                if not isinstance(item, dict):
                    continue

                # Extract TABLE
                if "table" in item and not header:  # Only extract first table
                    table = item["table"]

                    # Try rule-based extraction first
                    extractor = RuleExtractTool()
                    result = extractor.execute(doc, {
                        "content": table,
                        "content_type": "table"
                    })

                    if result.success and result.data:
                        header = result.data.get("header", [])
                        rows = result.data.get("data", [])

                # Collect TEXT annotations (NEW!)
                elif "type" in item and item["type"] == "text":
                    text_content = item.get("content", "") or item.get("text", "")

                    if text_content and self._should_collect_text(text_content, instruction):
                        annotations.append({
                            "section_idx": idx,
                            "text": text_content,
                            "type": "annotation"
                        })

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

        if not header and text_fragments:  # No table found, try text extraction
            combined = "\n\n".join(text_fragments)
            llm_extractor = LLMExtractTool()
            result = llm_extractor.execute(doc, {
                "content": combined,
                "content_type": "text",
                "instruction": "보험 상품의 명칭/보험종목/유형 정보를 표 형태로 추출하세요."
            })

            if result.success and result.data:
                header = result.data.get("header", [])
                rows = result.data.get("data", [])

        return header, rows, annotations

    def _should_collect_text(self, text: str, instruction: str) -> bool:
        """
        Determine if text should be collected as annotation

        Args:
            text: Text content
            instruction: Additional instruction

        Returns:
            bool: True if should collect
        """
        # Default: Collect annotation markers
        annotation_markers = ["※", "주:", "주)", "주의", "참고", "단,", "단서"]
        if any(marker in text for marker in annotation_markers):
            return True

        # Instruction-based collection
        if instruction:
            # "모든 text" or "전체 text" → collect all
            if any(keyword in instruction for keyword in ["모든 text", "전체 text", "text 요소"]):
                return True

            # Specific keywords in instruction
            if "변경" in instruction and "변경" in text:
                return True

            if "주석" in instruction:
                return True

        return False

    def _merge_with_annotations(
        self,
        sections: List[Dict],
        annotation_indices: List[int],
        base_header: List[str],
        base_rows: List[List[str]],
        doc: Any
    ) -> tuple[List[str], List[List[str]]]:
        """
        Merge annotation text with base table using LLM

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

        llm_extractor = LLMExtractTool()
        result = llm_extractor.execute(doc, {
            "content": combined_content,
            "content_type": "mixed",
            "instruction": (
                "JSON의 base_table.header/base_table.data는 기존 정의 테이블이고, "
                "annotations는 해당 정의에 대한 설명/변경/예외 텍스트입니다. "
                "annotations를 반영하여 최종 정의 테이블을 header/data 형태로 다시 구성하세요. "
                "가능하면 컬럼 구조는 유지하고, 값만 필요할 때 수정하거나 추가/제거하세요."
            )
        })

        if result.success and result.data:
            merged_header = result.data.get("header", base_header)
            merged_rows = result.data.get("data", base_rows)
            return merged_header, merged_rows

        # Fallback to base if LLM merge fails
        return base_header, base_rows


class RuleExtractTool:
    """
    Rule-based Extract: 표준 테이블 구조 빠르게 파싱

    장점: 빠르고 정확 (표준 형식일 때)
    단점: 복잡한 구조 처리 못함
    """

    def __init__(self):
        self.name = "rule_extract"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        테이블 또는 텍스트 파싱

        Args:
            doc: 문서
            params: {
                "content": {...table...} or str,
                "content_type": "table" or "text" (default: "table")
            }

        Returns:
            ToolResult with data = {
                "header": [...],
                "data": [[...], ...]
            }
        """
        try:
            content = params.get("content")
            content_type = params.get("content_type", "table")

            if not content:
                return ToolResult(
                    success=False,
                    error="No content provided",
                    tool_name=self.name
                )

            # 타입별 처리
            if content_type == "text":
                return self._extract_from_text(content)
            else:  # "table"
                return self._extract_from_table(content)

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"RuleExtractTool error: {str(e)}",
                tool_name=self.name
            )

    def _extract_from_table(self, content: Dict) -> ToolResult:
        """테이블에서 데이터 추출"""
        try:
            # 테이블 형식 판별
            table_elements = content.get("table_elements", [])

            if not table_elements:
                return ToolResult(
                    success=False,
                    error="No table_elements found",
                    tool_name=self.name
                )

            # Dict 형식 (이미 파싱됨)
            if isinstance(table_elements[0], dict) and "cells" not in table_elements[0]:
                header = list(table_elements[0].keys())
                data = []
                for row in table_elements:
                    data.append([str(row.get(col, "")) for col in header])

                return ToolResult(
                    success=True,
                    data={"header": header, "data": data},
                    tool_name=self.name
                )

            # Cells 형식
            else:
                rows = []
                for row in table_elements:
                    cells = row.get("cells", [])
                    if not cells:
                        continue

                    # 주석 행 필터링
                    first_cell = cells[0].get("text", "").strip()
                    if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                        continue

                    row_data = [cell.get("text", "").strip() for cell in cells]
                    rows.append(row_data)

                if len(rows) < 2:
                    return ToolResult(
                        success=False,
                        error="Not enough rows",
                        tool_name=self.name
                    )

                header = rows[0]
                data = rows[1:]

                return ToolResult(
                    success=True,
                    data={"header": header, "data": data},
                    tool_name=self.name
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Table extraction error: {str(e)}",
                tool_name=self.name
            )

    def _extract_from_text(self, text_content: str) -> ToolResult:
        """
        텍스트에서 구조화된 데이터 추출

        예:
        "1) 해약환급금 미지급형
           - 간편심사(315)형
           - 일반심사형
         2) 일반형
           - 간편심사(335)형"

        → header: ["보종명", "유형1"]
        → data: [["해약환급금 미지급형", "간편심사(315)형/일반심사형"],
                 ["일반형", "간편심사(335)형"]]
        """
        try:
            lines = text_content.split("\n")

            # 패턴 1: 번호 매겨진 리스트 (1), 2), ...)
            # 패턴 2: 들여쓰기 리스트 (-, *, •)

            groups = []  # 그룹별로 분류
            current_group = None

            for line in lines:
                line = line.strip()
                if not line or line.startswith("※") or line.startswith("주"):
                    continue

                # 그룹 헤더 감지 (1), 2), ...)
                if re.match(r"^\d+\)", line):
                    group_name = line.split(")", 1)[1].strip()
                    current_group = {"name": group_name, "items": []}
                    groups.append(current_group)
                # 항목 감지 (-, *, •)
                elif current_group and re.match(r"^[-*•]\s+", line):
                    item = re.sub(r"^[-*•]\s+", "", line).strip()
                    current_group["items"].append(item)

            # 데이터 구조화
            if not groups:
                return ToolResult(
                    success=False,
                    error="Could not parse text content (no structured groups found)",
                    tool_name=self.name
                )

            # 가정: 첫 컬럼은 보종명, 나머지는 유형
            header = ["보종명"]
            max_items = max(len(g["items"]) for g in groups) if groups else 0

            # 유형 컬럼 생성
            if max_items > 0:
                header.append("유형1")

            # 데이터 생성
            data = []
            for group in groups:
                # 그룹 항목들을 슬래시로 연결
                if group["items"]:
                    row = [group["name"], "/".join(group["items"])]
                else:
                    row = [group["name"]]
                data.append(row)

            return ToolResult(
                success=True,
                data={
                    "header": header,
                    "data": data,
                    "extraction_method": "text_parsing"
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Text extraction error: {str(e)}",
                tool_name=self.name
            )


class LLMExtractTool:
    """
    LLM-based Extract: 복잡한 구조도 처리

    장점: 유연함, 주석 처리, 특수문자 정규화
    단점: 느리고 비쌈
    """

    def __init__(self):
        self.name = "llm_extract"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        LLM으로 데이터 추출

        Args:
            doc: 문서
            params: {
                "content": {...} or str,
                "content_type": "table" or "text" (optional),
                "instruction": "..." (optional)
            }

        Returns:
            ToolResult
        """
        try:
            content = params.get("content")
            content_type = params.get("content_type", "unknown")
            instruction = params.get("instruction", "")

            if not content:
                return ToolResult(
                    success=False,
                    error="No content provided",
                    tool_name=self.name
                )

            # 콘텐츠를 문자열로 변환
            if isinstance(content, str):
                content_str = content
            else:
                content_str = json.dumps(content, ensure_ascii=False)

            prompt = f"""다음 콘텐츠에서 구조화된 데이터를 추출하세요 (형식: {content_type}).

콘텐츠:
{content_str}

{f"**추가 지시사항**: {instruction}" if instruction else ""}

**기본 규칙**:
1. 테이블 형식: 행과 열 파싱
2. 텍스트 형식: 구조를 파악하여 표 형태로 변환
3. Header와 Data rows로 구분

**출력 형식 (JSON)**:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ...
  ],
  "extraction_method": "table" or "text",
  "notes": "처리 내용"
}}

반드시 JSON 형식으로 응답하세요."""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=3000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("header") or not result.get("data"):
                return ToolResult(
                    success=False,
                    error="LLM failed to extract data",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "header": result["header"],
                    "data": result["data"],
                    "notes": result.get("notes", "")
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"LLMExtractTool error: {str(e)}",
                tool_name=self.name
            )


# ============================================================================
# TRANSFORM TOOLS
# ============================================================================

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

            # Optional extra instruction block, built outside the f-string to
            # avoid backslashes inside f-string expressions.
            extra_instruction = ""
            if instruction:
                extra_instruction = (
                    "**추가 지시사항 (이전 시도 에러 기반)**:\n"
                    f"{instruction}\n\n"
                )

            if not header or not data:
                return ToolResult(
                    success=False,
                    error="Header or data is empty",
                    tool_name=self.name
                )

            # Step 1: LLM으로 값 분리 (일반화된 프롬프트)
            prompt = f"""다음 표 데이터의 각 셀 값을 독립된 옵션들로 분리하세요.

Header: {json.dumps(header, ensure_ascii=False)}
Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

{extra_instruction}

**기본 규칙**:
1. 각 셀의 값을 적절한 구분자로 분리하여 옵션 리스트로 변환
2. 줄바꿈과 불필요한 공백 제거
3. 각 행은 독립적으로 처리

**출력 형식 (JSON)**:
{{
  "parsed_rows": [
    [
      ["값1-1"],
      ["값1-2", "값1-3"],
      ["값1-4"]
    ],
    [
      ["값2-1"],
      ["값2-2"],
      ["값2-3", "값2-4", "값2-5"]
    ]
  ]
}}

- 각 행은 셀 단위 리스트
- 각 셀은 분리된 옵션들의 리스트
- 각 행의 셀 개수 = header 개수
- 반드시 JSON 형식으로 응답
"""

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
                instruction: str (optional) - Additional classification instruction

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
            instruction = params.get("instruction", "")  # NEW: instruction parameter

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

            # Step 2: Build classification prompt (with instruction)
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
            instruction: Additional instruction for classification

        Returns:
            str: Classification prompt
        """
        prompt = """주어진 모든 섹션을 4가지 카테고리로 분류하세요.

### 카테고리

1. **definition_core**: 핵심 정의/구조를 설명하는 섹션
2. **definition_annotation**: definition_core에 대한 주석/보충 설명
3. **condition**: 조건/제약사항을 설명하는 섹션
4. **other**: 위 3가지에 해당하지 않는 섹션

### 기본 규칙

- 제목이 없어도 내용(preview)을 보고 판단
- 모든 섹션은 정확히 한 카테고리에만 속함
"""

        # Add additional instruction if provided
        if instruction:
            prompt += f"""
### 추가 지시사항 (중요!)

{instruction}

"""

        prompt += """
**입력 섹션**:

"""

        # Add section summaries
        for i, s in enumerate(summaries):
            prompt += f"\n[Section {s['index']}]\n"
            prompt += f"Title: {s['title'] or '(no title)'}\n"
            prompt += f"Has Table: {s['has_table']}\n"
            prompt += f"Has Text: {s['has_text']}\n"
            prompt += f"Preview: {s['preview'][:200]}\n"
            prompt += "---\n"

        prompt += """

**출력 형식** (JSON):

{
    "definition_core": [섹션 인덱스들],
    "definition_annotation": [섹션 인덱스들],
    "condition": [섹션 인덱스들],
    "other": [섹션 인덱스들],
    "reasoning": "분류 근거"
}

**예시**:
{
    "definition_core": [0, 2],
    "definition_annotation": [1, 3],
    "condition": [4],
    "other": [5, 6],
    "reasoning": "분류 근거"
}

반드시 JSON 형식으로 응답하세요. 위 섹션들을 분류해주세요:"""

        return prompt
