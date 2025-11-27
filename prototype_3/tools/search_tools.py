"""
Search Tools: 유연한 검색 도구들

문서 구조에 독립적으로 정의 섹션을 찾는 도구들입니다.
"""

from typing import Dict, List, Any, Optional
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from .base import FlexibleTool, ToolType
from core.flexible_result import FlexibleToolResult, ResultStatus, ResultMetadata
from core.document_accessor import DocumentAccessor


class KeywordSearchTool(FlexibleTool):
    """
    키워드 기반 빠른 검색 도구

    특징:
        - LLM 호출 없이 빠른 검색
        - 키워드 매칭으로 섹션 찾기
        - DocumentAccessor 활용

    파라미터:
        - keywords: 검색할 키워드 리스트 (optional)
        - require_table: 테이블 포함 여부 필터 (optional, default: False)
        - limit: 최대 결과 수 (optional)
    """

    def get_type(self) -> ToolType:
        return ToolType.SEARCH

    def get_description(self) -> str:
        return "Fast keyword-based search for definition sections using DocumentAccessor"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "keywords": {
                "type": "list",
                "description": "Keywords to search in section titles",
                "required": False,
                "default": ["정의", "용어", "명칭", "보험종목"]
            },
            "require_table": {
                "type": "boolean",
                "description": "Filter sections that contain tables",
                "required": False,
                "default": False
            },
            "limit": {
                "type": "int",
                "description": "Maximum number of results",
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

            # 파라미터 추출
            keywords = params.get("keywords", ["정의", "용어", "명칭", "보험종목"])
            require_table = params.get("require_table", False)
            limit = params.get("limit")

            # 키워드로 섹션 검색
            criteria = {"title_contains": keywords}
            if require_table:
                criteria["has_table"] = True

            found_sections = acc.find_sections(criteria, limit)

            if not found_sections:
                return self._create_error(
                    f"No sections found matching keywords: {keywords}"
                )

            # 결과 포맷팅
            results = []
            for section in found_sections:
                results.append({
                    "section_index": section.index,
                    "title": section.title,
                    "access_path": section.access_path,
                    "content_count": len(section.content_items),
                    "metadata": section.metadata
                })

            # 메타데이터 생성
            metadata = ResultMetadata(
                output_schema={
                    "found_sections": "list of matched sections",
                    "primary_match": "first matched section",
                    "total_matches": "number of matches"
                },
                access_hints={
                    "primary_result": "found_sections[0]",
                    "how_to_use_access_path": "Use DocumentAccessor to navigate to this section",
                    "next_step_example": "Extract content from found_sections[0] using access_path"
                },
                confidence=1.0 if len(found_sections) > 0 else 0.5,
                processing_notes=f"Found {len(results)} sections using keywords: {keywords}"
            )

            return self._create_success(
                data={
                    "found_sections": results,
                    "primary_match": results[0] if results else None,
                    "total_matches": len(results),
                    "search_method": "keyword_matching",
                    "keywords_used": keywords
                },
                metadata=metadata
            )

        except Exception as e:
            return self._create_error(f"KeywordSearchTool error: {str(e)}")


class FlexibleSearchTool(FlexibleTool):
    """
    LLM 기반 유연한 검색 도구

    특징:
        - 문서 전체를 LLM이 분석
        - 문맥 기반 섹션 찾기
        - 비표준 제목도 인식 가능
        - 유연한 출력 형식

    파라미터:
        - search_goal: 검색 목표 (required)
        - instruction: 추가 지시사항 (optional)
        - max_results: 최대 결과 수 (optional)
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_type(self) -> ToolType:
        return ToolType.SEARCH

    def get_description(self) -> str:
        return "LLM-based flexible search with context understanding for any document structure"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "search_goal": {
                "type": "string",
                "description": "What to search for (e.g., '보험 상품 정의 섹션')",
                "required": True
            },
            "instruction": {
                "type": "string",
                "description": "Additional instructions for LLM",
                "required": False
            },
            "max_results": {
                "type": "int",
                "description": "Maximum number of results",
                "required": False,
                "default": 3
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

            # 파라미터 추출
            search_goal = params.get("search_goal")
            if not search_goal:
                return self._create_error("search_goal parameter is required")

            instruction = params.get("instruction", "")
            max_results = params.get("max_results", 3)

            # 문서 요약 정보 생성
            all_sections = acc.get_all_sections()
            doc_summary = acc.get_summary()

            # 섹션 정보를 LLM에 제공
            sections_info = []
            for section in all_sections:
                has_table = any(
                    "table" in str(item.keys()).lower()
                    for item in section.content_items
                    if isinstance(item, dict)
                )

                sections_info.append({
                    "index": section.index,
                    "title": section.title,
                    "content_items_count": len(section.content_items),
                    "has_table": has_table,
                    "access_path": section.access_path
                })

            # LLM 프롬프트
            prompt = f"""다음은 보험 문서의 전체 구조입니다.

문서 형식: {doc_summary['format']}
총 섹션 수: {doc_summary['total_sections']}

모든 섹션 정보:
{json.dumps(sections_info, ensure_ascii=False, indent=2)}

**검색 목표**: {search_goal}

{f"**추가 지시사항**: {instruction}" if instruction else ""}

**요구사항**:
1. 검색 목표에 가장 적합한 섹션을 찾으세요
2. 최대 {max_results}개까지 반환
3. 각 섹션에 대해 선택 이유를 설명하세요
4. access_path를 정확히 포함하세요

다음 JSON 형식으로 반환:
{{
  "found_sections": [
    {{
      "section_index": <인덱스>,
      "title": "<제목>",
      "access_path": <접근 경로>,
      "reasoning": "<선택 이유>",
      "confidence": <0.0~1.0>
    }},
    ...
  ],
  "search_strategy": "<사용한 검색 전략>",
  "total_matches": <매칭 개수>
}}

섹션을 찾지 못한 경우:
{{
  "found_sections": [],
  "search_strategy": "<시도한 전략>",
  "total_matches": 0,
  "failure_reason": "<실패 이유>"
}}
"""

            # LLM 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)

            # 결과 검증
            found_sections = result.get("found_sections", [])

            if not found_sections:
                return self._create_error(
                    result.get("failure_reason", "No sections found"),
                    partial_data=result
                )

            # 메타데이터 생성
            avg_confidence = sum(s.get("confidence", 0.5) for s in found_sections) / len(found_sections)

            metadata = ResultMetadata(
                output_schema={
                    "found_sections": "list of matched sections with reasoning",
                    "search_strategy": "strategy used by LLM",
                    "total_matches": "number of matches"
                },
                access_hints={
                    "primary_result": "found_sections[0]",
                    "how_to_use": "Each section includes access_path for document navigation",
                    "confidence_scores": "Each result has individual confidence score"
                },
                confidence=avg_confidence,
                processing_notes=f"LLM search strategy: {result.get('search_strategy', 'N/A')}"
            )

            return self._create_success(
                data=result,
                metadata=metadata
            )

        except Exception as e:
            return self._create_error(f"FlexibleSearchTool error: {str(e)}")
