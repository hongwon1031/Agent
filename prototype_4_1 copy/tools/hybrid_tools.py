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

            prompt = f"""다음은 보험 문서의 콘텐츠입니다 (형식: {content_type}).

콘텐츠:
{content_str}

**추출 목표**: 보험 상품의 명칭과 유형 정보

**형식별 처리**:
- 테이블 형식: 행과 열을 파싱
- 텍스트 형식: 번호/들여쓰기 구조를 파싱하여 구조화

**요구사항**:
1. 주석 행 제외 (※, 주:, 주), *, - 로 시작하는 설명)
2. Header와 Data rows로 구분
3. 텍스트 형식인 경우, 계층 구조를 평면화하여 표 형태로 변환
4. 특수문자 정규화

{f"**추가 지시사항**: {instruction}" if instruction else ""}

다음 JSON 형식으로 반환:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ...
  ],
  "extraction_method": "table" or "text",
  "notes": "처리 내용"
}}"""

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
            merge_indices = sorted(set(annotation_indices + core_indices))  # core 섹션도 포함
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

            # Combine base instruction with additional instruction
            base_instruction = "보험 상품의 명칭/보험종목/유형 정보를 표 형태로 추출하세요."
            final_instruction = f"{base_instruction}\n{instruction}" if instruction else base_instruction

            # Use private LLM helper
            header, rows, _ = self._llm_extract_helper(combined, "text", final_instruction)
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

        # Combine base instruction with additional instruction
        base_instruction = (
            "JSON의 base_table.header/base_table.data는 기존 정의 테이블이고, "
            "annotations는 해당 정의에 대한 설명/변경/예외 사항입니다.\n\n"
            "**임무**: annotations를 **반드시 분석하고 적용**하세요! 무시하지 마세요!\n\n"
            
            "## 기본 원칙\n\n"
            "Annotations는 base_table에 대한 **수정 지시사항**입니다.\n"
            "각 annotation 문장의 **의도**를 파악하고, 테이블을 그에 맞게 변경하세요:\n\n"
            
            "1. **통합/동일 취급 지시**: 여러 값을 하나로 합치라는 의미\n"
            "   - \"A와 B를 동일하게 취급\", \"A와 B는 같은 것으로 간주\"\n"
            "   - **행동**: 둘 중 하나를 선택하거나, \"A/B\" 형태로 병합\n"
            "   - **핵심**: 별도로 존재하는 게 아니라 **하나로 통합**\n\n"
            
            "2. **제외/삭제 지시**: 특정 값을 제거하라는 의미\n"
            "   - \"X를 제외\", \"Y는 적용하지 않음\"\n"
            "   - **행동**: 해당 값이 포함된 행을 삭제\n\n"
            
            "3. **대체/변경 지시**: 값이나 명칭을 바꾸라는 의미\n"
            "   - \"A를 B로 변경\", \"C는 D로 표기\"\n"
            "   - **행동**: 테이블에서 A를 찾아 B로 교체\n\n"
            
            "4. **조건부 적용**: 특정 조건에서만 값이 달라지는 경우\n"
            "   - \"2024년 이후 X형 추가\", \"특정 경우에만 Y 적용\"\n"
            "   - **행동**: 맥락 판단 후 적절히 반영 (행 추가/수정)\n\n"
            
            "5. **단순 설명**: 테이블 변경이 필요 없는 정보성 텍스트\n"
            "   - **행동**: 테이블을 그대로 유지\n\n"
            "---\n\n"
            
            "## 예시로 배우기\n\n"
            "**예시 1 - 동일 취급 (통합)**:\n"
            "```\n"
            "base_table.data = [\n"
            "  [\"상품A\", \"온라인형\"],\n"
            "  [\"상품A\", \"인터넷전용형\"]\n"
            "]\n"
            "annotation = \"온라인형과 인터넷전용형은 동일하게 본다\"\n"
            "\n"
            "→ 의도: 두 값은 의미만 다를 뿐 **동일한 옵션**이므로\n"
            "  최종 테이블에서는 하나의 값으로 취급해야 함\n"
            "\n"
            "최종 data = [\n"
            "  [\"상품A\", \"온라인/인터넷전용형\"]  ← 통합됨\n"
            "]\n"
            "또는\n"
            "최종 data = [\n"
            "  [\"상품A\", \"온라인형\"]  ← 하나만 남김\n"
            "]\n"
            "```\n\n"

            "**예시 2 - 제외**:\n"
            "```\n"
            "base_table.data = [\n"
            "  [\"특약B\", \"일반형\"],\n"
            "  [\"특약B\", \"특수형\"]\n"
            "]\n"
            "annotation = \"특수형은 이 계약에서 제외한다\"\n\n"
            "→ 의도: 특수형 행을 삭제\n\n"
            "최종 data = [\n"
            "  [\"특약B\", \"일반형\"]  ← 특수형 삭제됨\n"
            "]\n"
            "```\n\n"
            
            "**예시 3 - 변경/대체**:\n"
            "```\n"
            "base_table.data = [\n"
            "  [\"특약C\", \"구형\"],\n"
            "  [\"특약C\", \"신형\"]\n"
            "]\n"
            "annotation = \"구형은 레거시형으로 표기한다\"\n\n"
            "→ 의도: 명칭 변경\n\n"
            "최종 data = [\n"
            "  [\"특약C\", \"레거시형\"],  ← 변경됨\n"
            "  [\"특약C\", \"신형\"]\n"
            "]\n"
            "```\n\n"
            "---\n\n"
            
            "## 적용 지침\n\n"
            "- **적극적으로 적용**: 애매하면 **적용하는 쪽**으로 판단하세요\n"
            "- **맥락 이해**: 문장의 **의도**를 파악하고 테이블에 반영하세요\n"
            "- **보수적 금지**: 확실하지 않다고 무시하지 마세요. 합리적으로 해석하여 적용하세요\n"
            "- 통합/동일 취급은 annotation 문장에 **직접 등장한 값들만** 대상으로 합니다.\n"
            "- 문장에 언급되지 않은 값은 어떤 통합/제외/변경에도 포함하지 마세요.\n"
            "- 새로운 패턴을 추론해서 값을 추가하거나 더 많이 묶지 마세요.\n"
            "- 애매하거나 문장에 명시되지 않은 경우에는 **테이블을 그대로 유지**하세요.\n\n"

            
            "최종 header/data를 JSON으로 반환하세요."
        )
        final_instruction = f"{base_instruction}\n\n추가 지시사항:\n{instruction}" if instruction else base_instruction

        # Use private LLM helper
        merged_header, merged_rows, _ = self._llm_extract_helper(
            combined_content,
            "mixed",
            final_instruction
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

            # Step 1: LLM으로 값 분리
            prompt = f"""다음 데이터의 각 셀 값을 문맥을 고려하여 독립된 옵션들로 분리하고, JSON 형식으로 반환하세요.

Header: {json.dumps(header, ensure_ascii=False)}
Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

{extra_instruction}

**중요 규칙**:
1. **컬럼별 주 구분자(primary delimiter) 파악**:
   각 셀의 값을 분리하기 전에, **해당 셀이 속한 컬럼 전체**를 관찰하세요:

   - 컬럼에서 `/`와 `,` 중 **어느 것이 더 자주** 등장하는지 확인
   - **더 자주 등장하는 구분자**를 실제 구분자로 사용
   - **덜 등장하는 구분자**는 내용의 일부로 취급 (분리하지 않음)

   **예시**:
   - 컬럼 값: "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"
     → `,`가 여러 번, `/`는 한 번만 등장
     → 주 구분자: `,`
     → 분리 결과: ["두경부암(전이포함)", "위암(전이포함)", "남성/여성생식기암(전이포함)"]
     → "남성/여성생식기암"은 분리하지 않음 (/ is not primary delimiter)

   - 컬럼 값: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
     → `/`가 여러 번, `,` 없음
     → 주 구분자: `/`
     → 분리 결과: ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형"]

2. 줄바꿈(\\n)과 공백은 strip하되, 보종명(첫 번째 컬럼)은 줄바꿈 유지

3. 각 행은 독립적으로 처리

**출력 형식 (중요!)**:
각 행을 셀 단위로 분리하고, 각 셀은 옵션 리스트로 표현.

{{
  "parsed_rows": [
    [
      ["보종명1"],
      ["유형값1"],
      ["옵션A", "옵션B", "옵션C"],
      ["암종류1", "암종류2", ...]
    ],
    [...]
  ]
}}

**예시 1**:
Input:
Header: ["명칭", "유형", "보험종목"]
Data: [["특약A", "일반형", "간편심사(315)형/간편심사(335)형"]]

Output:
{{
  "parsed_rows": [
    [
      ["특약A"],
      ["일반형"],
      ["간편심사(315)형", "간편심사(335)형"]
    ]
  ]
}}

**예시 2**:
Input:
Header: ["명칭", "유형", "보험종목", "보장계약"]
Data: [["특약B", "해약환급금미지급형", "간편심사(315)형/간편심사(335)형", "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"]]

Output:
{{
  "parsed_rows": [
    [
      ["특약B"],
      ["해약환급금미지급형"],
      ["간편심사(315)형", "간편심사(335)형"],
      ["두경부암(전이포함)", "위암(전이포함)", "남성/여성생식기암(전이포함)"]
    ]
  ]
}}

주의:
- 위 예시 2에서 "보장계약" 컬럼은 `,`가 주 구분자이므로 `/`는 내용의 일부입니다!
- 각 셀은 header 개수와 동일하게 맞춰야 함!
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
        prompt = """당신은 보험 약관 문서의 섹션을 분류하는 전문가입니다.

**임무**: 주어진 모든 섹션을 4가지 카테고리로 분류하세요.

### 카테고리 정의 (의미 기준)

1. **definition_core** (핵심 정의 섹션)

   - 질문: 이 문서에서 정의하는 **상품/특약/보장계약이 무엇이며, 어떤 종류/조합으로 구성되어 있는가?**
   - 예:
     - 상품/특약의 명칭과 버전(해약환급금 미지급형 vs 일반형)
     - 1종/2종, 주계약/특약, 보장계약 타입 등
     - 각 버전이 어떤 축(유형1/유형2/심사형/보장계약 등)으로 나뉘는지
   - 특징:
     - "무엇으로 구성되어 있는지"를 설명하는 정적인 구조 정의
     - 표(table)인 경우가 많지만, 텍스트만으로 정의하는 경우도 있음
     - 기간, 가입나이, 납입기간, 납입주기 등 **숫자 기반 가입조건은 핵심이 아님**

2. **definition_annotation** (정의 주석/보충 섹션)

   - 질문: 위에서 정의한 구조에 대해 **어떤 예외/변경/추가 설명**이 있는가?
   - 예:
     - 명칭/표기법 설명: "상품명 앞에 '(간편)'을 붙인다"
     - 정의값에 대한 보충: "N은 1, 3, 5를 의미한다"
     - 정의에 대한 예외/주의: "단, 일부 채널에서는 OO라는 명칭을 사용"
     - 각주, "※", "참고", "주)" 로 시작하는 문장 등
   - 특징:
     - definition_core에서 정의한 값들을 수정/보완/해석하는 텍스트
     - 가입조건(보험기간, 가입나이, 납입기간 등)을 새로 정의하는 것은 아님

3. **condition** (계약/가입 조건 섹션)

   - 질문: 각 종류(유형/종/보장형)를 **어떤 조건으로 가입/유지할 수 있는가?**
   - 예:
     - 보험기간: 10/20/30년, 60/70/80세, 종신
     - 보험료 납입기간: 10/15/20/25/30년납, 전기납
     - 가입나이: "만15세 ~ min(세만기 - 년납, 70세)"
     - 보험료 납입주기: 월납/연납 등
   - 특징:
     - "언제까지, 얼마 동안, 몇 살부터 몇 살까지, 어떻게 내야 하는지" 같은
       기간/연령/납입 조건을 수치/범위로 표현
     - 표 제목이 "가입가능 조건", "보험기간/보험료 납입기간/가입나이/납입주기" 등인 경우가 많음
     - 정의(상품 구조)를 새로 소개하기보다는, 이미 정의된 유형에 대한 조건을 설명

4. **other** (기타 섹션)

   - 위 3가지에 해당하지 않는 모든 섹션
   - 예: 목차, 서문, 일반 설명, 부록, 클레임/면책조항 등

### 중요 규칙

- 제목이 비표준이어도(예: "상품 구성", 숫자만 있는 제목 등) 내용상
  상품/보장 구조를 정의하면 **definition_core**로 분류하세요.
- 기간/가입나이/납입기간/납입주기에 대한 수치/범위가 중심이면 **condition**으로 분류하세요.
- "※", "참고", "주)", "단," 등으로 시작하는 정의 관련 설명은
  구조 정의가 아니면 **definition_annotation**으로 분류하세요.
- 제목이 없더라도 내용(preview)을 보고 판단하세요.
- 표/텍스트 형식은 보조 정보일 뿐, 의미(정의 vs 조건)를 우선적으로 고려하세요.
- 모든 섹션은 정확히 한 카테고리에만 속해야 합니다.
"""

        # Add additional instruction if provided
        if instruction:
            prompt += f"""
**추가 지시사항** (중요 - 반드시 따를 것):
{instruction}

"""

        prompt += """**입력 섹션**:

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
    "reasoning": "분류 근거에 대한 간단한 설명"
}

**예시**:
{
    "definition_core": [0, 2],
    "definition_annotation": [1, 3],
    "condition": [4],
    "other": [5, 6],
    "reasoning": "Section 0과 2는 보험종목/명칭 테이블, Section 1과 3은 정의에 대한 주석, Section 4는 가입조건, 나머지는 목차/서문"
}

이제 위 섹션들을 분류해주세요:"""

        return prompt
