"""
Document Accessor: 문서 구조에 독립적인 접근 계층

모든 형태의 문서 구조를 자동으로 파악하고 일관된 인터페이스로 접근을 제공합니다.

핵심 기능:
    - 자동 구조 감지
    - 통일된 섹션 접근
    - 콘텐츠 타입 자동 판별
    - 유연한 검색 및 필터링
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum


class DocumentFormat(Enum):
    """문서 구조 형식"""
    STANDARD_ELEMENTS = "standard_elements"  # doc[0]["elements"]
    PAGES = "pages"  # {"pages": [...]}
    SECTIONS = "sections"  # {"sections": [...]}
    DOCUMENT_SECTIONS = "document_sections"  # {"document": {"sections": [...]}}
    NESTED = "nested"  # 복잡한 중첩 구조
    UNKNOWN = "unknown"


class ContentType(Enum):
    """콘텐츠 타입"""
    TABLE = "table"
    TEXT = "text"
    LIST = "list"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class Section:
    """
    구조에 독립적인 섹션 표현

    Attributes:
        index: 섹션 인덱스 (문서 전체에서의 순서)
        title: 섹션 제목
        content_items: 콘텐츠 항목들 (paragraph, table 등)
        metadata: 추가 메타데이터
        access_path: 원본 문서에서의 접근 경로
        content_summary: 콘텐츠 형식 요약 정보
    """
    index: int
    title: str
    content_items: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    access_path: List[Union[str, int]]  # 예: ["document", "sections", 0, "content"]
    content_summary: Dict[str, Any] = None  # 새로 추가


@dataclass
class Content:
    """
    구조에 독립적인 콘텐츠 표현

    Attributes:
        type: 콘텐츠 타입 (table, text, list 등)
        data: 실제 데이터
        source_section: 출처 섹션
        metadata: 추가 메타데이터
    """
    type: ContentType
    data: Any
    source_section: Section
    metadata: Dict[str, Any]


class DocumentAccessor:
    """
    문서 구조에 독립적인 접근자

    문서의 구조를 자동으로 파악하고 통일된 인터페이스로 접근을 제공합니다.

    사용 예시:
        accessor = DocumentAccessor(doc)

        # 자동 구조 감지
        format = accessor.detect_format()

        # 모든 섹션 가져오기
        sections = accessor.get_all_sections()

        # 조건으로 섹션 찾기
        found = accessor.find_sections(criteria={"title_contains": "정의"})

        # 콘텐츠 추출
        content = accessor.extract_content(section, content_type="table")
    """

    def __init__(self, document: Any):
        """
        Args:
            document: 파싱된 문서 (어떤 구조든 가능)
        """
        self.raw_document = document
        self.format = self.detect_format()
        self._sections_cache = None

    def detect_format(self) -> DocumentFormat:
        """
        문서 구조 형식 자동 감지

        Returns:
            DocumentFormat: 감지된 형식
        """
        if not self.raw_document:
            return DocumentFormat.UNKNOWN

        # List 형태인 경우 첫 번째 요소 확인
        if isinstance(self.raw_document, list):
            if len(self.raw_document) > 0:
                first = self.raw_document[0]
                if isinstance(first, dict):
                    if "elements" in first:
                        return DocumentFormat.STANDARD_ELEMENTS
                    elif "pages" in first:
                        return DocumentFormat.PAGES

        # Dict 형태인 경우
        if isinstance(self.raw_document, dict):
            if "pages" in self.raw_document:
                return DocumentFormat.PAGES
            elif "sections" in self.raw_document:
                return DocumentFormat.SECTIONS
            elif "document" in self.raw_document:
                if isinstance(self.raw_document["document"], dict):
                    if "sections" in self.raw_document["document"]:
                        return DocumentFormat.DOCUMENT_SECTIONS
            elif "elements" in self.raw_document:
                return DocumentFormat.STANDARD_ELEMENTS

        return DocumentFormat.NESTED

    def get_all_sections(self) -> List[Section]:
        """
        문서의 모든 섹션 가져오기

        Returns:
            List[Section]: 모든 섹션 리스트
        """
        if self._sections_cache is not None:
            return self._sections_cache

        sections = []

        if self.format == DocumentFormat.STANDARD_ELEMENTS:
            sections = self._extract_standard_elements()
        elif self.format == DocumentFormat.PAGES:
            sections = self._extract_pages()
        elif self.format == DocumentFormat.SECTIONS:
            sections = self._extract_sections()
        elif self.format == DocumentFormat.DOCUMENT_SECTIONS:
            sections = self._extract_document_sections()
        elif self.format == DocumentFormat.NESTED:
            sections = self._extract_nested()

        self._sections_cache = sections
        return sections

    def _extract_standard_elements(self) -> List[Section]:
        """Standard elements 형식에서 섹션 추출"""
        sections = []

        # doc[0]["elements"] 형태
        if isinstance(self.raw_document, list) and len(self.raw_document) > 0:
            elements = self.raw_document[0].get("elements", [])
        elif isinstance(self.raw_document, dict):
            elements = self.raw_document.get("elements", [])
        else:
            return sections

        for idx, element in enumerate(elements):
            content_items = element.get("paragraphs", [])
            section = Section(
                index=idx,
                title=element.get("title", ""),
                content_items=content_items,
                metadata={
                    "original_element": element
                },
                access_path=[0, "elements", idx] if isinstance(self.raw_document, list) else ["elements", idx],
                content_summary=self._analyze_content_summary(content_items)
            )
            sections.append(section)

        return sections

    def _extract_pages(self) -> List[Section]:
        """Pages 형식에서 섹션 추출"""
        sections = []

        if isinstance(self.raw_document, dict):
            pages = self.raw_document.get("pages", [])
        else:
            pages = []

        for idx, page in enumerate(pages):
            # Page를 하나의 섹션으로 취급
            content_items = page.get("content", []) if isinstance(page, dict) else []
            if not isinstance(content_items, list):
                content_items = [content_items]

            section = Section(
                index=idx,
                title=page.get("title", f"Page {idx + 1}") if isinstance(page, dict) else f"Page {idx + 1}",
                content_items=content_items,
                metadata={
                    "page_number": idx + 1,
                    "original_page": page
                },
                access_path=["pages", idx],
                content_summary=self._analyze_content_summary(content_items)
            )
            sections.append(section)

        return sections

    def _extract_sections(self) -> List[Section]:
        """Sections 형식에서 섹션 추출"""
        sections = []

        if isinstance(self.raw_document, dict):
            sections_data = self.raw_document.get("sections", [])
        else:
            sections_data = []

        for idx, sec in enumerate(sections_data):
            content_items = sec.get("content", []) if isinstance(sec, dict) else []
            section = Section(
                index=idx,
                title=sec.get("title", "") if isinstance(sec, dict) else "",
                content_items=content_items,
                metadata={
                    "original_section": sec
                },
                access_path=["sections", idx],
                content_summary=self._analyze_content_summary(content_items)
            )
            sections.append(section)

        return sections

    def _extract_document_sections(self) -> List[Section]:
        """Document.sections 형식에서 섹션 추출"""
        sections = []

        doc = self.raw_document.get("document", {})
        sections_data = doc.get("sections", [])

        for idx, sec in enumerate(sections_data):
            content_items = sec.get("content", []) if isinstance(sec, dict) else []
            section = Section(
                index=idx,
                title=sec.get("title", "") if isinstance(sec, dict) else "",
                content_items=content_items,
                metadata={
                    "original_section": sec
                },
                access_path=["document", "sections", idx],
                content_summary=self._analyze_content_summary(content_items)
            )
            sections.append(section)

        return sections

    def _extract_nested(self) -> List[Section]:
        """복잡한 중첩 구조에서 섹션 추출 (재귀적 탐색)"""
        sections = []

        def recursive_find(obj, path=[]):
            """재귀적으로 섹션 후보를 찾음"""
            if isinstance(obj, dict):
                # 섹션처럼 보이는 구조 확인
                if "title" in obj or "heading" in obj or "name" in obj:
                    title = obj.get("title") or obj.get("heading") or obj.get("name", "")
                    content_items = []

                    # 콘텐츠 찾기
                    for key in ["content", "paragraphs", "items", "data"]:
                        if key in obj:
                            content_items = obj[key] if isinstance(obj[key], list) else [obj[key]]
                            break

                    sections.append(Section(
                        index=len(sections),
                        title=str(title),
                        content_items=content_items,
                        metadata={"original_obj": obj},
                        access_path=path.copy(),
                        content_summary=self._analyze_content_summary(content_items)
                    ))

                # 재귀적으로 탐색
                for key, value in obj.items():
                    recursive_find(value, path + [key])

            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    recursive_find(item, path + [idx])

        recursive_find(self.raw_document, [])
        return sections

    def find_sections(
        self,
        criteria: Dict[str, Any] = None,
        limit: Optional[int] = None
    ) -> List[Section]:
        """
        조건에 맞는 섹션 찾기

        Args:
            criteria: 검색 조건
                - title_contains: 제목에 포함되어야 할 키워드(들)
                - title_equals: 제목이 정확히 일치
                - has_table: 테이블 포함 여부
                - has_content_type: 특정 콘텐츠 타입 포함
                - index_range: 인덱스 범위 (start, end)
            limit: 최대 반환 개수

        Returns:
            List[Section]: 조건에 맞는 섹션들
        """
        if criteria is None:
            criteria = {}

        all_sections = self.get_all_sections()
        matched = []

        for section in all_sections:
            if self._matches_criteria(section, criteria):
                matched.append(section)
                if limit and len(matched) >= limit:
                    break

        return matched

    def _matches_criteria(self, section: Section, criteria: Dict[str, Any]) -> bool:
        """섹션이 조건에 맞는지 확인"""
        # title_contains
        if "title_contains" in criteria:
            keywords = criteria["title_contains"]
            if isinstance(keywords, str):
                keywords = [keywords]
            if not any(kw in section.title for kw in keywords):
                return False

        # title_equals
        if "title_equals" in criteria:
            if section.title != criteria["title_equals"]:
                return False

        # has_table
        if "has_table" in criteria:
            has_table = any("table" in str(item.keys()).lower() for item in section.content_items if isinstance(item, dict))
            if has_table != criteria["has_table"]:
                return False

        # index_range
        if "index_range" in criteria:
            start, end = criteria["index_range"]
            if not (start <= section.index < end):
                return False

        return True

    def extract_content(
        self,
        section: Section,
        content_type: Optional[str] = None
    ) -> List[Content]:
        """
        섹션에서 콘텐츠 추출

        Args:
            section: 대상 섹션
            content_type: 추출할 콘텐츠 타입 ("table", "text", "list" 등)
                         None이면 모든 타입 추출

        Returns:
            List[Content]: 추출된 콘텐츠들
        """
        contents = []

        for item in section.content_items:
            if not isinstance(item, dict):
                continue

            # 콘텐츠 타입 자동 감지
            detected_type = self._detect_content_type(item)

            # 타입 필터링
            if content_type and detected_type.value != content_type:
                continue

            # 데이터 추출
            data = self._extract_data_from_item(item, detected_type)

            content = Content(
                type=detected_type,
                data=data,
                source_section=section,
                metadata={
                    "original_item": item
                }
            )
            contents.append(content)

        return contents

    def _analyze_content_summary(self, content_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        콘텐츠 요약 정보 생성

        Args:
            content_items: 섹션의 콘텐츠 항목들

        Returns:
            Dict: 콘텐츠 요약 정보
                - has_table: bool
                - has_text: bool
                - table_count: int
                - text_count: int
                - primary_type: ContentType
                - content_preview: str (최대 200자)
        """
        has_table = False
        has_text = False
        table_count = 0
        text_count = 0
        text_preview = []

        for item in content_items:
            if not isinstance(item, dict):
                continue

            # 테이블 감지
            if "table" in item or "table_elements" in item:
                has_table = True
                table_count += 1
                # 테이블이 실제로 데이터가 있는지 확인
                table = item.get("table", {})
                if isinstance(table, dict):
                    table_elements = table.get("table_elements", [])
                    if not table_elements:  # 빈 테이블이면 카운트 안함
                        table_count -= 1
                        has_table = has_table and table_count > 0

            # 텍스트 감지
            text_content = item.get("content") or item.get("text", "")
            if isinstance(text_content, str) and text_content.strip():
                has_text = True
                text_count += 1
                # 텍스트 미리보기 수집 (최대 100자씩, 최대 3개)
                if len(text_preview) < 3:
                    preview = text_content.strip()[:100]
                    if preview:
                        text_preview.append(preview)

        # Primary type 결정
        if has_table and has_text:
            primary_type = ContentType.MIXED
        elif has_table:
            primary_type = ContentType.TABLE
        elif has_text:
            primary_type = ContentType.TEXT
        else:
            primary_type = ContentType.UNKNOWN

        return {
            "has_table": has_table,
            "has_text": has_text,
            "table_count": table_count,
            "text_count": text_count,
            "primary_type": primary_type.value,
            "content_preview": "\n".join(text_preview)  # 최대 3개 미리보기
        }

    def _detect_content_type(self, item: Dict[str, Any]) -> ContentType:
        """콘텐츠 타입 자동 감지"""
        # 테이블 확인
        if "table" in item or "table_elements" in item:
            return ContentType.TABLE

        # 텍스트 확인
        if "text" in item or "content" in item:
            return ContentType.TEXT

        # 리스트 확인
        if "items" in item or "list" in item:
            return ContentType.LIST

        # 혼합형 (여러 타입 포함)
        type_count = sum([
            "table" in item,
            "text" in item,
            "items" in item
        ])
        if type_count > 1:
            return ContentType.MIXED

        return ContentType.UNKNOWN

    def _extract_data_from_item(self, item: Dict[str, Any], content_type: ContentType) -> Any:
        """항목에서 실제 데이터 추출"""
        if content_type == ContentType.TABLE:
            return item.get("table") or item.get("table_elements")
        elif content_type == ContentType.TEXT:
            return item.get("text") or item.get("content")
        elif content_type == ContentType.LIST:
            return item.get("items") or item.get("list")
        elif content_type == ContentType.MIXED:
            return item
        else:
            return item

    def get_summary(self) -> Dict[str, Any]:
        """
        문서 구조 요약 정보

        Returns:
            Dict: 요약 정보
        """
        sections = self.get_all_sections()

        # 형식별 섹션 분류
        sections_by_format = {
            "table_only": [],
            "text_only": [],
            "mixed": [],
            "unknown": []
        }

        for s in sections:
            if s.content_summary:
                primary_type = s.content_summary.get("primary_type", "unknown")
                if primary_type == "table":
                    sections_by_format["table_only"].append(s.index)
                elif primary_type == "text":
                    sections_by_format["text_only"].append(s.index)
                elif primary_type == "mixed":
                    sections_by_format["mixed"].append(s.index)
                else:
                    sections_by_format["unknown"].append(s.index)

        return {
            "format": self.format.value,
            "total_sections": len(sections),
            "sections_with_tables": sum(
                1 for s in sections
                if s.content_summary and s.content_summary.get("has_table", False)
            ),
            "sections_with_text": sum(
                1 for s in sections
                if s.content_summary and s.content_summary.get("has_text", False)
            ),
            "section_titles": [s.title for s in sections],
            "sections_by_format": sections_by_format  # 새로 추가
        }
