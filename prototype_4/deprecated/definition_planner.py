"""
Definition-aware Planner wrapper (deprecated in prototype_4)

Prototype 4 초기 실험용으로 사용되던 Planner 래퍼입니다.
현재는 core.llm_planner.LLMPlanner를 직접 사용하므로,
이 모듈은 deprecated 디렉터리로 이동되었습니다.
"""

from typing import Any, Dict, List

from core.llm_planner import LLMPlanner as BasePlanner


class LLMPlanner(BasePlanner):
    """Prototype 4 Definition-aware Planner (DEPRECATED)"""

    def create_plan(
        self,
        doc: Any,
        goal: str = """
        - 보험 상품 정의(보종명/유형 계층)의 모든 조합 추출
        - 조건(보험기간/가입기간 등)은 별도 Task에서 계획
        """
    ) -> Dict[str, Any]:
        """기존 Planner가 생성한 plan을 받아 definition-aware 형태로 보정"""
        plan = super().create_plan(doc, goal)
        return self._patch_plan_for_definitions(plan)

    def _patch_plan_for_definitions(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prototype 4: LLM이 만든 plan을 definition_search/definition_extract 기반으로 보정.

        - 첫 번째 search task를 definition_search로 강제
        - 그 search에 의존하는 extract task를 definition_extract로 전환
        """
        tasks: List[Dict[str, Any]] = plan.get("tasks") or []
        if not tasks:
            return plan

        # 첫 번째 search task 찾기
        search_task = None
        for t in tasks:
            if t.get("type") == "search":
                search_task = t
                break

        if not search_task:
            return plan

        search_task_id = search_task.get("task_id")

        # search task를 definition_search로 고정
        search_task["strategy"] = "rule"
        search_task["fallback"] = None
        search_task["tool_name"] = "definition_search"
        search_task["parameters"] = {
            "sections": "$sections"
        }

        # 해당 search를 사용하는 extract task를 definition_extract로 전환
        extract_task = None
        for t in tasks:
            if t.get("type") == "extract" and t.get("depends_on") == search_task_id:
                extract_task = t
                break

        if extract_task is None:
            return plan

        extract_task["strategy"] = "rule"
        extract_task["tool_name"] = "definition_extract"
        extract_task["parameters"] = {
            "sections": "$sections",
            "definition_candidates": f"{{{{task{search_task_id}.definition_candidates}}}}"
        }

        plan["tasks"] = tasks
        return plan

