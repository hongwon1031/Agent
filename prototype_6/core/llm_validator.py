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
            task_type: "search" | "extract" | "extract_condition" | "transform" | "merge"
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
        elif task_type == "extract_condition":
            return self.validate_condition_extract(task_output, context)
        elif task_type == "transform":
            return self.validate_transform(task_output, context)
        elif task_type == "merge":
            return self.validate_merge(task_output, context)
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

    def validate_condition_extract(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Condition Extract 결과 검증

        Args:
            task_output: {"header": [...], "data": [[]]}
            context: {"condition_sections": [...]}

        Returns:
            Dict: 검증 결과
        """
        try:
            header = task_output.get("header") or []
            data = task_output.get("data") or []

            # If no condition sections were provided, empty result is valid
            condition_sections = context.get("condition_sections", [])
            if not condition_sections:
                if not header and not data:
                    return {
                        "is_valid": True,
                        "confidence": 1.0,
                        "errors": [],
                        "suggestions": [],
                        "reasoning": "No condition sections provided, empty result is valid"
                    }

            # If sections exist, we expect some data
            if not header or not data:
                return {
                    "is_valid": False,
                    "confidence": 0.7,
                    "errors": ["condition_extract returned empty header or data despite condition sections existing"],
                    "suggestions": [
                        "Check if condition sections contain valid tables",
                        "Review column name normalization logic"
                    ],
                    "reasoning": "condition_extract produced empty table"
                }

            # Check for minimum required columns (at least 2 condition columns beyond JOIN keys)
            # Common JOIN keys: 유형1, 유형2, 심사형, 보장형
            join_key_candidates = ["유형1", "유형2", "심사형", "보장형"]
            condition_columns = [col for col in header if col not in join_key_candidates]

            if len(condition_columns) < 2:
                return {
                    "is_valid": False,
                    "confidence": 0.6,
                    "errors": [f"Too few condition columns found: {condition_columns}"],
                    "suggestions": [
                        "Check if condition table has columns like 보험기간, 납입기간, etc.",
                        "Review extraction logic"
                    ],
                    "reasoning": f"Expected at least 2 condition columns, found {len(condition_columns)}"
                }

            # Check for JOIN keys (at least one type column)
            join_keys_found = [col for col in header if col in join_key_candidates]
            if not join_keys_found:
                return {
                    "is_valid": False,
                    "confidence": 0.7,
                    "errors": ["No JOIN key columns (유형1, 유형2, etc.) found in condition table"],
                    "suggestions": [
                        "Ensure condition table includes type columns for joining",
                        "Check column name normalization"
                    ],
                    "reasoning": "Condition table missing JOIN key columns"
                }

            # Basic validation passed
            return {
                "is_valid": True,
                "confidence": 0.9,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Condition extract successful: {len(header)} columns, {len(data)} rows, JOIN keys: {join_keys_found}"
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check condition_extract output format"],
                "reasoning": "Condition extract validation failed"
            }

    def validate_merge(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Definition + Condition Merge 결과 검증

        Args:
            task_output: {"definitions": [...], "total_count": int, "join_stats": {...}}
            context: {
                "definition_result": {...},
                "condition_result": {...}
            }

        Returns:
            Dict: 검증 결과
        """
        try:
            definitions = task_output.get("definitions", [])
            total_count = task_output.get("total_count", 0)
            join_stats = task_output.get("join_stats", {})

            # If no definitions, merge failed
            if not definitions:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["Merge produced no definitions"],
                    "suggestions": ["Check input definition and condition data"],
                    "reasoning": "Merge result is empty"
                }

            # Check if definitions have both definition and condition columns
            if definitions:
                sample_def = definitions[0]
                # Definition columns: 보종명, 유형1, 유형2, etc.
                # Condition columns: 보험기간, 납입기간, etc.
                has_definition_cols = "보종명" in sample_def

                # Check for typical condition columns
                condition_col_candidates = ["보험기간", "납입기간", "가입나이_남", "가입나이_여", "납입주기"]
                has_condition_cols = any(col in sample_def for col in condition_col_candidates)

                if not has_definition_cols:
                    return {
                        "is_valid": False,
                        "confidence": 0.8,
                        "errors": ["Merged definitions missing core definition column (보종명)"],
                        "suggestions": ["Check definition input data"],
                        "reasoning": "Merged result missing definition columns"
                    }

                # If condition data exists but no condition columns in result, that's suspicious
                condition_input = context.get("condition_result", {})
                condition_header = condition_input.get("header", [])
                if condition_header and not has_condition_cols:
                    # This might be OK if condition data doesn't have standard columns
                    # Just warn, don't fail
                    pass

            # Check unmatched ratio
            matched = join_stats.get("matched", 0)
            unmatched = join_stats.get("unmatched", 0)

            if matched + unmatched > 0:
                unmatched_ratio = unmatched / (matched + unmatched)
                if unmatched_ratio > 0.5:
                    return {
                        "is_valid": False,
                        "confidence": 0.6,
                        "errors": [f"Too many unmatched definitions: {unmatched}/{matched + unmatched} ({unmatched_ratio:.1%})"],
                        "suggestions": [
                            "Check JOIN key matching logic",
                            "Review wildcard rules",
                            "Verify condition data includes matching rows"
                        ],
                        "reasoning": f"Unmatched ratio {unmatched_ratio:.1%} exceeds 50% threshold"
                    }

            # All checks passed
            return {
                "is_valid": True,
                "confidence": 0.9,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Merge successful: {total_count} definitions, {matched} matched, {unmatched} unmatched"
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check merge output format"],
                "reasoning": "Merge validation failed"
            }
