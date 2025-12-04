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

        if task_type == "search" or task_type == "classify":
            return self.validate_classify(task_output, context)
        elif task_type == "extract":
            # V2: definition_extract_v2 결과 (extraction_method로 구분)
            if isinstance(task_output, dict) and task_output.get("extraction_method") == "v2_classifier_based":
                # LLM 기반 상세 검증 수행
                return self.validate_definition_extract_v2_llm(task_output, context)

            # V1: definition_extract 결과(core_candidate 포함)는 구조만 확인하고 통과
            if isinstance(task_output, dict) and "core_candidate" in task_output:
                header = task_output.get("header") or []
                data = task_output.get("data") or []
                if not header or not data:
                    return {
                        "is_valid": False,
                        "confidence": 0.8,
                        "errors": ["Definition extract returned empty header or data"],
                        "suggestions": ["Check definition_search/definition_extract rules"],
                        "reasoning": "definition_extract produced empty table"
                    }
                return {
                    "is_valid": True,
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

    def validate_classify(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Section Classifier 결과 검증 (V2 workflow)

        Args:
            task_output: {"definition_core": [...], "definition_annotation": [...], "condition": [...], "other": [...]}
            context: {"all_sections": [...]}

        Returns:
            Dict: 검증 결과
        """
        try:
            # Section Classifier 결과인 경우 (V2 workflow)
            if all(key in task_output for key in ["definition_core", "definition_annotation", "condition", "other"]):
                # LLM 기반 상세 검증 수행
                return self.validate_section_classifier_llm(task_output, context)

            # 예외 처리: section_classifier 결과가 아닌 경우
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": ["Invalid section_classifier output format"],
                "suggestions": ["Ensure section_classifier returns all 4 category keys"],
                "reasoning": "Expected section_classifier output with 4 categories"
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": [],
                "reasoning": "Validation failed"
            }

    def validate_section_classifier_llm(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        SectionClassifier 결과를 LLM으로 상세 검증

        각 분류 카테고리의 섹션들이 올바르게 분류되었는지 실제 내용을 검토합니다.

        Args:
            task_output: {"definition_core": [...], "definition_annotation": [...],
                         "condition": [...], "other": [...]}
            context: {"all_sections": [...]} - 전체 섹션 정보

        Returns:
            Dict: 검증 결과
        """
        try:
            definition_core = task_output.get("definition_core", [])
            definition_annotation = task_output.get("definition_annotation", [])
            condition = task_output.get("condition", [])
            other = task_output.get("other", [])

            # 기본 형태 검증
            if not definition_core:
                return {
                    "is_valid": False,
                    "confidence": 0.7,
                    "errors": ["No definition_core sections found by classifier"],
                    "suggestions": [
                        "Re-run classifier with adjusted parameters",
                        "Check if document actually contains definition information"
                    ],
                    "reasoning": "section_classifier found no core definition sections"
                }

            for key in ["definition_core", "definition_annotation", "condition", "other"]:
                if not isinstance(task_output.get(key), list):
                    return {
                        "is_valid": False,
                        "confidence": 0.3,
                        "errors": [f"Invalid type for {key}: expected list"],
                        "suggestions": ["Check classifier output format"],
                        "reasoning": f"section_classifier output has wrong type for {key}"
                    }

            # 전체 섹션 정보 가져오기
            all_sections = context.get("all_sections", [])

            # 각 카테고리별 샘플 섹션 내용 준비 (검증용)
            def get_section_content_sample(indices, sections, max_sections=None):
                """인덱스 리스트에 해당하는 섹션의 샘플 내용 추출"""
                if max_sections == None:
                    max_sections = len(indices)
                samples = []
                for idx in indices[:max_sections]:
                    if idx < len(sections):
                        section = sections[idx]
                        title = section.get("title", "(제목 없음)")
                        content = section.get("content", [])
                        # 내용 미리보기 (처음 300자)
                        content_preview = json.dumps(content, ensure_ascii=False)[:300]
                        samples.append({
                            "index": idx,
                            "title": title,
                            "content_preview": content_preview
                        })
                return samples

            core_samples = get_section_content_sample(definition_core, all_sections)
            annotation_samples = get_section_content_sample(definition_annotation, all_sections,)
            condition_samples = get_section_content_sample(condition, all_sections)
            other_samples = get_section_content_sample(other, all_sections,3)

            prompt = f"""당신은 보험 약관 문서의 섹션 분류 결과를 검토하는 전문가입니다.

**임무**: 다음 분류 결과가 **전반적으로 합리적인지** 확인하세요.

**분류 결과 요약**:
- definition_core (정의 핵심): {len(definition_core)}개 섹션
- definition_annotation (정의 보조): {len(definition_annotation)}개 섹션
- condition (보장 조건): {len(condition)}개 섹션
- other (기타): {len(other)}개 섹션

**definition_core 샘플 섹션들**:
{json.dumps(core_samples, ensure_ascii=False, indent=2)}

**definition_annotation 샘플 섹션들**:
{json.dumps(annotation_samples, ensure_ascii=False, indent=2)}

**condition 샘플 섹션들**:
{json.dumps(condition_samples, ensure_ascii=False, indent=2)}

**other 샘플 섹션들**:
{json.dumps(other_samples, ensure_ascii=False, indent=2)}

### 카테고리 정의 (참고용)

1. **definition_core** (핵심 정의 섹션)
   - 질문: 이 문서에서 정의하는 **상품/특약/보장계약이 무엇이며, 어떤 종류/조합으로 구성되어 있는가?**
   - 예: 상품/특약의 명칭과 버전(해약환급금 미지급형 vs 일반형), 1종/2종, 주계약/특약 등
   - 특징: "무엇으로 구성되어 있는지"를 설명하는 정적인 구조 정의
   - **"정의"와 "설명"은 실질적으로 같은 의미입니다. 구분하지 마세요.**

2. **definition_annotation** (정의 주석/보충 섹션)
   - 질문: 위에서 정의한 구조에 대해 **어떤 예외/변경/추가 설명**이 있는가?
   - 예: 명칭/표기법 설명, 정의값에 대한 보충, 각주, "※", "참고" 등
   - 특징: definition_core에서 정의한 값들을 수정/보완/해석하는 텍스트

3. **condition** (계약/가입 조건 섹션)
   - 질문: 각 종류(유형/종/보장형)를 **어떤 조건으로 가입/유지할 수 있는가?**
   - 예: 보험기간, 보험료 납입기간, 가입나이, 보험료 납입주기 등
   - 특징: 기간/연령/납입 조건을 수치/범위로 표현
   - **중요**: "유형1", "유형2" 같은 컬럼이 있어도 condition일 수 있음 (숫자 조건 컬럼이 2개 이상이면 condition 가능성 높음)

4. **other** (기타 섹션)
   - 위 3가지에 해당하지 않는 모든 섹션

### 검토 규칙

**중요한 마음가짐**:
- 분류 시스템이 이미 전문적으로 분류했다고 가정하세요
- **명백하고 심각한 오류**만 지적하세요
- 사소한 차이나 애매한 경계는 무시하세요
- **3개 이상의 명백한 오분류**가 있을 때만 is_valid=false로 설정하세요

**합리적인 분류 (is_valid=true)**:
- definition_core에 상품 구조/종류/명칭 관련 내용이 있음
- condition에 기간/나이 등 조건 정보가 있음
- 대부분의 분류가 말이 됨

**명백한 오류 (is_valid=false가 될 수 있음)**:
- definition_core에 정의 관련 내용이 전혀 없고 조건만 있음
- condition에 정의 테이블만 있고 조건이 없음
- **3개 이상**의 섹션이 명백하게 잘못 분류됨

**무시해야 할 것들**:
- "정의한다" vs "설명한다" 같은 표현 차이 → 실질적으로 같음
- core vs annotation의 경계 애매함 → 둘 다 합리적이면 OK
- 제목과 내용의 미묘한 불일치 → 내용 우선

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 오분류만 기록 (사소한 차이는 무시)
    // 예: "섹션 5가 definition_core로 분류되었으나 명백히 조건 테이블임"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
  ],
  "reasoning": "분류 결과가 전반적으로 합리적인지 평가"
}}

**참고**: 당신의 역할은 재분류가 아니라 합리성 확인입니다. 애매한 경우는 is_valid=true를 반환하세요."""

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
                "suggestions": ["Check classifier output and retry"],
                "reasoning": "SectionClassifier validation failed"
            }

    def validate_definition_extract_v2_llm(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        DefinitionExtractV2 결과를 LLM으로 상세 검증

        추출된 테이블이 정의 정보를 올바르게 구조화했는지 검증합니다.

        Args:
            task_output: {"header": [...], "data": [[...], ...], "extraction_method": "v2_classifier_based"}
            context: {
                "core_sections": [...] - 원본 core 섹션들
                "annotation_sections": [...] - 원본 annotation 섹션들 (optional)
            }

        Returns:
            Dict: 검증 결과
        """
        try:
            header = task_output.get("header") or []
            data = task_output.get("data") or []

            # 기본 형태 검증
            if not header or not data:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["definition_extract_v2 returned empty header or data"],
                    "suggestions": [
                        "Check if core sections contain valid tables or text",
                        "Try LLM-based extraction as fallback"
                    ],
                    "reasoning": "definition_extract_v2 produced empty table"
                }

            # 원본 core 섹션 정보 가져오기
            core_sections = context.get("core_sections", [])
            annotation_sections = context.get("annotation_sections", [])

            # core 섹션들의 내용 미리보기 준비
            core_sections_preview = []
            for idx, section in enumerate(core_sections[:]):  # 최대 3개 샘플
                title = section.get("title", "(제목 없음)")
                content = section.get("content", [])
                content_str = json.dumps(content, ensure_ascii=False)[:]
                core_sections_preview.append({
                    "index": idx,
                    "title": title,
                    "content_preview": content_str
                })

            # annotation 섹션들의 내용 미리보기 준비
            annotation_sections_preview = []
            for idx, section in enumerate(annotation_sections[:]):  # 최대 3개 샘플
                title = section.get("title", "(제목 없음)")
                content = section.get("content", [])
                content_str = json.dumps(content, ensure_ascii=False)[:]
                annotation_sections_preview.append({
                    "index": idx,
                    "title": title,
                    "content_preview": content_str
                })
            definition_sections = context.get("definition_sections", [])

            prompt = f"""당신은 데이터 추출 품질을 검토하는 전문가입니다.

**임무**: 
- DefinitionExtractV2 도구가 원본 섹션에서 테이블을 **올바르게 추출**했는지 확인하세요.
- 정의 관련 섹션들(테이블 + 텍스트)를 보고, DefinitinoExtractV2가 추출한 테이블이 이 섹션들의 정의 + 주석/예외를 대체로 잘 반영했는지 확인하세요

**원본 정의 관련 섹션들 (샘플)**:
{json.dumps(definition_sections, ensure_ascii=False, indent=2)}

**추출된 테이블**:
Header: {json.dumps(header, ensure_ascii=False)}
Data 행 수: {len(data)}
전체 Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

### DefinitionExtractV2의 역할 이해하기

**ExtractV2가 하는 일**:
- 원본 core 섹션의 테이블/텍스트에서 **있는 그대로** header와 data 추출
- 원본 컬럼명 유지 (예: "명칭", "보험종목" → 그대로 사용)
- 여러 core 섹션의 테이블 병합
- **Annotation 섹션이 있으면** LLM으로 병합 (주석 반영해서 테이블 업데이트)

**ExtractV2가 하지 않는 일** (이건 다음 단계인 Cartesian의 역할):
- ❌ 컬럼명 정규화 ("명칭" → "보종명", "보험종목" → "유형1" 변환 등)
- ❌ 계층 구조 확장/재구성
- ❌ 데이터 변환/재배치

### 검증 기준 (추출 품질만 확인)

**합리적인 추출 (is_valid=true)**:
1. Header와 Data가 비어있지 않음
2. 원본 정의 섹션의 주요 내용이 누락되지 않음
3. 주석 행("※", "주:", "*")이 데이터로 잘못 포함되지 않음
4. 여러 섹션 병합 시 데이터 손실이나 중복이 없음
5. 정의 섹션 안에 주석/예외 텍스트가 있는 경우, 주석/예외 내용이 합리적으로 반영됨 (완벽하지 않아도 OK)

**명백한 추출 오류 (is_valid=false가 될 수 있음)**:
1. Header나 Data가 완전히 비어있음
2. 원본 정의 섹션에 있는 중요한 데이터 행이 추출되지 않음
3. "※", "주:", "참고" 같은 주석이 데이터 행으로 잘못 포함됨
4. 여러 테이블 병합 시 명백한 헤더 불일치로 데이터 깨짐
5. 정의 테이블과 주석/예외 병합 과정에서 정의 데이터가 손실되거나 완전히 잘못됨

**무시해야 할 것들** (다음 단계의 역할):
- ❌ "보종명" 컬럼이 없다 → 원본에 "명칭"이면 그대로 추출하는 게 맞음
- ❌ "유형1", "유형2"로 표준화 안 됨 → Cartesian의 역할
- ❌ 계층 구조가 부족함 → 원본 그대로 추출하면 OK
- ❌ 컬럼명이 이상함 → 원본이 이상한 거면 그대로 추출하는 게 맞음

### 검토 규칙

**중요한 마음가짐**:
- ExtractV2는 **변환기가 아니라 추출기**입니다
- 원본에 있는 내용을 **있는 그대로** 잘 가져왔는지만 확인하세요
- 컬럼명 표준화나 구조 개선은 다음 단계의 역할입니다
- **명백한 추출 오류**만 지적하세요

다음 JSON 형식으로 반환:
{{
  "is_valid": true/false,
  "confidence": 0.0~1.0,
  "errors": [
    // 명백한 추출 오류만 기록
    // 예: "원본 테이블의 2번째 행이 누락됨"
    // 예: "주석 행 '※ 참고사항'이 데이터로 잘못 포함됨"
  ],
  "suggestions": [
    // errors가 있을 때만 구체적 개선 제안
    // 예: "LLM 기반 추출로 재시도"
  ],
  "reasoning": "원본 섹션의 내용이 테이블로 올바르게 추출되었는지 평가"
}}

**참고**: 컬럼명이나 구조가 이상해도, 원본이 그렇다면 올바른 추출입니다. is_valid=true를 반환하세요."""

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
                "suggestions": ["Check ExtractV2 output and retry"],
                "reasoning": "DefinitionExtractV2 validation failed"
            }

    def validate_extract_definitions(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        [DEPRECATED - V1 workflow only]
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
