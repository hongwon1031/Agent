"""
Base tool interface for the agent system.
All tools must inherit from SimpleTool and implement the execute method.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Standardized tool execution result"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tool_name: str

    class Config:
        arbitrary_types_allowed = True


class SimpleTool:
    """Base class for all tools"""

    def __init__(self):
        self.name = self.__class__.__name__
        self.description = self.get_description()
        self.parameters_schema = self.get_parameters_schema()

    def get_description(self) -> str:
        """Return tool description for planner"""
        raise NotImplementedError

    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return expected parameters schema"""
        raise NotImplementedError

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given document and parameters.

        Args:
            doc: Original parsed JSON document
            params: Tool parameters including optional 'instruction' field

        Returns:
            ToolResult with success status and data/error
        """
        raise NotImplementedError

    def _create_success(self, data: Dict[str, Any]) -> ToolResult:
        """Helper to create success result"""
        return ToolResult(
            success=True,
            data=data,
            error=None,
            tool_name=self.name
        )

    def _create_error(self, error_msg: str) -> ToolResult:
        """Helper to create error result"""
        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
            tool_name=self.name
        )
