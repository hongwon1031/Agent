"""
Tools for searching and locating definition sections in insurance documents.

이 모듈은 보험 문서에서 정의 섹션을 찾는 두 가지 접근 방식을 제공합니다:
    1. RuleSearchTool: 키워드 기반의 빠른 규칙 기반 검색
    2. LLMSearchTool: 문맥을 이해하는 유연한 LLM 기반 검색

전략:
    - 먼저 RuleSearchTool로 빠르게 시도
    - 실패 시 Replanner가 LLMSearchTool로 전환
    - Validator가 찾은 위치의 적합성 검증
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class RuleSearchTool(SimpleTool):
    """
    규칙 기반 정의 섹션 검색 도구

    동작 방식:
        1. 문서의 각 섹션 제목에서 키워드 검색
        2. 키워드가 포함된 섹션 내에서 테이블이 있는 paragraph 찾기
        3. 첫 번째 매칭 결과 반환

    장점:
        - 빠른 실행 속도 (LLM 호출 없음)
        - 비용 없음
        - 명확한 패턴 매칭

    단점:
        - 키워드가 정확히 일치해야 함
        - 문맥 이해 불가
        - 비표준 제목에 약함

    사용 시나리오:
        - 표준적인 보험 문서 (제목이 "정의", "용어의 정의" 등)
        - 빠른 프로토타이핑
        - 첫 번째 시도 (실패 시 LLM으로 전환)
    """

    def get_description(self) -> str:
        """
        도구 설명 반환 (Planner가 사용)

        Returns:
            str: "키워드 매칭을 사용한 규칙 기반 정의 섹션 검색"
        """
        return "Rule-based search for definition sections using keyword matching"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        파라미터 스키마 정의

        Returns:
            Dict: 다음 파라미터들을 포함:
                - keywords (list, optional): 검색할 키워드 목록
                - instruction (string, optional): Replanner의 커스텀 지시사항
        """
        return {
            "keywords": {
                "type": "list",
                "description": "Keywords to search for (default: ['정의', '용어'])",
                "required": False
            },
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        키워드 기반 검색 실행

        Args:
            doc (List[Dict]): 파싱된 보험 문서
                구조: [{"elements": [{"title": str, "paragraphs": [{"table": {...}}]}]}]
            params (Dict[str, Any]):
                - keywords (optional): 검색 키워드 리스트
                - instruction (optional): 사용되지 않음 (호환성 유지용)

        Returns:
            ToolResult:
                성공 시 data = {
                    "location": {
                        "section_index": int,     # 섹션 인덱스
                        "paragraph_index": int,   # paragraph 인덱스
                        "title": str,             # 섹션 제목
                        "match_type": "title",    # 매칭 타입
                        "keyword": str            # 매칭된 키워드
                    },
                    "all_matches": List[Dict]     # 모든 매칭 결과
                }
                실패 시 error = "키워드로 정의 섹션을 찾을 수 없음"

        알고리즘:
            1. keywords 추출 (기본값: ["정의", "용어의 정의", "용어", "명칭", "보험종목"])
            2. 문서의 모든 섹션 순회
            3. 각 섹션 제목에 키워드가 포함되는지 확인
            4. 매칭되면 해당 섹션의 paragraphs에서 table 찾기
            5. 테이블이 있는 paragraph의 위치 저장
            6. 첫 번째 매칭 결과 반환
        """
        try:
            # 파라미터에서 키워드 추출 (없으면 기본값 사용)
            keywords = params.get("keywords", ["정의", "용어의 정의", "용어", "명칭", "보험종목"])
            
            # 매칭된 위치들을 저장할 리스트
            found_locations = []

            # 문서 유효성 검사
            if not doc or len(doc) == 0:
                return self._create_error("Document is empty")

            # 문서의 elements 추출
            elements = doc[0].get("elements", [])

            # 각 섹션 순회
            for section_idx, section in enumerate(elements):
                # 섹션 제목 추출
                title = section.get("title", "")

                # 각 키워드로 제목 검사
                for keyword in keywords:
                    if keyword in title:
                        # 키워드가 제목에 포함됨 → 이 섹션의 paragraphs에서 테이블 찾기
                        paragraphs = section.get("paragraphs", [])
                        for para_idx, para in enumerate(paragraphs):
                            # 테이블이 있는 paragraph 발견
                            if "table" in para:
                                found_locations.append({
                                    "section_index": section_idx,
                                    "paragraph_index": para_idx,
                                    "title": title,
                                    "match_type": "title",
                                    "keyword": keyword
                                })

            # 매칭 결과가 없으면 에러 반환
            if not found_locations:
                return self._create_error(
                    f"No definition sections found with keywords: {keywords}"
                )

            # 첫 번째 매칭 결과 반환 (추후 확장 가능: 모든 결과 반환)
            return self._create_success({
                "location": found_locations[0],
                "all_matches": found_locations
            })

        except Exception as e:
            # 예외 발생 시 에러 메시지 반환
            return self._create_error(f"RuleSearchTool error: {str(e)}")


class LLMSearchTool(SimpleTool):
    """
    LLM 기반 정의 섹션 검색 도구

    동작 방식:
        1. 문서 구조를 간략화 (섹션 제목, paragraph 수, 테이블 유무)
        2. LLM에게 문서 구조 제공하고 정의 섹션 찾기 요청
        3. LLM이 문맥을 이해하고 적절한 섹션 선택
        4. 선택된 섹션에서 테이블이 있는 paragraph 위치 반환

    장점:
        - 문맥 이해 가능
        - 비표준 제목 처리 가능
        - 유연한 판단 (예: "보험종목의 명칭"도 인식)
        - Replanner의 커스텀 지시사항 반영 가능

    단점:
        - LLM 호출 비용 발생
        - RuleSearchTool보다 느림
        - API 키 필요

    사용 시나리오:
        - RuleSearchTool 실패 후
        - 비표준 문서 구조
        - 문맥 기반 판단이 필요한 경우
        - Replanner가 특별 지시사항을 추가한 경우
    """

    def __init__(self):
        """
        LLM 클라이언트 초기화

        환경 변수에서 OPENAI_API_KEY 로드하여 OpenAI 클라이언트 생성
        """
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_description(self) -> str:
        """
        도구 설명 반환 (Planner가 사용)

        Returns:
            str: "문맥 이해가 가능한 LLM 기반 정의 섹션 검색"
        """
        return "LLM-based search for definition sections with context understanding"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        파라미터 스키마 정의

        Returns:
            Dict: 다음 파라미터들을 포함:
                - instruction (string, optional): Replanner의 커스텀 지시사항
        """
        return {
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        LLM 기반 검색 실행

        Args:
            doc (List[Dict]): 파싱된 보험 문서
                구조: [{"elements": [{"title": str, "paragraphs": [...]}]}]
            params (Dict[str, Any]):
                - instruction (optional): Replanner가 제공하는 커스텀 지시사항
                  예: "제목에 '명칭'이 포함된 섹션도 고려하세요"

        Returns:
            ToolResult:
                성공 시 data = {
                    "location": {
                        "section_index": int,       # 섹션 인덱스
                        "paragraph_index": int,     # paragraph 인덱스
                        "title": str,               # 섹션 제목
                        "reasoning": str            # LLM의 선택 이유
                    }
                }
                실패 시 error = "LLM이 정의 섹션을 찾을 수 없음: <이유>"

        알고리즘:
            1. 문서 구조를 간략화 (섹션 제목, paragraph 수, 테이블 유무)
            2. LLM에게 구조 정보와 함께 정의 섹션 찾기 요청
            3. LLM 응답에서 section_index 추출
            4. 해당 섹션에서 테이블이 있는 paragraph 찾기
            5. 위치 정보 반환

        LLM 프롬프트 전략:
            - 문서 구조만 전달 (토큰 절약)
            - 명확한 출력 형식 지정 (JSON)
            - 특별 지시사항 포함 (Replanner의 피드백 반영)
        """
        try:
            # 커스텀 지시사항 추출 (Replanner가 제공)
            custom_instruction = params.get("instruction", "")

            # 문서 유효성 검사
            if not doc or len(doc) == 0:
                return self._create_error("Document is empty")

            # 문서의 elements 추출
            elements = doc[0].get("elements", [])

            # LLM을 위한 간략화된 문서 구조 생성
            # (전체 내용을 보내면 토큰이 너무 많이 소모됨)
            doc_structure = []
            for idx, section in enumerate(elements):
                title = section.get("title", "")
                para_count = len(section.get("paragraphs", []))
                # 이 섹션에 테이블이 있는지 확인
                has_tables = any("table" in p for p in section.get("paragraphs", []))

                doc_structure.append({
                    "section_index": idx,
                    "title": title,
                    "paragraph_count": para_count,
                    "has_tables": has_tables
                })

            # LLM 프롬프트 구성
            prompt = f"""다음은 보험 문서의 섹션 구조입니다.

문서 구조:
{doc_structure}

**목표**: "정의" 또는 "용어의 정의"에 해당하는 섹션을 찾아 section_index를 반환하세요.
일반적으로 정의 섹션은 표(table)를 포함하고 있습니다.

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "section_index": <섹션 인덱스>,
  "paragraph_index": <표가 있는 paragraph 인덱스>,
  "reasoning": "<선택 이유>"
}}

정의 섹션을 찾을 수 없으면:
{{
  "section_index": null,
  "paragraph_index": null,
  "reasoning": "<이유>"
}}
"""

            # LLM API 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},  # JSON 형식 강제
                temperature=0  # 결정론적 출력
            )

            # LLM 응답 파싱
            result = json.loads(response.choices[0].message.content)

            # LLM이 섹션을 찾지 못한 경우
            if result["section_index"] is None:
                return self._create_error(
                    f"LLM could not find definition section: {result['reasoning']}"
                )

            # 해당 섹션에서 테이블이 있는 paragraph 찾기
            section = elements[result["section_index"]]
            paragraphs = section.get("paragraphs", [])

            table_para_idx = None
            for idx, para in enumerate(paragraphs):
                if "table" in para:
                    table_para_idx = idx
                    break

            # 테이블이 없으면 에러
            if table_para_idx is None:
                return self._create_error(
                    f"Section {result['section_index']} has no table"
                )

            # 성공 결과 반환
            return self._create_success({
                "location": {
                    "section_index": result["section_index"],
                    "paragraph_index": table_para_idx,
                    "title": section.get("title", ""),
                    "reasoning": result["reasoning"]
                }
            })

        except Exception as e:
            # 예외 발생 시 에러 메시지 반환
            return self._create_error(f"LLMSearchTool error: {str(e)}")
