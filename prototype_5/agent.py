"""
Prototype 3 Agent: 완전히 일반화된 Multi-Agent 시스템

LLM 기반 동적 계획 + Hybrid Tools + 완전 검증
"""

import json
from typing import Dict, Any, List

# [DEPRECATED] DocumentAnalyzer 사용 중단 - DocumentAccessor로 대체
# from core.llm_document_analyzer import LLMDocumentAnalyzer
from core.llm_planner import LLMPlanner
from core.llm_validator import LLMValidator
from tools.hybrid_tools import (
    RuleSearchTool, LLMSearchTool, DefinitionSearchTool,
    RuleExtractTool, LLMExtractTool, DefinitionExtractTool, DefinitionExtractToolV2,
    RuleCartesianTool, LLMCartesianTool,
    SectionClassifierTool
)


class Prototype3Agent:
    """
    완전히 일반화된 Multi-Agent 시스템

    워크플로우:
        1. LLM Document Analyzer: 문서 구조 자동 분석
        2. LLM Planner: 동적 N단계 계획 수립
        3. Tool Executor: Rule 우선 시도, 실패 시 LLM
        4. LLM Validator: 전체 데이터 검증
        5. LLM Replanner: 실패 시 재계획
        6. 최종 결과 반환
    """

    def __init__(self, max_replan_per_task: int = 6):
        """
        Initialize agent

        Args:
            max_replan_per_task: Task당 최대 재시도 횟수
        """
        # [DEPRECATED] DocumentAnalyzer 사용 중단
        # self.analyzer = LLMDocumentAnalyzer()
        self.planner = LLMPlanner()
        self.validator = LLMValidator()
        self.max_replan = max_replan_per_task

        # 모든 도구 초기화
        self.tools = {
            # New V2 tools (recommended)
            "section_classifier": SectionClassifierTool(),
            "definition_extract_v2": DefinitionExtractToolV2(),

            # Legacy tools (kept for backward compatibility)
            "rule_search": RuleSearchTool(),
            "definition_search": DefinitionSearchTool(),
            "definition_extract": DefinitionExtractTool(),
            "llm_search": LLMSearchTool(),

            # Extract tools
            "rule_extract": RuleExtractTool(),
            "llm_extract": LLMExtractTool(),

            # Transform tools
            "rule_cartesian": RuleCartesianTool(),
            "llm_cartesian": LLMCartesianTool(),
        }

    def run(self, doc: Any) -> Dict[str, Any]:
        """
        Main execution loop

        Args:
            doc: 원본 문서 (어떤 형식이든 가능)

        Returns:
            Dict: 최종 결과
                {
                    "success": bool,
                    "document_analysis": {...},
                    "execution_plan": {...},
                    "final_data": {...},
                    "execution_log": [...],
                    "error": str | null
                }
        """
        print("="*80)
        print("Prototype 3: Fully Generalized Multi-Agent System")
        print("="*80)

        # [DEPRECATED] DocumentAnalyzer 사용 중단 - DocumentAccessor로 대체
        # # Step 1: 문서 구조 분석 (LLM)
        # print("\n[STEP 1] Analyzing document structure with LLM...")
        # structure_analysis = self.analyzer.analyze(doc)
        #
        # if "error" in structure_analysis:
        #     return {
        #         "success": False,
        #         "document_analysis": structure_analysis,
        #         "error": f"Document analysis failed: {structure_analysis['error']}"
        #     }
        #
        # print(f"[OK] Structure detected: {structure_analysis.get('structure_type')}")
        # print(f"   Sections path: {structure_analysis.get('sections_path')}")
        # print(f"   Estimated sections: {structure_analysis.get('total_sections_estimate')}")
        #
        # # 섹션 추출
        # sections = self.analyzer.get_sections(doc, structure_analysis)
        # print(f"   Actual sections found: {len(sections)}")

        # NEW: DocumentAccessor 사용
        print("\n[STEP 1] Extracting sections with DocumentAccessor...")
        from core.document_accessor import DocumentAccessor
        accessor = DocumentAccessor(doc)
        sections_raw = accessor.get_all_sections()
        print(f"[OK] Found {len(sections_raw)} sections (Format: {accessor.format.value})")

        # Section 객체를 도구들이 기대하는 dict 형태로 변환
        sections = []
        for section in sections_raw:
            sections.append({
                "index": section.index,
                "title": section.title,
                "content": section.content_items,
                "raw": section.metadata.get("original_element") or section.metadata.get("original_section") or section.metadata
            })
        print(f"   Converted {len(sections)} Section objects to dict format")

        # Step 2: 계획 수립 (LLM)
        print("\n[STEP 2] Creating dynamic plan with LLM...")
        # OLD: plan = self.planner.create_plan(doc, structure_analysis)
        plan = self.planner.create_plan(doc)  # NEW: structure_analysis 제거

        if "error" in plan:
            return {
                "success": False,
                "error": f"Planning failed: {plan['error']}"
            }

        # Validate plan structure (3-stage workflow)
        validation_error = self._validate_plan_structure(plan)
        if validation_error:
            return {
                "success": False,
                "error": f"Plan validation failed: {validation_error}"
            }

        tasks = plan.get("tasks", [])
        domain_analysis = plan.get("domain_analysis", {})
        print(f"[OK] Plan created with {len(tasks)} tasks")
        print(f"   Domain: {domain_analysis.get('entities', 'Unknown')}")
        print(f"   Categories: {', '.join(domain_analysis.get('categories', []))}")
        for task in tasks:
            print(f"   Task {task['task_id']}: {task['description']} [{task['tool_name']}]")

        # Step 3: Task 실행
        print("\n[STEP 3] Executing tasks...")
        execution_log = []
        previous_results = {}

        for task in tasks:
            task_id = task["task_id"]
            print(f"\n[TASK {task_id}] {task['description']}")

            # Task 실행 with replan (pass domain_analysis for validation)
            task_result = self._execute_task_with_replan(
                task, doc, sections, previous_results, execution_log, domain_analysis
            )

            if not task_result["success"]:
                print(f"[FAIL] Task {task_id} failed after {task_result['attempts']} attempts")
                return {
                    "success": False,
                    "execution_plan": plan,
                    "execution_log": execution_log,
                    "error": f"Task {task_id} failed: {task_result['error']}"
                }

            print(f"[OK] Task {task_id} succeeded")
            previous_results[task_id] = task_result["data"]

        # Step 4: 최종 결과
        print("\n" + "="*80)
        print("All tasks completed successfully!")
        print("="*80)

        final_task_id = tasks[-1]["task_id"]
        final_data = previous_results[final_task_id]

        return {
            "success": True,
            "execution_plan": plan,
            "final_data": final_data,
            "execution_log": execution_log,
            "error": None
        }

    def _execute_task_with_replan(
        self,
        task: Dict[str, Any],
        doc: Any,
        sections: List[Dict],
        previous_results: Dict[int, Any],
        execution_log: List[Dict],
        domain_analysis: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Task 실행 with replanning loop

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str | null,
                "attempts": int
            }
        """
        current_task = task.copy()
        attempts = []

        for attempt_num in range(self.max_replan + 1):
            print(f"  Attempt {attempt_num + 1}/{self.max_replan + 1}: {current_task['tool_name']}")

            # 파라미터 해석
            params = self._resolve_parameters(
                current_task["parameters"],
                previous_results,
                sections,
                doc
            )

            # 도구 실행
            tool = self.tools[current_task["tool_name"]]
            result = tool.execute(doc, params)

            # 시도 기록
            attempt_log = {
                "attempt": attempt_num + 1,
                "tool": current_task["tool_name"],
                "parameters": params,
                "success": result.success,
                "error": result.error
            }
            # ✅ 각 시도의 tool 출력도 로그에 포함
            if result.success:
                attempt_log["output"] = result.data
                
            if not result.success:
                # 도구 실행 실패
                print(f"  [FAIL] Tool execution failed: {result.error}")
                attempt_log["validation"] = None
                attempts.append(attempt_log)

                # Fallback 시도
                if current_task.get("fallback") and attempt_num < self.max_replan:
                    print(f"  [->] Trying fallback: {current_task['fallback']}")
                    fallback_tool_name = f"{current_task['fallback']}_{current_task['type']}"
                    current_task["tool_name"] = fallback_tool_name
                    continue

                # Replan
                if attempt_num < self.max_replan:
                    new_plan = self.planner.replan(
                        current_task, result.error, None, attempts
                    )
                    if "error" not in new_plan:
                        current_task["tool_name"] = new_plan["tool_name"]
                        current_task["parameters"] = new_plan["parameters"]
                        print(f"  → Replanned: {new_plan.get('reasoning')}")
                        continue

                break

            else:
                # 도구 실행 성공 → 검증
                print(f"  [OK] Tool execution succeeded")

                # Validation context 준비 (domain context 포함)
                validation_context = self._prepare_validation_context_v2(
                    task, previous_results, domain_analysis
                )

                validation_result = self.validator.validate(
                    task["type"],
                    result.data,
                    validation_context
                )

                attempt_log["validation"] = validation_result
                attempts.append(attempt_log)

                if validation_result["is_valid"]:
                    # 검증 성공!
                    print(f"  [OK] Validation passed (confidence: {validation_result.get('confidence', 'N/A')})")

                    execution_log.append({
                        "task_id": task["task_id"],
                        "description": task["description"],
                        "attempts": attempts,
                        "final_success": True
                    })

                    return {
                        "success": True,
                        "data": result.data,
                        "error": None,
                        "attempts": len(attempts)
                    }
                else:
                    # 검증 실패
                    print(f"  [FAIL] Validation failed:")
                    for error in validation_result.get("errors", []):
                        print(f"    - {error}")

                    if attempt_num < self.max_replan:
                        # Replan
                        new_plan = self.planner.replan(
                            current_task, "", validation_result, attempts
                        )
                        if "error" not in new_plan:
                            current_task["tool_name"] = new_plan["tool_name"]
                            current_task["parameters"] = new_plan["parameters"]
                            print(f"  → Replanned: {new_plan.get('reasoning')}")
                            continue

                    break

        # 모든 시도 실패
        execution_log.append({
            "task_id": task["task_id"],
            "description": task["description"],
            "attempts": attempts,
            "final_success": False
        })

        last_attempt = attempts[-1] if attempts else {}
        error_msg = last_attempt.get("error") or \
                    (last_attempt.get("validation", {}).get("errors", ["Unknown error"])[0])

        return {
            "success": False,
            "data": None,
            "error": error_msg,
            "attempts": len(attempts)
        }

    def _resolve_parameters(
        self,
        params: Dict[str, Any],
        previous_results: Dict[int, Any],
        sections: List[Dict],
        doc: Any
    ) -> Dict[str, Any]:
        """
        파라미터 참조 해석

        - "{{taskN.field}}" → 이전 task 결과 참조
        - "$sections" → runtime sections 주입
        - "$doc" → runtime doc 주입
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str):
                # Task 결과 참조: {{task1.found_table}}
                if value.startswith("{{") and value.endswith("}}"):
                    ref = value[2:-2]  # {{ }} 제거
                    parts = ref.split(".")

                    if parts[0].startswith("task"):
                        task_id = int(parts[0].replace("task", ""))
                        result = previous_results.get(task_id)

                        for field in parts[1:]:
                            if result and isinstance(result, dict):
                                result = result.get(field)

                        resolved[key] = result
                    else:
                        resolved[key] = value

                # Runtime injection: $sections, $doc
                elif value == "$sections":
                    resolved[key] = sections
                elif value == "$doc":
                    resolved[key] = doc
                else:
                    resolved[key] = value
            else:
                resolved[key] = value

        return resolved

    def _prepare_validation_context(
        self,
        task: Dict[str, Any],
        previous_results: Dict[int, Any]
    ) -> Dict[str, Any]:
        """
        Validation을 위한 컨텍스트 준비
        """
        context = {}

        # Extract validation: 원본 컨텐츠 필요 (table 또는 text)
        if task["type"] == "extract":
            depends_on = task.get("depends_on")
            if depends_on:
                prev_result = previous_results.get(depends_on, {})
                # found_content (text) 또는 found_table 전달
                original_content = prev_result.get("found_content") or prev_result.get("found_table")
                context["original_content"] = original_content

        # Transform validation: 추출된 데이터 필요
        elif task["type"] == "transform":
            depends_on = task.get("depends_on")
            if depends_on:
                context["extracted_data"] = previous_results.get(depends_on, {})

        return context

    def _prepare_validation_context_v2(
        self,
        task: Dict[str, Any],
        previous_results: Dict[int, Any],
        domain_analysis: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Validation을 위한 컨텍스트 준비 (domain context 포함)
        """
        context: Dict[str, Any] = {}

        # Add domain context from plan
        if domain_analysis:
            context["domain_context"] = {
                "entities": domain_analysis.get("entities", ""),
                "categories": domain_analysis.get("categories", []),
                "key_fields": domain_analysis.get("key_fields", [])
            }

        # Extract instruction from task parameters for reference
        if "parameters" in task and "instruction" in task["parameters"]:
            context["task_instruction"] = task["parameters"]["instruction"]

        # Extract validation: 원본 컨텐츠가 필요 (table 또는 text)
        if task["type"] == "extract":
            depends_on = task.get("depends_on")
            if depends_on:
                prev_result = previous_results.get(depends_on, {})
                # Search 단계에서 찾은 정의 섹션의 원본 전달
                original_content = prev_result.get("found_content") or prev_result.get("found_table")
                context["original_content"] = original_content
                # 섹션 제목도 함께 전달 (없으면 빈 문자열)
                context["section_title"] = prev_result.get("section_title", "")

        # Transform validation: 추출된 데이터가 필요
        elif task["type"] == "transform":
            depends_on = task.get("depends_on")
            if depends_on:
                context["extracted_data"] = previous_results.get(depends_on, {})

        return context

    def _validate_plan_structure(self, plan: Dict[str, Any]) -> str:
        """
        Validate that plan follows the required 3-stage structure

        Returns:
            str: Error message if invalid, empty string if valid
        """
        # Check domain_analysis
        if "domain_analysis" not in plan:
            return "Plan missing 'domain_analysis' field"

        domain = plan["domain_analysis"]
        if not isinstance(domain, dict):
            return "'domain_analysis' must be a dict"

        required_domain_keys = ["entities", "categories", "key_fields"]
        for key in required_domain_keys:
            if key not in domain:
                return f"domain_analysis missing required key: '{key}'"

        # Check tasks
        if "tasks" not in plan:
            return "Plan missing 'tasks' field"

        tasks = plan["tasks"]
        if not isinstance(tasks, list):
            return "'tasks' must be a list"

        if len(tasks) != 3:
            return f"Plan must have exactly 3 tasks, got {len(tasks)}"

        # Validate task sequence
        expected_sequence = [
            {"type": "classify", "tool": "section_classifier"},
            {"type": "extract", "tool": "definition_extract_v2"},
            {"type": "transform", "tool": "llm_cartesian"}
        ]

        for i, (task, expected) in enumerate(zip(tasks, expected_sequence)):
            # Check task_id
            if task.get("task_id") != i + 1:
                return f"Task {i+1} has invalid task_id: {task.get('task_id')}"

            # Check type
            if task.get("type") != expected["type"]:
                return f"Task {i+1} must be type '{expected['type']}', got '{task.get('type')}'"

            # Check tool_name contains expected tool
            tool_name = task.get("tool_name", "")
            if expected["tool"] not in tool_name:
                return f"Task {i+1} should use tool '{expected['tool']}', got '{tool_name}'"

            # Check instruction exists
            params = task.get("parameters", {})
            if "instruction" not in params:
                return f"Task {i+1} missing 'instruction' in parameters"

            # Check instruction is not empty
            if not params["instruction"] or not params["instruction"].strip():
                return f"Task {i+1} has empty instruction"

        return ""  # Valid
