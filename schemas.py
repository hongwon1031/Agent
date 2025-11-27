# schemas.py
from typing import List, Optional, Dict, Any, Union
# schemas.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# 정의 단계
class DefinitionLevel(BaseModel):
    level: int          # 정의 레벨
    column_name: str    # 컬럼명
    values: List[str]   # 값들
    description: str    # 설명

# 정의 예시
class DefinitionSampleData(BaseModel):
    계층구조: List[DefinitionLevel]
    hierarchy_depth: int                # 트리 깊이
    hierarchy_tree_example: str         # 예시

class DefinitionLocation(BaseModel):
    paragraph_indices: Dict[str, List[int]]  # {"tables": [...], "texts": [...]}
    primary_table_index: int

class DefinitionSectionSummary(BaseModel):
    section_index: int
    title: str
    structure: str
    table_count: int
    columns: List[str]
    location: DefinitionLocation
    sample_data: DefinitionSampleData
    특이사항: str
    누락_위험: str

class SubtitleMapping(BaseModel):
    subtitle: str
    paragraph_index: int
    estimated_type: str
    table_index: Optional[int] = None
    table_types: Dict[str, List[str]]

class ConditionHierarchy(BaseModel):
    has_subtitles: bool
    subtitle_mapping: List[SubtitleMapping]
    all_unique_types: Dict[str, List[str]]
    hierarchy_tree_example: str

class ConditionSampleConditions(BaseModel):
    보험기간: List[str]
    납입기간: List[str]
    나이_표현: List[str]
    has_formula: bool
    formula_examples: List[str]

class ConditionLocation(BaseModel):
    paragraph_map: List[Dict[str, Any]]  # {index, type, content}

class ConditionSectionSummary(BaseModel):
    section_index: int
    title: str
    structure: str
    table_count: int
    location: ConditionLocation
    condition_hierarchy: ConditionHierarchy
    sample_conditions: ConditionSampleConditions
    특이사항: str
    누락_위험: str

class OtherSection(BaseModel):
    index: int
    title: str
    relevance: str

class DocumentAnalysis(BaseModel):
    total_sections: int
    definition_section: DefinitionSectionSummary
    condition_section: ConditionSectionSummary
    other_sections: List[OtherSection]
    complexity: str
    complexity_reason: str

class OnlyDocOutput(BaseModel):
    source_file: Optional[str] = None
    doc_title: Optional[str] = None

    document_analysis: DocumentAnalysis
