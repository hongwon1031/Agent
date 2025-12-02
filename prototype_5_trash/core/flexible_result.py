"""
Flexible Tool Result: 유연한 도구 결과 형식

Tool이 상황에 맞게 자유롭게 출력 구조를 결정할 수 있도록 합니다.

핵심 개념:
    - Tool은 고정된 출력 형식에 얽매이지 않음
    - 메타데이터로 출력 스키마와 사용 힌트 제공
    - 다음 단계 Tool이 유연하게 활용 가능
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class ResultStatus(Enum):
    """결과 상태"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"  # 부분적 성공
    FAILURE = "failure"
    ERROR = "error"


@dataclass
class ResultMetadata:
    """
    결과 메타데이터

    Attributes:
        output_schema: 출력 데이터의 스키마 설명
        access_hints: 다음 단계에서 데이터를 사용하는 방법
        confidence: 결과의 신뢰도 (0.0 ~ 1.0)
        processing_notes: 처리 과정 설명
        alternative_paths: 대안 접근 경로들
    """
    output_schema: Dict[str, Any] = field(default_factory=dict)
    access_hints: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    processing_notes: str = ""
    alternative_paths: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FlexibleToolResult:
    """
    유연한 Tool 결과

    Tool이 자유롭게 출력 구조를 결정하고, 메타데이터로 사용 방법을 안내합니다.

    Attributes:
        status: 결과 상태
        data: 실제 결과 데이터 (자유로운 구조)
        metadata: 결과 메타데이터
        error: 에러 메시지 (실패 시)
        tool_name: 도구 이름
        task_type: Task 타입 (classifier, extract, transform 등)

    사용 예시:
        # Tool이 자유롭게 구조 결정
        result = FlexibleToolResult(
            status=ResultStatus.SUCCESS,
            data={
                "found_sections": [
                    {"title": "정의", "access_path": ["doc", "sections", 2]}
                ],
                "search_method": "keyword_matching",
                "total_matches": 1
            },
            metadata=ResultMetadata(
                output_schema={
                    "found_sections": "list of dicts with title and access_path",
                    "search_method": "str",
                    "total_matches": "int"
                },
                access_hints={
                    "primary_result": "found_sections[0]",
                    "how_to_access": "Use access_path to navigate document"
                },
                confidence=0.95
            ),
            tool_name="FlexibleSearchTool",
            task_type="search"
        )
    """
    status: ResultStatus
    data: Optional[Dict[str, Any]] = None
    metadata: ResultMetadata = field(default_factory=ResultMetadata)
    error: Optional[str] = None
    tool_name: str = ""
    task_type: str = ""

    def is_success(self) -> bool:
        """성공 여부 확인"""
        return self.status in [ResultStatus.SUCCESS, ResultStatus.PARTIAL_SUCCESS]

    def is_failure(self) -> bool:
        """실패 여부 확인"""
        return self.status in [ResultStatus.FAILURE, ResultStatus.ERROR]

    def get_primary_result(self) -> Any:
        """
        주요 결과 추출

        metadata.access_hints에 "primary_result" 키가 있으면 해당 경로로 접근,
        없으면 data 전체 반환

        Returns:
            Any: 주요 결과
        """
        if not self.data:
            return None

        primary_path = self.metadata.access_hints.get("primary_result")
        if not primary_path:
            return self.data

        # 경로 파싱 및 접근
        try:
            result = self.data
            # "found_sections[0].title" 같은 경로 지원
            import re
            parts = re.split(r'[\.\[]', primary_path)
            for part in parts:
                part = part.rstrip(']')
                if part.isdigit():
                    result = result[int(part)]
                else:
                    result = result[part]
            return result
        except (KeyError, IndexError, TypeError):
            return self.data

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (직렬화용)"""
        return {
            "status": self.status.value,
            "data": self.data,
            "metadata": {
                "output_schema": self.metadata.output_schema,
                "access_hints": self.metadata.access_hints,
                "confidence": self.metadata.confidence,
                "processing_notes": self.metadata.processing_notes,
                "alternative_paths": self.metadata.alternative_paths
            },
            "error": self.error,
            "tool_name": self.tool_name,
            "task_type": self.task_type
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FlexibleToolResult':
        """딕셔너리에서 생성"""
        metadata_dict = data.get("metadata", {})
        metadata = ResultMetadata(
            output_schema=metadata_dict.get("output_schema", {}),
            access_hints=metadata_dict.get("access_hints", {}),
            confidence=metadata_dict.get("confidence", 1.0),
            processing_notes=metadata_dict.get("processing_notes", ""),
            alternative_paths=metadata_dict.get("alternative_paths", [])
        )

        return cls(
            status=ResultStatus(data.get("status", "success")),
            data=data.get("data"),
            metadata=metadata,
            error=data.get("error"),
            tool_name=data.get("tool_name", ""),
            task_type=data.get("task_type", "")
        )
