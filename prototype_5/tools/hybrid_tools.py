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

            prompt = f"""다음 콘텐츠에서 구조화된 데이터를 추출하세요 (형식: {content_type}).

            **콘텐츠**:
            {content_str}

            **추출 지시사항(Extraction Instructions)**:
            {instruction if instruction else "콘텐츠에서 구조화된 데이터를 추출하여 header와 data 행을 갖는 테이블 형태로 정리하세요."}

            **일반 가이드라인(General Guidelines)**:
            1. table 형식인 경우: 행과 열을 파싱하세요.
            2. text 형식인 경우: 계층 구조를 파악한 뒤 테이블 형태로 평탄화(flatten)하세요.
            3. header 행과 data 행을 명확히 구분하세요.
            4. 특수 문자는 가능한 한 정규화(normalize)하세요.

            **출력 형식(Output Format)** (JSON):
            {{
            "header": ["Column1", "Column2", ...],
            "data": [
                ["value1", "value2", ...],
                ...
            ],
            "extraction_method": "table" 또는 "text",
            "notes": "처리 과정 및 참고 사항"
            }}

            위 지시사항에 따라 데이터를 추출하세요:"""


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

            **일반 규칙(General Rules)**:
            1. **컬럼 단위 기본 구분자(column-wise primary delimiter) 탐지**:
            셀 값을 분리하기 전에, 먼저 해당 컬럼 전체를 관찰하세요:
            - 어떤 구분자(`/`, `,` 등)가 더 자주 등장하는지 확인합니다.
            - 더 자주 등장하는 구분자가 **기본 구분자(primary delimiter)**이며, 이 구분자로 split 합니다.
            - 덜 등장하는 구분자는 **내용의 일부**로 취급하고, 그 기준으로는 split 하지 않습니다.

            예시 로직:
            - 해당 컬럼의 대부분 값에 `/`가 쓰이면 → 기본 구분자는 `/`
            - 대부분 값에 `,`가 쓰이면 → 기본 구분자는 `,`
            - 혼합된 경우: 컬럼 내 모든 셀에서 구분자 등장 횟수를 세어 비교

            2. (지시사항에 별도 언급이 없는 한) 줄바꿈과 공백은 제거(strip)하세요.
            3. 각 행(row)은 서로 독립적으로 처리하세요.

            **출력 형식(Output Format)** (JSON):
            {{
            "parsed_rows": [
                [
                ["value1"],
                ["value2_option1", "value2_option2"],
                ["value3_option1", "value3_option2", "value3_option3"]
                ],
                ...
            ]
            }}

            - 각 행(row)은 여러 셀(cell)로 이루어진 리스트입니다.
            - 각 셀은 분리된 옵션들의 리스트입니다.
            - 한 행의 셀 개수는 항상 header 길이와 같아야 합니다.

            **예시(Example)**:
            Input:
            Header: ["Name", "Type", "Category"]
            Data: [["Product A", "Standard", "Cat1/Cat2/Cat3"]]

            Output:
            {{
            "parsed_rows": [
                [
                ["Product A"],
                ["Standard"],
                ["Cat1", "Cat2", "Cat3"]
                ]
            ]
            }}
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
        Classify all sections into semantic categories

        Args:
            params:
                sections: list[dict] - All sections from DocumentAccessor
                instruction: str - Classification instruction with:
                    - Domain context
                    - Category definitions
                    - Classification criteria
                    (If not provided, uses default 4-way insurance classification)

        Returns:
            ToolResult with data:
                {
                    "category_1": [int] - Section indices,
                    "category_2": [int] - Section indices,
                    ...
                    "reasoning": str - Classification reasoning
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
            if instruction:
                # Use generalized prompt with instruction
                prompt = self._build_classification_prompt_v2(summaries, instruction)
            else:
                # Fallback to legacy insurance-specific prompt
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
            # If instruction provided, extract expected categories from it
            # Otherwise use legacy 4-way classification
            if instruction:
                # Flexible validation: check that result has list values
                # Categories are defined by instruction, not hardcoded
                if not isinstance(result, dict):
                    return ToolResult(
                        success=False,
                        error="LLM response must be a JSON object",
                        tool_name=self.name
                    )

                # Check that all values are lists
                for key, value in result.items():
                    if key == "reasoning":
                        continue  # reasoning is string
                    if not isinstance(value, list):
                        return ToolResult(
                            success=False,
                            error=f"Category '{key}' must be a list of section indices",
                            tool_name=self.name
                        )
            else:
                # Legacy validation: expect 4-way classification
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
        Section에서 LLM이 이해할 수 있을 정도의 요약 텍스트를 만든다.
        - 테이블: header(컬럼 이름) + 첫 행 값
        - 텍스트: type == "text" 인 항목의 content
        """
        content = section.get("content", [])
        if not content:
            return ""

        texts = []

        for item in content:
            if isinstance(item, dict):
                # 1) 테이블 요약: table_elements 기반
                if "table" in item:
                    table = item.get("table") or {}
                    elements = table.get("table_elements") or []
                    if elements and isinstance(elements[0], dict):
                        first_row = elements[0]
                        headers = list(first_row.keys())
                        # 헤더 + 첫 행 값 일부만 사용
                        header_part = ", ".join(headers[:3])
                        value_part = ", ".join(str(first_row.get(h, "")) for h in headers[:3])
                        texts.append(f"[Table: {header_part} | {value_part}]")

                # 2) 텍스트 요약: type == "text" 인 항목의 content
                if item.get("type") == "text":
                    text = item.get("content") or item.get("text") or ""
                    if text and isinstance(text, str):
                        texts.append(text.strip())

            elif isinstance(item, str):
                texts.append(item.strip())

        preview = " ".join(t for t in texts if t)
        if len(preview) > max_chars:
            preview = preview[:max_chars] + "..."
        print(f'preview : {preview}')
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

    def _build_classification_prompt_v2(self, summaries: List[Dict], instruction: str) -> str:
        """
        Build domain-agnostic classification prompt with instruction injection

        Args:
            summaries: List of section summaries
            instruction: Domain-specific instruction from Planner containing:
                - Domain context
                - Category definitions
                - Classification criteria
                - Expected output format

        Returns:
            str: Classification prompt
        """
        prompt = f"""당신은 문서의 섹션을 분류하는 분류기입니다.

**Task**: 아래에 주어진 도메인 컨텍스트와 기준에 따라, 모든 섹션을 의미(semantic) 기반 카테고리로 분류하세요.

**도메인별 분류 지시사항(Domain-Specific Classification Instructions)**:
{instruction}

**입력 섹션(Input Sections)**:

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

**중요(Important)**:
- 단순한 형식(table vs text)이 아니라 **의미(semantic)**를 기준으로 분류하세요.
- 모든 섹션은 정확히 하나의 카테고리에만 속해야 합니다.
- 위 instruction에서 지정한 카테고리 이름만 사용하세요.
- 각 분류에 대한 간단한 근거(reasoning)를 함께 제공하세요.

위 instruction에서 지정한 JSON 형식에 맞추어 섹션들을 분류 결과로 반환하세요."""


        return prompt
