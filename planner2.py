# -*- coding: utf-8 -*-
"""
개선된 Multi-Agent 아키텍처 프로토타입
- 고정된 4단계 파이프라인
- 각 Stage에서 Planner가 유연하게 Tool 선택
- 실제 OpenAI GPT 기반 Planner가 자율적으로 Tool 조합 선택
"""

import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# ============================================================================
# 1. Fixed Pipeline Definition
# ============================================================================

class Stage(Enum):
    """고정된 4단계 파이프라인"""
    EXTRACT_DEFINITIONS = "extract_definitions"  # 정의 추출
    PARSE_CONDITIONS = "parse_conditions"        # 조건 파싱
    MERGE_DATA = "merge_data"                    # 데이터 병합
    FORMAT_OUTPUT = "format_output"              # 출력 포맷팅


# ============================================================================
# 2. Tool/Agent Registry (descriptions only, no actual implementation)
# ============================================================================

TOOL_REGISTRY = {
    # ========== Stage 1: Extract Definitions ==========
    "RuleBasedDefinitionExtractor": {
        "description": "Parse structured Title1 table using xpath/pattern matching to extract product hierarchy",
        "type": "rule_based",
        "best_for": "Tables with consistent structure and simple rowspan/colspan",
        "confidence": 0.95,
        "speed": "fast"
    },

    "LLMDefinitionInterpreter": {
        "description": "Use LLM to interpret Title1 table/text freely to derive product relationships",
        "type": "llm_based",
        "best_for": "Complex table structures or heavy text descriptions",
        "confidence": 0.85,
        "speed": "slow",
        "model": "gpt-4o"
    },

    # ========== Stage 2: Parse Conditions ==========
    "SimpleRangeParser": {
        "description": "Extract simple age ranges like '15-70' using regex only",
        "type": "rule_based",
        "best_for": "No formulas, only simple ranges",
        "confidence": 0.98,
        "speed": "fast"
    },

    "FormulaAwareConditionParser": {
        "description": "Parse conditions with formulas like 'min[age_limit - payment_years, 90 - payment_years, 80]'",
        "type": "hybrid",
        "best_for": "Conditions containing mathematical formulas",
        "sub_tools": ["FormulaDetector", "VariableExtractor", "FormulaEvaluator"],
        "confidence": 0.90,
        "speed": "medium"
    },

    "LLMConditionParser": {
        "description": "Use LLM to extract eligibility conditions from unstructured text",
        "type": "llm_based",
        "best_for": "Non-tabular or narrative-style conditions",
        "confidence": 0.80,
        "speed": "slow",
        "model": "gpt-4o"
    },

    # ========== Sub-Tools (used by FormulaAwareConditionParser) ==========
    "FormulaDetector": {
        "description": "Detect formula patterns like 'min[...]', 'max[...]' in text",
        "type": "rule_based"
    },

    "VariableExtractor": {
        "description": "Find actual values of variables (e.g., 'age_limit', 'payment_years') in document",
        "type": "hybrid",
        "params": {
            "search_scope": ["Title1", "Title3"],
            "use_llm_if_ambiguous": True
        }
    },

    "FormulaEvaluator": {
        "description": "Evaluate formula to get result (e.g., min[70, 80, 80] = 70)",
        "type": "rule_based"
    },

    # ========== Stage 3: Merge Data ==========
    "CartesianProductMerger": {
        "description": "Generate all combinations of definitions (type1 x type2) and conditions (period x payment)",
        "type": "rule_based",
        "best_for": "Need all possible combinations without filtering",
        "confidence": 1.0,
        "speed": "fast"
    },

    "FilteredMerger": {
        "description": "Merge only eligible combinations, excluding ineligible conditions",
        "type": "rule_based",
        "best_for": "When separate 'ineligible conditions' table exists",
        "confidence": 0.95,
        "speed": "medium"
    },

    # ========== Stage 4: Format Output ==========
    "SchemaFormatter": {
        "description": "Transform intermediate data to TARGET_FIELDS schema and infer codes",
        "type": "hybrid",
        "sub_tools": ["AgeCodeInferencer", "GenderCodeMapper"],
        "confidence": 0.98,
        "speed": "fast"
    },

    "AgeCodeInferencer": {
        "description": "Infer age classification codes from text ('age 15' -> '(2)actual_age', '70 years' -> '(1)insurance_age')",
        "type": "rule_based"
    },

    "GenderCodeMapper": {
        "description": "Convert gender text to codes ('male' -> '(1)male', 'female' -> '(2)female')",
        "type": "rule_based"
    }
}


# Stage별 사용 가능한 Tool 매핑
STAGE_TOOLS = {
    Stage.EXTRACT_DEFINITIONS: [
        "RuleBasedDefinitionExtractor",
        "LLMDefinitionInterpreter"
    ],
    Stage.PARSE_CONDITIONS: [
        "SimpleRangeParser",
        "FormulaAwareConditionParser",
        "LLMConditionParser"
    ],
    Stage.MERGE_DATA: [
        "CartesianProductMerger",
        "FilteredMerger"
    ],
    Stage.FORMAT_OUTPUT: [
        "SchemaFormatter"
    ]
}


# ============================================================================
# 3. Data Structures
# ============================================================================

@dataclass
class DocumentStructure:
    """LLM이 발견한 문서 계층 구조"""
    hierarchy_section: Dict  # Title 1 전체 정보 (상품 계층)
    conditions_section: Dict  # Title 3 전체 정보 (가입 조건)
    subtitle_to_tables: Dict  # 소제목 → 표 매핑 {"가. 해약환급금 미지급형": ["가입가능 조건"]}
    hierarchy_title: str  # "1. 보험종목의 명칭"
    conditions_title: str  # "3. 보험기간, ..."


@dataclass
class DocumentAnalysis:
    """Document analysis result by Planner"""
    stage: Stage
    has_table: bool
    table_structure: str
    has_formula: bool
    formula_complexity: str
    text_density: float
    column_count: int
    row_span_usage: bool
    sample_content: str  # 실제 내용 일부
    subtitle_context: str = ""  # 소제목 정보 ("가. 해약환급금 미지급형")
    discovered_structure: Optional['DocumentStructure'] = None  # 발견한 구조

    def to_dict(self):
        return {
            "stage": self.stage.value,
            "has_table": self.has_table,
            "table_structure": self.table_structure,
            "has_formula": self.has_formula,
            "formula_complexity": self.formula_complexity,
            "text_density": self.text_density,
            "column_count": self.column_count,
            "row_span_usage": self.row_span_usage,
            "sample_content": self.sample_content[:500],  # 처음 500자만
            "subtitle_context": self.subtitle_context
        }


@dataclass
class ToolPlan:
    """Tool execution plan selected by Planner"""
    primary_tools: List[str]
    fallback_tool: Optional[str] = None
    params: Dict[str, Any] = None
    estimated_confidence: float = 0.0
    reasoning: str = ""

    def to_dict(self):
        return {
            "primary_tools": self.primary_tools,
            "fallback_tool": self.fallback_tool,
            "params": self.params or {},
            "estimated_confidence": self.estimated_confidence,
            "reasoning": self.reasoning
        }


@dataclass
class ValidationResult:
    """Validation result by ValidationAgent"""
    stage: Stage
    status: str
    errors: List[Dict[str, str]]
    warnings: List[Dict[str, str]]
    action: str
    suggestion: Optional[str] = None

    def to_dict(self):
        return {
            "stage": self.stage.value,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "action": self.action,
            "suggestion": self.suggestion
        }


# ============================================================================
# 4. REAL PlannerAgent - GPT-based Tool Selection
# ============================================================================

class PlannerAgent:
    """
    REAL Planner using OpenAI GPT to select optimal tool combination
    """

    def __init__(self, model: str = "gpt-4o", analysis_mode: str = "llm_based"):
        """
        Args:
            model: GPT 모델 (계획 수립용)
            analysis_mode: 문서 분석 방식
                - "rule_based": 패턴 매칭 (빠름, 새로운 형식에 취약)
                - "llm_based": LLM 분석 (유연, 느림, 비용↑)
                - "hybrid": Rule 먼저 시도, 실패 시 LLM
        """
        self.tool_registry = TOOL_REGISTRY
        self.model = model
        self.analysis_mode = analysis_mode
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found in environment")
        self.client = OpenAI(api_key=api_key)
        self._document_structure_cache = None  # 문서 구조 캐싱 (1회만 실행)

    def _discover_document_structure(self, data: Dict) -> DocumentStructure:
        """
        LLM이 문서 구조를 자동 발견
        - Title 1: 상품 계층 (유형1, 유형2)
        - Title 3: 가입 조건 + 소제목 → 표 매핑
        """
        # 캐시 확인
        if self._document_structure_cache is not None:
            return self._document_structure_cache

        # JSON이 list일 경우 첫 번째 요소 사용
        if isinstance(data, list):
            data = data[0] if data else {}

        # 문서 제목 목록 추출 (LLM에게 힌트 제공)
        titles = []
        for element in data.get("elements", []):
            titles.append(element.get("title", ""))

        titles_summary = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles[:10]))  # 처음 10개만

        # LLM에게 구조 발견 요청
        discovery_prompt = f"""다음은 보험 약관 문서입니다.
이 문서의 구조를 분석하여 필요한 정보가 어디에 있는지 찾으세요.

문서 Title 목록:
{titles_summary}

찾아야 할 정보:
1. 상품 계층/명칭 정보 (유형1, 유형2 등) → 주로 "보험종목의 명칭" Title
2. 가입 조건 정보 (보험기간, 납입기간, 나이 등) → 주로 "보험기간, ..." Title
3. Title 3 내부의 소제목과 표 관계:
   - 각 소제목(가., 나., ...)
   - 각 소제목 아래 "가입가능 조건" 표의 위치

출력 형식 (JSON):
{{
  "hierarchy_title": "1. 보험종목의 명칭",
  "conditions_title": "3. 보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
  "subtitle_mappings": [
    {{"subtitle": "가. 해약환급금 미지급형", "tables": ["가입가능 조건", "가입불가 조건"]}},
    {{"subtitle": "나. 일반형", "tables": ["가입가능 조건"]}}
  ]
}}

반드시 JSON 형식으로만 응답하세요."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document structure analyzer. Find where the required information is located in insurance documents."
                    },
                    {"role": "user", "content": discovery_prompt}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            discovery_result = json.loads(response.choices[0].message.content)

            print(f"\n[LLM 문서 구조 발견]")
            print(json.dumps(discovery_result, indent=2, ensure_ascii=False))
            print()

            # 실제 섹션 추출
            hierarchy_title = discovery_result.get("hierarchy_title", "")
            conditions_title = discovery_result.get("conditions_title", "")

            hierarchy_section = None
            conditions_section = None

            for element in data.get("elements", []):
                title = element.get("title", "")
                if hierarchy_title and hierarchy_title in title:
                    hierarchy_section = element
                if conditions_title and conditions_title in title:
                    conditions_section = element

            # 소제목 → 표 매핑 생성
            subtitle_to_tables = {}
            for mapping in discovery_result.get("subtitle_mappings", []):
                subtitle = mapping.get("subtitle", "")
                tables = mapping.get("tables", [])
                subtitle_to_tables[subtitle] = tables

            structure = DocumentStructure(
                hierarchy_section=hierarchy_section or {},
                conditions_section=conditions_section or {},
                subtitle_to_tables=subtitle_to_tables,
                hierarchy_title=hierarchy_title,
                conditions_title=conditions_title
            )

            # 캐싱
            self._document_structure_cache = structure
            return structure

        except Exception as e:
            print(f"LLM 구조 발견 실패: {e}")
            # Fallback: 하드코딩된 방식
            return DocumentStructure(
                hierarchy_section=self._find_section(data, "1.") or {},
                conditions_section=self._find_section(data, "3.") or {},
                subtitle_to_tables={},
                hierarchy_title="1. 보험종목의 명칭",
                conditions_title="3. 보험기간, ..."
            )

    def _analyze_document_rule_based(self, data: Dict, stage: Stage) -> DocumentAnalysis:
        """Rule-based 문서 특성 분석 (패턴 매칭)"""
        # JSON이 list일 경우 첫 번째 요소 사용
        if isinstance(data, list):
            data = data[0] if data else {}

        title3_section = self._find_section(data, "3.")

        if not title3_section:
            return DocumentAnalysis(
                stage=stage,
                has_table=False,
                table_structure="none",
                has_formula=False,
                formula_complexity="none",
                text_density=1.0,
                column_count=0,
                row_span_usage=False,
                sample_content=json.dumps(data, ensure_ascii=False)[:500]
            )

        has_table = any(p.get("type") == "table" for p in title3_section.get("paragraphs", []))
        text_content = json.dumps(title3_section, ensure_ascii=False)
        has_formula = "min[" in text_content or "max[" in text_content

        table_structure = "regular"
        row_span_usage = False
        column_count = 0

        if has_table:
            for para in title3_section.get("paragraphs", []):
                if para.get("type") == "table":
                    table_elements = para.get("table", {}).get("table_elements", [])
                    if table_elements:
                        column_count = len(table_elements[0])
                    if "rowspan" in para.get("content", ""):
                        row_span_usage = True
                        table_structure = "irregular"

        return DocumentAnalysis(
            stage=stage,
            has_table=has_table,
            table_structure=table_structure,
            has_formula=has_formula,
            formula_complexity="medium" if has_formula else "none",
            text_density=0.3 if has_table else 0.9,
            column_count=column_count,
            row_span_usage=row_span_usage,
            sample_content=text_content[:1000]
        )

    def _analyze_document_llm_based(self, data: Dict, stage: Stage) -> DocumentAnalysis:
        """LLM-based 문서 특성 분석 (의미론적 이해)"""
        # JSON이 list일 경우 첫 번째 요소 사용
        if isinstance(data, list):
            data = data[0] if data else {}

        # 1. 문서 구조 발견 (캐싱됨)
        structure = self._discover_document_structure(data)

        # 2. Stage에 따라 관련 섹션 추출
        subtitle_context = ""
        if stage == Stage.EXTRACT_DEFINITIONS:
            # Title 1: 상품 계층
            sample_data = json.dumps(structure.hierarchy_section, ensure_ascii=False)[:3000]
        elif stage == Stage.PARSE_CONDITIONS:
            # Title 3: 가입 조건 + 첫 번째 소제목 정보
            sample_data = json.dumps(structure.conditions_section, ensure_ascii=False)[:4000]
            # 소제목 정보 추가
            if structure.subtitle_to_tables:
                first_subtitle = list(structure.subtitle_to_tables.keys())[0]
                subtitle_context = first_subtitle
        else:
            # 다른 Stage는 전체 문서
            sample_data = json.dumps(data, ensure_ascii=False)[:3000]

        # LLM에게 문서 분석 요청
        analysis_prompt = f"""다음은 보험 약관 문서의 일부입니다.
이 문서의 구조적 특성을 분석하여 JSON으로 반환하세요.

문서 내용:
{sample_data}

분석 항목:
1. has_table: 표가 존재하는가? (true/false)
2. table_structure: 표의 구조 복잡도 ("none", "regular", "irregular")
   - regular: 단순한 행/열 구조
   - irregular: rowspan, colspan 등 복잡한 병합 셀 사용
3. has_formula: 수식이 존재하는가? (min[], max[] 같은 계산식) (true/false)
4. formula_complexity: 수식 복잡도 ("none", "simple", "medium", "complex")
5. text_density: 텍스트 비율 (0.0~1.0, 표가 많으면 낮고 텍스트가 많으면 높음)
6. column_count: 표의 열 개수 (표가 없으면 0)
7. row_span_usage: rowspan 같은 셀 병합 사용 여부 (true/false)

출력 형식 (JSON):
{{
  "has_table": true,
  "table_structure": "irregular",
  "has_formula": false,
  "formula_complexity": "none",
  "text_density": 0.3,
  "column_count": 4,
  "row_span_usage": true
}}

반드시 JSON 형식으로만 응답하세요."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # 빠르고 저렴한 모델
                messages=[
                    {
                        "role": "system",
                        "content": "You are a document structure analyzer. Analyze the given insurance document and return ONLY valid JSON."
                    },
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"}
            )

            analysis_result = json.loads(response.choices[0].message.content)

            print(f"\n[LLM 문서 분석 결과]")
            print(json.dumps(analysis_result, indent=2, ensure_ascii=False))
            print()

            return DocumentAnalysis(
                stage=stage,
                has_table=analysis_result.get("has_table", False),
                table_structure=analysis_result.get("table_structure", "none"),
                has_formula=analysis_result.get("has_formula", False),
                formula_complexity=analysis_result.get("formula_complexity", "none"),
                text_density=analysis_result.get("text_density", 0.5),
                column_count=analysis_result.get("column_count", 0),
                row_span_usage=analysis_result.get("row_span_usage", False),
                sample_content=sample_data[:500],
                subtitle_context=subtitle_context,
                discovered_structure=structure
            )

        except Exception as e:
            print(f"LLM 분석 실패, Rule-based로 폴백: {e}")
            return self._analyze_document_rule_based(data, stage)

    def plan_for_stage(self, data: Dict, stage: Stage) -> ToolPlan:
        """
        REAL GPT-based planning

        GPT가 문서 특성과 Tool Registry를 보고 직접 Tool 조합 선택
        """
        # 분석 방식 선택
        if self.analysis_mode == "rule_based":
            analysis = self._analyze_document_rule_based(data, stage)
        elif self.analysis_mode == "llm_based":
            analysis = self._analyze_document_llm_based(data, stage)
        elif self.analysis_mode == "hybrid":
            # Hybrid: Rule 먼저 시도, Title3 섹션이 없으면 LLM 사용
            analysis = self._analyze_document_rule_based(data, stage)
            if analysis.table_structure == "none" and analysis.text_density >= 0.9:
                print("[Hybrid 모드] Rule-based 분석 결과 불확실 → LLM으로 재분석")
                analysis = self._analyze_document_llm_based(data, stage)
        else:
            raise ValueError(f"Unknown analysis_mode: {self.analysis_mode}")
        available_tools = STAGE_TOOLS.get(stage, [])

        # Tool 정보를 GPT에게 제공
        tools_info = {
            tool_name: self.tool_registry[tool_name]
            for tool_name in available_tools
        }

        # GPT에게 Tool 선택 요청
        prompt = self._build_planning_prompt(stage, analysis, tools_info)

        print(f"\n{'='*60}")
        print(f"GPT에게 Stage 계획 요청: {stage.value}")
        print(f"{'='*60}")
        print(f"문서 분석 결과:")
        print(f"  - 표 존재: {analysis.has_table}")
        print(f"  - 수식 존재: {analysis.has_formula}")
        print(f"  - 표 구조: {analysis.table_structure}")
        print(f"  - 사용 가능한 Tool: {available_tools}")
        print(f"\nGPT에게 프롬프트 전송 중...\n")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "너는 multi-agent system의 strategic planner이다. "
                                   "너의 임무는 각 stage에 맞는 최적의 Tool 조합을 선택하는 것이다. "
                                   "문서 특성과 tool의 기능을 기반으로 판단하여라. "
                                   "모든 응답은 반드시 한국어로 작성하고, 특히 reasoning 필드는 한국어로 명확하게 설명해야 한다."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"}
            )

            plan_json = json.loads(response.choices[0].message.content)

            print(f"GPT 응답:")
            print(json.dumps(plan_json, indent=2, ensure_ascii=False))
            print()

            return ToolPlan(
                primary_tools=plan_json.get("primary_tools", []),
                fallback_tool=plan_json.get("fallback_tool"),
                params=plan_json.get("params", {}),
                estimated_confidence=plan_json.get("estimated_confidence", 0.0),
                reasoning=plan_json.get("reasoning", "")
            )

        except Exception as e:
            print(f"GPT 호출 에러: {e}")
            # 간단한 휴리스틱으로 Fallback
            return self._fallback_plan(stage, analysis)

    def _build_planning_prompt(self, stage: Stage, analysis: DocumentAnalysis, tools_info: Dict) -> str:
        """GPT에게 보낼 프롬프트 생성"""

        return f"""You are planning the execution strategy for stage: {stage.value}

DOCUMENT ANALYSIS:
{json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False)}

AVAILABLE TOOLS FOR THIS STAGE:
{json.dumps(tools_info, indent=2, ensure_ascii=False)}

당신의 임무:
문서 특성과 도구 능력을 바탕으로 최적의 도구 조합을 선택하세요.

선택 기준:
1. 구조화된 표가 있고 패턴이 단순함 -> rule_based 도구 우선
2. 수식이 있음 (min[], max[]) -> FormulaAwareConditionParser 또는 하위 도구 사용
3. 비구조화되었거나 복잡함 -> llm_based 도구 우선
4. 속도 vs 정확도 트레이드오프 고려
5. 항상 fallback_tool을 지정하여 실패 대비

출력 형식 (JSON):
{{
  "primary_tools": ["도구이름1", "도구이름2", ...],  // 메인 도구 파이프라인 (단일 또는 여러 도구 순차 실행)
  "fallback_tool": "폴백도구이름",  // 실패 시 사용할 도구 (선택이지만 권장)
  "params": {{}},  // 도구 파라미터 (선택)
  "estimated_confidence": 0.85,  // 이 계획에 대한 신뢰도 (0.0 ~ 1.0)
  "reasoning": "문서 특성 기반으로 이 도구들을 선택한 명확한 이유"
}}

중요사항:
- primary_tools는 사용 가능한 도구 목록에서 선택한 도구 이름 리스트여야 함
- 단순한 경우: 단일 도구 사용 ["SimpleRangeParser"]
- 복잡한 경우: 여러 도구 연쇄 ["FormulaDetector", "VariableExtractor", "FormulaEvaluator"]
- 항상 선택 이유를 명확히 설명할 것

이제 결정을 내리고 유효한 JSON만 출력하세요:"""

    def _fallback_plan(self, stage: Stage, analysis: DocumentAnalysis) -> ToolPlan:
        """GPT 호출 실패 시 간단한 휴리스틱 사용"""
        if stage == Stage.PARSE_CONDITIONS:
            if analysis.has_formula:
                return ToolPlan(
                    primary_tools=["FormulaAwareConditionParser"],
                    fallback_tool="LLMConditionParser",
                    estimated_confidence=0.7,
                    reasoning="Fallback heuristic: formula detected"
                )
            else:
                return ToolPlan(
                    primary_tools=["SimpleRangeParser"],
                    fallback_tool="LLMConditionParser",
                    estimated_confidence=0.8,
                    reasoning="Fallback heuristic: simple range parsing"
                )

        # 다른 Stage는 첫 번째 Tool 사용
        available = STAGE_TOOLS.get(stage, [])
        return ToolPlan(
            primary_tools=[available[0]] if available else [],
            estimated_confidence=0.5,
            reasoning="Fallback: using first available tool"
        )

    def _find_section(self, data: Dict, title_pattern: str) -> Optional[Dict]:
        """문서에서 특정 섹션 찾기"""
        # data가 dict인 경우
        if isinstance(data, dict):
            for element in data.get("elements", []):
                if title_pattern in element.get("title", ""):
                    return element
        return None


# ============================================================================
# 5. ExecutorAgent - Tool Execution (Mock)
# ============================================================================

class ExecutorAgent:
    """Execute plan generated by Planner"""

    def __init__(self):
        self.tool_registry = TOOL_REGISTRY

    def execute_stage(self, stage: Stage, data: Dict, plan: ToolPlan) -> Dict:
        """Stage 실행"""
        print(f"\n{'='*60}")
        print(f"Stage 실행 중: {stage.value}")
        print(f"{'='*60}\n")

        result = data

        try:
            for tool_name in plan.primary_tools:
                print(f"  -> Tool 실행: {tool_name}")
                tool_info = self.tool_registry.get(tool_name, {})
                print(f"     타입: {tool_info.get('type', 'unknown')}")
                print(f"     설명: {tool_info.get('description', '설명 없음')}")

                # Mock 실행
                result = self._execute_tool(tool_name, result, plan.params)
                print(f"     ✓ 성공\n")

        except Exception as e:
            if plan.fallback_tool:
                print(f"  ✗ 에러: {e}")
                print(f"  -> Fallback Tool로 전환: {plan.fallback_tool}\n")

                fallback_info = self.tool_registry.get(plan.fallback_tool, {})
                print(f"     타입: {fallback_info.get('type', 'unknown')}")
                print(f"     설명: {fallback_info.get('description', '설명 없음')}")

                result = self._execute_tool(plan.fallback_tool, data, plan.params)
                print(f"     ✓ Fallback 성공\n")
            else:
                raise

        return result

    def _execute_tool(self, tool_name: str, data: Dict, params: Optional[Dict] = None) -> Dict:
        """Execute individual tool (Mock)"""
        # data가 list일 경우 처리
        if isinstance(data, list):
            data = data[0] if data else {}

        # dict가 아닐 경우 빈 dict로
        if not isinstance(data, dict):
            data = {}

        return {
            **data,
            f"processed_by_{tool_name}": True
        }


# ============================================================================
# 6. ValidationAgent - Result Validation
# ============================================================================

class ValidationAgent:
    """Validate each stage execution result"""

    def validate_stage(self, stage: Stage, result: Dict) -> ValidationResult:
        """간단한 검증만 수행 (실제 로직 생략)"""
        return ValidationResult(
            stage=stage,
            status="성공",
            errors=[],
            warnings=[],
            action="계속",
            suggestion=None
        )


# ============================================================================
# 7. Pipeline Orchestrator
# ============================================================================

class PipelineOrchestrator:
    """Manage and execute entire 4-stage pipeline"""

    def __init__(self, model: str = "gpt-4o", analysis_mode: str = "llm_based"):
        self.planner = PlannerAgent(model=model, analysis_mode=analysis_mode)
        self.executor = ExecutorAgent()
        self.validator = ValidationAgent()
        self.stages = [
            Stage.EXTRACT_DEFINITIONS,
            Stage.PARSE_CONDITIONS,
            Stage.MERGE_DATA,
            Stage.FORMAT_OUTPUT
        ]

    def run(self, input_data: Dict) -> Dict:
        """전체 파이프라인 실행"""
        result = input_data
        execution_log = []

        for stage in self.stages:
            print(f"\n{'#'*60}")
            print(f"# Stage: {stage.value}")
            print(f"{'#'*60}")

            # 1. GPT 기반 Planner가 Tool 조합 선택
            plan = self.planner.plan_for_stage(result, stage)

            # 2. Executor가 실행
            stage_result = self.executor.execute_stage(stage, result, plan)

            # 3. Validator가 검증
            validation = self.validator.validate_stage(stage, stage_result)

            print(f"\n  검증 결과: {validation.status}")

            # Log
            execution_log.append({
                "stage": stage.value,
                "plan": plan.to_dict(),
                "validation": validation.to_dict()
            })

            result = stage_result

        return {
            "final_output": result,
            "execution_log": execution_log
        }


# ============================================================================
# 8. Example Execution
# ============================================================================

def main():
    """실제 파싱된 5개 데이터로 테스트"""

    # 실제 데이터 파일 경로
    data_dir = r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과"

    test_files = [
        "(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json",
        "(간편)통합암(전이포함)진단특약TC(무배당, 해약환급금 미지급형)_parsed.json",
        "경증이상치매보장특약(무배당, 해약환급금 미지급형)_parsed.json",
        "신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json",
        "신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json"
    ]

    # LLM 기반 문서 분석 사용
    orchestrator = PipelineOrchestrator(model="gpt-4o", analysis_mode="llm_based")

    all_results = []

    for idx, filename in enumerate(test_files, 1):
        filepath = os.path.join(data_dir, filename)

        print("\n\n" + "="*80)
        print(f"테스트 케이스 {idx}/{len(test_files)}: {filename}")
        print("="*80)

        # 파일 읽기
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                input_data = json.load(f)

            # 파이프라인 실행
            result = orchestrator.run(input_data)
            all_results.append({
                "filename": filename,
                "result": result
            })

        except Exception as e:
            print(f"에러 발생: {e}")
            continue

    # 전체 요약
    print("\n\n" + "="*80)
    print("전체 실행 요약")
    print("="*80)

    for idx, res in enumerate(all_results, 1):
        print(f"\n{'='*80}")
        print(f"{idx}. {res['filename']}")
        print(f"{'='*80}")

        for log in res['result']['execution_log']:
            stage = log['stage']
            tools = log['plan']['primary_tools']
            reasoning = log['plan']['reasoning']
            confidence = log['plan'].get('estimated_confidence', 0)

            print(f"\n  [{stage}]")
            print(f"    선택된 Tool: {', '.join(tools)}")
            print(f"    신뢰도: {confidence:.2f}")
            print(f"    이유: {reasoning[:100]}..." if len(reasoning) > 100 else f"    이유: {reasoning}")


if __name__ == "__main__":
    main()
