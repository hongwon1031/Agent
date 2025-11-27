"""
Tool for generating Cartesian product from extracted data.

이 모듈은 추출된 보험 정의 데이터로부터 모든 가능한 조합(Cartesian Product)을 생성합니다.

핵심 기능:
    - 슬래시(/)로 구분된 값들을 각각 분리
    - 모든 가능한 조합 생성 (보종명 × 유형1 × 유형2 × ...)
    - 중복 제거
    - 보종명의 줄바꿈 유지, 유형 필드의 줄바꿈 제거

예시:
    입력:
        header = ["명칭", "유형"]
        data = [["재해장해특약\\n(무배당)", "간편(315)형/간편(335)형"]]

    출력:
        definitions = [
            {"보종명": "재해장해특약\\n(무배당)", "유형1": "간편(315)형"},
            {"보종명": "재해장해특약\\n(무배당)", "유형1": "간편(335)형"}
        ]
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class GenerateCartesianTool(SimpleTool):
    """
    Cartesian Product 생성 도구

    동작 방식:
        1. header와 data를 LLM에게 전달
        2. LLM이 테이블 구조 이해 (명칭 컬럼, 유형 컬럼 등)
        3. 슬래시(/)로 구분된 값들을 각각 분리
        4. 모든 가능한 조합 생성 (Cartesian Product)
        5. 중복 제거 및 정리
        6. 표준 형식으로 반환: [{"보종명": "...", "유형1": "...", "유형2": "..."}, ...]

    특수 처리:
        - 보종명: 줄바꿈(\\n) 유지 (원본 데이터 그대로)
        - 유형: 줄바꿈 제거 (깔끔한 문자열)
        - 슬래시(/): 각 값으로 분리하여 조합 생성

    왜 LLM을 사용하는가?
        - 테이블 구조가 문서마다 다름 (컬럼명이 "명칭", "보험종목", "보장종목" 등 다양)
        - 규칙으로 정의하기 어려운 패턴들이 존재
        - LLM이 유연하게 판단하여 정확한 조합 생성 가능

    사용 시나리오:
        - Extract 단계 이후 마지막 단계
        - 모든 보험 상품 조합을 생성하는 것이 최종 목표
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
            str: "구조화된 데이터로부터 모든 정의 조합의 Cartesian Product 생성"
        """
        return "Generate Cartesian product of all definition combinations from structured data"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        파라미터 스키마 정의

        Returns:
            Dict: 다음 파라미터들을 포함:
                - header (list, required): 추출된 데이터의 컬럼 헤더
                - data (list, required): 추출된 데이터의 행들
                - instruction (string, optional): Replanner의 커스텀 지시사항
        """
        return {
            "header": {
                "type": "list",
                "description": "Column headers from extracted data",
                "required": True
            },
            "data": {
                "type": "list",
                "description": "Data rows from extracted data",
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
        Cartesian Product 생성 실행

        Args:
            doc (List[Dict]): 원본 문서 (사용하지 않음, 인터페이스 통일용)
            params (Dict[str, Any]):
                - header (List[str]): 컬럼 헤더 (예: ["명칭", "유형"])
                - data (List[List[str]]): 데이터 행들
                - instruction (optional): Replanner의 커스텀 지시사항
                  예: "슬래시 구분을 더 엄격하게 처리하세요"

        Returns:
            ToolResult:
                성공 시 data = {
                    "definitions": List[Dict],  # 생성된 모든 조합
                                                # 예: [{"보종명": "...", "유형1": "..."}, ...]
                    "total_count": int,         # 총 조합 수
                    "notes": str                # LLM의 처리 설명
                }
                실패 시 error = "LLM이 조합 생성 실패: <이유>"

        알고리즘:
            1. header와 data 유효성 검사
            2. LLM에게 Cartesian Product 생성 요청
            3. LLM이 다음을 수행:
               - "명칭" 류의 컬럼 → "보종명" 필드로 매핑
               - 나머지 컬럼들 → "유형1", "유형2", ... 필드로 매핑
               - 슬래시(/)로 구분된 값들을 분리
               - 모든 조합 생성 (Cartesian Product)
               - 줄바꿈 처리: 보종명은 유지, 유형은 제거
            4. 생성된 조합 검증 (필수 필드 확인)
            5. 결과 반환

        LLM 프롬프트 전략:
            - 명확한 예시 제공
            - 줄바꿈 처리 규칙 명시
            - 슬래시 구분 규칙 명시
            - 중복 제거 요청
        """
        try:
            # 파라미터 추출
            header = params["header"]
            data = params["data"]
            custom_instruction = params.get("instruction", "")

            # 입력 데이터 유효성 검사
            if not header or not data:
                return self._create_error("Header or data is empty")

            # LLM 프롬프트 구성 - Cartesian Product 생성 요청
            prompt = f"""다음은 보험 정의 테이블의 데이터입니다.

Header: {json.dumps(header, ensure_ascii=False)}

Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

**목표**: 이 데이터에서 모든 가능한 조합(Cartesian Product)을 생성하세요.

**규칙**:
1. "명칭" 또는 유사한 컬럼 → "보종명" 필드
2. 다른 컬럼들 → "유형1", "유형2", "유형3", ... 필드
3. 슬래시(/)로 구분된 값들은 각각 분리하여 조합 생성
4. 줄바꿈(\\n)은 보종명에서는 유지, 유형에서는 제거
5. 모든 가능한 조합을 생성 (Cartesian Product)
6. 중복 제거

**예시**:
입력:
- Header: ["명칭", "유형"]
- Data: [["재해장해특약\\n(무배당)", "간편심사(315)형/간편심사(335)형"]]

출력:
[
  {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(315)형"}},
  {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(335)형"}}
]

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "definitions": [
    {{"보종명": "...", "유형1": "...", "유형2": "...", ...}},
    ...
  ],
  "total_count": <생성된 조합 수>,
  "notes": "<처리 과정 설명>"
}}
"""

            # LLM API 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},  # JSON 형식 강제
                temperature=0,  # 결정론적 출력
                max_tokens=4000  # 많은 조합 생성을 위한 충분한 토큰
            )

            # LLM 응답 파싱
            result = json.loads(response.choices[0].message.content)

            # LLM이 조합 생성에 실패한 경우
            if not result.get("definitions"):
                return self._create_error(
                    f"LLM failed to generate combinations: {result.get('notes', 'Unknown error')}"
                )

            definitions = result["definitions"]

            # 기본 구조 검증
            # 모든 요소가 dict 타입인지 확인
            if not all(isinstance(d, dict) for d in definitions):
                return self._create_error("Invalid definition format")

            # 필수 필드("보종명", "유형1") 존재 여부 확인
            if not all("보종명" in d and "유형1" in d for d in definitions):
                return self._create_error(
                    "All definitions must have '보종명' and '유형1'"
                )

            # 성공 결과 반환
            return self._create_success({
                "definitions": definitions,
                "total_count": len(definitions),
                "notes": result.get("notes", "")
            })

        except KeyError as e:
            # 필수 파라미터 누락 시
            return self._create_error(f"Missing required parameter: {str(e)}")
        except Exception as e:
            # 기타 예외 처리
            return self._create_error(f"GenerateCartesianTool error: {str(e)}")
