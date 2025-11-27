"""
Tools for extracting structured data from definition tables or text.

이 모듈은 정의 테이블에서 구조화된 데이터를 추출하는 두 가지 접근 방식을 제공합니다:
    1. RuleExtractTool: 표준 테이블 구조를 가정한 빠른 규칙 기반 추출
    2. LLMExtractTool: 복잡한 형식과 엣지 케이스를 처리하는 유연한 LLM 기반 추출

전략:
    - 먼저 RuleExtractTool로 빠르게 시도
    - 실패 시 Replanner가 LLMExtractTool로 전환
    - 주석 행, 특수문자, 비표준 형식 등의 문제를 LLM이 해결
    - Validator가 추출된 데이터의 완전성 검증
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class RuleExtractTool(SimpleTool):
    """
    규칙 기반 테이블 데이터 추출 도구

    동작 방식:
        1. 지정된 위치(section_index, paragraph_index)의 테이블에 접근
        2. 테이블 구조 파악 (cells 형식 or 이미 파싱된 dict 형식)
        3. 주석 행 필터링 (※, 주:, 주), *, - 로 시작하는 행 제외)
        4. 첫 번째 행을 header로, 나머지를 data로 추출
        5. header와 data 반환

    가정:
        - 표준 테이블 구조 (행과 셀로 구성)
        - 첫 번째 행은 항상 헤더
        - 주석 행은 특정 기호로 시작

    장점:
        - 빠른 실행 속도 (LLM 호출 없음)
        - 비용 없음
        - 단순 명확한 로직

    단점:
        - 비표준 테이블 구조 처리 불가
        - 특수문자 변환 불가 (ASCII 코드 등)
        - 복잡한 주석 패턴 인식 어려움

    사용 시나리오:
        - 표준적인 테이블 구조
        - 빠른 프로토타이핑
        - 첫 번째 시도 (실패 시 LLM으로 전환)
    """

    def get_description(self) -> str:
        """
        도구 설명 반환 (Planner가 사용)

        Returns:
            str: "표준 구조의 테이블에서 규칙 기반 데이터 추출"
        """
        return "Rule-based data extraction from tables with standard structure"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        파라미터 스키마 정의

        Returns:
            Dict: 다음 파라미터들을 포함:
                - section_index (int, required): 문서의 섹션 인덱스
                - paragraph_index (int, required): 테이블이 있는 paragraph 인덱스
                - instruction (string, optional): Replanner의 커스텀 지시사항
        """
        return {
            "section_index": {
                "type": "int",
                "description": "Section index in document",
                "required": True
            },
            "paragraph_index": {
                "type": "int",
                "description": "Paragraph index containing the table",
                "required": True
            },
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        규칙 기반 테이블 데이터 추출 실행

        Args:
            doc (List[Dict]): 파싱된 보험 문서
            params (Dict[str, Any]):
                - section_index (int): 섹션 인덱스
                - paragraph_index (int): paragraph 인덱스
                - instruction (optional): 사용되지 않음 (호환성 유지용)

        Returns:
            ToolResult:
                성공 시 data = {
                    "header": List[str],        # 컬럼 헤더 목록
                    "data": List[List[str]],    # 데이터 행들
                    "row_count": int            # 데이터 행 수
                }
                실패 시 error = "테이블을 찾을 수 없음 / 테이블이 비어있음"

        알고리즘:
            1. 지정된 위치의 테이블에 접근
            2. 테이블 형식 판별:
               - cells 형식: [{"cells": [{"text": "..."}, ...]}, ...]
               - 이미 파싱된 dict 형식: [{"명칭": "...", "유형": "..."}, ...]
            3. cells 형식인 경우:
               - 각 행의 cells에서 text 추출
               - 주석 행 필터링 (※, 주:, 주), *, - 로 시작)
               - 첫 번째 행을 header로 설정
               - 나머지 행을 data로 설정
            4. dict 형식인 경우:
               - keys를 header로, values를 data로 변환
            5. header와 data 반환
        """
        try:
            # 파라미터에서 위치 정보 추출
            section_idx = params["section_index"]
            para_idx = params["paragraph_index"]

            # 지정된 위치의 테이블에 접근
            section = doc[0]["elements"][section_idx]
            paragraph = section["paragraphs"][para_idx]

            # 테이블 존재 확인
            if "table" not in paragraph:
                return self._create_error(
                    f"No table found at section {section_idx}, paragraph {para_idx}"
                )

            table = paragraph["table"]
            table_elements = table.get("table_elements", [])

            # 테이블이 비어있는지 확인
            if not table_elements:
                return self._create_error("Table is empty")

            # 테이블 형식 판별 및 데이터 추출
            # 두 가지 형식을 모두 지원: 파싱된 dict 형식과 cells 형식
            if table_elements and isinstance(table_elements[0], dict):
                # 첫 번째 요소가 dict인지 확인
                if "cells" not in table_elements[0]:
                    # 이미 파싱된 dict 형식
                    # 예: [{"명칭": "...", "보험종목": "...", ...}, ...]
                    header = list(table_elements[0].keys())
                    data = [list(row.values()) for row in table_elements]
                else:
                    # cells 형식 (일반적인 경우)
                    # 예: [{"cells": [{"text": "..."}, ...]}, ...]
                    data_rows = []

                    # 각 행 처리
                    for row in table_elements:
                        cells = row.get("cells", [])
                        if not cells:
                            continue  # 빈 행 건너뛰기

                        # 주석 행 필터링
                        # 첫 번째 셀이 특정 기호로 시작하면 주석 행으로 간주
                        first_cell = cells[0].get("text", "").strip()
                        if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                            continue  # 주석 행 건너뛰기

                        # 각 셀의 텍스트 추출
                        row_data = [cell.get("text", "").strip() for cell in cells]
                        data_rows.append(row_data)

                    # 최소 2행 필요 (header + 데이터 1행 이상)
                    if len(data_rows) < 2:
                        return self._create_error(
                            "Not enough data rows (need at least header + 1 data row)"
                        )

                    # 첫 번째 행을 header로 설정
                    header = data_rows[0]
                    # 나머지 행을 data로 설정
                    data = data_rows[1:]
            else:
                # 지원하지 않는 테이블 형식
                return self._create_error("Invalid table format")

            # 성공 결과 반환
            return self._create_success({
                "header": header,
                "data": data,
                "row_count": len(data)
            })

        except KeyError as e:
            # 문서 구조가 예상과 다를 때 (section_idx나 para_idx가 잘못됨)
            return self._create_error(f"Invalid document structure: {str(e)}")
        except Exception as e:
            # 기타 예외 처리
            return self._create_error(f"RuleExtractTool error: {str(e)}")


class LLMExtractTool(SimpleTool):
    """
    LLM 기반 테이블/텍스트 데이터 추출 도구

    동작 방식:
        1. 지정된 위치의 테이블 또는 텍스트 콘텐츠 추출
        2. 콘텐츠를 LLM에게 전달
        3. LLM이 header와 data 행 식별 및 추출
        4. 주석 행 자동 제거, 특수문자 변환, 구조 정리
        5. 정제된 header와 data 반환

    장점:
        - 비표준 테이블 구조 처리 가능
        - 복잡한 주석 패턴 인식 (다양한 형태의 주석)
        - ASCII 코드 등 특수문자 자동 변환
        - 테이블과 일반 텍스트 모두 처리 가능
        - Replanner의 커스텀 지시사항 반영 가능

    단점:
        - LLM 호출 비용 발생
        - RuleExtractTool보다 느림
        - API 키 필요

    사용 시나리오:
        - RuleExtractTool 실패 후
        - 비표준 테이블 구조
        - 주석 행이 복잡하게 섞여있는 경우
        - 특수문자 변환이 필요한 경우
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
            str: "복잡한 형식과 엣지 케이스를 처리하는 LLM 기반 데이터 추출"
        """
        return "LLM-based data extraction handling complex formats and edge cases"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        파라미터 스키마 정의

        Returns:
            Dict: 다음 파라미터들을 포함:
                - section_index (int, required): 섹션 인덱스
                - paragraph_index (int, required): paragraph 인덱스
                - instruction (string, optional): Replanner의 커스텀 지시사항
        """
        return {
            "section_index": {
                "type": "int",
                "description": "Section index in document",
                "required": True
            },
            "paragraph_index": {
                "type": "int",
                "description": "Paragraph index containing data",
                "required": True
            },
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        LLM 기반 데이터 추출 실행

        Args:
            doc (List[Dict]): 파싱된 보험 문서
            params (Dict[str, Any]):
                - section_index (int): 섹션 인덱스
                - paragraph_index (int): paragraph 인덱스
                - instruction (optional): Replanner의 커스텀 지시사항
                  예: "주석 행을 더 엄격하게 필터링하세요"

        Returns:
            ToolResult:
                성공 시 data = {
                    "header": List[str],            # 컬럼 헤더 목록
                    "data": List[List[str]],        # 데이터 행들
                    "row_count": int,               # 데이터 행 수
                    "excluded_rows": List[str],     # 제외된 주석 행들
                    "notes": str                    # LLM의 처리 과정 설명
                }
                실패 시 error = "LLM이 데이터를 추출하지 못함: <이유>"

        알고리즘:
            1. 지정된 위치의 콘텐츠 추출 (테이블 or 텍스트)
            2. 콘텐츠 타입에 따라 LLM 입력 형식으로 변환
            3. LLM에게 데이터 추출 요청 (프롬프트에 지시사항 포함)
            4. LLM 응답에서 header와 data 추출
            5. 결과 검증 및 반환

        LLM 프롬프트 전략:
            - 주석 행 필터링 규칙 명시
            - 특수문자 변환 요청
            - 제외된 행 목록도 함께 반환 요청 (디버깅용)
        """
        try:
            # 파라미터 추출
            section_idx = params["section_index"]
            para_idx = params["paragraph_index"]
            custom_instruction = params.get("instruction", "")

            # 지정된 위치의 콘텐츠에 접근
            section = doc[0]["elements"][section_idx]
            paragraph = section["paragraphs"][para_idx]

            # 콘텐츠 타입 판별 (테이블 or 텍스트)
            content = None
            content_type = None

            if "table" in paragraph:
                # 테이블 형식의 콘텐츠
                content = paragraph["table"].get("table_elements", [])
                content_type = "table"
            elif "text" in paragraph:
                # 일반 텍스트 형식의 콘텐츠
                content = paragraph["text"]
                content_type = "text"
            else:
                return self._create_error("Paragraph has neither table nor text")

            # LLM 입력을 위한 콘텐츠 직렬화
            if content_type == "table":
                # 테이블 데이터를 2차원 배열로 변환
                table_data = []
                for row in content:
                    cells = row.get("cells", [])
                    row_texts = [cell.get("text", "") for cell in cells]
                    table_data.append(row_texts)
                # JSON 문자열로 직렬화
                content_str = json.dumps(table_data, ensure_ascii=False, indent=2)
            else:
                # 텍스트는 그대로 사용
                content_str = content

            # LLM 프롬프트 구성
            # 주석 행 필터링, 특수문자 변환, 데이터 구조화를 LLM에게 요청
            prompt = f"""다음은 보험 문서의 정의 데이터입니다.

콘텐츠 타입: {content_type}

데이터:
{content_str}

**목표**: 이 데이터에서 header와 data rows를 추출하세요.

**주의사항**:
1. 주석 행은 제외 (※, 주:, 주), * , - 등으로 시작하는 행)
2. ASCII 코드 형태의 특수문자는 원래 문자로 변환
3. Header는 첫 번째 의미있는 행
4. Data는 실제 정의 항목들

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ["값1", "값2", ...],
    ...
  ],
  "excluded_rows": ["제외된 행1", "제외된 행2", ...],
  "notes": "<처리 과정 설명>"
}}
"""

            # LLM API 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},  # JSON 형식 강제
                temperature=0,  # 결정론적 출력
                max_tokens=3000  # 충분한 토큰 할당
            )

            # LLM 응답 파싱
            result = json.loads(response.choices[0].message.content)

            # LLM이 데이터 추출에 실패한 경우
            if not result.get("header") or not result.get("data"):
                return self._create_error(
                    f"LLM failed to extract data: {result.get('notes', 'Unknown error')}"
                )

            # 성공 결과 반환
            return self._create_success({
                "header": result["header"],
                "data": result["data"],
                "row_count": len(result["data"]),
                "excluded_rows": result.get("excluded_rows", []),
                "notes": result.get("notes", "")
            })

        except KeyError as e:
            # 문서 구조가 예상과 다를 때
            return self._create_error(f"Invalid document structure: {str(e)}")
        except Exception as e:
            # 기타 예외 처리
            return self._create_error(f"LLMExtractTool error: {str(e)}")
