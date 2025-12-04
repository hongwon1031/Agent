"""
Core components for prototype_3 agent system.

이 패키지는 문서 접근, 결과 형식, 참조 시스템 등 핵심 기능을 제공합니다.
"""

from .document_accessor import DocumentAccessor, Section, Content
from .flexible_result import FlexibleToolResult, ResultMetadata
from .smart_reference import SmartReference, ReferenceResolver

__all__ = [
    'DocumentAccessor',
    'Section',
    'Content',
    'FlexibleToolResult',
    'ResultMetadata',
    'SmartReference',
    'ReferenceResolver',
]
