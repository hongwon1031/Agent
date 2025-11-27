"""
LLM-based Validator

Task 결과를 LLM이 검증합니다.
- Task 타입별 검증 로직
- 전체 데이터 검증 (샘플 X)
- 구체적인 에러 메시지와 개선 제안
"""

import json
import os
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv


class LLMValidator:
    """
    LLM 기반 Task 결과 검증기

    역할:
        - Search 결과 검증
        - Extract 결과 검증
        - Transform 결과 검증
        - 구체적인 피드백 제공
    """

    def __init__(self):
        """Initialize OpenAI client"""
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def validate(
        self,
        task_type: str,
        task_output: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Task 타입에 맞는 검증 수행

        Args:
            task_type: "search" | "extract" | "transform"
            task_output: 도구 실행 결과
            context: 추가 컨텍스트 (원본 문서 등)

        Returns:
            Dict: 검증 결과
                {
                    "is_valid": bool,
                    "confidence": float,
                    "errors": List[str],
                    "suggestions": List[str],
                    "reasoning": str
                }
        """
        if context is None:
            context = {}

        if task_type == "search":
            return self.validate_search(task_output, context)
        elif task_type == "extract":
            return self.validate_extract(task_output, context)
        elif task_type == "transform":
            return self.validate_transform(task_output, context)
        else:
            return {
                "is_valid": True,
                "confidence": 1.0,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Unknown task type: {task_type}, skipping validation"
            }

    def validate_search(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Search 결과 검증

        Args:
            task_output: {"found_table": {...}, "section_title": "..."}
            context: {"all_sections": [...]}

        Returns:
            Dict: 검증 결과
        """
        try:
            found_table = task_output.get("found_table")
            section_title = task_output.get("section_title", "")

            if not found_table:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["No table found"],
                    "suggestions": ["Try LLM-based search"],
                    "reasoning": "Search result has no table"
                }

            # 테이블 미리보기
            table_str = json.dumps(found_table, ensure_ascii=False)[:500]

            prompt = f"""다음은 정의 섹션을 찾은 결과입니다.

섹션 제목: {section_title}

테이블 미리보기:
{table_str}

**검증 목표**: 이 섹션이 보험 상품의 정의/명칭 정보를 담고 있는지 확인하세요.

**검증 기준**:
1. 제목이 적절한가? (정의, 명칭, 보험종목 등)
2. 테이블에 상품 정보가 있어 보이는가?
3. 데이터가 추출 가능한 형식인가?

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", ...] (is_valid=false인 경우),
  "suggestions": ["제안1", ...] (is_valid=false인 경우),
  "reasoning": "판단 이유"
}}"""

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
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": [],
                "reasoning": "Validation failed"
            }

    def validate_extract(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract 결과 검증

        Args:
            task_output: {"header": [...], "data": [[...], ...]}
            context: {"original_table": {...}}

        Returns:
            Dict: 검증 결과
        """
        try:
            header = task_output.get("header", [])
            data = task_output.get("data", [])

            if not header or not data:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["Header or data is empty"],
                    "suggestions": ["Try LLM-based extraction"],
                    "reasoning": "Extraction result is empty"
                }

            # 전체 데이터 검증 (샘플 X)
            prompt = f"""다음은 테이블에서 추출한 데이터입니다.

Header: {json.dumps(header, ensure_ascii=False)}

Data 행 수: {len(data)}
전체 Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

**검증 목표**: 추출이 올바르게 되었는지 전체 데이터를 확인하세요.

**검증 기준**:
1. Header가 의미있는가? (명칭, 유형 등)
2. Data 행 수가 적절한가?
3. 주석 행이 잘못 포함되지 않았는가? (※, 주:, * 등)
4. 데이터가 잘리거나 손상되지 않았는가?
5. 특수문자나 줄바꿈이 적절히 처리되었는가?
6. **모든 행**을 확인하세요 (샘플만 보지 마세요)

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...],
  "suggestions": ["제안1", "제안2", ...],
  "reasoning": "판단 이유",
  "invalid_row_indices": [0, 3, ...]  (문제가 있는 행 인덱스)
}}"""

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
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": [],
                "reasoning": "Validation failed"
            }

    def validate_transform(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transform (Cartesian) 결과 검증

        Args:
            task_output: {"definitions": [...], "total_count": int}
            context: {"extracted_data": {"header": [...], "data": [...]}}

        Returns:
            Dict: 검증 결과
        """
        try:
            definitions = task_output.get("definitions", [])
            total_count = task_output.get("total_count", 0)

            if not definitions:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["No definitions generated"],
                    "suggestions": ["Check input data"],
                    "reasoning": "Transform result is empty"
                }

            # 원본 데이터로 예상 조합 수 계산
            extracted_data = context.get("extracted_data", {})
            header = extracted_data.get("header", [])
            data = extracted_data.get("data", [])

            # 행별로 예상 조합 수 계산
            expected_per_row = []
            for row in data:
                row_combos = 1
                for cell in row:
                    cell_clean = cell.replace('\n', '').strip()
                    values = [v.strip() for v in cell_clean.split('/') if v.strip()]
                    row_combos *= len(values)
                expected_per_row.append(row_combos)

            expected_total = sum(expected_per_row)

            prompt = f"""다음은 Cartesian Product 생성 결과입니다.

원본 Data:
Header: {json.dumps(header, ensure_ascii=False)}
Data 전체:
{json.dumps(data, ensure_ascii=False, indent=2)}

행별 예상 조합 수: {expected_per_row}
예상 총 조합 수: {expected_total}

생성된 Definitions:
개수: {len(definitions)}
전체 목록:
{json.dumps(definitions, ensure_ascii=False, indent=2)}

**검증 목표**: Cartesian Product가 올바르게 생성되었는지 확인하세요.

**검증 기준**:
1. 최종 definitions의 각 항목에는
   - '보종명' 키가 반드시 있어야 하고,
   - '유형1'부터 '유형{len(header)-1}'까지 모든 키가 존재해야 한다.
2. 어떤 유형 축도 누락되면 is_valid=false로 보고,
   - "어느 유형 키가 빠졌는지"를 errors에 명시한다.
3. 슬래시(/)로 구분된 값들이 각각 분리됨
4. 생성된 조합 수({len(definitions)})가 예상({expected_total})과 일치하는가?
5. 중복이 있는가?
6. 보종명이 완전한가? (잘리지 않음)
7. **중요**: 보종명의 줄바꿈(\\n)은 정상입니다!
8. 유형 필드는 깔끔한가?



다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", ...],
  "suggestions": ["제안1", ...],
  "reasoning": "판단 이유",
  "expected_count": {expected_total},
  "actual_count": {len(definitions)}
}}"""

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
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": [],
                "reasoning": "Validation failed"
            }
