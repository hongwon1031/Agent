"""
Reflection-Based Planner

초기 계획보다 'Reflection을 통한 Prompt Tuning'에 집중
- 초기 계획: 고정된 워크플로우 로드
- 핵심 역할: Validator 피드백 분석 → instruction 생성 → Tool 튜닝
"""

import json
import os
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add parent directory to path
parent_path = Path(__file__).parent.parent
sys.path.insert(0, str(parent_path))

from core.fixed_workflow import DefinitionExtractionWorkflow


class ReflectionPlanner:
    """
    Reflection 기반 계획 수립 및 튜닝

    역할:
        1. 초기 계획: 고정 워크플로우 로드 (단순)
        2. 실패 대응: Validator 피드백 분석
        3. Prompt 튜닝: instruction 생성 및 누적
        4. Tool 전환: Rule ↔ LLM
    """

    def __init__(self):
        """Initialize OpenAI client and workflow"""
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.workflow = DefinitionExtractionWorkflow()
        self.instruction_history = {}  # {task_id: [inst1, inst2, ...]}

    def create_initial_plan(self, doc: Any) -> Dict[str, Any]:
        """
        초기 계획 수립 - 고정 워크플로우 로드

        Args:
            doc: 원본 문서 (사용 안함 - 고정 워크플로우이므로)

        Returns:
            Dict: 계획
        """
        return self.workflow.to_agent_format()

    def reflect_and_tune(
        self,
        failed_task: Dict[str, Any],
        error_message: str,
        validation_result: Dict[str, Any] = None,
        previous_attempts: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        실패 분석 및 Prompt 튜닝

        Args:
            failed_task: 실패한 Task 정보
            error_message: 도구 에러 메시지
            validation_result: Validator 결과
            previous_attempts: 이전 시도 기록

        Returns:
            Dict: 새로운 Task 설정
                {
                    "tool_name": str,
                    "parameters": Dict,
                    "reasoning": str,
                    "changes": str
                }
        """
        if previous_attempts is None:
            previous_attempts = []

        task_id = failed_task.get("task_id")

        # 이전 instructions 가져오기
        prev_instructions = self.instruction_history.get(task_id, [])

        # LLM에게 reflection 요청
        reflection = self._generate_reflection(
            failed_task,
            error_message,
            validation_result,
            prev_instructions,
            previous_attempts
        )

        if "error" in reflection:
            return reflection

        # Instruction 누적
        new_instruction = reflection.get("instruction", "")
        if new_instruction:
            updated_instructions = prev_instructions + [new_instruction]
            self.instruction_history[task_id] = updated_instructions

            # 누적된 instruction 합치기
            combined_instruction = "\n".join([f"- {inst}" for inst in updated_instructions])
        else:
            combined_instruction = ""

        # Tool 전환 여부
        tool_change = reflection.get("tool_change")
        if tool_change:
            # Workflow에 Tool 변경 반영
            if not self.workflow.switch_task_tool(task_id, tool_change):
                print(f"[WARNING] Tool switch to {tool_change} not allowed for task {task_id}")
                tool_change = None  # 전환 실패시 기존 도구 유지

        new_tool_name = tool_change if tool_change else failed_task["tool_name"]

        # 새 parameters 구성
        new_params = {**failed_task.get("parameters", {})}

        if combined_instruction:
            new_params["instruction"] = combined_instruction

        return {
            "tool_name": new_tool_name,
            "parameters": new_params,
            "reasoning": reflection.get("root_cause", ""),
            "changes": f"Tool: {new_tool_name}, Instruction added: {bool(new_instruction)}"
        }

    def _generate_reflection(
        self,
        failed_task: Dict[str, Any],
        error_message: str,
        validation_result: Dict[str, Any],
        prev_instructions: List[str],
        previous_attempts: List[Dict]
    ) -> Dict[str, Any]:
        """
        LLM을 사용하여 reflection 수행

        Args:
            failed_task: 실패한 Task
            error_message: 에러 메시지
            validation_result: Validator 결과
            prev_instructions: 이전 instructions
            previous_attempts: 이전 시도들

        Returns:
            Dict: Reflection 결과
                {
                    "root_cause": str,
                    "instruction": str,
                    "tool_change": str | null,
                    "confidence": float
                }
        """
        # Validation errors 정리
        if validation_result:
            errors = validation_result.get("errors", [])
            # errors는 string 리스트
            error_summary = "\n".join([f"- {err}" for err in errors]) if errors else "검증 실패"

            suggestions_list = validation_result.get("suggestions", [])
            suggestions = "\n".join([f"- {sug}" for sug in suggestions_list]) if suggestions_list else ""
        else:
            error_summary = error_message
            suggestions = ""

        # 이전 instructions 요약
        prev_inst_text = "\n".join([f"{i+1}. {inst}" for i, inst in enumerate(prev_instructions)])
        if not prev_inst_text:
            prev_inst_text = "(없음)"

        prompt = f"""Task가 실패했습니다. 근본 원인을 분석하고 개선 방안을 제시하세요.

**실패한 Task**:
- Task ID: {failed_task.get('task_id')}
- Tool: {failed_task.get('tool_name')}
- Type: {failed_task.get('type')}

**에러 정보**:
{error_summary}

**Validator 제안사항**:
{suggestions}

**이전에 시도한 instructions** ({len(prev_instructions)}개):
{prev_inst_text}

**이전 시도 횟수**: {len(previous_attempts)}

---

**분석 절차**:

1. **근본 원인 파악**:
   - 왜 이 Task가 실패했는가?
   - 이전 instruction들이 있다면, 왜 해결이 안됐는가?

2. **개선 방안 도출**:
   - 어떤 **새로운 instruction**을 추가하면 해결될까?
   - 도구를 바꿔야 하나? (rule → llm 또는 그 반대)
   - 이전 instruction과 **중복되지 않고**, **구체적**이어야 함

3. **Tool 전환 판단**:
   - classify task: section_classifier (전환 불가)
   - extract task: definition_extract_v2 (전환 불가)
   - transform task: rule_cartesian ↔ llm_cartesian (전환 가능)

**출력 형식** (JSON):
{{
  "root_cause": "실패의 근본 원인 (구체적으로)",
  "instruction": "추가할 새로운 instruction (구체적이고 실행 가능하게)",
  "tool_change": "llm_cartesian" | null,
  "confidence": 0.0~1.0
}}

**예시**:
{{
  "root_cause": "조건 섹션(가입연령, 보험기간)과 정의 섹션(보험종목, 명칭)의 테이블 구조가 유사하여, section_classifier가 제목만 보고 오분류함",
  "instruction": "섹션 제목에 '가입', '연령', '기간', '조건' 같은 키워드가 있으면 반드시 'condition'으로 분류하세요. 정의는 '명칭', '종목', '유형' 같은 키워드가 있어야 합니다.",
  "tool_change": null,
  "confidence": 0.9
}}

위 형식으로 JSON만 반환하세요."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.5
            )

            reflection = json.loads(response.choices[0].message.content)
            return reflection

        except Exception as e:
            return {
                "error": f"Reflection failed: {str(e)}"
            }

    # Backward compatibility: replan() 메서드 유지
    def replan(
        self,
        failed_task: Dict[str, Any],
        error_message: str,
        validation_result: Dict[str, Any] = None,
        previous_attempts: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Backward compatibility wrapper for reflect_and_tune()
        """
        return self.reflect_and_tune(
            failed_task,
            error_message,
            validation_result,
            previous_attempts
        )
