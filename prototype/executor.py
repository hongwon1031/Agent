"""
Tool Executor for Prototype Agent
"""
from typing import List, Dict, Any
from pydantic import BaseModel
from tools import TOOL_REGISTRY, ToolResult


class ToolCall(BaseModel):
    tool_name: str
    parameters: Dict


class ExecutionResult(BaseModel):
    success: bool
    final_data: Dict
    execution_log: List[Dict]


class ToolExecutor:
    def __init__(self):
        self.tools = TOOL_REGISTRY

    def execute_plan(self, doc: List[Dict], plan: List[ToolCall]) -> ExecutionResult:
        """
        Plan의 Tool들을 순차 실행
        하나라도 성공하면 종료 (Early stopping)
        """
        execution_log = []

        for i, tool_call in enumerate(plan):
            print(f"\n[Executing Tool {i+1}/{len(plan)}] {tool_call.tool_name}")
            print(f"  Parameters: {tool_call.parameters}")

            tool = self.tools.get(tool_call.tool_name)
            if not tool:
                log_entry = {
                    "step": i,
                    "tool": tool_call.tool_name,
                    "success": False,
                    "error": f"Tool not found: {tool_call.tool_name}"
                }
                execution_log.append(log_entry)
                print(f"  ❌ Error: Tool not found")
                continue

            # Tool 실행
            result = tool.execute(doc, {}, tool_call.parameters)

            log_entry = {
                "step": i,
                "tool": tool_call.tool_name,
                "success": result.success,
                "data": result.data,
                "error": result.error
            }
            execution_log.append(log_entry)

            print(f"  ✅ Success: {result.success}")
            if result.success:
                print(f"  📊 Data preview: {str(result.data)[:200]}...")
                # 성공하면 즉시 종료
                return ExecutionResult(
                    success=True,
                    final_data=result.data,
                    execution_log=execution_log
                )
            else:
                print(f"  ❌ Error: {result.error}")

        # 모든 Tool 실패
        return ExecutionResult(
            success=False,
            final_data={},
            execution_log=execution_log
        )
