"""
Multi-step planner and replanner with LLM-based task generation.
"""

import os
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv


class MultiStepPlanner:
    """
    Creates initial multi-step plan and handles replanning on failures.
    """

    def __init__(self, tools: Dict[str, Any] = None):
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.tools = tools or {}

    def create_initial_plan(self, doc: List[Dict]) -> Dict[str, Any]:
        """
        Create initial 3-step plan: Search → Extract → Cartesian

        Returns:
            {
                "tasks": [
                    {
                        "task_id": 1,
                        "description": "...",
                        "tool_name": "...",
                        "parameters": {...},
                        "depends_on": None or task_id
                    },
                    ...
                ]
            }
        """
        try:
            # Analyze document structure for context
            if not doc or len(doc) == 0:
                return {"error": "Document is empty"}

            elements = doc[0].get("elements", [])

            # Create simplified structure for LLM
            doc_overview = []
            for idx, section in enumerate(elements[:10]):  # First 10 sections
                title = section.get("title", "")
                para_count = len(section.get("paragraphs", []))
                has_tables = any("table" in p for p in section.get("paragraphs", []))
                doc_overview.append({
                    "section_index": idx,
                    "title": title,
                    "paragraph_count": para_count,
                    "has_tables": has_tables
                })

            # Generate tool descriptions from actual tool schemas
            tool_descriptions = []
            for tool_name, tool in self.tools.items():
                desc = f"{tool_name}: {tool.get_description()}\n"
                desc += f"   - parameters: {json.dumps(tool.get_parameters_schema(), ensure_ascii=False)}"
                tool_descriptions.append(desc)

            tools_section = "\n\n".join(tool_descriptions)

            # Planning prompt
            prompt = f"""다음은 보험 문서의 구조 개요입니다.

문서 구조 (처음 10개 섹션):
{json.dumps(doc_overview, ensure_ascii=False, indent=2)}

**목표**: 이 문서에서 보험 상품의 모든 조합(명칭 + 유형)을 추출하는 3단계 계획을 수립하세요.

**사용 가능한 Tools**:
{tools_section}

**전략**:
- 첫 시도는 빠른 rule-based tool 사용
- 실패시 replanner가 llm-based tool로 전환
- 각 Task는 이전 Task의 결과를 depends_on으로 참조

**3단계 계획**:
1. Task 1: 정의 섹션 찾기 (Search)
2. Task 2: 데이터 추출 (Extract) - Task 1 결과 사용
3. Task 3: Cartesian Product 생성 (Cartesian) - Task 2 결과 사용

다음 JSON 형식으로 반환:
{{
  "tasks": [
    {{
      "task_id": 1,
      "description": "정의 섹션 찾기",
      "tool_name": "rule_search",
      "parameters": {{"keywords": ["정의", "용어", "명칭", "보험종목"]}},
      "depends_on": null
    }},
    {{
      "task_id": 2,
      "description": "데이터 추출",
      "tool_name": "rule_extract",
      "parameters": {{"section_index": "{{task1.location.section_index}}", "paragraph_index": "{{task1.location.paragraph_index}}"}},
      "depends_on": 1
    }},
    {{
      "task_id": 3,
      "description": "Cartesian Product 생성",
      "tool_name": "cartesian",
      "parameters": {{"header": "{{task2.header}}", "data": "{{task2.data}}"}},
      "depends_on": 2
    }}
  ],
  "reasoning": "<계획 수립 이유>"
}}

**Tool Output 구조 (Parameter 참조용)**:
1. Search tools (rule_search, llm_search) 출력:
   {{
     "location": {{
       "section_index": 0,
       "paragraph_index": 0,
       ...
     }}
   }}
   → 참조: {{{{task1.location.section_index}}}}, {{{{task1.location.paragraph_index}}}}

2. Extract tools (rule_extract, llm_extract) 출력:
   {{
     "header": ["컬럼1", "컬럼2", ...],
     "data": [["값1", "값2", ...], ...]
   }}
   → 참조: {{{{task2.header}}}}, {{{{task2.data}}}}

3. Cartesian tool 출력:
   {{
     "definitions": [{{"보종명": "...", "유형1": "...", ...}}, ...]
   }}

**중요**: 절대 {{{{task1.section_index}}}} 같은 잘못된 경로 사용 금지!
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            plan = json.loads(response.choices[0].message.content)
            return plan

        except Exception as e:
            return {"error": f"Planning failed: {str(e)}"}

    def replan_task(
        self,
        failed_task: Dict[str, Any],
        tool_error: str,
        validation_result: Optional[Dict[str, Any]],
        previous_attempts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a new plan for a failed task based on error analysis.

        Args:
            failed_task: The task that failed
            tool_error: Error message from tool execution
            validation_result: Validation result (if tool succeeded but validation failed)
            previous_attempts: List of previous attempts for this task

        Returns:
            {
                "tool_name": "...",
                "parameters": {...},
                "reasoning": "..."
            }
        """
        try:
            # Determine failure reason
            if validation_result and not validation_result.get("is_valid"):
                # Tool succeeded but validation failed
                failure_type = "validation_failure"
                errors = validation_result.get("errors", [])
                suggestions = validation_result.get("suggestions", [])
            else:
                # Tool execution failed
                failure_type = "tool_failure"
                errors = [tool_error]
                suggestions = []

            # Prepare replanning prompt
            prompt = f"""다음은 실패한 Task에 대한 정보입니다.

**Task 정보**:
- Task ID: {failed_task.get('task_id')}
- Description: {failed_task.get('description')}
- 사용한 Tool: {failed_task.get('tool_name')}
- Parameters: {json.dumps(failed_task.get('parameters'), ensure_ascii=False)}

**실패 유형**: {failure_type}

**에러 메시지**:
{json.dumps(errors, ensure_ascii=False, indent=2)}

**제안사항** (Validator가 제공):
{json.dumps(suggestions, ensure_ascii=False, indent=2)}

**이전 시도 횟수**: {len(previous_attempts)}

**목표**: 이 Task를 성공시키기 위한 새로운 계획을 수립하세요.

**전략**:
1. 에러 분석: 왜 실패했는가?
2. Tool 선택:
   - rule-based 실패 → llm-based 시도
   - 표 구조 문제 → instruction에 구체적 지시 추가
   - 주석/노이즈 문제 → instruction에 제거 지시 추가
3. Parameters:
   - 기존 parameters 유지하되 필요시 수정
   - instruction 필드에 구체적인 지시사항 추가

**사용 가능한 Tools**:
- rule_search, llm_search
- rule_extract, llm_extract
- cartesian

다음 JSON 형식으로 반환:
{{
  "tool_name": "...",
  "parameters": {{...}},
  "reasoning": "<새 계획 수립 이유>",
  "changes": "<이전 시도 대비 변경사항>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3  # Slightly higher for creative problem-solving
            )

            new_plan = json.loads(response.choices[0].message.content)
            return new_plan

        except Exception as e:
            return {"error": f"Replanning failed: {str(e)}"}
