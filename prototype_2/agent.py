"""
Main agent orchestration with multi-step planning, execution, validation, and replanning.

이 모듈은 전체 워크플로우를 조율하는 최상위 Agent입니다.

워크플로우:
    1. Plan: Planner가 초기 3단계 계획 생성
    2. Execute: 각 Task를 순차적으로 실행
    3. Validate: Validator가 Task 결과 검증
    4. Replan (필요시): 실패 시 Planner가 재계획 수립
    5. Repeat: 최대 재시도 횟수까지 반복
    6. Result: 모든 Task 성공 시 최종 결과 반환

핵심 아이디어:
    - Plan-Execute-Validate 루프
    - LLM 기반 동적 재계획
    - Validator 피드백을 통한 점진적 개선
"""

import json
from typing import Dict, List, Any
from planner import MultiStepPlanner
from executor import ToolExecutor
from validator import LLMValidator


class MultiStepAgent:
    """
    다단계 Agent 오케스트레이터

    전체 워크플로우를 관리하는 최상위 클래스입니다.

    역할:
        1. 초기 계획 수립 (Planner)
        2. Task 순차 실행 (Executor)
        3. 결과 검증 (Validator)
        4. 실패 시 재계획 (Planner)
        5. 최종 결과 반환

    Attributes:
        executor (ToolExecutor): 도구 실행 관리자
        planner (MultiStepPlanner): 계획 수립 및 재계획 관리자
        validator (LLMValidator): 결과 검증기
        max_replan_per_task (int): Task당 최대 재시도 횟수
    """

    def __init__(self, max_replan_per_task: int = 3):
        """
        Agent 초기화

        Args:
            max_replan_per_task (int): Task당 최대 재계획 횟수 (기본값: 3)
                예: 3이면 최대 4번 시도 (초기 1회 + 재계획 3회)
        """
        self.executor = ToolExecutor()
        self.planner = MultiStepPlanner(tools=self.executor.tools)
        self.validator = LLMValidator()
        self.max_replan_per_task = max_replan_per_task

    def run(self, doc: List[Dict]) -> Dict[str, Any]:
        """
        Main execution loop.

        Args:
            doc: Original parsed JSON document

        Returns:
            {
                "success": bool,
                "final_data": {...} or None,
                "execution_log": [...],
                "error": str or None
            }
        """
        print("\n" + "="*80)
        print("Starting Multi-Step Agent")
        print("="*80)

        # Step 1: Create initial plan
        print("\n[STEP 1] Creating initial plan...")
        plan = self.planner.create_initial_plan(doc)

        if "error" in plan:
            return {
                "success": False,
                "final_data": None,
                "execution_log": [],
                "error": f"Planning failed: {plan['error']}"
            }

        tasks = plan["tasks"]
        print(f"[OK] Created plan with {len(tasks)} tasks")
        for task in tasks:
            print(f"  - Task {task['task_id']}: {task['description']} [{task['tool_name']}]")

        # Step 2: Execute tasks sequentially with validation
        execution_log = []
        previous_results = {}  # Store results keyed by task_id

        for task in tasks:
            task_id = task["task_id"]
            print(f"\n[TASK {task_id}] {task['description']}")
            print(f"Tool: {task['tool_name']}")

            # Execute task with replanning loop
            task_result = self._execute_task_with_replan(
                task, doc, previous_results, execution_log
            )

            if not task_result["success"]:
                # Task failed after all replan attempts
                print(f"\n✗ Task {task_id} failed after {task_result['attempts']} attempts")
                return {
                    "success": False,
                    "final_data": None,
                    "execution_log": execution_log,
                    "error": f"Task {task_id} failed: {task_result['error']}"
                }

            # Task succeeded
            print(f"[OK] Task {task_id} succeeded")
            previous_results[task_id] = task_result["data"]

        # Step 3: Extract final result
        print("\n" + "="*80)
        print("All tasks completed successfully!")
        print("="*80)

        # Final result is from the last task (Cartesian product)
        final_task_id = tasks[-1]["task_id"]
        final_data = previous_results[final_task_id]

        return {
            "success": True,
            "final_data": final_data,
            "execution_log": execution_log,
            "error": None
        }

    def _execute_task_with_replan(
        self,
        task: Dict[str, Any],
        doc: List[Dict],
        previous_results: Dict[int, Any],
        execution_log: List[Dict]
    ) -> Dict[str, Any]:
        """
        Execute a single task with replanning loop on failure.

        Returns:
            {
                "success": bool,
                "data": {...} or None,
                "error": str or None,
                "attempts": int
            }
        """
        current_task = task.copy()
        attempts = []

        for attempt_num in range(self.max_replan_per_task + 1):
            print(f"\n  Attempt {attempt_num + 1}/{self.max_replan_per_task + 1}")
            print(f"  Tool: {current_task['tool_name']}")
            print(f"  Parameters: {json.dumps(current_task['parameters'], ensure_ascii=False)}")

            # Execute tool
            result = self.executor.execute_task(current_task, doc, previous_results)

            # Log attempt
            attempt_log = {
                "attempt": attempt_num + 1,
                "tool": current_task["tool_name"],
                "parameters": current_task["parameters"],
                "success": result.success,
                "data": result.data,
                "error": result.error
            }

            if not result.success:
                # Tool execution failed
                print(f"  ✗ Tool execution failed: {result.error}")
                attempt_log["validation"] = None
                attempts.append(attempt_log)

                if attempt_num < self.max_replan_per_task:
                    # Replan
                    print(f"  → Replanning...")
                    new_plan = self.planner.replan_task(
                        failed_task=current_task,
                        tool_error=result.error,
                        validation_result=None,
                        previous_attempts=attempts
                    )

                    if "error" in new_plan:
                        print(f"  ✗ Replanning failed: {new_plan['error']}")
                        break

                    print(f"  → New plan: {new_plan.get('reasoning', 'No reasoning provided')}")

                    # Update task with new plan
                    current_task["tool_name"] = new_plan["tool_name"]
                    current_task["parameters"] = new_plan["parameters"]
                    continue
                else:
                    # Max attempts reached
                    break

            else:
                # Tool execution succeeded, validate result
                print(f"  [OK] Tool execution succeeded")

                validation_result = self._validate_task_result(
                    task_id=task["task_id"],
                    task_description=task["description"],
                    tool_output=result.data,
                    doc=doc,
                    previous_results=previous_results
                )

                attempt_log["validation"] = validation_result
                attempts.append(attempt_log)

                if validation_result["is_valid"]:
                    # Success!
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
                    # Validation failed
                    print(f"  ✗ Validation failed:")
                    for error in validation_result.get("errors", []):
                        print(f"    - {error}")

                    if attempt_num < self.max_replan_per_task:
                        # Replan
                        print(f"  → Replanning based on validation feedback...")
                        new_plan = self.planner.replan_task(
                            failed_task=current_task,
                            tool_error="",
                            validation_result=validation_result,
                            previous_attempts=attempts
                        )

                        if "error" in new_plan:
                            print(f"  ✗ Replanning failed: {new_plan['error']}")
                            break

                        print(f"  → New plan: {new_plan.get('reasoning', 'No reasoning provided')}")

                        # Update task with new plan
                        current_task["tool_name"] = new_plan["tool_name"]
                        current_task["parameters"] = new_plan["parameters"]
                        continue
                    else:
                        # Max attempts reached
                        break

        # All attempts failed
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

    def _validate_task_result(
        self,
        task_id: int,
        task_description: str,
        tool_output: Dict[str, Any],
        doc: List[Dict],
        previous_results: Dict[int, Any]
    ) -> Dict[str, Any]:
        """
        Validate task result based on task type.
        """
        # Determine task type from task_id
        if task_id == 1:
            # Search task
            return self.validator.validate_search(tool_output, doc)
        elif task_id == 2:
            # Extract task
            location = previous_results.get(1, {}).get("location", {})
            return self.validator.validate_extract(tool_output, doc, location)
        elif task_id == 3:
            # Cartesian task
            extracted_data = previous_results.get(2, {})
            return self.validator.validate_cartesian(tool_output, extracted_data)
        else:
            # Unknown task type, assume valid
            return {
                "is_valid": True,
                "confidence": 1.0,
                "reasoning": "Unknown task type, skipping validation"
            }
