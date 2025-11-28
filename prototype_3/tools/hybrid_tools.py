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
            params: {
                "keywords": [...],
                "sections": [...],
                "search_in_content": bool (default: True) - content도 검색할지 여부
            }

        Returns:
            ToolResult with data = {
                "found_sections": [...],
                "found_content": {...} or str,
                "content_type": "table" or "text",
                "section_title": str
            }
        """
        try:
            keywords = params.get("keywords", ["정의", "명칭"])
            sections = params.get("sections", [])
            search_in_content = params.get("search_in_content", True)

            found = []

            for section in sections:
                title = section.get("title", "")
                matched = False

                # Title 검색
                if any(kw in title for kw in keywords):
                    matched = True

                # Content 검색 (옵션)
                if not matched and search_in_content:
                    content = section.get("content", [])
                    for item in content:
                        if isinstance(item, dict):
                            # 텍스트 콘텐츠 검색
                            text_content = item.get("content", "") or item.get("text", "")
                            if isinstance(text_content, str) and any(kw in text_content for kw in keywords):
                                matched = True
                                break

                if matched:
                    found.append(section)

            if not found:
                return ToolResult(
                    success=False,
                    error=f"No sections found with keywords: {keywords}",
                    tool_name=self.name
                )

            # 첫 번째 매칭 섹션에서 콘텐츠 찾기 (테이블 또는 텍스트)
            first_section = found[0]
            content_result = self._find_content(first_section)

            if not content_result:
                return ToolResult(
                    success=False,
                    error="Found section but no extractable content",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "found_sections": found,
                    "found_content": content_result["content"],
                    "content_type": content_result["type"],  # "table" or "text"
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

    def _find_content(self, section: Dict) -> Optional[Dict]:
        """
        섹션에서 추출 가능한 콘텐츠 찾기 (테이블 우선, 없으면 텍스트)

        Returns:
            {
                "content": {...} or str,
                "type": "table" or "text"
            }
            또는 None (콘텐츠 없음)
        """
        content = section.get("content", [])

        # 1. 테이블 우선 검색
        for item in content:
            if isinstance(item, dict) and "table" in item:
                table = item["table"]
                # 빈 테이블이 아닌지 확인
                if isinstance(table, dict):
                    table_elements = table.get("table_elements", [])
                    if table_elements:  # 실제 데이터가 있음
                        return {"content": table, "type": "table"}

        # 2. 텍스트 검색
        text_content = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("content", "") or item.get("text", "")
                if isinstance(text, str) and text.strip():
                    text_content.append(text.strip())

        if text_content:
            return {
                "content": "\n\n".join(text_content),
                "type": "text"
            }

        return None

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

            # 섹션 요약 (제목 + 콘텐츠 미리보기)
            sections_summary = []
            for i, s in enumerate(sections):
                summary = {"index": i, "title": s.get("title", "")}

                # 콘텐츠 미리보기 추가
                content = s.get("content", [])
                content_preview = []
                has_table = False
                has_text = False

                for item in content[:3]:  # 최대 3개만
                    if isinstance(item, dict):
                        if "table" in item:
                            table = item.get("table", {})
                            if isinstance(table, dict) and table.get("table_elements"):
                                has_table = True
                        text = item.get("content", "") or item.get("text", "")
                        if text and isinstance(text, str):
                            has_text = True
                            content_preview.append(text[:150])  # 150자까지

                summary["has_table"] = has_table
                summary["has_text"] = has_text
                summary["content_preview"] = "\n".join(content_preview)

                sections_summary.append(summary)

            prompt = f"""다음 섹션들 중에서 보험 상품의 정의/명칭 정보를 담고 있는 섹션을 찾으세요.

섹션 목록 (제목과 콘텐츠 미리보기):
{json.dumps(sections_summary, ensure_ascii=False, indent=2)}

{instruction}

**중요**:
- 테이블 형식뿐 아니라 텍스트 형식으로 정의가 있을 수 있음
- content_preview를 참고하여 실제 정의 정보가 있는지 확인

다음 JSON 형식으로 반환:
{{
  "selected_index": 0,
  "reasoning": "이 섹션이 정의를 담고 있는 이유",
  "content_type": "table" or "text"
}}

찾지 못하면:
{{
  "selected_index": null,
  "reasoning": "찾지 못한 이유",
  "content_type": null
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

            # 콘텐츠 찾기 (테이블 또는 텍스트)
            content_result = self._find_content(selected_section)

            if not content_result:
                return ToolResult(
                    success=False,
                    error="Found section but no extractable content",
                    tool_name=self.name
                )

            return ToolResult(
                success=True,
                data={
                    "found_sections": [selected_section],
                    "found_content": content_result["content"],
                    "content_type": result.get("content_type", content_result["type"]),  # LLM 판단 우선, 아니면 자동 감지
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

    def _find_content(self, section: Dict) -> Optional[Dict]:
        """
        섹션에서 추출 가능한 콘텐츠 찾기 (테이블 우선, 없으면 텍스트)

        Returns:
            {
                "content": {...} or str,
                "type": "table" or "text"
            }
            또는 None (콘텐츠 없음)
        """
        content = section.get("content", [])

        # 1. 테이블 우선 검색
        for item in content:
            if isinstance(item, dict) and "table" in item:
                table = item["table"]
                # 빈 테이블이 아닌지 확인
                if isinstance(table, dict):
                    table_elements = table.get("table_elements", [])
                    if table_elements:  # 실제 데이터가 있음
                        return {"content": table, "type": "table"}

        # 2. 텍스트 검색
        text_content = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("content", "") or item.get("text", "")
                if isinstance(text, str) and text.strip():
                    text_content.append(text.strip())

        if text_content:
            return {
                "content": "\n\n".join(text_content),
                "type": "text"
            }

        return None

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
