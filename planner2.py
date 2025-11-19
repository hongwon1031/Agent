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
            "sample_content": self.sample_content[:500]  # 처음 500자만
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

    def __init__(self, model: str = "gpt-4o"):
        self.tool_registry = TOOL_REGISTRY
        self.model = model
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found in environment")
        self.client = OpenAI(api_key=api_key)

    def analyze_document(self, data: Dict, stage: Stage) -> DocumentAnalysis:
        """문서 특성 분석 (기존 로직 유지)"""
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

    def plan_for_stage(self, data: Dict, stage: Stage) -> ToolPlan:
        """
        REAL GPT-based planning

        GPT가 문서 특성과 Tool Registry를 보고 직접 Tool 조합 선택
        """
        analysis = self.analyze_document(data, stage)
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
                        "content": "You are a strategic planner for a multi-agent system. "
                                   "Your job is to select the optimal tool combination for each stage "
                                   "based on document characteristics and tool capabilities."
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

YOUR TASK:
Based on the document characteristics and tool capabilities, select the optimal tool combination.

DECISION CRITERIA:
1. If the document has structured tables with simple patterns -> prefer rule_based tools
2. If there are formulas (min[], max[]) -> use FormulaAwareConditionParser or its sub-tools
3. If the document is unstructured or complex -> prefer llm_based tools
4. Consider speed vs accuracy tradeoff
5. Always specify a fallback_tool in case the primary tool fails

OUTPUT FORMAT (JSON):
{{
  "primary_tools": ["ToolName1", "ToolName2", ...],  // Main tool pipeline (can be single tool or multiple tools in sequence)
  "fallback_tool": "FallbackToolName",  // Tool to use if primary fails (optional but recommended)
  "params": {{}},  // Any parameters for the tools (optional)
  "estimated_confidence": 0.85,  // Your confidence in this plan (0.0 to 1.0)
  "reasoning": "Clear explanation of why you chose these tools based on document characteristics"
}}

IMPORTANT:
- primary_tools should be a list of tool names from the available tools
- For simple cases, use a single tool: ["SimpleRangeParser"]
- For complex cases, chain multiple tools: ["FormulaDetector", "VariableExtractor", "FormulaEvaluator"]
- Always explain your reasoning clearly

Now, make your decision and output ONLY valid JSON:"""

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

    def __init__(self, model: str = "gpt-4o"):
        self.planner = PlannerAgent(model=model)
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

    orchestrator = PipelineOrchestrator(model="gpt-4o")

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
