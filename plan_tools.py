from typing import List, Dict, Any

"""
only_plan.py에서 사용하는 Tool 카탈로그.
각 Tool은 이름/설명/타입(rule, hybrid, gpt-4o 등)/latency/cost 메타데이터를 가진다.
"""

TOOLS: List[Dict[str, Any]] = [
    # ---------------- Definition 계열 (정의 섹션) ----------------
    # 가장 기본: 단일 표, 계층 1~2단, 컬럼 명확
    {
        "name": "DefinitionSimpleTableRule",
        "description": "명칭/보험종목/보험종목_1 등 컬럼이 명확한 단일 정의 표를 순수 규칙으로 파싱",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DefinitionMultiColumnRule",
        "description": "멀티 컬럼(명칭+보험종목+심사유형 등) 구조이지만 rowspan/colspan이 단순한 정의 표를 규칙 기반으로 파싱",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DefinitionDeepHierarchyHybrid",
        "description": "3단계 이상 깊은 계층(보종명/타입1/타입2/타입3 등)을 갖는 정의 표를 규칙+LLM 하이브리드로 파싱",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "DefinitionTextOnlyLLM",
        "description": "정의가 표 없이 텍스트 문단에만 흩어져 있을 때 LLM으로 보종명/유형 계층을 추출",
        "type": "gpt-4o",
        "latency": "high",
        "cost": "high",
    },
    {
        "name": "DefinitionNameNormalizer",
        "description": "줄바꿈/괄호/공백을 정리하여 보종명을 일관된 형태로 정규화",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DefinitionColumnGuesser",
        "description": "컬럼명이 애매한 정의 표에서 어느 컬럼이 보종명/타입1/타입2인지 LLM으로 추론",
        "type": "gpt-4o-mini",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "DefinitionRiderSplitter",
        "description": "주계약/특약이 한 정의 표에 섞여 있을 때 특약만 분리하여 정의 계층을 구성",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    # 기존 generic 도구도 유지 (백워드 호환)
    {
        "name": "DefinitionRule",
        "description": "정의 섹션이 단순 표 구조인 경우 사용하는 기본 규칙 기반 파서",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DefinitionLLM",
        "description": "정의 섹션 텍스트가 복잡하거나 표만으로 계층이 보이지 않을 때 LLM으로 직접 정의를 추출",
        "type": "gpt-4o",
        "latency": "high",
        "cost": "high",
    },
    {
        "name": "DefinitionHybrid",
        "description": "표+텍스트가 혼합되고 계층이 2~3단 정도인 일반적인 정의 섹션용 하이브리드 파서",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },

    # ---------------- Rowspan/Colspan 및 복잡 표 ----------------
    {
        "name": "RowspanHandler",
        "description": "rowspan으로 위/아래 행이 공유하는 값(보험기간, 심사유형 등)을 각 행으로 펼쳐 넣기",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ColspanHandler",
        "description": "colspan으로 병합된 헤더/셀을 개별 컬럼으로 분해하여 정규화",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ComplexTableParser",
        "description": "rowspan/colspan이 복합적으로 섞인 표를 구조적으로 파싱하는 하이브리드 파서",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "HeaderDetectionLLM",
        "description": "헤더 행이 애매하거나 여러 줄로 나뉜 표에서 헤더/본문 행을 LLM으로 구분",
        "type": "gpt-4o-mini",
        "latency": "medium",
        "cost": "medium",
    },

    # ---------------- Condition 계열 (가입조건 섹션) ----------------
    {
        "name": "ConditionSimpleTableRule",
        "description": "하나의 조건 표에 보험기간/납입기간/남자나이/여자나이 컬럼이 깔끔히 있을 때 규칙 기반으로 조건 추출",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ConditionSubtitleHybrid",
        "description": "가./나. 소제목별로 다른 조건 표가 붙는 구조에서 소제목-표 매핑을 이용해 조건을 분리 추출",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "ConditionTextOnlyLLM",
        "description": "표 없이 텍스트 문단으로만 가입조건이 설명된 경우 LLM으로 범위/조건을 추출",
        "type": "gpt-4o",
        "latency": "high",
        "cost": "high",
    },
    {
        "name": "ConditionSamplerLongDoc",
        "description": "문서가 너무 길 때 조건과 관련된 구간만 샘플링하여 후속 Condition 툴에 전달",
        "type": "gpt-4o-mini",
        "latency": "medium",
        "cost": "low",
    },
    {
        "name": "ConditionGapFinderLight",
        "description": "추출된 조건에서 보험기간/납입기간/연령 조합이 누락된 구간이 있는지 빠르게 검사",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ConditionRule",
        "description": "조건 섹션이 단일 표 구조일 때 사용하는 기본 규칙 기반 조건 파서",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ConditionLLM",
        "description": "조건 표현이 복잡하거나 텍스트/주석에 많이 숨어 있을 때 LLM으로 보완 추출",
        "type": "gpt-4o",
        "latency": "high",
        "cost": "high",
    },
    {
        "name": "ConditionHybrid",
        "description": "표+텍스트가 혼합된 조건 섹션을 규칙+LLM으로 함께 처리하는 일반 하이브리드 조건 파서",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },

    # ---------------- 소제목-표 매핑 ----------------
    {
        "name": "SubtitleMapper",
        "description": "소제목 바로 아래에 있는 표를 1:1로 매핑하는 기본 규칙 기반 매퍼",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DistantMappingHandler",
        "description": "소제목과 표 사이에 텍스트가 끼어 있거나 여러 표가 있을 때 가장 관련도 높은 표를 선택",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "CloseProximityMapper",
        "description": "소제목과 물리적으로 가장 가까운 표를 빠르게 매핑하는 경량 규칙",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },

    # ---------------- 수식/코드/단위 정규화 ----------------
    {
        "name": "FormulaEvaluator",
        "description": "min[세만기-년납, 90-년납, 80]과 같은 연령/기간 수식을 평가 또는 정규화된 표현으로 변환",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "FormulaExtractorLLM",
        "description": "표/텍스트에 흩어진 수식 패턴을 LLM으로 찾아 일관된 수식 리스트로 정리",
        "type": "gpt-4o-mini",
        "latency": "medium",
        "cost": "low",
    },
    {
        "name": "CodeNormalizer",
        "description": "심사형 코드, 성별 코드 등 이산 코드 값을 사전 정의된 표준 코드로 정규화",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "UnitConverter",
        "description": "기간/연령 단위를 통일(년/세/개월 등)하고 혼합 표기(25/30년 만기 등)를 분해",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },

    # ---------------- 계층 및 조합 생성 ----------------
    {
        "name": "HierarchyExtractor",
        "description": "보종/타입1/타입2/타입3 등 계층 구조를 분석하여 각 레벨의 고유값을 추출",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "DeepHierarchyHandler",
        "description": "3단계 이상 깊은 계층(예: 상품군/라인업/세부타입)을 펼쳐서 조합 가능한 형태로 정리",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "Mapping",
        "description": "내부 스키마(보종명/타입1/타입2/기간/연령 등)에 맞게 필드명을 매핑",
        "type": "hybrid",
        "latency": "medium",
        "cost": "medium",
    },
    {
        "name": "CartesianProduct",
        "description": "보종 × 기간 × 납입기간 × 연령 × 성별 등 가능한 모든 조합을 생성",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "Normalize",
        "description": "중복 조합 제거, 정렬, 필드 이름/값 정규화 등 최종 JSON 구조를 정리",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "ValidationLight",
        "description": "필수 필드 존재 여부, 조합 개수, 기본 범위(연령/기간) 검사 등 경량 검증",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    {
        "name": "FinalWriter",
        "description": "최종 스키마에 맞춰 JSON을 파일로 저장하는 단계",
        "type": "rule",
        "latency": "low",
        "cost": "low",
    },
    # ---------------- 그 외 Tool ----------------
    {
        "name": "EnglishToKorean",
        "description": "영어를 한국어로 번역",
        "type": "gpt-4o-mini",
        "latency": "midium",
        "cost": "midium",
    },
    {
        "name": "ChineseToKorean",
        "description": "중국어를 한국어로 번역",
        "type": "gpt-4o-mini",
        "latency": "midium",
        "cost": "midium",
    },
]

