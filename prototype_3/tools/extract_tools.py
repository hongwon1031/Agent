"""
Extract Tools: 유연한 추출 도구들

다양한 형식의 데이터를 추출하는 도구들입니다.
"""

from typing import Dict, List, Any, Optional
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from .base import FlexibleTool, ToolType
from core.flexible_result import FlexibleToolResult, ResultStatus, ResultMetadata
from core.document_accessor import DocumentAccessor, ContentType


class TableExtractTool(FlexibleTool):
    """
    규칙 기반 테이블 추출 도구

    특징:
        - 빠른 테이블 데이터 추출
        - DocumentAccessor 활용
        - 주석 행 필터링

    파라미터:
        - access_path: 섹션 접근 경로 (required)
        - section_index: 섹션 인덱스 (required)
        - filter_annotations: 주석 행 필터링 여부 (optional)
    """

    def get_type(self) -> ToolType:
        return ToolType.EXTRACT

    def get_description(self) -> str:
        return "Fast rule-based table data extraction with annotation filtering"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "access_path": {
                "type": "list",
                "description": "Document access path to the section",
                "required": False
            },
            "section_index": {
                "type": "int",
                "description": "Section index (alternative to access_path)",
                "required": False
            },
            "filter_annotations": {
                "type": "boolean",
                "description": "Filter out annotation rows",
                "required": False,
                "default": True
            }
        }

    def execute(
        self,
        document: Any,
        params: Dict[str, Any],
        accessor: Optional[DocumentAccessor] = None
    ) -> FlexibleToolResult:
        try:
            # DocumentAccessor 가져오기
            acc = self._get_accessor(document, accessor)

            # 섹션 찾기
            section_index = params.get("section_index")
            access_path = params.get("access_path")

            if section_index is None and not access_path:
                return self._create_error("Either section_index or access_path is required")

            # 섹션 가져오기
            all_sections = acc.get_all_sections()

            if section_index is not None:
                if section_index >= len(all_sections):
                    return self._create_error(f"Section index {section_index} out of range")
                section = all_sections[section_index]
            else:
                # access_path로 찾기
                section = None
                for s in all_sections:
                    if s.access_path == access_path:
                        section = s
                        break
                if section is None:
                    return self._create_error(f"Section not found with access_path: {access_path}")

            # 테이블 콘텐츠 추출
            table_contents = acc.extract_content(section, content_type="table")

            if not table_contents:
                return self._create_error(f"No table found in section: {section.title}")

            # 첫 번째 테이블 사용
            table_content = table_contents[0]
            table_data = table_content.data

            # 테이블 데이터 파싱
            header, data = self._parse_table(table_data, params.get("filter_annotations", True))

            if not header or not data:
                return self._create_error("Failed to parse table data")

            # 메타데이터 생성
            metadata = ResultMetadata(
                output_schema={
                    "header": "list of column names",
                    "data": "list of data rows",
                    "row_count": "number of data rows",
                    "source_section": "section information"
                },
                access_hints={
                    "primary_result": "data",
                    "how_to_use": "header and data are ready for Cartesian product"
                },
                confidence=1.0,
                processing_notes=f"Extracted {len(data)} rows from table"
            )

            return self._create_success(
                data={
                    "header": header,
                    "data": data,
                    "row_count": len(data),
                    "source_section": {
                        "index": section.index,
                        "title": section.title,
                        "access_path": section.access_path
                    }
                },
                metadata=metadata
            )

        except Exception as e:
            return self._create_error(f"TableExtractTool error: {str(e)}")

    def _parse_table(self, table_data: Any, filter_annotations: bool) -> tuple:
        """테이블 데이터 파싱"""
        if not table_data:
            return None, None

        # table_elements 형식
        if isinstance(table_data, dict):
            table_elements = table_data.get("table_elements", [])
        elif isinstance(table_data, list):
            table_elements = table_data
        else:
            return None, None

        if not table_elements:
            return None, None

        data_rows = []

        # cells 형식 파싱
        for row in table_elements:
            if isinstance(row, dict) and "cells" in row:
                cells = row.get("cells", [])
                row_texts = [cell.get("text", "").strip() for cell in cells]

                # 주석 행 필터링
                if filter_annotations and row_texts:
                    first_cell = row_texts[0]
                    # 다양한 주석 패턴
                    if any(first_cell.startswith(pattern) for pattern in
                           ["※", "주:", "주)", "* ", "- ", "[", "(주)", "<", "＊", "○", "•", "·"]):
                        continue

                    # 빈 행 제외
                    if all(not cell for cell in row_texts):
                        continue

                data_rows.append(row_texts)

        if len(data_rows) < 2:
            return None, None

        # 첫 행을 header로
        header = data_rows[0]
        data = data_rows[1:]

        return header, data


class FlexibleExtractTool(FlexibleTool):
    """
    LLM 기반 유연한 추출 도구

    특징:
        - 복잡한 형식 처리 가능
        - 텍스트/테이블 모두 처리
        - 주석 동적 인식
        - 특수문자 변환

    파라미터:
        - search_result: 이전 검색 결과 (required)
        - extraction_goal: 추출 목표 (optional)
        - instruction: 추가 지시사항 (optional)
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_type(self) -> ToolType:
        return ToolType.EXTRACT

    def get_description(self) -> str:
        return "LLM-based flexible extraction handling complex formats and edge cases"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "search_result": {
                "type": "dict",
                "description": "Search result from previous task",
                "required": True
            },
            "extraction_goal": {
                "type": "string",
                "description": "What data to extract (e.g., '보험 상품명과 유형')",
                "required": False,
                "default": "보험 상품의 명칭과 유형"
            },
            "instruction": {
                "type": "string",
                "description": "Additional extraction instructions",
                "required": False
            }
        }

    def execute(
        self,
        document: Any,
        params: Dict[str, Any],
        accessor: Optional[DocumentAccessor] = None
    ) -> FlexibleToolResult:
        try:
            # DocumentAccessor 가져오기
            acc = self._get_accessor(document, accessor)

            # 검색 결과에서 섹션 정보 추출
            search_result = params.get("search_result")
            if not search_result:
                return self._create_error("search_result parameter is required")

            # 우선순위: primary_match > found_sections[0]
            target_section = search_result.get("primary_match") or \
                           (search_result.get("found_sections", [{}])[0] if search_result.get("found_sections") else None)

            if not target_section:
                return self._create_error("No target section in search_result")

            # 섹션 찾기
            section_index = target_section.get("section_index")
            all_sections = acc.get_all_sections()

            if section_index >= len(all_sections):
                return self._create_error(f"Section index {section_index} out of range")

            section = all_sections[section_index]

            # 콘텐츠 추출 (모든 타입)
            all_contents = acc.extract_content(section)

            if not all_contents:
                return self._create_error(f"No content found in section: {section.title}")

            # 콘텐츠를 LLM에 전달 가능한 형식으로 변환
            content_str = self._format_content_for_llm(all_contents)

            # LLM 프롬프트
            extraction_goal = params.get("extraction_goal", "보험 상품의 명칭과 유형")
            instruction = params.get("instruction", "")

            prompt = f"""다음은 보험 문서의 콘텐츠입니다.

섹션 제목: {section.title}

콘텐츠:
{content_str}

**추출 목표**: {extraction_goal}

{f"**추가 지시사항**: {instruction}" if instruction else ""}

**요구사항**:
1. 주석 행은 제외 (※, 주:, [, (, *, -, ○ 등으로 시작)
2. Header와 Data rows를 구분
3. ASCII 코드 등 특수문자는 원래 문자로 변환
4. 빈 행 제외
5. 데이터 완전성 확보

다음 JSON 형식으로 반환:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ["값1", "값2", ...],
    ...
  ],
  "excluded_rows": ["제외된 행1", "제외된 행2", ...],
  "processing_notes": "<처리 과정 설명>",
  "data_format": "<원본 데이터 형식: table/text/mixed>"
}}
"""

            # LLM 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )

            result = json.loads(response.choices[0].message.content)

            # 결과 검증
            header = result.get("header", [])
            data = result.get("data", [])

            if not header or not data:
                return self._create_error(
                    "LLM failed to extract data",
                    partial_data=result
                )

            # 메타데이터 생성
            metadata = ResultMetadata(
                output_schema={
                    "header": "list of column names",
                    "data": "list of data rows (all rows, not sample)",
                    "row_count": "total number of rows",
                    "excluded_rows": "rows that were filtered out",
                    "data_format": "original format"
                },
                access_hints={
                    "primary_result": "data",
                    "all_rows_included": "true - all data rows are included",
                    "ready_for_transform": "true"
                },
                confidence=0.9,
                processing_notes=result.get("processing_notes", "")
            )

            return self._create_success(
                data={
                    "header": header,
                    "data": data,
                    "row_count": len(data),
                    "excluded_rows": result.get("excluded_rows", []),
                    "data_format": result.get("data_format", "unknown"),
                    "source_section": {
                        "index": section.index,
                        "title": section.title
                    }
                },
                metadata=metadata
            )

        except Exception as e:
            return self._create_error(f"FlexibleExtractTool error: {str(e)}")

    def _format_content_for_llm(self, contents: List) -> str:
        """콘텐츠를 LLM에 전달할 형식으로 변환"""
        formatted = []

        for content in contents:
            if content.type == ContentType.TABLE:
                # 테이블 데이터
                table_data = content.data

                if isinstance(table_data, dict):
                    table_elements = table_data.get("table_elements", [])
                elif isinstance(table_data, list):
                    table_elements = table_data
                else:
                    table_elements = []

                # 2D 배열로 변환
                rows = []
                for row in table_elements:
                    if isinstance(row, dict) and "cells" in row:
                        row_texts = [cell.get("text", "") for cell in row.get("cells", [])]
                        rows.append(row_texts)

                formatted.append(f"[TABLE]\n{json.dumps(rows, ensure_ascii=False, indent=2)}\n[/TABLE]")

            elif content.type == ContentType.TEXT:
                # 텍스트 데이터
                formatted.append(f"[TEXT]\n{content.data}\n[/TEXT]")

        return "\n\n".join(formatted)
