"""
Base Tool: 유연한 도구 기본 클래스

모든 도구가 상속받는 기본 인터페이스입니다.
"""

from typing import Dict, List, Any, Optional
from enum import Enum
from abc import ABC, abstractmethod
import sys
import os

# 상위 디렉토리를 path에 추가하여 core 모듈 import 가능하게 함
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.flexible_result import FlexibleToolResult, ResultStatus, ResultMetadata
from core.document_accessor import DocumentAccessor


class ToolType(Enum):
    """도구 타입"""
    SEARCH = "search"
    EXTRACT = "extract"
    TRANSFORM = "transform"
    VALIDATE = "validate"
    CUSTOM = "custom"


class FlexibleTool(ABC):
    """
    유연한 도구 기본 클래스

    모든 도구는 이 클래스를 상속받아 구현합니다.

    주요 특징:
        - 도구별로 최적화된 파라미터 스키마
        - 자유로운 출력 구조
        - DocumentAccessor 활용
        - 메타데이터로 사용 힌트 제공

    구현해야 할 메서드:
        - get_type(): 도구 타입 반환
        - get_description(): 도구 설명
        - get_parameters_schema(): 파라미터 스키마
        - execute(): 실제 실행 로직
    """

    def __init__(self):
        self.name = self.__class__.__name__
        self.type = self.get_type()
        self.description = self.get_description()
        self.parameters_schema = self.get_parameters_schema()

    @abstractmethod
    def get_type(self) -> ToolType:
        """도구 타입 반환"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """도구 설명 반환"""
        pass

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """파라미터 스키마 반환"""
        pass

    @abstractmethod
    def execute(
        self,
        document: Any,
        params: Dict[str, Any],
        accessor: Optional[DocumentAccessor] = None
    ) -> FlexibleToolResult:
        """
        도구 실행

        Args:
            document: 원본 문서
            params: 실행 파라미터
            accessor: DocumentAccessor (없으면 자동 생성)

        Returns:
            FlexibleToolResult: 실행 결과
        """
        pass

    def _create_success(
        self,
        data: Dict[str, Any],
        metadata: Optional[ResultMetadata] = None,
        status: ResultStatus = ResultStatus.SUCCESS
    ) -> FlexibleToolResult:
        """성공 결과 생성 헬퍼"""
        if metadata is None:
            metadata = ResultMetadata()

        return FlexibleToolResult(
            status=status,
            data=data,
            metadata=metadata,
            error=None,
            tool_name=self.name,
            task_type=self.type.value
        )

    def _create_error(
        self,
        error_msg: str,
        partial_data: Optional[Dict[str, Any]] = None
    ) -> FlexibleToolResult:
        """에러 결과 생성 헬퍼"""
        status = ResultStatus.PARTIAL_SUCCESS if partial_data else ResultStatus.ERROR

        return FlexibleToolResult(
            status=status,
            data=partial_data,
            metadata=ResultMetadata(),
            error=error_msg,
            tool_name=self.name,
            task_type=self.type.value
        )

    def _get_accessor(
        self,
        document: Any,
        accessor: Optional[DocumentAccessor]
    ) -> DocumentAccessor:
        """DocumentAccessor 가져오기 (없으면 생성)"""
        if accessor is not None:
            return accessor
        return DocumentAccessor(document)
