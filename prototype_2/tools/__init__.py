"""
Tools package for prototype_2 agent system.

이 패키지는 보험 문서에서 정의를 추출하기 위한 다양한 도구들을 제공합니다.

주요 구성 요소:
    - base: 모든 도구의 기본 인터페이스 (SimpleTool, ToolResult)
    - search: 문서에서 정의 섹션을 찾는 도구들 (Rule/LLM 기반)
    - extract: 테이블에서 데이터를 추출하는 도구들 (Rule/LLM 기반)
    - cartesian: 추출된 데이터로부터 모든 조합을 생성하는 도구

도구 선택 전략:
    1. 먼저 빠른 rule-based 도구 시도
    2. 실패 시 유연한 llm-based 도구로 전환
    3. Validator가 결과 품질 검증
    4. Replanner가 실패 시 새로운 전략 수립

사용 예시:
    from tools import RuleSearchTool, LLMExtractTool

    search_tool = RuleSearchTool()
    result = search_tool.execute(doc, {"keywords": ["정의", "용어"]})
"""

from .base import SimpleTool, ToolResult
from .search import RuleSearchTool, LLMSearchTool
from .extract import RuleExtractTool, LLMExtractTool
from .cartesian import GenerateCartesianTool

__all__ = [
    'SimpleTool',
    'ToolResult',
    'RuleSearchTool',
    'LLMSearchTool',
    'RuleExtractTool',
    'LLMExtractTool',
    'GenerateCartesianTool',
]
