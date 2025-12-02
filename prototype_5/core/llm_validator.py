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
                    "problem_type": str or None,
                    "confidence": float,
                    "errors": List[str],
                    "suggestions": List[str],
                    "reasoning": str
                }
        """
        if context is None:
            context = {}

        if task_type == "search" or task_type == "classify":
            return self.validate_search(task_output, context)
        elif task_type == "extract":
            # V2: definition_extract_v2 결과 (extraction_method로 구분)
            if isinstance(task_output, dict) and task_output.get("extraction_method") == "v2_classifier_based":
                header = task_output.get("header") or []
                data = task_output.get("data") or []
                if not header or not data:
                    return {
                        "is_valid": False,
                        "problem_type": "empty_extraction",
                        "confidence": 0.8,
                        "errors": ["definition_extract_v2 returned empty header or data"],
                        "suggestions": ["Check if core sections contain valid tables"],
                        "reasoning": "definition_extract_v2 produced empty table"
                    }
                return {
                    "is_valid": True,
                    "problem_type": None,
                    "confidence": 0.95,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"definition_extract_v2 extracted table with {len(header)} columns, {len(data)} rows"
                }

            # V1: definition_extract 결과(core_candidate 포함)는 구조만 확인하고 통과
            if isinstance(task_output, dict) and "core_candidate" in task_output:
                header = task_output.get("header") or []
                data = task_output.get("data") or []
                if not header or not data:
                    return {
                        "is_valid": False,
                        "problem_type": "empty_extraction",
                        "confidence": 0.8,
                        "errors": ["Definition extract returned empty header or data"],
                        "suggestions": ["Check definition_search/definition_extract rules"],
                        "reasoning": "definition_extract produced empty table"
                    }
                return {
                    "is_valid": True,
                    "problem_type": None,
                    "confidence": 0.9,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": "definition_extract output schema is valid (header/data/core_candidate present)"
                }
            # 그 외 extract는 기존 definition-aware validator 사용
            return self.validate_extract_definitions(task_output, context)
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
            task_output: {"found_table": {...}, "section_title": "...", "found_content": [...]}
            context: {"all_sections": [...]}

        Returns:
            Dict: 검증 결과
        """
        try:
            # Section Classifier 결과인 경우 (V2 workflow)
            if all(key in task_output for key in ["definition_core", "definition_annotation", "condition", "other"]):
                definition_core = task_output.get("definition_core", [])
                definition_annotation = task_output.get("definition_annotation", [])

                # 검증: 최소한 하나의 core 섹션이 있어야 함
                if not definition_core:
                    return {
                        "is_valid": False,
                        "problem_type": "no_sections_found",
                        "confidence": 0.7,
                        "errors": ["No definition_core sections found by classifier"],
                        "suggestions": [
                            "Classifier may have misclassified sections",
                            "Check if document actually contains definition information"
                        ],
                        "reasoning": "section_classifier found no core definition sections"
                    }

                # 검증: 모든 인덱스가 리스트 타입이어야 함
                for key in ["definition_core", "definition_annotation", "condition", "other"]:
                    if not isinstance(task_output.get(key), list):
                        return {
                            "is_valid": False,
                            "problem_type": "classification_schema_error",
                            "confidence": 0.3,
                            "errors": [f"Invalid type for {key}: expected list"],
                            "suggestions": ["Check classifier output format"],
                            "reasoning": f"section_classifier output has wrong type for {key}"
                        }

                # 성공: 분류 결과가 유효함
                return {
                    "is_valid": True,
                    "problem_type": None,
                    "confidence": 0.95,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"section_classifier found {len(definition_core)} core, {len(definition_annotation)} annotation sections"
                }

            # Definition-aware search (definition_search) 결과인 경우:
            # LLM 호출 없이 candidate 리스트의 형태만 가볍게 검증한다.
            if "definition_candidates" in task_output:
                candidates = task_output.get("definition_candidates") or []

                # 빈 리스트이거나 리스트가 아닌 경우 -> invalid
                if not isinstance(candidates, List) or not candidates:
                    return {
                        "is_valid": False,
                        "problem_type": "no_sections_found",
                        "confidence": 0.5,
                        "errors": ["No definition candidates found"],
                        "suggestions": [
                            "Check definition_search rules or fall back to llm_search"
                        ],
                        "reasoning": "definition_search returned empty or malformed candidate list"
                    }

                invalid_indices = [
                    idx for idx, c in enumerate(candidates)
                    if not isinstance(c, dict) or "index" not in c or "kind" not in c
                ]
                if invalid_indices:
                    return {
                        "is_valid": False,
                        "problem_type": "classification_schema_error",
                        "confidence": 0.3,
                        "errors": [
                            f"Invalid candidate entries at positions: {invalid_indices}"
                        ],
                            "suggestions": [
                            "Ensure each candidate has 'index' and 'kind' fields"
                        ],
                        "reasoning": "definition_search candidate schema is inconsistent"
                    }

                # shape만 정상이라면 일단 통과 (세부 평가는 Extract/Transform 단계에서 수행)
                return {
                    "is_valid": True,
                    "problem_type": None,
                    "confidence": 0.9,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"{len(candidates)} definition candidates collected (schema-level validation only)"
                }

            found_table = task_output.get("found_table")
            found_content = task_output.get("found_content", [])
            section_title = task_output.get("section_title", "")

            # 테이블과 컨텐츠 미리보기 준비
            table_str = json.dumps(found_table, ensure_ascii=False)[:500] if found_table else "없음"
            content_str = json.dumps(found_content, ensure_ascii=False)[:1000] if found_content else "없음"

            prompt = f"""다음은 정의 섹션을 찾은 결과입니다.

**섹션 제목**: {section_title if section_title else "(제목 없음)"}

**테이블 데이터**:
{table_str}

**섹션 컨텐츠 (전체)**:
{content_str}

**검증 목표**: 이 섹션이 보험 상품의 정의/명칭 정보를 담고 있는지 확인하세요.

**검증 기준**:
1. **제목이 없어도 괜찮습니다** - 컨텐츠 내용이 중요합니다
2. 테이블이 있으면: 상품명/보험종목/유형 같은 정의 정보가 있는가?
3. 테이블이 없으면: 텍스트로 정의/명칭을 설명하는가?
4. 데이터가 추출 가능한 형식인가?
5. **중요**: 테이블이나 텍스트 중 하나라도 정의 정보를 담고 있으면 valid입니다

**판단 원칙**:
- 하드코딩된 키워드에 의존하지 말고, 실제 내용을 보고 판단하세요
- 제목이 없거나 비어있어도, 컨텐츠에 정의 정보가 있으면 valid입니다
- "명칭", "보험종목", "유형", "상품명" 같은 단어가 테이블 헤더나 내용에 있으면 정의 섹션입니다

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", ...] (is_valid=false인 경우),
  "suggestions": ["제안1", ...] (is_valid=false인 경우),
  "reasoning": "판단 이유 (어떤 근거로 정의 섹션인지/아닌지 설명)"
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
            context: {"original_content": ... (원본 table 또는 text)}

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

            # 원본 컨텐츠 가져오기
            original_content = context.get("original_content", "없음")
            original_str = json.dumps(original_content, ensure_ascii=False)[:2000] if original_content != "없음" else "없음"

            # 전체 데이터 검증 (샘플 X)
            prompt = f"""다음은 원본 컨텐츠에서 데이터를 추출한 결과입니다.

**원본 컨텐츠 (미리보기)**:
{original_str}

**추출된 결과**:
Header: {json.dumps(header, ensure_ascii=False)}

Data 행 수: {len(data)}
전체 Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

**검증 목표**: 추출이 올바르게 되었는지 **원본과 비교**하여 전체 데이터를 확인하세요.

**검증 기준**:
1. **원본 컨텐츠와 추출 데이터가 일치하는가?**
   - 원본 text에서 "이 특약의 명칭은 XXX" 또는 "명칭: XXX" 처럼 **명칭/보종명을 명시**하는 부분이 있는가?
   - 그 명칭이 추출된 "보종명" 필드와 **정확히 일치**하는가?
   - **주의**: "다음과 같은 보험종목으로 구성됩니다: 1) AAA 2) BBB"에서 AAA, BBB는 **유형**이지 보종명이 아닙니다!
   - "보험종목"이라는 단어는 "유형" 의미입니다. 보종명과 혼동하지 마세요!
2. Header가 의미있는가? (명칭, 유형 등)
3. Data 행 수가 적절한가?
4. 주석 행이 잘못 포함되지 않았는가? (※, 주:, * 등)
5. 데이터가 잘리거나 손상되지 않았는가?
6. 특수문자나 줄바꿈이 적절히 처리되었는가?
7. **모든 행**을 확인하세요 (샘플만 보지 마세요)

**매우 중요**:
- 원본에서 **"명칭은"** 또는 **"명칭:"** 뒤에 나오는 값이 진짜 보종명입니다
- "보험종목으로 구성됩니다" 뒤의 1), 2) 리스트는 **유형**입니다
- 추출된 보종명이 원문의 "명칭은 XXX" 부분과 **완전히 일치**하는지 확인하세요!

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...],
  "suggestions": ["제안1", "제안2", ...],
  "reasoning": "판단 이유 (원본과 비교한 결과)",
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

    def validate_extract_definitions(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract 결과 검증 (정의 섹션 전용)

        정의/명칭 섹션의 원문 텍스트를 기준으로
        보종명/유형 구조가 올바르게 구조화되었는지 평가합니다.
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

            # 정의 섹션 원문 컨텍스트
            original_content = context.get("original_content", "")
            section_title = context.get("section_title", "")

            original_str = json.dumps(original_content, ensure_ascii=False) \
                if not isinstance(original_content, str) else original_content

            prompt = f"""다음 섹션은 '보험 상품 정의/명칭' 섹션입니다.

[섹션 제목]
{section_title if section_title else "(제목 없음)"}

[섹션 원문 텍스트]
{original_str}

[도구가 추출한 표]
Header: {json.dumps(header, ensure_ascii=False)}
행 개수: {len(data)}
전체 Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

당신의 역할:
- 위 정의 섹션 텍스트를 사람이 읽는 것처럼 이해하고,
  이 섹션이 설명하는 '보종명(상품명)', '유형1(보험종목)', '유형2(심사형/하위 유형)' 구조를 마음속에 먼저 정리하세요.
- 그 다음, 도구가 만든 표가 이 구조를 올바르게 반영하는지 평가하세요.

특히 다음을 중요하게 확인하세요:
1. 텍스트에서 "이 특약의 명칭은 XXX", "명칭은 XXX", "명칭: XXX"와 같이
   상품 전체 명칭/보종명을 나타내는 구절을 찾으세요.
   - 이 XXX가 진짜 보종명입니다.
   - 표의 첫 번째 컬럼 값이 이 보종명을 그대로 포함하거나,
     보종명 계층이 완전히 손실되지 않았는지 확인하세요.
   - 만약 첫 번째 컬럼에 "해약환급금 미지급형", "일반형"처럼 하위 유형만 있고,
     "[3-100%장해형]재해장해특약(무배당, 해약환급금 미지급형)" 같은 상위 명칭이
     전혀 표현되지 않았다면 잘못된 구조입니다.

2. "다음과 같은 보험종목으로 구성됩니다: 1) AAA 2) BBB" 와 같은 문장에서
   1), 2) 뒤에 나오는 AAA, BBB는 보통 유형(보험종목)입니다.
   - 이 값들이 보종명으로 잘못 올라가 있지 않고,
     '유형1'과 같은 하위 계층으로 들어가야 합니다.

3. 그 아래 불릿 리스트(- 간편심사(315)형, - 일반심사형 등)는
   또 다른 하위 유형(예: 심사형)으로 볼 수 있습니다.
   - 이 값들이 하나의 문자열로만 뭉쳐져 있어도 괜찮을 수 있지만,
     최소한 상위 계층(보종명/유형1)과 혼동되어서는 안 됩니다.

4. 헤더/컬럼 구조가 텍스트의 계층 깊이를 반영하는지 확인하세요.
   - 텍스트가 명확히 "상품명 → 보험종목(1,2) → 심사형(불릿)"의 3단 계층이라면,
     Header가 ["보종명", "유형1", "유형2"]처럼 충분한 축을 갖는 것이 이상적입니다.
   - Header가 1개나 2개뿐이라 계층의 중요한 수준이 누락되어 있으면
     추출이 불완전할 가능성이 높습니다.

종합적으로 판단해서, 이 표가
- 정의 섹션의 의미 구조를 잘 표현하고 있으면 is_valid=true,
- 보종명/유형 계층이 명백히 뒤섞였거나 중요한 계층이 빠졌다면 is_valid=false 로 판단하세요.

아래 JSON 형식으로 결과를 반환하세요:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", "에러2", ...],
  "suggestions": ["제안1", "제안2", ...],
  "reasoning": "왜 이 표가 원문 정의 구조와 맞는지/어긋나는지에 대한 설명",
  "invalid_row_indices": [0, 3, ...]
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
                    "problem_type": "empty_transformation",
                    "confidence": 1.0,
                    "errors": ["No definitions generated"],
                    "suggestions": ["Check input data"],
                    "reasoning": "Transform result is empty"
                }

            # 원본 데이터로 예상 조합 수 계산
            extracted_data = context.get("extracted_data", {})
            header = extracted_data.get("header", [])
            data = extracted_data.get("data", [])

            prompt = f"""다음은 Cartesian Product 생성 결과입니다.

원본 Data:
Header: {json.dumps(header, ensure_ascii=False)}
Data 전체:
{json.dumps(data, ensure_ascii=False, indent=2)}

생성된 Definitions:
개수: {len(definitions)}
전체 목록:
{json.dumps(definitions, ensure_ascii=False, indent=2)}

**검증 목표**: Cartesian Product가 올바르게 생성되었는지 확인하세요.

**검증 기준**:
1. 최종 definitions의 각 항목에는
   - 원본 Header에 있는 핵심 컬럼(예: "명칭"/"보종명"/"상품명" 등)과
   - 유형 축(예: "보험종목", "보험종목_1", "유형1", "유형2" 등)이
     빠짐없이 존재해야 합니다.
2. 특정 컬럼이 대부분의 정의에서 누락되어 있으면 is_valid=false로 보고,
   - "어느 컬럼(키)이 빠졌는지"를 errors에 명시하세요.
3. **슬래시(/)나 콤마(,) 구분 판단 (매우 중요!)**:
   **일반화된 규칙 - 컬럼별 주 구분자(primary delimiter) 파악**:

   원본 Data의 각 컬럼을 관찰하여:
   - 컬럼 전체에서 `/`와 `,` 중 어느 것이 **더 자주** 등장하는지 확인
   - **더 자주 등장하는 구분자**가 실제 구분자 (primary delimiter)
   - **덜 등장하는 구분자**는 내용의 일부로 취급

   **예시 1**: "두경부암(전이포함),위암(전이포함),남성/여성생식기암(전이포함)"
   → `,`가 여러 번 등장, `/`는 "남성/여성" 내부에만 등장
   → 주 구분자: `,`
   → 올바른 분리: ["두경부암(전이포함)", "위암(전이포함)", "남성/여성생식기암(전이포함)"]
   → "남성/여성생식기암"을 분리하지 않은 것이 **정답**

   **예시 2**: "간편심사(315)형/간편심사(335)형/간편심사(355)형"
   → `/`가 여러 번 등장, `,` 없음
   → 주 구분자: `/`
   → 올바른 분리: ["간편심사(315)형", "간편심사(335)형", "간편심사(355)형"]

   **검증 시 주의**:
   - 이 규칙을 따라 분리된 결과가 정상입니다
   - 특정 값(예: "남성/여성생식기암")을 명시적으로 체크하지 말고, **컬럼의 패턴**을 보세요!
4. definitions 개수가 원본 테이블 구조로부터 직관적으로 기대되는 범위를
   명백히 벗어나 너무 많거나(불필요한 분할) 너무 적은 경우(누락)에는
   is_valid=false로 판단하고, 이유를 설명하세요.
5. 동일한 보종명 + 유형 조합이 여러 번 반복되는 명백한 중복이 많다면
   is_valid=false로 보고, "어떤 키 조합이 중복되는지"를 errors에 적어주세요.
6. 보종명(또는 명칭) 값이 중간에서 끊기지 않고 온전한지 확인하세요.
   - 줄바꿈(\n)은 정상으로 간주합니다.
7. 유형 관련 필드(보험종목, 보험종목_1, 유형1/2 등)의 값이
   서로 뒤섞이거나 잘려 보이지 않고, 사람 기준으로 봐도
   자연스러운 분리/조합으로 보이면 is_valid=true로 판단하세요.




다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": ["에러1", ...],
  "suggestions": ["제안1", ...],
  "reasoning": "판단 이유",
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
