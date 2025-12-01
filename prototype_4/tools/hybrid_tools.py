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


class DefinitionSearchTool:
    """
    Definition-aware Search: 정의/명칭/보험종목 정보를 가진 섹션 후보 모으기

    - 여러 개의 정의 관련 섹션을 수집
    - 각 섹션에 간단한 role(kind) 태깅 (core_table / annotation / 기타)
    """

    def __init__(self):
        self.name = "definition_search"
        # 기본 키워드 (정의/명칭/보험종목 중심)
        self.core_title_keywords = ["정의", "명칭", "보험종목"]
        self.core_text_keywords = ["정의", "명칭", "보험종목"]
        # 주석/부가 설명에서 자주 등장하는 단어들
        self.annotation_keywords = ["구성", "간편", "무배당", "단 ", "단,", "다만"]

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        섹션 전체에서 정의 관련 섹션 후보를 수집하고 역할(kind)을 태깅한다.

        Args:
            doc: 원본 문서 (사용하지 않지만 인터페이스 통일용)
            params: {
                "sections": [...]
            }

        Returns:
            ToolResult with data = {
                "definition_candidates": [
                    {"index": 0, "kind": "core_table", "title": "...", "score": 3, ...},
                    ...
                ]
            }
        """
        try:
            sections = params.get("sections", [])

            if not sections:
                return ToolResult(
                    success=False,
                    error="No sections provided",
                    tool_name=self.name
                )

            candidates: List[Dict[str, Any]] = []

            for i, section in enumerate(sections):
                index = section.get("index", i)
                title = section.get("title") or ""
                content = section.get("content") or []

                has_table = False
                has_text = False
                text_fragments: List[str] = []

                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue

                        # 테이블 존재 여부
                        if "table" in item:
                            table = item.get("table") or item.get("table_elements")
                            if isinstance(table, dict):
                                table_elements = table.get("table_elements", [])
                                if table_elements:
                                    has_table = True

                        # 텍스트 미리보기
                        text = item.get("content", "") or item.get("text", "")
                        if isinstance(text, str) and text.strip():
                            has_text = True
                            if len(text_fragments) < 3:
                                text_fragments.append(text.strip()[:150])

                text_preview = "\n".join(text_fragments)
                combined_text = f"{title}\n{text_preview}"

                # "A형은 A_1형과 A_2형으로 나뉩니다" 같은 타입 분할 설명 패턴 탐지
                split_pattern = r"([A-Za-z0-9가-힣]+형)\s*(은|를|이)\s*.*(나뉘|구성|구별|분류|포함)"
                split_pattern_match = bool(re.search(split_pattern, combined_text))

                if split_pattern_match and not has_table:
                    # 테이블은 없지만 타입 분할 설명이 있는 텍스트 섹션 → annotation 후보
                    candidates.append({
                        "index": index,
                        "kind": "text_annotation",
                        "title": title,
                        "has_table": has_table,
                        "has_text": has_text,
                        "score": 1,
                    })
                    # 기존 규칙으로 한 번 더 잡을 필요는 없으니 다음 섹션으로
                    continue

                title_match = any(kw in title for kw in self.core_title_keywords)
                core_text_match = any(kw in combined_text for kw in self.core_text_keywords)
                annotation_match = any(kw in combined_text for kw in self.annotation_keywords)

                # 정의 관련 섹션 후보인지 여부
                is_core_like = title_match or core_text_match
                is_candidate = is_core_like or (has_table and annotation_match)

                if not is_candidate:
                    continue

                # kind 결정
                if has_table and is_core_like:
                    kind = "core_table"
                elif has_table:
                    kind = "related_table"
                else:
                    kind = "text_annotation" if (annotation_match or core_text_match) else "other_text"

                # 간단 점수 (정렬용)
                score = 0
                if title_match:
                    score += 2
                if core_text_match:
                    score += 1
                if has_table:
                    score += 1

                candidates.append({
                    "index": index,
                    "kind": kind,
                    "title": title,
                    "has_table": has_table,
                    "has_text": has_text,
                    "score": score,
                })

            if not candidates:
                return ToolResult(
                    success=False,
                    error="No definition-like sections found",
                    tool_name=self.name
                )

            # 우선순위: score 높은 순, index 낮은 순
            candidates.sort(key=lambda c: (-c["score"], c["index"]))

            return ToolResult(
                success=True,
                data={"definition_candidates": candidates},
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"DefinitionSearchTool error: {str(e)}",
                tool_name=self.name
            )


# ============================================================================
# EXTRACT TOOLS
# ============================================================================

class DefinitionExtractTool:
    """
    [DEPRECATED - Use DefinitionExtractToolV2]

    Definition-aware Extract: definition_candidates + sections 기반으로
    핵심 정의 테이블을 추출하고 표 형태(header, data)로 반환한다.

    - 입력: sections + definition_candidates
    - 동작: core_table 후보를 고르고, 해당 섹션의 테이블을 RuleExtractTool로 파싱
    """

    def __init__(self):
        self.name = "definition_extract"

    def execute(self, doc: Any, params: Dict[str, Any]) -> ToolResult:
        """
        Args:
            doc: 원본 문서 (현재는 직접 사용하지 않음)
            params: {
                "sections": [...],
                "definition_candidates": [...]
            }

        Returns:
            ToolResult with data = {
                "header": [...],
                "data": [[...], ...],
                "extraction_method": "table_parsing",
                "core_candidate": {...}
            }
        """
        try:
            sections = params.get("sections", [])
            candidates = params.get("definition_candidates", [])

            if not sections:
                return ToolResult(
                    success=False,
                    error="No sections provided",
                    tool_name=self.name
                )

            if not candidates:
                return ToolResult(
                    success=False,
                    error="No definition_candidates provided",
                    tool_name=self.name
                )

            # 1) core_table 후보 우선, 없으면 테이블이 있는 어떤 후보라도 사용
            core_candidates = [c for c in candidates if c.get("kind") == "core_table"]
            table_candidates = [c for c in candidates if c.get("kind") in ("core_table", "related_table")]

            if core_candidates:
                core = core_candidates[0]
            elif table_candidates:
                core = table_candidates[0]
            else:
                # 테이블 후보가 전혀 없는 경우: 텍스트 기반 정의 추출 시도
                text_indices: List[int] = []
                for c in candidates:
                    idx = c.get("index")
                    if isinstance(idx, int):
                        text_indices.append(idx)

                text_fragments: List[str] = []
                for idx in text_indices:
                    if idx < 0 or idx >= len(sections):
                        continue
                    section = sections[idx]
                    content = section.get("content") or []
                    if not isinstance(content, list):
                        continue
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        text = item.get("content", "") or item.get("text", "")
                        if isinstance(text, str) and text.strip():
                            text_fragments.append(text.strip())

                if not text_fragments:
                    return ToolResult(
                        success=False,
                        error="No table-like candidates and no text content for definition extraction",
                        tool_name=self.name
                    )

                combined_text = "\n\n".join(text_fragments)

                llm_extractor = LLMExtractTool()
                llm_result = llm_extractor.execute(doc, {
                    "content": combined_text,
                    "content_type": "text",
                    "instruction": "보험 상품의 명칭/보험종목/유형 정보를 표 형태로 추출하세요."
                })

                if not llm_result.success:
                    return ToolResult(
                        success=False,
                        error=f"LLMExtractTool failed: {llm_result.error}",
                        tool_name=self.name
                    )

                llm_data = llm_result.data or {}
                header = llm_data.get("header", [])
                rows = llm_data.get("data", [])

                return ToolResult(
                    success=True,
                    data={
                        "header": header,
                        "data": rows,
                        "extraction_method": llm_data.get("extraction_method", "text_llm")
                    },
                    tool_name=self.name
                )

            index = core.get("index", 0)
            if not isinstance(index, int) or index < 0 or index >= len(sections):
                return ToolResult(
                    success=False,
                    error=f"Core candidate index out of range: {index}",
                    tool_name=self.name
                )

            core_section = sections[index]

            # 2) 해당 섹션에서 테이블 콘텐츠 찾기 (RuleSearchTool의 로직 재사용)
            search_helper = RuleSearchTool()
            content_result = search_helper._find_content(core_section)

            if not content_result or content_result.get("type") != "table":
                return ToolResult(
                    success=False,
                    error="Core section does not contain a valid table",
                    tool_name=self.name
                )

            table = content_result["content"]

            # 3) 테이블을 RuleExtractTool로 파싱
            extract_helper = RuleExtractTool()
            base_result = extract_helper.execute(doc, {"content": table, "content_type": "table"})

            if not base_result.success:
                return ToolResult(
                    success=False,
                    error=f"Base extract failed: {base_result.error}",
                    tool_name=self.name
                )

            data = base_result.data or {}
            header = data.get("header", [])
            rows = data.get("data", [])

            # 4) 같은 섹션의 텍스트(annotation)를 함께 보고
            #    LLM 기반으로 최종 정의 테이블을 재구성할 여지를 준다.
            annotation_fragments: List[str] = []
            section_content = core_section.get("content") or []

            if isinstance(section_content, list):
                for item in section_content:
                    if not isinstance(item, dict):
                        continue
                    # 테이블 본문은 제외하고, 순수 텍스트만 수집
                    table_obj = item.get("table")
                    has_real_table = False
                    if isinstance(table_obj, dict):
                        if table_obj.get("table_elements"):
                            has_real_table = True
                    if has_real_table:
                        continue

                    text = item.get("content", "") or item.get("text", "")
                    if isinstance(text, str) and text.strip():
                        annotation_fragments.append(text.strip())

            if annotation_fragments:
                annotations_text = "\n\n".join(annotation_fragments)
                combined_content = {
                    "base_table": {
                        "header": header,
                        "data": rows
                    },
                    "annotations": annotations_text
                }

                llm_extractor = LLMExtractTool()
                llm_result = llm_extractor.execute(doc, {
                    "content": combined_content,
                    "content_type": "mixed",
                    "instruction": (
                        "JSON의 base_table.header/base_table.data는 기존 정의 테이블이고, "
                        "annotations는 해당 정의에 대한 설명/변경/예외 텍스트입니다. "
                        "annotations를 반영하여 최종 정의 테이블을 header/data 형태로 다시 구성하세요. "
                        "가능하면 컬럼 구조는 유지하고, 값만 필요할 때 수정하거나 추가/제거하세요."
                    )
                })

                if llm_result.success and llm_result.data:
                    llm_data = llm_result.data
                    header = llm_data.get("header", header)
                    rows = llm_data.get("data", rows)

            return ToolResult(
                success=True,
                data={
                    "header": header,
                    "data": rows,
                    "extraction_method": data.get("extraction_method", "table_parsing"),
                    "core_candidate": core
                },
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"DefinitionExtractTool error: {str(e)}",
                tool_name=self.name
            )


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
            header, rows = self._extract_from_cores(sections, core_indices, doc)

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
        self, sections: List[Dict], core_indices: List[int], doc: Any
    ) -> tuple[List[str], List[List[str]]]:
        """
        Extract base table from core sections

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

                    # Try rule-based extraction first
                    extractor = RuleExtractTool()
                    result = extractor.execute(doc, {
                        "content": table,
                        "content_type": "table"
                    })

                    if result.success and result.data:
                        header = result.data.get("header", [])
                        rows = result.data.get("data", [])
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
            llm_extractor = LLMExtractTool()
            result = llm_extractor.execute(doc, {
                "content": combined,
                "content_type": "text",
                "instruction": "보험 상품의 명칭/보험종목/유형 정보를 표 형태로 추출하세요."
            })

            if result.success and result.data:
                return result.data.get("header", []), result.data.get("data", [])

        return [], []

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
            prompt = self._build_classification_prompt(summaries)

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

    def _build_classification_prompt(self, summaries: List[Dict]) -> str:
        """
        Build LLM prompt for section classification

        Args:
            summaries: List of section summaries

        Returns:
            str: Classification prompt
        """
        prompt = """당신은 보험 약관 문서의 섹션을 분류하는 전문가입니다.

**임무**: 주어진 모든 섹션을 4가지 카테고리로 분류하세요.

**카테고리 정의**:

1. **definition_core** (핵심 정의 섹션)
   - 보험 상품의 명칭, 보험종목, 유형 등을 정의하는 **표(table)** 형태의 섹션
   - 예시 제목: "보험의 명칭", "보험종목", "상품 구성", "Product Definition"
   - 특징: 테이블 형태로 구조화된 정의 데이터

2. **definition_annotation** (정의 주석/설명 섹션)
   - 정의에 대한 **텍스트 설명/주석**을 담고 있는 섹션
   - 예시 내용: "※ 이 보험은...", "주) 보험종목은...", 각주, 참고사항
   - 특징: definition_core를 보완하는 텍스트 정보

3. **condition** (계약조건 섹션)
   - 가입조건, 계약조건, 보장내용 등을 담은 섹션
   - 예시 제목: "가입조건", "보장내용", "계약조건"
   - 특징: 정의가 아닌 계약 관련 정보

4. **other** (기타 무관한 섹션)
   - 위 3가지에 해당하지 않는 모든 섹션
   - 예시: 목차, 서문, 부록 등

**중요 규칙**:
- 제목이 표준적이지 않아도(예: "상품 구성") 의미상 정의 섹션이면 definition_core로 분류
- 제목이 없어도 내용을 보고 분류
- 영어/중국어 문서도 의미를 파악하여 분류
- 모든 섹션은 정확히 하나의 카테고리에 속해야 함

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
