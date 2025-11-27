"""
LLM-based validator for task outputs.
Validates each task's output against task goals and original document.

이 모듈은 각 Task의 출력 결과를 검증하여 품질을 보장합니다.

주요 기능:
    - validate_search: Search 도구 결과 검증 (올바른 위치인지)
    - validate_extract: Extract 도구 결과 검증 (데이터 완전성)
    - validate_cartesian: Cartesian 도구 결과 검증 (조합 완전성)

검증 전략:
    - 단순 규칙이 아닌 LLM의 판단으로 유연한 검증
    - 실패 시 구체적인 에러 메시지와 개선 제안 제공
    - Replanner가 이 피드백을 활용하여 재계획 수립
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv


class LLMValidator:
    """
    LLM 기반 Task 출력 검증기

    역할:
        1. Task 출력의 정확성 검증
        2. 에러 원인 분석 및 제안사항 생성
        3. Replanner에게 피드백 제공

    검증 방식:
        - 규칙 기반이 아닌 LLM의 문맥 이해 능력 활용
        - 원본 문서와 비교하여 데이터 손실 여부 확인
        - 예상 조합 수와 실제 조합 수 비교

    Attributes:
        client (OpenAI): OpenAI API 클라이언트
    """

    def __init__(self):
        """
        Validator 초기화

        OpenAI API 클라이언트 생성
        """
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def validate_search(
        self,
        tool_output: Dict[str, Any],
        original_doc: List[Dict]
    ) -> Dict[str, Any]:
        """
        Validate search tool output.
        Check if the found location actually contains definition data.
        """
        try:
            location = tool_output.get("location", {})
            section_idx = location.get("section_index")
            para_idx = location.get("paragraph_index")

            if section_idx is None or para_idx is None:
                return {
                    "is_valid": False,
                    "errors": ["Location not found"],
                    "suggestions": ["Try using LLM-based search tool"]
                }

            # Get the actual content at the location
            section = original_doc[0]["elements"][section_idx]
            title = section.get("title", "")
            paragraph = section["paragraphs"][para_idx]

            # Check if paragraph has table
            has_table = "table" in paragraph

            # Prepare validation prompt
            prompt = f"""다음은 보험 상품 조합 테이블을 찾은 결과입니다.

섹션 제목: {title}
섹션 인덱스: {section_idx}
Paragraph 인덱스: {para_idx}
Table 포함 여부: {has_table}

**검증 목표**: 이 위치가 보험 상품의 모든 조합(명칭 + 유형)을 담고 있는 테이블인지 확인하세요.

**검증 기준**:
1. Table이 존재해야 함
2. 제목에 "명칭", "보험종목", "정의", "용어" 등이 포함되어야 함
3. 테이블에 보험 상품 정보(명칭, 유형 등)가 있어 보임

**중요**: "보험종목의 명칭", "보험종목 명칭" 같은 제목도 VALID합니다!

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...] (is_valid=false인 경우),
  "suggestions": ["제안1", "제안2", ...] (is_valid=false인 경우),
  "reasoning": "<판단 이유>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check document structure"]
            }

    def validate_extract(
        self,
        tool_output: Dict[str, Any],
        original_doc: List[Dict],
        location: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate extraction tool output.
        Check if all data was extracted correctly without truncation or noise.
        """
        try:
            header = tool_output.get("header", [])
            data = tool_output.get("data", [])

            if not header or not data:
                return {
                    "is_valid": False,
                    "errors": ["Header or data is empty"],
                    "suggestions": ["Try using LLM-based extraction tool"]
                }

            # Get original table for comparison
            section_idx = location.get("section_index")
            para_idx = location.get("paragraph_index")

            section = original_doc[0]["elements"][section_idx]
            paragraph = section["paragraphs"][para_idx]
            table = paragraph.get("table", {})
            table_elements = table.get("table_elements", [])

            # Prepare validation prompt
            prompt = f"""다음은 정의 테이블에서 추출한 데이터입니다.

추출된 Header: {json.dumps(header, ensure_ascii=False)}
추출된 Data 행 수: {len(data)}
추출된 Data 샘플 (최대 3개):
{json.dumps(data[:3], ensure_ascii=False, indent=2)}

원본 테이블 행 수: {len(table_elements)}

**검증 목표**: 추출이 올바르게 되었는지 확인하세요.

**검증 기준**:
1. Header가 의미있는 컬럼명인가? (예: 명칭, 유형, 보장내용 등)
2. Data 행 수가 적절한가? (너무 적거나 많지 않은가)
3. 주석 행(※, 주:, * 등)이 잘못 포함되지 않았는가?
4. 데이터가 잘리거나 손상되지 않았는가?
5. 특수문자나 줄바꿈이 제대로 처리되었는가?

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...] (is_valid=false인 경우),
  "suggestions": ["제안1", "제안2", ...] (is_valid=false인 경우),
  "reasoning": "<판단 이유>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check extraction parameters"]
            }

    def validate_cartesian(
        self,
        tool_output: Dict[str, Any],
        extracted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate Cartesian product generation.
        Check if all combinations are generated without duplicates.
        """
        try:
            definitions = tool_output.get("definitions", [])

            if not definitions:
                return {
                    "is_valid": False,
                    "errors": ["No definitions generated"],
                    "suggestions": ["Check input data format"]
                }

            header = extracted_data.get("header", [])
            data = extracted_data.get("data", [])

            # Calculate unique values per column for validation
            unique_counts = []
            for col_idx in range(len(header)):
                unique_values = set()
                for row in data:
                    if col_idx < len(row):
                        # Split by slash
                        values = [v.strip() for v in row[col_idx].split('/')]
                        unique_values.update(values)
                unique_counts.append(len(unique_values))

            expected_count = 1
            for count in unique_counts:
                expected_count *= count

            # Prepare validation prompt
            prompt = f"""다음은 Cartesian Product 생성 결과입니다.

원본 Data (완전):
- Header: {json.dumps(header, ensure_ascii=False)}
- Data 전체:
{json.dumps(data, ensure_ascii=False, indent=2)}

생성된 Definitions 전체:
개수: {len(definitions)}
전체 목록:
{json.dumps(definitions, ensure_ascii=False, indent=2)}

**예상 조합 수 계산**:
각 컬럼의 고유 값 개수: {unique_counts}
예상 조합 수 = {' × '.join(map(str, unique_counts))} = {expected_count}

**검증 목표**: Cartesian Product가 올바르게 생성되었는지 확인하세요.

**검증 기준**:
1. 모든 definitions에 "보종명", "유형1" 필드 존재
2. 슬래시(/)로 구분된 값들이 각각 분리되어 조합 생성됨
3. 생성된 조합 수({len(definitions)})가 예상 조합 수({expected_count})와 일치하는가?
4. 중복이 있는가?
5. 보종명이 완전한가? (줄바꿈 유지, 잘리지 않음)
6. **중요**: 보종명 필드의 줄바꿈(\\n)은 정상입니다! 원본 데이터에 있던 줄바꿈을 유지한 것입니다.
7. 유형 필드는 깔끔한가? (불필요한 줄바꿈 제거됨)

**주의**: 보종명에 \\n이 있어도 정상입니다. 유형 필드에만 줄바꿈이 없어야 합니다.

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...] (is_valid=false인 경우),
  "suggestions": ["제안1", "제안2", ...] (is_valid=false인 경우),
  "reasoning": "<판단 이유>",
  "expected_count": {expected_count}
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check Cartesian product logic"]
            }
