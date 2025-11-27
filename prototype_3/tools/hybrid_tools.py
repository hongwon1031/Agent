"""
Hybrid Tools: Rule-based + LLM-based

각 기능별로 Rule/LLM 버전 제공:
- Search: 정의 섹션 찾기
- Extract: 데이터 추출
- Transform: Cartesian Product 생성
"""

import json
import os
from typing import Dict, Any, List
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

class RuleSearchTool:
    """
    Rule-based Search: 키워드 매칭으로 빠르게 찾기

    장점: 빠르고 저렴
    단점: 키워드가 정확히 일치해야 함
    """

    def __init__(self):
        self.name = "rule_search"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        키워드 매칭으로 섹션 찾기

        Args:
            doc: 문서
            params: {"keywords": [...], "sections": [...]}

        Returns:
            ToolResult with data = {
                "found_sections": [...],
                "found_table": {...}
            }
        """
        try:
            keywords = params.get("keywords", ["정의", "명칭"])
            sections = params.get("sections", [])

            found = []

            for section in sections:
                title = section.get("title", "")

                # 키워드 매칭
                if any(kw in title for kw in keywords):
                    found.append(section)

            if not found:
                return ToolResult(
                    success=False,
                    error=f"No sections found with keywords: {keywords}",
                    tool_name=self.name
                )

            # 첫 번째 매칭 섹션에서 테이블 찾기
            first_section = found[0]
            tables = self._find_tables(first_section)

            if not tables:
                return ToolResult(
                    success=False,
                    error="Found section but no table",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "found_sections": found,
                    "found_table": tables[0],
                    "section_title": first_section.get("title")
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"RuleSearchTool error: {str(e)}",
                tool_name=self.name
            )

    def _find_tables(self, section: Dict) -> List:
        """섹션에서 테이블 찾기"""
        content = section.get("content", [])
        tables = []

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "table" in item:
                    tables.append(item["table"])

        return tables


class LLMSearchTool:
    """
    LLM-based Search: 문맥을 이해하여 찾기

    장점: 유연함, 비표준 제목도 인식
    단점: 느리고 비쌈
    """

    def __init__(self):
        self.name = "llm_search"
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        LLM으로 정의 섹션 찾기

        Args:
            doc: 문서
            params: {"sections": [...], "instruction": "..."}

        Returns:
            ToolResult
        """
        try:
            sections = params.get("sections", [])
            instruction = params.get("instruction", "정의 섹션을 찾으세요")

            # 섹션 요약 (제목만)
            sections_summary = [
                {"index": i, "title": s.get("title", "")}
                for i, s in enumerate(sections)
            ]

            prompt = f"""다음 섹션들 중에서 보험 상품의 정의/명칭 정보를 담고 있는 섹션을 찾으세요.

섹션 목록:
{json.dumps(sections_summary, ensure_ascii=False, indent=2)}

{instruction}

다음 JSON 형식으로 반환:
{{
  "selected_index": 0,
  "reasoning": "이 섹션이 정의를 담고 있는 이유"
}}

찾지 못하면:
{{
  "selected_index": null,
  "reasoning": "찾지 못한 이유"
}}"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)

            if result["selected_index"] is None:
                return ToolResult(
                    success=False,
                    error=f"LLM could not find section: {result['reasoning']}",
                    tool_name=self.name
                )

            selected_section = sections[result["selected_index"]]

            # 테이블 찾기
            tables = self._find_tables(selected_section)

            if not tables:
                return ToolResult(
                    success=False,
                    error="Found section but no table",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "found_sections": [selected_section],
                    "found_table": tables[0],
                    "section_title": selected_section.get("title"),
                    "reasoning": result["reasoning"]
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"LLMSearchTool error: {str(e)}",
                tool_name=self.name
            )

    def _find_tables(self, section: Dict) -> List:
        """섹션에서 테이블 찾기"""
        content = section.get("content", [])
        tables = []

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "table" in item:
                    tables.append(item["table"])

        return tables


# ============================================================================
# EXTRACT TOOLS
# ============================================================================

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
        표준 테이블 파싱

        Args:
            doc: 문서
            params: {"content": {...table...}}

        Returns:
            ToolResult with data = {
                "header": [...],
                "data": [[...], ...]
            }
        """
        try:
            content = params.get("content")

            if not content:
                return ToolResult(
                    success=False,
                    error="No content provided",
                    tool_name=self.name
                )

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
                error=f"RuleExtractTool error: {str(e)}",
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
            params: {"content": {...}, "instruction": "..."}

        Returns:
            ToolResult
        """
        try:
            content = params.get("content")
            instruction = params.get("instruction", "")

            if not content:
                return ToolResult(
                    success=False,
                    error="No content provided",
                    tool_name=self.name
                )

            content_str = json.dumps(content, ensure_ascii=False)

            prompt = f"""다음 테이블 데이터에서 header와 data를 추출하세요.

데이터:
{content_str}

**추출 규칙**:
- 주석 행 제거 (※, 주:, 주), *, - 로 시작하는 행)
- Header는 컬럼명
- Data는 실제 데이터 행들
- 특수문자 정규화

{f"**추가 지시사항**: {instruction}" if instruction else ""}

다음 JSON 형식으로 반환:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ...
  ],
  "excluded_rows": ["제외된 행1", ...],
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
                # 각 셀을 슬래시로 분리
                options = []
                for cell in row:
                    cell_clean = cell.replace('\n', '').strip()
                    values = [v.strip() for v in cell_clean.split('/') if v.strip()]
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
        LLM으로 조합 생성 + 컬럼명 매핑

        Args:
            doc: 문서
            params: {"header": [...], "data": [[...], ...]}

        Returns:
            ToolResult
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

            prompt = f"""다음 데이터에서 Cartesian Product를 생성하세요.

Header: {json.dumps(header, ensure_ascii=False)}
Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

**규칙**:
1. "명칭" 컬럼 → "보종명" 필드
2. 다른 컬럼들 → "유형1", "유형2", ... 필드
3. 슬래시(/)로 분리된 값들은 각각 조합
4. 줄바꿈은 보종명에서만 유지, 유형은 제거
5. 행별로 독립적인 조합 생성

다음 JSON 형식으로 반환:
{{
  "definitions": [
    {{"보종명": "...", "유형1": "...", ...}},
    ...
  ],
  "total_count": 24,
  "notes": "처리 내용"
}}"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("definitions"):
                return ToolResult(
                    success=False,
                    error="LLM failed to generate combinations",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "definitions": result["definitions"],
                    "total_count": result["total_count"],
                    "notes": result.get("notes", "")
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"LLMCartesianTool error: {str(e)}",
                tool_name=self.name
            )
