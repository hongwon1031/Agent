"""
LLM-based Document Structure Analyzer

문서 구조를 LLM이 자동으로 분석합니다.
- 어떤 형식의 문서든 처리 가능
- 고정된 스키마 가정 없음
- 섹션, 테이블, 콘텐츠 위치 자동 파악
"""

import json
import os
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv


class LLMDocumentAnalyzer:
    """
    LLM 기반 문서 구조 분석기

    역할:
        - 문서의 최상위 구조 타입 파악
        - 섹션/페이지 접근 경로 찾기
        - 제목, 콘텐츠 필드명 식별
        - 테이블 데이터 위치 패턴 분석
    """

    def __init__(self):
        """Initialize OpenAI client"""
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def analyze(self, doc: Any) -> Dict[str, Any]:
        """
        문서 구조를 자동으로 분석

        Args:
            doc: 원본 문서 (어떤 형식이든 가능)

        Returns:
            Dict: 구조 분석 결과
                {
                    "structure_type": "list" | "dict" | "nested",
                    "sections_path": ["key1", "key2", ...],
                    "title_field": "field_name",
                    "content_field": "field_name",
                    "table_patterns": [...],
                    "sample_section": {...},
                    "total_sections": int,
                    "confidence": float
                }
        """
        # 문서를 JSON 문자열로 변환 (일부만)
        doc_sample = self._get_document_sample(doc)

        prompt = f"""다음 JSON 문서의 구조를 분석하세요.

문서 샘플:
{doc_sample}

**분석 목표**:
이 문서에서 "섹션"(페이지, 챕터 등)들을 어떻게 접근할 수 있는지 파악하세요.

**분석 항목**:
1. structure_type: 최상위 구조 타입
   - "list_of_dicts": 리스트 안에 딕셔너리들 (예: [{{...}}, {{...}}])
   - "dict_with_list": 딕셔너리의 특정 키에 리스트 (예: {{"elements": [...]}})
   - "nested": 복잡한 중첩 구조

2. sections_path: 섹션들에 접근하는 경로 (순서대로)
   - 예: ["elements"] → doc[0]["elements"]
   - 예: ["pages"] → doc["pages"]
   - 예: ["document", "sections"] → doc["document"]["sections"]

3. title_field: 각 섹션의 제목을 담고 있는 필드명
   - 예: "title", "heading", "name", "section_title"

4. content_field: 각 섹션의 콘텐츠를 담고 있는 필드명
   - 예: "paragraphs", "content", "items", "blocks"

5. table_patterns: 테이블 데이터가 있을 수 있는 패턴들
   - 예: ["table", "table_elements"]
   - 예: ["data", "rows"]

6. total_sections_estimate: 전체 섹션 수 (대략)

7. sample_section: 첫 번째 섹션 예시 (필드명 확인용)

**중요**:
- sections_path는 실제 접근 가능한 경로여야 함
- 모든 필드명은 실제 문서에 존재하는 것이어야 함

다음 JSON 형식으로 반환:
{{
  "structure_type": "...",
  "sections_path": ["...", "..."],
  "title_field": "...",
  "content_field": "...",
  "table_patterns": ["...", "..."],
  "total_sections_estimate": 10,
  "sample_section": {{...}},
  "confidence": 0.95,
  "reasoning": "분석 근거"
}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)

            # Verify result
            if not self._verify_analysis(result, doc):
                return {
                    "error": "Analysis verification failed",
                    "llm_result": result
                }

            return result

        except Exception as e:
            return {
                "error": f"Analysis failed: {str(e)}"
            }

    def _get_document_sample(self, doc: Any, max_chars: int = 3000) -> str:
        """
        문서의 샘플 추출 (LLM 입력용)

        너무 큰 문서는 일부만 보냄
        """
        doc_str = json.dumps(doc, ensure_ascii=False, indent=2)

        if len(doc_str) > max_chars:
            # 문서가 크면 일부만
            doc_str = doc_str[:max_chars] + "\n... (truncated)"

        return doc_str

    def _verify_analysis(self, analysis: Dict[str, Any], doc: Any) -> bool:
        """
        LLM 분석 결과가 실제로 문서에서 작동하는지 검증

        Args:
            analysis: LLM이 반환한 분석 결과
            doc: 원본 문서

        Returns:
            bool: 검증 성공 여부
        """
        try:
            # sections_path로 실제 접근 시도
            sections = self._navigate_path(doc, analysis["sections_path"])

            if not sections:
                return False

            # 리스트여야 함
            if not isinstance(sections, list):
                return False

            # 섹션이 하나 이상 있어야 함
            if len(sections) == 0:
                return False

            # 첫 번째 섹션에서 title_field 확인
            first_section = sections[0]
            if isinstance(first_section, dict):
                title_field = analysis.get("title_field")
                if title_field and title_field not in first_section:
                    return False

            return True

        except Exception as e:
            print(f"[Verification Error] {e}")
            return False

    def _navigate_path(self, obj: Any, path: List[str]) -> Any:
        """
        경로를 따라 객체 탐색

        Args:
            obj: 시작 객체
            path: 탐색 경로 (예: ["elements", "paragraphs"])

        Returns:
            탐색 결과 객체
        """
        current = obj

        for key in path:
            if isinstance(current, list):
                # 리스트인 경우 첫 번째 요소 접근
                if len(current) > 0:
                    current = current[0]
                else:
                    return None

            if isinstance(current, dict):
                if key in current:
                    current = current[key]
                else:
                    return None
            else:
                return None

        return current

    def get_sections(self, doc: Any, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        분석 결과를 바탕으로 실제 섹션들을 추출

        Args:
            doc: 원본 문서
            analysis: analyze() 결과

        Returns:
            List[Dict]: 섹션 리스트, 각 섹션은:
                {
                    "index": int,
                    "title": str,
                    "content": Any,
                    "raw": Dict  # 원본 섹션 데이터
                }
        """
        sections_path = analysis["sections_path"]
        title_field = analysis.get("title_field", "title")
        content_field = analysis.get("content_field", "content")

        raw_sections = self._navigate_path(doc, sections_path)

        if not raw_sections or not isinstance(raw_sections, list):
            return []

        result = []
        for idx, raw_section in enumerate(raw_sections):
            if not isinstance(raw_section, dict):
                continue

            section = {
                "index": idx,
                "title": raw_section.get(title_field, f"Section {idx}"),
                "content": raw_section.get(content_field, []),
                "raw": raw_section
            }
            result.append(section)

        return result

    def find_tables(self, section: Dict[str, Any], analysis: Dict[str, Any]) -> List[Any]:
        """
        섹션에서 테이블 데이터 찾기

        Args:
            section: get_sections()로 얻은 섹션
            analysis: analyze() 결과

        Returns:
            List: 찾은 테이블들
        """
        table_patterns = analysis.get("table_patterns", ["table", "table_elements"])
        content = section["content"]

        tables = []

        # content가 리스트인 경우 (paragraphs 등)
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    for pattern in table_patterns:
                        if pattern in item:
                            tables.append(item[pattern])

        # content가 딕셔너리인 경우
        elif isinstance(content, dict):
            for pattern in table_patterns:
                if pattern in content:
                    tables.append(content[pattern])

        return tables
