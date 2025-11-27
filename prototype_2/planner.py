"""
Multi-step planner and replanner with LLM-based task generation.

이 모듈은 LLM 기반으로 초기 계획을 수립하고, 실패 시 재계획하는 기능을 제공합니다.

주요 기능:
    - create_initial_plan: 3단계 계획 생성 (Search → Extract → Cartesian)
    - replan_task: 실패한 Task에 대한 새로운 계획 생성

계획 전략:
    1. 먼저 빠른 rule-based 도구 시도
    2. 실패 시 LLM이 에러 분석하여 llm-based 도구로 전환
    3. Validator 피드백을 반영하여 instruction 추가
    4. 최대 재시도 횟수까지 반복
"""

import os
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv


class MultiStepPlanner:
    """
    다단계 계획 수립 및 재계획 관리자

    역할:
        1. 초기 3단계 계획 생성 (Search → Extract → Cartesian)
        2. 실패한 Task에 대한 재계획 수립
        3. 에러 분석 및 대안 전략 제시
        4. Validator 피드백 반영

    Attributes:
        client (OpenAI): OpenAI API 클라이언트
        tools (Dict[str, SimpleTool]): 사용 가능한 도구 목록
    """

    def __init__(self, tools: Dict[str, Any] = None):
        """
        Planner 초기화

        Args:
            tools (Dict[str, SimpleTool], optional): 사용 가능한 도구 인스턴스
                Planner가 도구의 description과 schema를 참고하여 계획 수립
        """
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.tools = tools or {}

    def create_initial_plan(self, doc: List[Dict]) -> Dict[str, Any]:
        """
        초기 3단계 계획 생성

        보험 문서에서 정의를 추출하는 표준 3단계 계획을 LLM이 생성합니다:
            Task 1: 정의 섹션 찾기 (Search)
            Task 2: 데이터 추출하기 (Extract) - Task 1 결과 사용
            Task 3: Cartesian Product 생성 (Cartesian) - Task 2 결과 사용

        Args:
            doc (List[Dict]): 파싱된 보험 문서
                LLM에게 문서 구조를 간략히 제공하여 문맥 이해 돕기

        Returns:
            Dict[str, Any]: 계획 또는 에러
                성공 시: {
                    "tasks": [
                        {
                            "task_id": int,               # Task 고유 번호
                            "description": str,           # Task 설명
                            "tool_name": str,             # 사용할 도구 이름
                            "parameters": Dict,           # 도구 파라미터 (참조 포함)
                            "depends_on": Optional[int]   # 의존하는 Task ID
                        },
                        ...
                    ],
                    "reasoning": str  # 계획 수립 이유
                }
                실패 시: {"error": str}

        계획 전략:
            - 첫 시도는 빠른 rule-based 도구 (rule_search, rule_extract)
            - 파라미터에 이전 Task 결과 참조 포함 (예: {{task1.location.section_index}})
            - LLM이 도구 스키마를 보고 올바른 참조 경로 생성

        중요:
            - LLM에게 정확한 참조 형식 교육 ({{task1.location.section_index}})
            - 잘못된 참조({{task1.section_index}}) 방지
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
        실패한 Task에 대한 재계획 생성

        LLM이 에러를 분석하고 새로운 전략을 수립합니다.

        Args:
            failed_task (Dict[str, Any]): 실패한 Task 정보
                구조: {"task_id": int, "tool_name": str, "parameters": Dict, ...}
            tool_error (str): 도구 실행 에러 메시지
                예: "No definition sections found with keywords: ['정의']"
            validation_result (Optional[Dict[str, Any]]): Validator 결과
                도구는 성공했지만 검증 실패 시 제공됨
                구조: {"is_valid": bool, "errors": List[str], "suggestions": List[str]}
            previous_attempts (List[Dict[str, Any]]): 이전 시도 기록
                각 시도의 tool_name, parameters, error 포함

        Returns:
            Dict[str, Any]: 새로운 계획 또는 에러
                성공 시: {
                    "tool_name": str,        # 새로 시도할 도구 이름
                    "parameters": Dict,      # 새 파라미터 (instruction 포함 가능)
                    "reasoning": str,        # 전략 변경 이유
                    "changes": str           # 이전 대비 변경사항
                }
                실패 시: {"error": str}

        재계획 전략:
            1. 에러 분석:
               - 키워드 미매칭 → llm_search로 전환
               - 테이블 구조 복잡 → llm_extract로 전환
               - 주석 필터링 실패 → instruction에 구체적 지시 추가

            2. Validator 피드백 반영:
               - suggestions를 instruction에 포함
               - 예: "제목에 '명칭'이 포함된 섹션도 고려하세요"

            3. 점진적 개선:
               - 1차 시도: rule → llm 도구 전환
               - 2차 시도: instruction 추가
               - 3차 시도: 다른 파라미터 조합

        중요:
            - 동일한 실수 반복 방지 (previous_attempts 참고)
            - Validator의 suggestions를 최대한 활용
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
