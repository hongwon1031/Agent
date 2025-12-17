"""
LLM-based Validator

Task 결과를 LLM이 검증합니다.
- Task 타입별 검증 로직
- 전체 데이터 검증 (샘플 X)
- 구체적인 에러 메시지와 개선 제안
"""

import json
import os
from typing import Dict, Any, List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from core.prompt import (build_validate_section_classifier_llm,
                         build_validate_definition_extract_v2_llm,
                         build_validate_transform_llm,
                         build_validate_grouping_logic_llm_prompt)

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
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # LLM usage tracking
        self._llm_stats = {
            "validate_section_classifier": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_definition_extract_v2": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_table_split": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_condition_transform": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_transform": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_condition_extract": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "validate_grouping_logic": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0},
            "analyze_root_cause": {"call_count": 0, "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_tokens": 0, "total_time_ms": 0}
        }

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
            context: 추가 컨텍스트 (원본 문서, previous_results for Prototype 7)

        Returns:
            Dict: 검증 결과
                {
                    "is_valid": bool,
                    "confidence": float,
                    "errors": List[str],
                    "suggestions": List[str],
                    "reasoning": str,
                    "root_cause_task_id": Optional[str]  # Prototype 7: For backtracking
                }
        """
        if context is None:
            context = {}

        # CRITICAL: Check for execution errors and analyze upstream tasks
        # Define upstream task dependencies for each task type
        UPSTREAM_DEPENDENCIES = {
            "definition_extract_v2": ["section_classifier"],  # FIXED: Added missing dependency
            "table_split": ["definition_extract_v2"],
            "condition_extract": ["section_classifier"],      # FIXED: Added missing dependency
            "condition_transform": ["condition_extract"],
            "grouping": ["condition_transform", "llm_table_split"],
            "combination_generation": ["grouping_logic_extractor"],
        }

        execution_error = context.get("execution_error")
        task_output_is_empty = False

        # FIXED: Check if current task output is empty/invalid (even if tool succeeded)
        if isinstance(task_output, dict):
            header = task_output.get("header", [])
            data = task_output.get("data", [])
            groups = task_output.get("groups", [])

            if not header or not data:
                task_output_is_empty = True
            if task_type == "grouping" and not groups:
                task_output_is_empty = True

        # FIXED: Check upstream tasks for BOTH execution errors AND empty/invalid outputs
        if execution_error or task_output_is_empty:
            upstream_tools = UPSTREAM_DEPENDENCIES.get(task_type, [])
            if upstream_tools:
                previous_results = context.get("previous_results", [])

                # Check if upstream tasks produced empty/invalid data
                for result in reversed(previous_results):
                    tool_used = result.get("tool_used")
                    if tool_used in upstream_tools:
                        task_id = result.get("task_id")
                        data = result.get("data", {})

                        # Check if data is empty or invalid
                        is_empty = False
                        if isinstance(data, dict):
                            header = data.get("header", [])
                            rows = data.get("data", [])
                            groups = data.get("groups", [])

                            if not header or not rows:
                                is_empty = True
                            if tool_used == "grouping_logic_extractor" and not groups:
                                is_empty = True

                        if is_empty or not result.get("success"):
                            return {
                                "is_valid": False,
                                "confidence": 0.9,
                                "errors": [f"Execution failed: {execution_error}"],
                                "suggestions": [
                                    f"Upstream task {task_id} ({tool_used}) produced empty or invalid data",
                                    f"Re-run {task_id} to fix the root cause"
                                ],
                                "reasoning": f"Current task failed because upstream {task_id} did not produce valid data",
                                "root_cause_task_id": task_id,
                                "root_cause_reasoning": f"Task {task_id} ({tool_used}) produced no valid output"
                            }

        # CRITICAL FIX: Normalize task_type (Planner → Validator mapping)
        TASK_TYPE_ALIASES = {
            "classify_sections": "classify",
            "extract_definitions": "extract",
            "condition_extraction": "extract_condition",
            "combination_generation": "generate",
        }
        task_type = TASK_TYPE_ALIASES.get(task_type, task_type)

        # Route to appropriate validation method
        if task_type == "search" or task_type == "classify":
            result = self.validate_classify(task_output, context)
        elif task_type == "extract":
            # FIXED: V2가 기본이므로, 모든 extract는 V2 validator 사용
            # (V1 definition_extract는 deprecated)
            result = self.validate_definition_extract_v2_llm(task_output, context)
        elif task_type == "extract_condition":
            # NEW: LLM-based validation for condition_extract
            result = self.validate_condition_extract_llm(task_output, context)
        elif task_type == "table_split":
            # NEW: LLMTableSplitTool validation
            result = self.validate_table_split_llm(task_output, context)
        elif task_type == "transform":
            result = self.validate_transform(task_output, context)
        elif task_type == "condition_transform":
            # NEW: ConditionTransformTool validation
            result = self.validate_condition_transform_llm(task_output, context)
        elif task_type == "merge":
            result = self.validate_merge(task_output, context)
        elif task_type == "normalize_def":
            # Normalize definitions: just check structural validity (header + data)
            header = task_output.get("header", [])
            data = task_output.get("data", [])
            if not header or not data:
                result = {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["Normalized definitions missing header or data"],
                    "suggestions": ["Check normalize_definitions node logic"],
                    "reasoning": "normalize_definitions produced empty table"
                }
            else:
                result = {
                    "is_valid": True,
                    "confidence": 0.95,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"Normalized definitions table valid: {len(data)} rows, {len(header)} columns"
                }
        elif task_type == "normalize_cond":
            # Normalize conditions: just check structural validity (header + data)
            header = task_output.get("header", [])
            data = task_output.get("data", [])
            if not header or not data:
                result = {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["Normalized conditions missing header or data"],
                    "suggestions": ["Check normalize_conditions node logic"],
                    "reasoning": "normalize_conditions produced empty table"
                }
            else:
                result = {
                    "is_valid": True,
                    "confidence": 0.95,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"Normalized conditions table valid: {len(data)} rows, {len(header)} columns"
                }
        elif task_type == "grouping":
            # Extract grouping logic: use dedicated validator
            result = self.validate_grouping_logic(task_output, context)
        elif task_type == "generate":
            # Generate final combinations: use dedicated validator
            result = self.validate_final_combinations(task_output, context)
        else:
            result = {
                "is_valid": True,
                "confidence": 1.0,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Unknown task type: {task_type}, skipping validation"
            }

        # PROTOTYPE 7: Add root cause analysis if validation failed
        if not result.get("is_valid") and context.get("previous_results"):
            errors = result.get("errors", [])
            previous_results = context.get("previous_results", [])

            root_cause_analysis = self._analyze_root_cause(
                task_type=task_type,
                task_output=task_output,
                errors=errors,
                previous_results=previous_results
            )

            if root_cause_analysis:
                result["root_cause_task_id"] = root_cause_analysis.get("root_cause_task_id")
                result["root_cause_reasoning"] = root_cause_analysis.get("root_cause_reasoning", "")

        return result

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

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_section_classifier"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

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
                # FIXED: Check if upstream task (section_classifier) provided empty core sections
                previous_results = context.get("previous_results", [])
                definition_core_indices = []

                for result in previous_results:
                    if result.get("tool_used") == "section_classifier" and result.get("success"):
                        data_dict = result.get("data", {})
                        definition_core_indices = data_dict.get("definition_core", [])
                        break

                # If section_classifier produced no core sections, it's the root cause
                if not definition_core_indices:
                    return {
                        "is_valid": False,
                        "confidence": 0.9,
                        "errors": ["definition_extract_v2 returned empty because upstream section_classifier produced no definition_core sections"],
                        "suggestions": [
                            "Re-run section_classifier to properly identify definition sections",
                            "Check if document actually contains definition information"
                        ],
                        "reasoning": "definition_extract_v2 failed due to missing core sections from section_classifier",
                        "root_cause_task_id": "task0",
                        "root_cause_reasoning": "section_classifier produced no definition_core sections, causing definition_extract_v2 to fail"
                    }

                # Core sections exist but extraction still failed - current task's problem
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["definition_extract_v2 returned empty header or data"],
                    "suggestions": [
                        "Check if core sections contain valid tables or text",
                        "Try LLM-based extraction as fallback"
                    ],
                    "reasoning": "definition_extract_v2 produced empty table despite having core sections"
                }

            # 원본 core 섹션 정보 가져오기
            core_sections = context.get("core_sections", [])
            annotation_sections = context.get("annotation_sections", [])

            # core 섹션들의 내용 미리보기 준비
            # core_sections_preview = []
            # for idx, section in enumerate(core_sections[:]):  # 최대 3개 샘플
            #     title = section.get("title", "(제목 없음)")
            #     content = section.get("content", [])
            #     content_str = json.dumps(content, ensure_ascii=False)[:]
            #     core_sections_preview.append({
            #         "index": idx,
            #         "title": title,
            #         "content_preview": content_str
            #     })

            # # annotation 섹션들의 내용 미리보기 준비
            # annotation_sections_preview = []
            # for idx, section in enumerate(annotation_sections[:]):  # 최대 3개 샘플
            #     title = section.get("title", "(제목 없음)")
            #     content = section.get("content", [])
            #     content_str = json.dumps(content, ensure_ascii=False)[:]
            #     annotation_sections_preview.append({
            #         "index": idx,
            #         "title": title,
            #         "content_preview": content_str
            #     })
            # definition_sections = context.get("definition_sections", [])

            prompt = build_validate_definition_extract_v2_llm(
                        core_sections_preview = core_sections,
                        annotation_sections_preview=annotation_sections,
                        header=header,
                        data=data,
                        )

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_definition_extract_v2"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

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

    def validate_table_split_llm(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        LLMTableSplitTool 결과를 LLM으로 검증

        Args:
            task_output: {"header": [...], "data": [...], "notes": "..."}
            context: {
                "original_header": [...],
                "original_data": [...],
                "previous_results": [...]
            }

        Returns:
            Dict: 검증 결과
        """
        try:
            split_header = task_output.get("header") or []
            split_data = task_output.get("data") or []

            # 기본 형태 검증
            if not split_header or not split_data:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["table_split returned empty header or data"],
                    "suggestions": [
                        "Check if input table has valid data",
                        "Review split parameters"
                    ],
                    "reasoning": "table_split produced empty table"
                }

            # 원본 데이터 가져오기
            original_header = context.get("original_header", [])
            original_data = context.get("original_data", [])

            if not original_header or not original_data:
                return {
                    "is_valid": False,
                    "confidence": 0.5,
                    "errors": ["Original data not found in context"],
                    "suggestions": ["Ensure validate_task_node passes original_header/data in context"],
                    "reasoning": "Cannot validate without original data"
                }

            from core.prompt import build_validate_table_split_llm_prompt

            prompt = build_validate_table_split_llm_prompt(
                original_header=original_header,
                original_data=original_data,
                split_header=split_header,
                split_data=split_data,
            )

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_table_split"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check table_split output and retry"],
                "reasoning": "Table split validation failed"
            }

    def validate_condition_transform_llm(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ConditionTransformTool 결과를 LLM으로 검증

        Args:
            task_output: {"header": [...], "data": [...], "notes": "..."}
            context: {
                "original_header": [...],
                "original_data": [...],
                "previous_results": [...],
                "execution_error": str (if tool execution failed),
                "failed_task_id": str (current task id)
            }

        Returns:
            Dict: 검증 결과
        """
        try:
            # NOTE: Execution error analysis is now handled by validate() main function
            transformed_header = task_output.get("header") or []
            transformed_data = task_output.get("data") or []

            # 기본 형태 검증
            if not transformed_header or not transformed_data:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["condition_transform returned empty header or data"],
                    "suggestions": [
                        "Check if input condition table has valid data",
                        "Review transform parameters"
                    ],
                    "reasoning": "condition_transform produced empty table"
                }

            # 필수 컬럼 사전 체크 (빠른 실패)
            required_columns = [
                "보험기간", "납입기간",
                "주피보험자최소가입연령", "주피보험자최대가입연령",
                "주피보험자최소가입연령구분코드", "주피보험자최대가입연령구분코드",
                "주피보험자가입성별"
            ]

            missing_columns = [col for col in required_columns if col not in transformed_header]
            if missing_columns:
                return {
                    "is_valid": False,
                    "confidence": 0.9,
                    "errors": [f"필수 컬럼 누락: {missing_columns}"],
                    "suggestions": [
                        "Check ConditionTransformTool schema mapping logic",
                        f"Add missing columns: {missing_columns}"
                    ],
                    "reasoning": f"Required columns missing: {missing_columns}"
                }

            # 원본 데이터 가져오기
            original_header = context.get("original_header", [])
            original_data = context.get("original_data", [])

            if not original_header or not original_data:
                return {
                    "is_valid": False,
                    "confidence": 0.5,
                    "errors": ["Original condition data not found in context"],
                    "suggestions": ["Ensure validate_task_node passes original_header/data in context"],
                    "reasoning": "Cannot validate without original data"
                }

            from core.prompt import build_validate_condition_transform_llm_prompt

            prompt = build_validate_condition_transform_llm_prompt(
                original_header=original_header,
                original_data=original_data,
                transformed_header=transformed_header,
                transformed_data=transformed_data,
            )

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_condition_transform"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check condition_transform output and retry"],
                "reasoning": "Condition transform validation failed"
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

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_transform"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

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

    def validate_condition_extract_llm(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Condition Extract 결과를 LLM으로 검증

        Args:
            task_output: {"header": [...], "data": [...], "reasoning": "..."}
            context: {
                "condition_sections": [...],
                "all_sections": [...],
                "previous_results": [...]
            }

        Returns:
            Dict: {
                "is_valid": bool,
                "confidence": float,
                "errors": List[str],
                "suggestions": List[str],
                "reasoning": str
            }
        """
        try:
            extracted_header = task_output.get("header") or []
            extracted_data = task_output.get("data") or []

            # 기본 형태 검증
            if not extracted_header or not extracted_data:
                # Check if condition_sections exist
                condition_sections = context.get("condition_sections", [])
                if not condition_sections:
                    # FIXED: Check if document actually has no conditions or if section_classifier failed
                    all_sections = context.get("all_sections", [])

                    # Heuristic: Check if any section title contains condition-related keywords
                    condition_keywords = ["조건", "가입조건", "보험료", "납입", "계약조건", "특약"]
                    has_condition_content = False

                    if all_sections:
                        for section in all_sections:
                            title = str(section.get("title", "")).lower()
                            if any(keyword in title for keyword in condition_keywords):
                                has_condition_content = True
                                break

                    if has_condition_content:
                        # Document has condition-related sections but section_classifier missed them
                        return {
                            "is_valid": False,
                            "confidence": 0.85,
                            "errors": ["condition_extract returned empty because section_classifier failed to identify condition sections"],
                            "suggestions": [
                                "Re-run section_classifier to properly identify condition sections",
                                "Check section classification logic for condition-related keywords"
                            ],
                            "reasoning": "Document contains condition-related sections but section_classifier did not classify them as 'condition'",
                            "root_cause_task_id": "task0",
                            "root_cause_reasoning": "section_classifier failed to identify condition sections despite document having condition-related content"
                        }
                    else:
                        # Document actually has no condition sections - empty result is valid
                        return {
                            "is_valid": True,
                            "confidence": 1.0,
                            "errors": [],
                            "suggestions": [],
                            "reasoning": "No condition sections in document, empty result is valid"
                        }
                else:
                    # Sections exist but extraction returned empty
                    return {
                        "is_valid": False,
                        "confidence": 0.7,
                        "errors": ["condition_extract returned empty header/data despite condition sections existing"],
                        "suggestions": [
                            "Check if condition sections contain valid tables",
                            "Review extraction logic"
                        ],
                        "reasoning": "condition_extract produced empty table"
                    }

            # Get condition sections for validation
            condition_sections = context.get("condition_sections", [])

            if not condition_sections:
                # No original sections to compare against
                # Just do basic sanity checks
                join_key_candidates = ["유형0", "유형1", "유형2", "심사형", "보장형"]
                join_keys_found = [col for col in extracted_header if col in join_key_candidates]

                if not join_keys_found:
                    return {
                        "is_valid": False,
                        "confidence": 0.6,
                        "errors": ["No JOIN key columns (유형0, 유형1, etc.) found in extracted table"],
                        "suggestions": ["Ensure condition table includes type columns for joining"],
                        "reasoning": "Condition extract missing JOIN key columns"
                    }

                return {
                    "is_valid": True,
                    "confidence": 0.8,
                    "errors": [],
                    "suggestions": [],
                    "reasoning": f"Basic validation passed: {len(extracted_header)} columns, {len(extracted_data)} rows, JOIN keys: {join_keys_found}"
                }

            # Build LLM validation prompt
            from core.prompt import build_validate_condition_extract_llm_prompt

            # Get definition sections for annotation reference checking
            definition_sections = context.get("definition_sections", None)

            prompt = build_validate_condition_extract_llm_prompt(
                condition_sections=condition_sections,
                extracted_header=extracted_header,
                extracted_data=extracted_data,
                definition_sections=definition_sections
            )

            # Call LLM for validation
            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_condition_extract"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

            result = json.loads(response.choices[0].message.content)

            # Ensure required fields
            if "is_valid" not in result:
                result["is_valid"] = False
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "errors" not in result:
                result["errors"] = []
            if "suggestions" not in result:
                result["suggestions"] = []
            if "reasoning" not in result:
                result["reasoning"] = "LLM validation completed"

            return result

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"LLM validation error: {str(e)}"],
                "suggestions": ["Check condition_extract output format", "Review LLM validation prompt"],
                "reasoning": "Condition extract LLM validation failed"
            }

    def validate_merge(
        self,
        task_output: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Definition + Condition Merge 결과 검증 (for new LLM-based tool)

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
                    "suggestions": ["Check input definition and condition data", "Review merge prompt"],
                    "reasoning": "Merge result is empty"
                }

            # Check if definitions have the core definition column
            if definitions:
                sample_def = definitions[0]
                if "보종명" not in sample_def:
                    return {
                        "is_valid": False,
                        "confidence": 0.9,
                        "errors": ["Merged definitions missing core definition column (보종명)"],
                        "suggestions": ["Check merge tool's output formatting"],
                        "reasoning": "Merged result missing '보종명' column"
                    }

            # Check unmatched ratio from the new join_stats structure
            definition_count = join_stats.get("definition_count", 0)
            unmatched_indices = join_stats.get("unmatched_definition_indices", [])

            if definition_count > 0:
                unmatched_ratio = len(unmatched_indices) / definition_count
                if unmatched_ratio > 0.5:
                    return {
                        "is_valid": False,
                        "confidence": 0.6,
                        "errors": [f"Too many unmatched definitions: {len(unmatched_indices)}/{definition_count} ({unmatched_ratio:.1%})"],
                        "suggestions": [
                            "Check JOIN key matching logic in the LLM prompt",
                            "Review wildcard and semantic matching rules",
                            "Verify condition data includes matching rows for all definition types"
                        ],
                        "reasoning": f"Unmatched ratio {unmatched_ratio:.1%} exceeds 50% threshold"
                    }

            # All checks passed
            return {
                "is_valid": True,
                "confidence": 0.9,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Merge successful: {total_count} definitions generated. Unmatched: {len(unmatched_indices)}/{definition_count}."
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check merge tool's output format and keys"],
                "reasoning": "Merge validation failed due to an exception"
            }

    def _validate_grouping_logic_rules(self, task_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        STAGE 1: Rule-based structural validation for grouping logic.

        Fast checks for basic structure and coverage.

        Args:
            task_output: Grouping logic from GroupingLogicExtractorTool
            context: Definition and condition data

        Returns:
            Dict: Validation result (structure only)
        """
        try:
            # Extract required data
            column_mapping = task_output.get("column_mapping", {})
            groups = task_output.get("groups", [])
            unmatched = task_output.get("unmatched", {})
            summary = task_output.get("summary", {})

            definition_data = context.get("definition_data", [])
            condition_data = context.get("condition_data", [])

            # 1. Check required keys
            if not groups:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["No groups found in grouping logic"],
                    "suggestions": ["Check LLM grouping extraction", "Review prompt for clarity"],
                    "reasoning": "Grouping logic has no groups"
                }

            if not column_mapping:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["No column_mapping found in grouping logic"],
                    "suggestions": ["Check LLM output format"],
                    "reasoning": "Missing column_mapping"
                }

            # 2. Validate indices
            for group in groups:
                definition_indices = group.get("definition_indices", [])
                cond_indices = group.get("condition_indices", None)

                # Check definition indices
                for def_idx in definition_indices:
                    if def_idx < 0 or def_idx >= len(definition_data):
                        return {
                            "is_valid": False,
                            "confidence": 0.9,
                            "errors": [f"Invalid definition_index {def_idx} in group {group.get('id')} (out of range 0-{len(definition_data)-1})"],
                            "suggestions": ["Review grouping logic for index errors"],
                            "reasoning": "Definition index out of range"
                        }

                # Check condition index
                if cond_indices is None:
                    # fallback: legacy condition_index
                    single = group.get("condition_index", None)
                    if isinstance(single, int):
                        cond_indices = [single]
                    else:
                        return {
                            "is_valid": False,
                            "confidence": 0.9,
                            "errors": [
                                f"Missing condition_indices/condition_index in group {group.get('id')}"
                            ],
                            "suggestions": ["Ensure grouping outputs condition_indices"],
                            "reasoning": "Missing condition indices"
                        }

            # 3. Check coverage ratio
            coverage_ratio = summary.get("coverage_ratio", 0.0)
            matched_count = summary.get("matched_definition_count", 0)
            total_defs = summary.get("total_definitions", len(definition_data))

            if coverage_ratio < 0.5:
                return {
                    "is_valid": False,
                    "confidence": 0.7,
                    "errors": [f"Low coverage: only {matched_count}/{total_defs} definitions matched ({coverage_ratio:.1%})"],
                    "suggestions": [
                        "Check if condition data covers all definition types",
                        "Review fuzzy matching logic in prompt",
                        "Check wildcard handling"
                    ],
                    "reasoning": f"Coverage ratio {coverage_ratio:.1%} below 50% threshold"
                }

            # 4. Check JOIN keys
            join_keys = column_mapping.get("join_keys", [])
            if not join_keys:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["No JOIN keys specified in column_mapping"],
                    "suggestions": ["Review column_mapping logic", "Ensure common columns are identified"],
                    "reasoning": "Missing JOIN keys"
                }

            # All checks passed
            return {
                "is_valid": True,
                "confidence": 0.9,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Grouping logic valid: {len(groups)} groups, {matched_count}/{total_defs} definitions matched ({coverage_ratio:.1%})"
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check grouping logic output format"],
                "reasoning": "Grouping validation failed due to an exception"
            }

    def _validate_grouping_logic_llm(self, task_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        STAGE 2: LLM-based semantic validation for grouping logic.

        Deep validation for logical consistency:
        1. join_mappings values vs actual definition row values
        2. join_mappings values vs actual condition row values
        3. definition_indices actually satisfy join_mappings
        4. Unmatched definitions have valid reasons

        Args:
            task_output: Grouping logic from GroupingLogicExtractorTool
            context: Definition and condition data with headers

        Returns:
            Dict: Validation result with semantic analysis
        """
        try:
            column_mapping = task_output.get("column_mapping", {})
            groups = task_output.get("groups", [])
            unmatched = task_output.get("unmatched", {})
            summary = task_output.get("summary", {})

            definition_header = context.get("definition_header", [])
            definition_data = context.get("definition_data", [])
            condition_header = context.get("condition_header", [])
            condition_data = context.get("condition_data", [])

            # Build detailed group info for LLM
            groups_detail = []
            for group in groups[:10]:  # Limit to first 10 groups for prompt size
                group_id = group.get("id")
                matched_list_items = group.get("matched_list_items", None)
                join_mappings = group.get("join_mappings", [])
                definition_indices = group.get("definition_indices", [])
                condition_indices = group.get("condition_indices", [])
                if not isinstance(condition_indices, list):
                    condition_indices = [condition_indices]

                # Get actual definition rows
                def_rows = []
                for idx in definition_indices[:5]:  # Max 5 per group
                    if idx < len(definition_data):
                        row_dict = dict(zip(definition_header, definition_data[idx]))
                        def_rows.append({"index": idx, "data": row_dict})

                # Get actual condition row
                cond_rows = []

                for ci in condition_indices:
                    if ci < 0 or ci >= len(condition_data):
                        continue  # or raise error

                    cond_rows.append({
                        "index": ci,
                        "data": dict(zip(condition_header, condition_data[ci]))
                    })


                groups_detail.append({
                    "id": group_id,
                    "join_mappings": join_mappings,
                    "definition_rows": def_rows,
                    "condition_row": cond_rows,
                    "matched_list_items": matched_list_items,

                })

            # Unmatched definitions
            unmatched_def_indices = unmatched.get("definition_indices", [])
            unmatched_defs = []
            for idx in unmatched_def_indices[:5]:  # Max 5
                if idx < len(definition_data):
                    row_dict = dict(zip(definition_header, definition_data[idx]))
                    unmatched_defs.append({"index": idx, "data": row_dict})

            # Unmatched condition rows
            unmatched_cond_indices = unmatched.get("condition_indices", [])
            unmatched_conds = []
            for idx in unmatched_cond_indices[:5]:  # Max 5
                if idx < len(condition_data):
                    row_dict = dict(zip(condition_header, condition_data[idx]))
                    unmatched_conds.append({"index": idx, "data": row_dict})


            print('🔥definition_header🔥')
            print(definition_header)
            print('🔥condition_header🔥')
            print(condition_header)
            print('🔥groups_detail🔥')
            print(groups_detail)
            print('🔥unmatched_defs🔥')
            print(unmatched_defs)
            print('🔥column_mapping🔥')
            print(column_mapping)
            print('🔥summary🔥')
            print(summary)
            print('🔥END🔥')
            # Build prompt
            prompt = build_validate_grouping_logic_llm_prompt(
                definition_header=definition_header,
                condition_header=condition_header,
                groups_detail=groups_detail,
                unmatched_defs=unmatched_defs,
                unmatched_conds=unmatched_conds,
                column_mapping=column_mapping,
                summary=summary
            )

            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["validate_grouping_logic"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"LLM validation error: {str(e)}"],
                "suggestions": ["Check grouping logic LLM validation"],
                "reasoning": "Grouping LLM validation failed due to an exception"
            }

    def validate_grouping_logic(self, task_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        HYBRID: Validate grouping logic extraction (Rule + LLM).

        Two-stage validation:
        1. Rule-based: Fast structural checks
        2. LLM-based: Deep semantic consistency checks

        Args:
            task_output: Grouping logic from GroupingLogicExtractorTool
            context: {
                "definition_header": [...],
                "definition_data": [...],
                "condition_header": [...],
                "condition_data": [...]
            }

        Returns:
            Dict: Validation result
        """
        # STAGE 1: Rule-based structural validation
        # rule_result = self._validate_grouping_logic_rules(task_output, context)
        # if not rule_result.get("is_valid"):
        #     return rule_result  # Fast fail

        # STAGE 2: LLM-based semantic validation
        llm_result = self._validate_grouping_logic_llm(task_output, context)
        return llm_result

    def validate_final_combinations(self, task_output: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        NEW: Validate final combination generation.

        Checks:
        1. Definitions list is not empty
        2. Has required core column (보종명)
        3. Match rate is acceptable
        4. Generation stats are present

        Args:
            task_output: Final result from CombinationGeneratorTool
            {
                "definitions": [...],
                "total_count": int,
                "generation_stats": {...}
            }
            context: {
                "grouping_logic": {...}
            }

        Returns:
            Dict: Validation result
        """
        try:
            definitions = task_output.get("definitions", [])
            total_count = task_output.get("total_count", 0)
            stats = task_output.get("generation_stats", {})

            # 1. Check if definitions exist
            if not definitions:
                return {
                    "is_valid": False,
                    "confidence": 1.0,
                    "errors": ["Final combination generation produced no definitions"],
                    "suggestions": ["Check grouping logic", "Review combination generator logic"],
                    "reasoning": "No definitions generated",
                    "root_cause_task_id": None,
                }

            sample_def = definitions[0]
            if "보종명" not in sample_def:
                return {
                    "is_valid": False,
                    "confidence": 0.9,
                    "errors": ["Generated definitions missing core column (보종명)"],
                    "suggestions": ["Check combination generator's column mapping"],
                    "reasoning": "Missing '보종명' column",
                    "root_cause_task_id": None,
                }

            if not stats:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": ["Missing generation_stats in output"],
                    "suggestions": ["Check combination generator output format"],
                    "reasoning": "No stats available",
                    "root_cause_task_id": None,
                }

            matched = int(stats.get("matched_definitions", 0) or 0)
            unmatched = int(stats.get("unmatched_definitions", 0) or 0)

            # ✅ 핵심: match_rate는 "정의 row 단위"로 계산해야 함 (카티전 row 수로 나누면 안 됨)
            denom = matched + unmatched
            if denom > 0:
                match_rate = matched / denom

                # 너무 공격적으로 false 주지 말고, 정말 낮을 때만 fail 권장
                # (문서가 정의는 많고 조건은 일부만 주는 케이스가 흔함)
                if match_rate < 0.2:
                    return {
                        "is_valid": False,
                        "confidence": 0.6,
                        "errors": [f"Low definition-level match rate: {matched}/{denom} ({match_rate:.1%})"],
                        "suggestions": [
                            "Review grouping logic for accuracy",
                            "Check join_keys alignment between definition/condition (possible 유형 shift)",
                            "Verify wildcard ('-') handling as ANY-match",
                        ],
                        "reasoning": f"Definition-level match rate {match_rate:.1%} below 20% threshold",
                        "root_cause_task_id": None,
                    }

            # ✅ 최종 스키마 기준 required 컬럼 (너가 지금 쓰는 키들로 맞춤)
            required_value_cols = [
                "보험기간",
                "납입기간",
                "주피보험자최소가입연령",
                "주피보험자최대가입연령",
                "주피보험자최소가입연령구분코드",
                "주피보험자최대가입연령구분코드",
                "주피보험자가입성별",
            ]

            missing_cols = [col for col in required_value_cols if col not in sample_def]
            if missing_cols:
                return {
                    "is_valid": False,
                    "confidence": 0.8,
                    "errors": [f"Missing required columns in final output: {missing_cols}"],
                    "suggestions": ["Ensure combination_generator merges condition columns correctly"],
                    "reasoning": "Required columns absent in final output schema",
                    "root_cause_task_id": None,
                }

            # ✅ “전부 null” 체크는 '매칭된 row'만 대상으로 해야 함 (unmatched row는 null이어도 정상)
            def is_null(val):
                return val is None or (isinstance(val, str) and val.strip() == "")

            # 매칭된 row인지 판단: 보험기간/납입기간/연령 중 하나라도 있으면 matched row로 간주
            def looks_matched(row: Dict[str, Any]) -> bool:
                return not (
                    is_null(row.get("보험기간")) and
                    is_null(row.get("납입기간")) and
                    is_null(row.get("주피보험자최소가입연령")) and
                    is_null(row.get("주피보험자최대가입연령"))
                )

            matched_rows = [d for d in definitions if looks_matched(d)]
            if matched_rows:
                all_null_on_matched = all(
                    all(is_null(r.get(col)) for col in required_value_cols)
                    for r in matched_rows
                )
                if all_null_on_matched:
                    return {
                        "is_valid": False,
                        "confidence": 0.7,
                        "errors": ["All required condition columns are null on matched rows"],
                        "suggestions": [
                            "Check condition_extract/condition_transform output",
                            "Verify grouping_logic value_columns",
                            "Ensure combination_generator receives condition_header/data",
                        ],
                        "reasoning": "Matched rows exist but carry no condition values",
                        "root_cause_task_id": None,
                    }

            return {
                "is_valid": True,
                "confidence": 0.95,
                "errors": [],
                "suggestions": [],
                "reasoning": f"Final combinations valid: total_count={total_count}, definition_match={matched}/{denom if denom else 'N/A'}",
                "root_cause_task_id": None,
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "errors": [f"Validation error: {str(e)}"],
                "suggestions": ["Check final combination output format"],
                "reasoning": "Final combination validation failed due to an exception",
                "root_cause_task_id": None,
            }

    # ========== PROTOTYPE 7: Root Cause Analysis ==========

    def _analyze_root_cause(
        self,
        task_type: str,
        task_output: Any,
        errors: List[str],
        previous_results: List[Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """
        Analyze which earlier task caused current validation failure (Prototype 7).

        This enables true backtracking: when task1 fails because task0 produced
        bad data, we identify task0 as the root cause and re-execute it instead
        of just retrying task1.

        Args:
            task_type: Type of failed task (e.g., "normalize_definitions")
            task_output: Output of failed task
            errors: List of validation errors
            previous_results: List of earlier TaskResult dicts

        Returns:
            Dict with root cause info:
            {
                "root_cause_task_id": "task0",
                "root_cause_reasoning": "task0의 extract가 유형1 컬럼을 누락했음"
            }
            or None if no root cause found

        Example:
            - Current task: normalize_definitions (task1)
            - Error: "Column '유형1' not found"
            - Root cause: extract_definitions (task0) didn't capture this column
            - Return: {"root_cause_task_id": "task0", "root_cause_reasoning": "..."}
        """
        if not previous_results:
            return None

        # Build prompt for root cause analysis
        errors_str = "\n".join(f"- {e}" for e in errors)

        # Format previous results summary
        results_summary = []
        for r in previous_results:
            result_info = {
                "task_id": r.get("task_id"),
                "task_type": r.get("data", {}).get("task_type", "unknown"),
                "success": r.get("success"),
                "data_preview": str(r.get("data", {}))[:200]  # First 200 chars
            }
            results_summary.append(result_info)

        results_json = json.dumps(results_summary, ensure_ascii=False, indent=2)
        output_json = json.dumps(task_output, ensure_ascii=False, indent=2)[:500]  # Limit size

        prompt = f"""
당신은 작업 실패의 근본 원인을 분석하는 전문가입니다.

## 현재 실패한 작업
- 유형: {task_type}
- 오류:
{errors_str}
- 출력 (일부):
{output_json}

## 이전 작업 결과들
{results_json}

## 질문
현재 작업이 실패한 근본 원인이 되는 이전 작업이 있습니까?

**분석 기준:**
1. 현재 오류가 이전 작업의 출력 품질 문제로 인한 것인가?
2. 이전 작업이 필요한 데이터를 누락했는가?
3. 이전 작업의 포맷이 현재 작업의 기대와 불일치하는가?

**예시:**
- 현재 작업: normalize_definitions (task1)
- 오류: "Column '유형1' not found"
- 분석: extract_definitions (task0)가 '유형1' 컬럼을 추출하지 않았음
- 결론: has_root_cause=true, root_cause_task_id="task0"

**출력 형식 (JSON):**
{{
  "has_root_cause": true/false,
  "root_cause_task_id": "task0" or null,
  "reasoning": "왜 이 작업이 근본 원인인지 또는 왜 근본 원인이 없는지 설명"
}}

만약 현재 작업 자체의 문제라면 has_root_cause=false로 응답하세요.
"""

        try:
            import time
            start_time = time.time()

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            # Track LLM usage
            elapsed_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            stats = self._llm_stats["analyze_root_cause"]
            stats["call_count"] += 1
            stats["total_prompt_tokens"] += usage.prompt_tokens
            stats["total_completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens
            stats["total_time_ms"] += elapsed_ms

            analysis = json.loads(response.choices[0].message.content)

            if analysis.get("has_root_cause"):
                return {
                    "root_cause_task_id": analysis.get("root_cause_task_id"),
                    "root_cause_reasoning": analysis.get("reasoning", "")
                }
            else:
                return None

        except Exception as e:
            # If analysis fails, return None (no root cause identified)
            print(f"[WARN] Root cause analysis failed: {str(e)}")
            return None

    def get_llm_usage_stats(self) -> Dict[str, Any]:
        """
        Get aggregated LLM usage statistics with cost estimates.

        Returns:
            Dict with operation-level stats and estimated costs
        """
        stats_with_cost = {}
        for operation, stats in self._llm_stats.items():
            # Calculate estimated cost (GPT-4o pricing: $2.50/1M input, $10.00/1M output)
            input_cost = (stats["total_prompt_tokens"] / 1_000_000) * 2.50
            output_cost = (stats["total_completion_tokens"] / 1_000_000) * 10.00
            estimated_cost = round(input_cost + output_cost, 6)

            stats_with_cost[operation] = {
                **stats,
                "estimated_cost_usd": estimated_cost
            }

        return stats_with_cost
