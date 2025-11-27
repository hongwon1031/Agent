"""
Base tool interface for the agent system.
All tools must inherit from SimpleTool and implement the execute method.

이 모듈은 모든 도구가 따라야 하는 기본 인터페이스를 정의합니다.

주요 개념:
    - SimpleTool: 모든 도구의 추상 기본 클래스
    - ToolResult: 도구 실행 결과의 표준화된 형식

설계 원칙:
    1. 일관성: 모든 도구는 동일한 execute() 인터페이스 사용
    2. 표준화: ToolResult로 성공/실패 상태 명확히 구분
    3. 확장성: 새로운 도구 추가 시 SimpleTool 상속만 하면 됨
    4. 유연성: params에 instruction 필드로 커스텀 지시사항 전달 가능
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class ToolResult(BaseModel):
    """
    도구 실행 결과를 담는 표준화된 데이터 모델

    Attributes:
        success (bool): 도구 실행의 성공 여부
        data (Optional[Dict[str, Any]]): 성공 시 결과 데이터
            - search 도구: {"location": {"section_index": int, "paragraph_index": int, ...}}
            - extract 도구: {"header": List[str], "data": List[List[str]], ...}
            - cartesian 도구: {"definitions": List[Dict], "total_count": int, ...}
        error (Optional[str]): 실패 시 에러 메시지
        tool_name (str): 실행된 도구의 이름 (디버깅/로깅용)

    사용 예시:
        result = ToolResult(
            success=True,
            data={"location": {"section_index": 0, "paragraph_index": 1}},
            error=None,
            tool_name="RuleSearchTool"
        )
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tool_name: str

    class Config:
        arbitrary_types_allowed = True


class SimpleTool:
    """
    모든 도구의 추상 기본 클래스

    이 클래스를 상속받아 새로운 도구를 만들 때는 반드시 다음 메서드들을 구현해야 합니다:
        - get_description(): 도구의 기능 설명 (Planner가 사용)
        - get_parameters_schema(): 도구가 필요로 하는 파라미터 스키마
        - execute(): 실제 도구 실행 로직

    Attributes:
        name (str): 도구의 이름 (클래스명으로 자동 설정)
        description (str): 도구의 기능 설명
        parameters_schema (Dict): 파라미터 스키마

    내부 헬퍼 메서드:
        - _create_success(): 성공 결과 생성
        - _create_error(): 실패 결과 생성
    """

    def __init__(self):
        """
        도구 초기화

        자동으로 다음 속성들을 설정:
            - name: 클래스명
            - description: get_description() 호출 결과
            - parameters_schema: get_parameters_schema() 호출 결과
        """
        self.name = self.__class__.__name__
        self.description = self.get_description()
        self.parameters_schema = self.get_parameters_schema()

    def get_description(self) -> str:
        """
        도구의 기능 설명을 반환

        Planner가 이 설명을 읽고 적절한 도구를 선택합니다.

        Returns:
            str: 도구의 간단한 기능 설명

        구현 예시:
            return "Rule-based search for definition sections using keyword matching"
        """
        raise NotImplementedError

    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        도구가 필요로 하는 파라미터 스키마를 반환

        Returns:
            Dict[str, Any]: 파라미터 이름과 타입, 필수 여부 등을 담은 스키마

        구현 예시:
            return {
                "keywords": {
                    "type": "list",
                    "description": "검색할 키워드 목록",
                    "required": False
                },
                "instruction": {
                    "type": "string",
                    "description": "Replanner의 커스텀 지시사항",
                    "required": False
                }
            }
        """
        raise NotImplementedError

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        """
        도구의 핵심 실행 로직

        Args:
            doc (List[Dict]): 파싱된 보험 문서 JSON
                구조: [{"elements": [{"title": str, "paragraphs": [...]}]}]
            params (Dict[str, Any]): 도구 실행에 필요한 파라미터
                - 각 도구마다 필요한 파라미터가 다름
                - "instruction" 필드는 선택적으로 Replanner가 추가 가능

        Returns:
            ToolResult: 실행 결과 (성공/실패, 데이터/에러)

        구현 시 주의사항:
            1. 예외 처리를 반드시 포함
            2. 성공 시 _create_success() 사용
            3. 실패 시 _create_error() 사용
            4. params에서 required 필드 누락 시 KeyError 처리

        구현 예시:
            try:
                # 파라미터 추출
                keywords = params.get("keywords", ["정의"])

                # 로직 실행
                result = self._search_logic(doc, keywords)

                # 성공 결과 반환
                return self._create_success({"location": result})
            except Exception as e:
                return self._create_error(f"Error: {str(e)}")
        """
        raise NotImplementedError

    def _create_success(self, data: Dict[str, Any]) -> ToolResult:
        """
        성공 결과를 생성하는 헬퍼 메서드

        Args:
            data (Dict[str, Any]): 결과 데이터

        Returns:
            ToolResult: success=True인 결과 객체
        """
        return ToolResult(
            success=True,
            data=data,
            error=None,
            tool_name=self.name
        )

    def _create_error(self, error_msg: str) -> ToolResult:
        """
        실패 결과를 생성하는 헬퍼 메서드

        Args:
            error_msg (str): 에러 메시지

        Returns:
            ToolResult: success=False인 결과 객체
        """
        return ToolResult(
            success=False,
            data=None,
            error=error_msg,
            tool_name=self.name
        )
