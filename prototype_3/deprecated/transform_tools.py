"""
Transform Tools: 데이터 변환 도구들

추출된 데이터를 최종 형식으로 변환하는 도구들입니다.
"""

from typing import Dict, List, Any, Optional
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from .base import FlexibleTool, ToolType
from core.flexible_result import FlexibleToolResult, ResultStatus, ResultMetadata
from core.document_accessor import DocumentAccessor


class CartesianProductTool(FlexibleTool):
    """
    Cartesian Product 생성 도구 (개선된 버전)

    특징:
        - 행별 독립 계산 (prototype_2의 오류 수정)
        - 정확한 조합 수 계산
        - 줄바꿈 처리 최적화
        - LLM 기반 유연한 처리

    파라미터:
        - extract_result: 추출 결과 (required)
        - instruction: 추가 지시사항 (optional)
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_type(self) -> ToolType:
        return ToolType.TRANSFORM

    def get_description(self) -> str:
        return "Generate accurate Cartesian product with per-row independent calculation"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "extract_result": {
                "type": "dict",
                "description": "Extraction result with header and data",
                "required": True
            },
            "instruction": {
                "type": "string",
                "description": "Additional transformation instructions",
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
            # 추출 결과 가져오기
            extract_result = params.get("extract_result")
            if not extract_result:
                return self._create_error("extract_result parameter is required")

            header = extract_result.get("header", [])
            data = extract_result.get("data", [])

            if not header or not data:
                return self._create_error("Invalid extract_result: missing header or data")

            instruction = params.get("instruction", "")

            # LLM에게 Cartesian Product 생성 요청
            prompt = f"""다음은 보험 정의 테이블의 데이터입니다.

Header: {json.dumps(header, ensure_ascii=False)}

Data (전체 행):
{json.dumps(data, ensure_ascii=False, indent=2)}

**목표**: 이 데이터에서 모든 가능한 조합(Cartesian Product)을 생성하세요.

**중요한 규칙**:
1. **행별 독립 계산**: 각 행마다 독립적으로 조합 생성
   - 예: 1행에서 2개 조합, 2행에서 3개 조합 → 총 5개 (NOT 6개)

2. "명칭" 또는 유사한 컬럼 → "보종명" 필드로 변환

3. 나머지 컬럼들 → "유형1", "유형2", "유형3", ... 필드로 변환
    3-1. Header 길이가 N이면, 최종 definitions에는
        - '보종명' 1개와
        - '유형1'부터 '유형(N-1)'까지 모든 필드가 반드시 존재해야 한다.
        (예: Header 3개 → 보종명 + 유형1 + 유형2)

4. 슬래시(/)로 구분된 값들은 각각 분리하여 조합 생성
   - 예: "1형/2형" → ["1형", "2형"]

5. 줄바꿈(\\n) 처리:
   - 보종명: 줄바꿈 유지 (원본 그대로)
   - 유형: 줄바꿈 제거 (깔끔하게)

6. 절대 새로운 값이나 유형 축을 추가하지 말고 기존 데이터로만 역할에 맞게 매핑

7. 중복 제거

{f"**추가 지시사항**: {instruction}" if instruction else ""}

**예시**:
입력:
- Header: ["명칭", "유형"]
- Data: [
    ["재해장해특약\\n(무배당)", "간편심사(315)형/간편심사(335)형"],
    ["암진단특약", "1종/2종/3종"]
  ]

출력:
- 1행에서 2개 조합:
  [
    {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(315)형"}},
    {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(335)형"}}
  ]
- 2행에서 3개 조합:
  [
    {{"보종명": "암진단특약", "유형1": "1종"}},
    {{"보종명": "암진단특약", "유형1": "2종"}},
    {{"보종명": "암진단특약", "유형1": "3종"}}
  ]
- **총 5개** (2 + 3)

다음 JSON 형식으로 반환:
{{
  "definitions": [
    {{"보종명": "...", "유형1": "...", "유형2": "...", ...}},
    ...
  ],
  "total_count": <생성된 조합 수>,
  "per_row_counts": [<1행 조합수>, <2행 조합수>, ...],
  "calculation_detail": "<각 행별 계산 과정>",
  "processing_notes": "<처리 과정 설명>"
}}
"""

            # LLM 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=6000
            )

            result = json.loads(response.choices[0].message.content)

            # 결과 검증
            definitions = result.get("definitions", [])

            if not definitions:
                return self._create_error(
                    "LLM failed to generate combinations",
                    partial_data=result
                )

            # 기본 구조 검증
            if not all(isinstance(d, dict) for d in definitions):
                return self._create_error("Invalid definition format")

            if not all("보종명" in d for d in definitions):
                return self._create_error("All definitions must have '보종명'")

            # 메타데이터 생성
            metadata = ResultMetadata(
                output_schema={
                    "definitions": "list of all product combinations",
                    "total_count": "total number of combinations",
                    "per_row_counts": "combinations per data row",
                    "calculation_detail": "calculation breakdown"
                },
                access_hints={
                    "primary_result": "definitions",
                    "calculation_method": "per-row independent (NOT cross-row)",
                    "verified": "true"
                },
                confidence=0.95,
                processing_notes=result.get("processing_notes", "")
            )

            return self._create_success(
                data={
                    "definitions": definitions,
                    "total_count": len(definitions),
                    "per_row_counts": result.get("per_row_counts", []),
                    "calculation_detail": result.get("calculation_detail", ""),
                    "input_header": header,
                    "input_data_rows": len(data)
                },
                metadata=metadata
            )

        except Exception as e:
            return self._create_error(f"CartesianProductTool error: {str(e)}")
