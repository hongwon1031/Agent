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
from core.prompt import (build_validate_section_classifier_llm,
                         build_validate_definition_extract_v2_llm,
                         build_validate_transform_llm)

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

            prompt = build_validate_section_classifier_llm(
                definition_core = definition_core,
                definition_annotation = definition_annotation,
                condition = condition,
                other = other,
                core_samples = core_samples,
                annotation_samples = annotation_samples,
                condition_samples = condition_samples,
                other_samples = other_samples, 
            )

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

            prompt = build_validate_definition_extract_v2_llm(
                        definition_sections=definition_sections,
                        header=header,
                        data=data,
                        )

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

            prompt = build_validate_transform_llm(header, data, definitions)


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
