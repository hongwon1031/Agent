"""
Fixed Workflow Definition

고정된 3단계 워크플로우 정의:
1. Section Classification (section_classifier)
2. Definition Extraction (definition_extract_v2)
3. Cartesian Product (rule_cartesian or llm_cartesian)
"""

from typing import Dict, Any, List


class DefinitionExtractionWorkflow:
    """
    정의 추출을 위한 고정된 3단계 워크플로우

    Planner는 이 워크플로우를 기반으로 instruction만 튜닝함
    """

    def __init__(self):
        self.tasks = self._define_tasks()

    def _define_tasks(self) -> List[Dict[str, Any]]:
        """
        고정된 3단계 Task 정의

        Returns:
            List[Dict]: Task 리스트
        """
        return [
            {
                "task_id": 1,
                "type": "classify",
                "description": "전체 섹션을 의미 기반으로 분류",
                "strategy": "llm",
                "fallback": None,
                "tool_name": "section_classifier",
                "base_params": {
                    "sections": "$sections"  # Runtime injection
                },
                "tunable": True,  # instruction 튜닝 가능
                "instruction": ""  # 초기값 빈 문자열
            },
            {
                "task_id": 2,
                "type": "extract",
                "description": "분류된 섹션에서 정의 데이터 추출",
                "strategy": "hybrid",
                "fallback": None,
                "tool_name": "definition_extract_v2",
                "base_params": {
                    "sections": "$sections",
                    "core_indices": "{{task1.definition_core}}",
                    "annotation_indices": "{{task1.definition_annotation}}"
                },
                "tunable": True,
                "instruction": ""
            },
            {
                "task_id": 3,
                "type": "transform",
                "description": "정의 조합 생성",
                "strategy": "rule",
                "fallback": None,
                "tool_name": "rule_cartesian",
                "base_params": {
                    "header": "{{task2.header}}",
                    "data": "{{task2.data}}"
                },
                "tunable": True,
                "instruction": "",
                "alternatives": ["llm_cartesian"]  # Reflection 실패 시 전환
            }
        ]

    def get_tasks(self) -> List[Dict[str, Any]]:
        """
        Task 리스트 반환

        Returns:
            List[Dict]: Task 정의 리스트
        """
        return self.tasks

    def get_task_by_id(self, task_id: int) -> Dict[str, Any]:
        """
        특정 Task ID로 Task 조회

        Args:
            task_id: Task ID

        Returns:
            Dict: Task 정의
        """
        for task in self.tasks:
            if task["task_id"] == task_id:
                return task
        return None

    def update_task_instruction(self, task_id: int, instruction: str):
        """
        특정 Task의 instruction 업데이트

        Args:
            task_id: Task ID
            instruction: 새로운 instruction
        """
        task = self.get_task_by_id(task_id)
        if task and task.get("tunable"):
            task["instruction"] = instruction

    def switch_task_tool(self, task_id: int, new_tool_name: str):
        """
        특정 Task의 도구 전환 (alternatives에 있는 것만 가능)

        Args:
            task_id: Task ID
            new_tool_name: 새 도구 이름

        Returns:
            bool: 전환 성공 여부
        """
        task = self.get_task_by_id(task_id)
        if not task:
            return False

        alternatives = task.get("alternatives", [])
        current_tool = task["tool_name"]

        # 새 도구가 alternatives에 있거나 현재 도구로 돌아가는 경우
        if new_tool_name in alternatives or new_tool_name == current_tool:
            task["tool_name"] = new_tool_name
            return True

        return False

    def to_agent_format(self) -> Dict[str, Any]:
        """
        Agent가 사용하는 형식으로 변환

        Returns:
            Dict: Agent 계획 형식
        """
        # base_params와 instruction을 합쳐서 parameters로
        formatted_tasks = []

        for task in self.tasks:
            formatted_task = {
                "task_id": task["task_id"],
                "type": task["type"],
                "description": task["description"],
                "strategy": task["strategy"],
                "fallback": task["fallback"],
                "tool_name": task["tool_name"],
                "parameters": {
                    **task["base_params"]
                },
                "depends_on": None if task["task_id"] == 1 else task["task_id"] - 1
            }

            # instruction이 있으면 추가
            if task.get("instruction"):
                formatted_task["parameters"]["instruction"] = task["instruction"]

            formatted_tasks.append(formatted_task)

        return {
            "tasks": formatted_tasks,
            "reasoning": "Fixed 3-stage workflow for definition extraction",
            "estimated_difficulty": "medium"
        }
