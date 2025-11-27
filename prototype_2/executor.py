"""
Tool executor that instantiates and runs tools based on plan.

이 모듈은 Planner가 생성한 계획에 따라 도구를 실행하는 역할을 합니다.

주요 기능:
    - 모든 도구 인스턴스 관리
    - Task 파라미터의 참조 해석 (예: {{task1.location.section_index}})
    - 이전 Task 결과를 현재 Task에 전달
    - 도구 실행 및 결과 반환

참조 해석 예시:
    파라미터: {"section_index": "{{task1.location.section_index}}"}
    이전 결과: {1: {"location": {"section_index": 0}}}
    해석 결과: {"section_index": 0}
"""

from typing import Dict, List, Any
from tools import (
    RuleSearchTool, LLMSearchTool,
    RuleExtractTool, LLMExtractTool,
    GenerateCartesianTool,
    ToolResult
)


class ToolExecutor:
    """
    도구 실행 관리자

    역할:
        1. 모든 도구 인스턴스 생성 및 관리
        2. Task 스펙에 따라 적절한 도구 선택
        3. 파라미터 참조 해석 (이전 Task 결과 활용)
        4. 도구 실행 및 결과 반환

    Attributes:
        tools (Dict[str, SimpleTool]): 도구 이름 → 도구 인스턴스 매핑
    """

    def __init__(self):
        """
        모든 사용 가능한 도구 인스턴스 생성

        초기화되는 도구들:
            - rule_search: 규칙 기반 검색
            - llm_search: LLM 기반 검색
            - rule_extract: 규칙 기반 추출
            - llm_extract: LLM 기반 추출
            - cartesian: Cartesian Product 생성
        """
        self.tools = {
            "rule_search": RuleSearchTool(),
            "llm_search": LLMSearchTool(),
            "rule_extract": RuleExtractTool(),
            "llm_extract": LLMExtractTool(),
            "cartesian": GenerateCartesianTool(),
        }

    def execute_task(
        self,
        task: Dict[str, Any],
        doc: List[Dict],
        previous_results: Dict[int, Any]
    ) -> ToolResult:
        """
        단일 Task 실행

        Args:
            task (Dict[str, Any]): Planner가 생성한 Task 스펙
                구조: {
                    "task_id": int,
                    "description": str,
                    "tool_name": str,
                    "parameters": Dict,
                    "depends_on": Optional[int]
                }
            doc (List[Dict]): 원본 문서 (도구에 전달)
            previous_results (Dict[int, Any]): 이전 Task들의 결과
                키: task_id, 값: 해당 Task의 data 필드

        Returns:
            ToolResult: 도구 실행 결과 (성공/실패, 데이터/에러)

        동작 과정:
            1. Task에서 tool_name과 parameters 추출
            2. parameters에 포함된 참조({{taskN.field}}) 해석
            3. 해당 도구 인스턴스 가져오기
            4. 도구 실행 (doc와 해석된 파라미터 전달)
            5. 결과 반환
        """
        try:
            tool_name = task["tool_name"]
            parameters = task["parameters"].copy()

            print(f"\n[DEBUG] Raw parameters: {parameters}")
            print(f"[DEBUG] Previous results keys: {previous_results.keys()}")

            # Resolve parameter references to previous task results
            # e.g., "{{task1.location.section_index}}" → previous_results[1]["location"]["section_index"]
            resolved_params = self._resolve_parameters(parameters, previous_results)
            
            print(f"[DEBUG] Resolved parameters: {resolved_params}")

            # Get tool
            if tool_name not in self.tools:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Unknown tool: {tool_name}",
                    tool_name=tool_name
                )

            tool = self.tools[tool_name]

            # Execute tool
            result = tool.execute(doc, resolved_params)

            return result

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Executor error: {str(e)}",
                tool_name=task.get("tool_name", "unknown")
            )

    def _resolve_parameters(
        self,
        parameters: Dict[str, Any],
        previous_results: Dict[int, Any]
    ) -> Dict[str, Any]:
        """
        파라미터 참조를 실제 값으로 해석

        이전 Task의 결과를 참조하는 문자열 패턴을 실제 값으로 치환합니다.

        Args:
            parameters (Dict[str, Any]): 원본 파라미터 (참조 포함 가능)
                예: {"section_index": "{{task1.location.section_index}}"}
            previous_results (Dict[int, Any]): 이전 Task 결과
                예: {1: {"location": {"section_index": 0, "paragraph_index": 1}}}

        Returns:
            Dict[str, Any]: 해석된 파라미터 (실제 값으로 치환)
                예: {"section_index": 0}

        참조 형식:
            - "{{taskN.field1.field2.field3}}" (이중 중괄호)
            - "{taskN.field1.field2}" (단일 중괄호, task 키워드 포함 시)

        동작 과정:
            1. 각 파라미터 값 검사
            2. 문자열이고 {{...}} 또는 {task...} 형식이면 참조로 판단
            3. taskN에서 N 추출 (task_id)
            4. previous_results[N]에서 시작하여 점(.)으로 구분된 필드를 순회
            5. 최종 값 반환
            6. 참조가 아니면 원본 값 유지

        예외:
            - task_id에 해당하는 결과가 없으면 ValueError
            - 필드 접근 실패 시 ValueError
        """
        resolved = {}

        for key, value in parameters.items():
            # Support both {{task1.field}} and {task1.field} formats
            if isinstance(value, str) and (
                (value.startswith("{{") and value.endswith("}}")) or
                (value.startswith("{") and value.endswith("}") and "task" in value)
            ):
                # This is a reference to previous task result
                # Format: "{{taskN.field1.field2.field3}}" or "{taskN.field1.field2}"
                if value.startswith("{{"):
                    reference = value[2:-2]  # Remove {{ and }}
                else:
                    reference = value[1:-1]  # Remove { and }
                parts = reference.split(".")

                if parts[0].startswith("task"):
                    # Extract task_id
                    task_id = int(parts[0].replace("task", ""))

                    # Navigate through result structure
                    result = previous_results.get(task_id)
                    if result is None:
                        raise ValueError(f"Task {task_id} result not found")

                    # Navigate through nested fields
                    for field in parts[1:]:
                        if isinstance(result, dict):
                            result = result.get(field)
                        else:
                            raise ValueError(f"Cannot access field {field} in {result}")

                    resolved[key] = result
                else:
                    # Not a task reference, keep as is
                    resolved[key] = value
            else:
                # Not a reference, keep as is
                resolved[key] = value

        return resolved
