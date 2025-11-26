"""
Tool executor that instantiates and runs tools based on plan.
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
    Executes tools based on task specifications.
    """

    def __init__(self):
        # Instantiate all available tools
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
        Execute a single task.

        Args:
            task: Task specification from planner
            doc: Original document
            previous_results: Results from previous tasks (keyed by task_id)

        Returns:
            ToolResult from tool execution
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
        Resolve parameter references like "{{task1.location.section_index}}"
        to actual values from previous_results.

        Args:
            parameters: Raw parameters with possible references
            previous_results: Results from previous tasks

        Returns:
            Resolved parameters with actual values
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
