# 보험 약관 가입 조건 추출 시스템 - 프로젝트 아키텍처

## 📋 프로젝트 개요

### 목적
보험 약관 문서에서 **모든 가입 가능 조건의 경우의 수를 자동으로 추출**하는 Autonomous Multi-Agent 시스템 구축

### 핵심 목표
1. **문서 구조 독립성**: 어떤 형태의 문서라도 처리 가능
   - "보험종목의 명칭"이 Title 1에 있을 수도, Title 2에 있을 수도, "보험종목의 정의"라는 이름일 수도 있음
   - LLM이 의미론적으로 추론하여 자동 탐지
2. **완전한 경우의 수 생성**: 정의 트리 구조와 조건을 매칭하여 모든 조합 도출
3. **자율적 재계획**: 검증 실패 시 Planner가 자동으로 재계획

### 기술 스택
- **Agent 제어**: LangGraph
- **LLM**: OpenAI GPT-4o, GPT-4.1
- **언어**: Python 3.10+

---

## 🔄 시스템 아키텍처

### Multi-Agent 구조

```
┌─────────────────────────────────────────────────────────────┐
│                      PLANNER AGENT                          │
│  - 문서 구조 분석 (LLM 기반)                                  │
│  - 실행 계획 수립 (Tool 선택)                                 │
│  - 재계획 판단 (Validation 피드백 기반)                        │
└────────────┬────────────────────────────────────────────────┘
             │ Plan
             ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTOR AGENTS                          │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Definition       │  │ Condition        │                │
│  │ Extraction       │  │ Parsing          │                │
│  │ Agent            │  │ Agent            │                │
│  └──────────────────┘  └──────────────────┘                │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Semantic         │  │ Schema           │                │
│  │ Matching         │  │ Mapping          │                │
│  │ Agent            │  │ Agent            │                │
│  └──────────────────┘  └──────────────────┘                │
└────────────┬────────────────────────────────────────────────┘
             │ Results
             ▼
┌─────────────────────────────────────────────────────────────┐
│                   VALIDATION AGENT                          │
│  - 결과 완전성 검증                                           │
│  - 스키마 준수 검증                                           │
│  - 오류 탐지 및 피드백 생성                                    │
└────────────┬────────────────────────────────────────────────┘
             │ Feedback
             └──────────► Planner (재계획 트리거)
```

### LangGraph 제어 흐름

```
START
  │
  ▼
┌─────────────┐
│  문서 분석   │ (Planner: 구조 자동 탐지)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  계획 수립   │ (Planner: Tool 선택)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Tool 실행   │ (Executors)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  결과 검증   │ (Validator)
└──────┬──────┘
       │
       ├──► [성공] ──► END
       │
       └──► [실패] ──► 재계획 (루프백)
```

---

## 📊 입출력 명세

### 입력 스키마 (`*_parsed.json`)

**파일 경로**: `data/토이프로젝트_데이터/파싱결과/*.json`

```json
[
  {
    "doc_title": "문서명",
    "elements": [
      {
        "title": "1. 보험종목의 명칭",
        "paragraphs": [
          {
            "type": "table",
            "table": {
              "table_title": "",
              "table_elements": [
                {
                  "명칭": "경증이상치매보장특약(무배당, 해약환급금 미지급형)",
                  "명칭_1": "경증이상치매 보장계약",
                  "보험종목": "해약환급금 미지급형"
                }
              ]
            }
          }
        ]
      },
      {
        "title": "3. 보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
        "paragraphs": [
          {
            "type": "title",
            "content": "가. 해약환급금 미지급형"
          },
          {
            "type": "table",
            "table": {
              "table_title": "가입가능 조건",
              "table_elements": [
                {
                  "유형1": "-",
                  "유형2": "-",
                  "보험기간": "90/100세만기, 종신",
                  "보험료 납입기간": "10/15/20/25/30년납",
                  "남자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
                  "여자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
                  "보험료 납입주기": "월납"
                }
              ]
            }
          }
        ]
      }
    ]
  }
]
```

**주요 특징**:
- `elements`: 문서의 섹션들 (Title 1, Title 3 등)
- `type`: `table`, `text`, `title` 등
- **동적 구조**: Title 번호나 섹션명이 문서마다 다를 수 있음

### 출력 스키마 (`*_가입가능조건.json`)

**파일 경로**: `업무/토이프로젝트_데이터/추출결과/*.json`

```json
[
  {
    "보종명": "경증이상치매보장특약(무배당,해약환급금미지급형)",
    "유형1": "해약환급금미지급형",
    "유형2": "경증이상치매보장계약",
    "보험기간": "90세만기",
    "납입기간": "10년납",
    "주피보험자최소가입연령": 15,
    "주피보험자최대가입연령": 70,
    "주피보험자최소가입연령구분코드": "(2)만연령",
    "주피보험자최대가입연령구분코드": "(1)보험연령",
    "주피보험자가입성별": "(1)남자"
  },
  {
    "보종명": "경증이상치매보장특약(무배당,해약환급금미지급형)",
    "유형1": "해약환급금미지급형",
    "유형2": "경증이상치매보장계약",
    "보험기간": "90세만기",
    "납입기간": "15년납",
    "주피보험자최소가입연령": 15,
    "주피보험자최대가입연령": 70,
    "주피보험자최소가입연령구분코드": "(2)만연령",
    "주피보험자최대가입연령구분코드": "(1)보험연령",
    "주피보험자가입성별": "(1)남자"
  }
  // ... (모든 경우의 수)
]
```

**필드 설명**:
- `보종명`: 보험 종목 전체 명칭
- `유형1`, `유형2`: 계층 구조 (더 많을 수 있음)
- `보험기간`, `납입기간`: 범위에서 분해된 개별 값
- `주피보험자최소/최대가입연령`: 수식 평가 결과
- `주피보험자가입성별`: `(1)남자`, `(2)여자`
- **코드 값**: LLM이 추론 (`(1)보험연령`, `(2)만연령`)

**출력 특징**:
- **Cartesian Product**: 모든 조건의 조합
- **평탄화**: 중첩 구조 → 1차원 배열
- **수식 평가**: `min[세만기 - 년납, 90 - 년납, 70]` → 구체적 숫자

---

## 🧠 핵심 처리 로직

### Phase 1: 보험종목 명칭 정의 파악

**목표**: 상품의 계층 구조 추출 (보종명 → 유형1 → 유형2 → ...)

#### 1.1 동적 섹션 탐지 (LLM 기반)

```python
# Planner Agent가 문서 전체를 스캔하여 정의 섹션 찾기
prompt = """
다음 문서에서 "보험종목의 명칭" 또는 "보험종목의 정의"에 해당하는 섹션을 찾아주세요.
섹션 제목은 다음과 같을 수 있습니다:
- "1. 보험종목의 명칭"
- "2. 보험상품의 정의"
- "보험종목"
등등

문서: {document_elements}
"""
```

**출력**:
```json
{
  "section_title": "1. 보험종목의 명칭",
  "section_index": 0
}
```

#### 1.2 정의 트리 구조 추출

**입력**:
```json
{
  "table_elements": [
    {
      "명칭": "경증이상치매보장특약(무배당, 해약환급금 미지급형)",
      "명칭_1": "경증이상치매 보장계약",
      "보험종목": "해약환급금 미지급형"
    }
  ]
}
```

**Executor Agent 처리**:
1. rowspan/colspan 분석하여 계층 구조 파악
2. 트리 구조 생성:
   ```
   경증이상치매보장특약(무배당, 해약환급금 미지급형)
   ├── 해약환급금 미지급형 (유형1)
   │   └── 경증이상치매 보장계약 (유형2)
   └── 일반형 (유형1)
       └── 경증이상치매 보장계약 (유형2)
   ```

**출력**:
```json
{
  "보종명": "경증이상치매보장특약(무배당,해약환급금미지급형)",
  "hierarchy": [
    {
      "유형1": "해약환급금미지급형",
      "유형2": ["경증이상치매보장계약"]
    },
    {
      "유형1": "일반형",
      "유형2": ["경증이상치매보장계약"]
    }
  ]
}
```

### Phase 2: 가입 가능 조건 파악

**목표**: 각 유형별 가입 조건 (보험기간, 납입기간, 나이) 추출

#### 2.1 조건 섹션 탐지 (LLM 기반)

```python
prompt = """
다음 문서에서 "가입 가능 조건" 또는 "피보험자 가입나이"에 해당하는 섹션을 찾아주세요.
섹션 제목은 다음과 같을 수 있습니다:
- "3. 보험기간, 보험료 납입기간..."
- "가입 조건"
등등

문서: {document_elements}
"""
```

#### 2.2 소제목 → 유형 매칭

**패턴 인식**:
```
type=title: "가. 해약환급금 미지급형"  ──┐
                                      ├─> 매칭
type=table: 가입가능 조건 표            ──┘
```

**Executor Agent 로직**:
1. `type=title` 발견 시 바로 다음 `type=table`을 연결
2. 소제목 텍스트를 Phase 1의 유형명과 매칭:
   - "가. 해약환급금 미지급형" → `유형1 = "해약환급금미지급형"`
   - "나. 일반형" → `유형1 = "일반형"`

#### 2.3 조건 파싱 및 범위 분해

**입력**:
```json
{
  "보험기간": "90/100세만기, 종신",
  "보험료 납입기간": "10/15/20/25/30년납",
  "남자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세"
}
```

**Executor Agent 처리**:
1. **범위 분해**:
   - `"90/100세만기, 종신"` → `["90세만기", "100세만기", "종신"]`
   - `"10/15/20/25/30년납"` → `["10년납", "15년납", "20년납", "25년납", "30년납"]`

2. **수식 평가** (조합별로):
   ```python
   # 예: 보험기간=90세만기, 납입기간=10년납
   세만기 = 90
   년납 = 10
   최대나이 = min(90 - 10, 90 - 10, 70) = 70
   ```

3. **성별 분리**:
   - `"남자나이"` → `주피보험자가입성별 = "(1)남자"`
   - `"여자나이"` → `주피보험자가입성별 = "(2)여자"`

**출력**:
```json
{
  "유형1": "해약환급금미지급형",
  "conditions": [
    {
      "보험기간": "90세만기",
      "납입기간": "10년납",
      "최소나이": 15,
      "최대나이": 70,
      "성별": "(1)남자"
    },
    {
      "보험기간": "90세만기",
      "납입기간": "15년납",
      "최소나이": 15,
      "최대나이": 70,
      "성별": "(1)남자"
    }
    // ... (모든 조합)
  ]
}
```

### Phase 3: 정의 트리 ↔ 조건 의미 매칭

**목표**: Phase 1의 계층 구조와 Phase 2의 조건을 의미론적으로 매칭

#### 3.1 유형 매칭

**Phase 1 출력**:
```json
{
  "hierarchy": [
    {"유형1": "해약환급금미지급형", "유형2": ["경증이상치매보장계약"]}
  ]
}
```

**Phase 2 출력**:
```json
{
  "유형1": "해약환급금미지급형",
  "conditions": [...]
}
```

**매칭 로직**:
```python
# LLM 기반 fuzzy matching
def match_types(definition_type, condition_type):
    # "해약환급금 미지급형" vs "해약환급금미지급형" (공백 차이)
    # LLM이 의미론적으로 동일하다고 판단
    return llm.call(f"Are these the same? {definition_type} vs {condition_type}")
```

#### 3.2 계층 구조 전파

**조건에 유형2 정보 추가**:
```json
{
  "보종명": "경증이상치매보장특약(무배당,해약환급금미지급형)",
  "유형1": "해약환급금미지급형",
  "유형2": "경증이상치매보장계약",  // ← Phase 1에서 전파
  "보험기간": "90세만기",
  "납입기간": "10년납",
  ...
}
```

### Phase 4: Cartesian Product로 경우의 수 생성

**목표**: 모든 조건 조합의 완전한 리스트 생성

#### 4.1 조합 생성

```python
from itertools import product

# 예시 데이터
유형1_list = ["해약환급금미지급형", "일반형"]
유형2_list = ["경증이상치매보장계약"]
보험기간_list = ["90세만기", "100세만기", "종신"]
납입기간_list = ["10년납", "15년납", "20년납", "25년납", "30년납"]
성별_list = ["(1)남자", "(2)여자"]

# Cartesian Product
combinations = list(product(
    유형1_list,
    유형2_list,
    보험기간_list,
    납입기간_list,
    성별_list
))

# 총 경우의 수: 2 × 1 × 3 × 5 × 2 = 60
```

#### 4.2 수식 평가 (각 조합마다)

```python
for combo in combinations:
    유형1, 유형2, 보험기간, 납입기간, 성별 = combo

    # 수식 평가
    세만기 = extract_age(보험기간)  # "90세만기" → 90
    년납 = extract_years(납입기간)  # "10년납" → 10

    최대나이 = min(세만기 - 년납, 90 - 년납, 70)

    # 레코드 생성
    record = {
        "보종명": "...",
        "유형1": 유형1,
        "유형2": 유형2,
        "보험기간": 보험기간,
        "납입기간": 납입기간,
        "주피보험자최소가입연령": 15,
        "주피보험자최대가입연령": 최대나이,
        "주피보험자가입성별": 성별,
        ...
    }
```

#### 4.3 스키마 매핑

**코드 추론 (LLM 기반)**:
```python
# 나이 구분 코드 추론
if "만" in 나이_표현:
    코드 = "(2)만연령"
else:
    코드 = "(1)보험연령"
```

**최종 출력**:
```json
[
  {
    "보종명": "경증이상치매보장특약(무배당,해약환급금미지급형)",
    "유형1": "해약환급금미지급형",
    "유형2": "경증이상치매보장계약",
    "보험기간": "90세만기",
    "납입기간": "10년납",
    "주피보험자최소가입연령": 15,
    "주피보험자최대가입연령": 70,
    "주피보험자최소가입연령구분코드": "(2)만연령",
    "주피보험자최대가입연령구분코드": "(1)보험연령",
    "주피보험자가입성별": "(1)남자"
  }
  // ... (1,440개 레코드)
]
```

---

## 🔍 일반화 전략

### 문제: 문서마다 다른 구조

**예시**:
- 문서 A: "1. 보험종목의 명칭"
- 문서 B: "2. 보험상품의 정의"
- 문서 C: Title 없이 바로 표

### 해결책: LLM 기반 동적 탐지

#### 전략 1: 의미론적 섹션 탐지

```python
class DocumentStructureDiscovery:
    def find_definition_section(self, document):
        """
        LLM이 문서를 읽고 "정의" 섹션을 찾음
        """
        prompt = f"""
        다음 문서에서 보험 상품의 계층 구조(보종명, 유형 등)를
        정의하는 섹션을 찾아주세요.

        섹션 제목의 예:
        - "보험종목의 명칭"
        - "상품 구조"
        - "보험상품의 정의"

        문서:
        {document}

        JSON으로 답변:
        {{
          "section_title": "찾은 섹션 제목",
          "section_index": 인덱스,
          "confidence": 0.0~1.0
        }}
        """
        return llm.call(prompt)

    def find_condition_section(self, document):
        """
        LLM이 "가입 조건" 섹션을 찾음
        """
        # 유사한 로직
        pass
```

#### 전략 2: Fallback 체인

```python
def extract_definitions(document):
    # 1차 시도: LLM 기반 탐지
    try:
        section = discovery.find_definition_section(document)
        return parse_definition_table(section)
    except:
        pass

    # 2차 시도: 패턴 매칭
    try:
        section = regex_find(document, r"보험종목|상품.*정의")
        return parse_definition_table(section)
    except:
        pass

    # 3차 시도: 모든 표 스캔
    all_tables = extract_all_tables(document)
    for table in all_tables:
        if looks_like_definition_table(table):  # LLM 판단
            return parse_definition_table(table)

    # 실패
    raise NoDefinitionFoundError()
```

#### 전략 3: 소제목 → 표 자동 매핑

```python
def map_subtitles_to_tables(paragraphs):
    """
    type=title 뒤에 type=table이 오는 패턴 자동 인식
    """
    mappings = []

    for i, para in enumerate(paragraphs):
        if para["type"] == "title":
            # 다음 요소가 표인지 확인
            if i+1 < len(paragraphs) and paragraphs[i+1]["type"] == "table":
                mappings.append({
                    "subtitle": para["content"],
                    "table": paragraphs[i+1]
                })

    return mappings
```

#### 전략 4: 유형 fuzzy matching

```python
def match_type_names(name1, name2):
    """
    LLM이 의미론적으로 동일한지 판단
    """
    # 예:
    # "해약환급금 미지급형" vs "해약환급금미지급형" → True
    # "일반형" vs "무배당형" → False

    prompt = f"""
    다음 두 보험 유형명이 동일한 상품을 지칭하나요?

    이름1: {name1}
    이름2: {name2}

    JSON으로 답변:
    {{
      "is_same": true/false,
      "confidence": 0.0~1.0,
      "reason": "판단 이유"
    }}
    """
    return llm.call(prompt)
```

### 다양한 문서 패턴 대응

| 패턴 | 대응 전략 |
|------|-----------|
| Title 번호 다름 | LLM 의미론적 탐지 |
| Title 없음 | 모든 표 스캔 + LLM 판단 |
| 표 구조 다름 (rowspan/colspan) | LLM이 계층 구조 직접 추출 |
| 소제목 위치 다름 | 거리 기반 매칭 (가장 가까운 표) |
| 유형명 공백/기호 차이 | Fuzzy matching + LLM 검증 |
| 수식 표현 다름 | LLM이 자연어로 수식 이해 |

---

## 🕸️ LangGraph 구현 가이드

### State Schema 정의

```python
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph import StateGraph, END
import operator

class AgentState(TypedDict):
    # 입력
    document: dict
    file_path: str

    # Phase 1: 정의 추출
    definition_section: Optional[dict]
    product_hierarchy: Optional[dict]

    # Phase 2: 조건 파싱
    condition_section: Optional[dict]
    parsed_conditions: Optional[List[dict]]

    # Phase 3: 매칭
    matched_data: Optional[List[dict]]

    # Phase 4: 최종 출력
    final_output: Optional[List[dict]]

    # 제어 플로우
    plan: Optional[dict]
    validation_result: Optional[dict]
    retry_count: int
    errors: Annotated[List[str], operator.add]
```

### Node 정의

```python
def planner_node(state: AgentState) -> AgentState:
    """
    Planner Agent: 문서 분석 및 계획 수립
    """
    document = state["document"]

    # 문서 구조 자동 탐지
    structure_analysis = analyze_structure(document)

    # Tool 선택 계획 수립
    plan = create_execution_plan(structure_analysis)

    return {
        **state,
        "plan": plan
    }

def extract_definitions_node(state: AgentState) -> AgentState:
    """
    Executor: 정의 추출
    """
    document = state["document"]
    plan = state["plan"]

    # LLM 기반 섹션 탐지
    section = find_definition_section(document)

    # 계층 구조 추출
    hierarchy = extract_product_hierarchy(section)

    return {
        **state,
        "definition_section": section,
        "product_hierarchy": hierarchy
    }

def parse_conditions_node(state: AgentState) -> AgentState:
    """
    Executor: 조건 파싱
    """
    document = state["document"]

    # 조건 섹션 탐지
    section = find_condition_section(document)

    # 소제목 → 표 매핑
    mappings = map_subtitles_to_tables(section["paragraphs"])

    # 조건 파싱 및 범위 분해
    conditions = []
    for mapping in mappings:
        parsed = parse_condition_table(mapping["table"])
        conditions.append({
            "type": extract_type_from_subtitle(mapping["subtitle"]),
            "conditions": parsed
        })

    return {
        **state,
        "condition_section": section,
        "parsed_conditions": conditions
    }

def match_and_generate_node(state: AgentState) -> AgentState:
    """
    Executor: 매칭 및 경우의 수 생성
    """
    hierarchy = state["product_hierarchy"]
    conditions = state["parsed_conditions"]

    # 유형 매칭
    matched = match_types(hierarchy, conditions)

    # Cartesian Product
    combinations = generate_combinations(matched)

    # 스키마 매핑
    final_output = [
        map_to_schema(combo) for combo in combinations
    ]

    return {
        **state,
        "matched_data": matched,
        "final_output": final_output
    }

def validation_node(state: AgentState) -> AgentState:
    """
    Validation Agent: 결과 검증
    """
    output = state["final_output"]

    # 검증 로직
    validation_result = {
        "is_valid": True,
        "errors": [],
        "warnings": []
    }

    # 1. 필수 필드 존재 확인
    required_fields = ["보종명", "유형1", "보험기간", "납입기간"]
    for record in output:
        missing = [f for f in required_fields if f not in record]
        if missing:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Missing fields: {missing}")

    # 2. 경우의 수 완전성 확인
    expected_count = calculate_expected_combinations(state["product_hierarchy"])
    actual_count = len(output)
    if actual_count != expected_count:
        validation_result["warnings"].append(
            f"Expected {expected_count} combinations, got {actual_count}"
        )

    # 3. 수식 평가 검증
    for record in output:
        if record["주피보험자최대가입연령"] < record["주피보험자최소가입연령"]:
            validation_result["is_valid"] = False
            validation_result["errors"].append("Invalid age range")

    return {
        **state,
        "validation_result": validation_result
    }
```

### Edge 및 조건부 분기

```python
def should_replan(state: AgentState) -> str:
    """
    검증 결과에 따라 재계획 여부 결정
    """
    validation = state["validation_result"]
    retry_count = state.get("retry_count", 0)

    if validation["is_valid"]:
        return "end"
    elif retry_count >= 3:
        return "end"  # 최대 재시도 횟수 초과
    else:
        return "replan"

# Graph 구성
workflow = StateGraph(AgentState)

# Node 추가
workflow.add_node("planner", planner_node)
workflow.add_node("extract_definitions", extract_definitions_node)
workflow.add_node("parse_conditions", parse_conditions_node)
workflow.add_node("match_and_generate", match_and_generate_node)
workflow.add_node("validation", validation_node)

# Edge 추가
workflow.set_entry_point("planner")
workflow.add_edge("planner", "extract_definitions")
workflow.add_edge("extract_definitions", "parse_conditions")
workflow.add_edge("parse_conditions", "match_and_generate")
workflow.add_edge("match_and_generate", "validation")

# 조건부 Edge
workflow.add_conditional_edges(
    "validation",
    should_replan,
    {
        "end": END,
        "replan": "planner"  # 루프백
    }
)

# 컴파일
app = workflow.compile()
```

### 재계획 (Replanning) 로직

```python
def planner_node_with_feedback(state: AgentState) -> AgentState:
    """
    검증 피드백을 반영한 재계획
    """
    document = state["document"]
    validation = state.get("validation_result")

    if validation and not validation["is_valid"]:
        # 실패 원인 분석
        errors = validation["errors"]

        # 재계획 프롬프트
        prompt = f"""
        이전 시도가 실패했습니다.

        오류:
        {errors}

        문서:
        {document}

        다른 접근 방법을 제안해주세요.
        예:
        - 다른 섹션 탐색
        - 다른 Tool 조합 사용
        - 더 관대한 매칭 기준 적용
        """

        new_plan = llm.call(prompt)
    else:
        # 첫 시도
        new_plan = create_execution_plan(document)

    return {
        **state,
        "plan": new_plan,
        "retry_count": state.get("retry_count", 0) + 1
    }
```

### 실행 예시

```python
# 초기 상태
initial_state = {
    "document": load_json("data/토이프로젝트_데이터/파싱결과/경증이상치매보장특약_parsed.json"),
    "file_path": "...",
    "retry_count": 0,
    "errors": []
}

# 실행
result = app.invoke(initial_state)

# 결과 저장
save_json(
    result["final_output"],
    "업무/토이프로젝트_데이터/추출결과/경증이상치매보장특약_가입가능조건.json"
)
```

---

## 📁 프로젝트 구조

```
Project/Toy/
├── main.py                          # LangGraph 진입점
├── agents/
│   ├── planner_agent.py             # Planner Agent
│   ├── executor_agents.py           # Executor Agents
│   └── validation_agent.py          # Validation Agent
├── tools/
│   ├── definition_extractor.py      # 정의 추출 Tool
│   ├── condition_parser.py          # 조건 파싱 Tool
│   ├── semantic_matcher.py          # 의미론적 매칭 Tool
│   └── schema_mapper.py             # 스키마 매핑 Tool
├── utils/
│   ├── document_discovery.py        # 동적 구조 탐지
│   ├── llm_client.py                # OpenAI API 래퍼
│   └── evaluation.py                # 수식 평가
├── data/
│   └── 토이프로젝트_데이터/
│       ├── 원본문서/                # .hwp
│       ├── 파싱결과/                # *_parsed.json (입력)
│       └── 추출결과/                # *_가입가능조건.json (출력)
├── tests/
│   ├── test_definition_extraction.py
│   ├── test_condition_parsing.py
│   └── test_end_to_end.py
├── .env                             # OPENAI_API_KEY
├── requirements.txt
├── AGENTS.md                        # 코딩 가이드라인
└── PROJECT_ARCHITECTURE.md          # 이 문서
```

---

## ✅ 현재 구현 상태

### 완료된 부분 ✓

**없음** - 프로젝트는 현재 기획 단계이며, 실제 구현된 코드는 없습니다.

### 실험/프로토타입 파일 (참고용, 미완성)

다음 파일들은 구조 파악 및 실험용으로 끄적여본 수준입니다:

1. **`Title_1.py`** - Title 1 섹션 추출 실험
   - 상태: 테스트 코드 수준
   - 용도: 정의 섹션이 어떻게 생겼는지 파악

2. **`Title_3.py`** - Title 3 섹션 필터링 실험
   - 상태: 테스트 코드 수준
   - 용도: 조건 섹션 구조 파악

3. **`planner.py`** - Planner 아이디어 스케치
   - 상태: 컨셉 스케치
   - 용도: Tool 목록 정리

4. **`planner2.py`** - 개선된 Planner 컨셉
   - 상태: 설계 스케치
   - 용도: 4단계 파이프라인 아이디어

5. **`structure_discovery_test.py`** - 문서 구조 탐지 테스트
   - 상태: 실험 코드
   - 용도: LLM으로 섹션 찾기 테스트

6. **데이터 샘플**
   - 5개 약관 문서의 입출력 샘플 파일은 준비됨

**⚠️ 주의**: 위 파일들은 실제 동작하는 시스템이 아니며, 단순 실험/컨셉 코드입니다.

### 구현 필요 사항 ❌

1. **LangGraph 통합**
   - State Schema 정의
   - Node 및 Edge 구성
   - 조건부 분기 및 루프 설정

2. **Executor Agents 실제 구현**
   - 현재 Mock 상태
   - Tool 실행 로직 구현 필요
   - `Title_1.py`, `Title_3.py`를 Tool로 래핑

3. **Validation Agent 강화**
   - 현재 간단한 성공 응답만 반환
   - 완전성 검증 로직 추가
   - 스키마 준수 검증

4. **재계획 로직**
   - 검증 실패 시 Planner로 피드백
   - 대안 전략 선택 로직

5. **Semantic Matching Tool**
   - Phase 3의 유형 매칭 구현
   - Fuzzy matching + LLM 검증

6. **Cartesian Product Generator**
   - Phase 4의 조합 생성 로직
   - 수식 평가 엔진

7. **Schema Mapper**
   - 최종 출력 스키마 변환
   - 코드 값 추론 (LLM 기반)

8. **통합 테스트**
   - 5개 샘플 파일 End-to-End 테스트
   - 회귀 테스트 자동화

---

## 🎯 구현 우선순위

### Phase 1: 핵심 파이프라인 구축 (1-2주)
1. LangGraph State Schema 및 기본 Graph 구성
2. `Title_1.py`, `Title_3.py`를 Tool로 통합
3. 간단한 Executor Agent 구현 (정의 추출, 조건 파싱)
4. End-to-End 테스트 (1개 샘플 파일)

### Phase 2: 매칭 및 생성 로직 (1주)
5. Semantic Matching Tool 구현
6. Cartesian Product Generator 구현
7. 수식 평가 엔진 구현
8. Schema Mapper 구현

### Phase 3: 검증 및 재계획 (1주)
9. Validation Agent 강화
10. 재계획 로직 구현
11. 조건부 분기 설정
12. 최대 재시도 횟수 제한

### Phase 4: 일반화 및 안정화 (1-2주)
13. 다양한 문서 패턴 테스트
14. Fallback 메커니즘 구현
15. 5개 샘플 파일 모두 통과
16. 에러 핸들링 강화

---

## 🛠️ 기술적 고려사항

### LLM 사용 최적화

**비용 절감 전략**:
1. **Hybrid 접근**: 규칙 기반 + LLM
   - 간단한 패턴은 정규식으로
   - 복잡한 판단만 LLM 사용

2. **모델 선택**:
   - 단순 작업: GPT-4o-mini
   - 복잡한 추론: GPT-4o, GPT-4.1

3. **캐싱**:
   - 동일 문서 재처리 시 캐시 활용
   - LangGraph의 checkpointing 기능 사용

### 에러 핸들링

```python
class ToolExecutionError(Exception):
    """Tool 실행 실패"""
    pass

class ValidationError(Exception):
    """검증 실패"""
    pass

def safe_tool_execution(tool, input_data, max_retries=3):
    for attempt in range(max_retries):
        try:
            return tool.execute(input_data)
        except Exception as e:
            if attempt == max_retries - 1:
                raise ToolExecutionError(f"Tool failed after {max_retries} retries: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff
```

### 성능 모니터링

```python
import time
from functools import wraps

def measure_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"{func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper

@measure_time
def extract_definitions_node(state):
    # ...
    pass
```

---

## 📚 참고 자료

### LangGraph
- [공식 문서](https://langchain-ai.github.io/langgraph/)
- [Multi-Agent 예제](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/)

### 유사 프로젝트
- BabyAGI: Autonomous Task Management
- AutoGPT: Goal-oriented Agent

### OpenAI API
- [GPT-4 Turbo 문서](https://platform.openai.com/docs/models/gpt-4-and-gpt-4-turbo)
- [Function Calling](https://platform.openai.com/docs/guides/function-calling)

---

## 🔄 버전 히스토리

- **v0.1** (2024-01-XX): 초기 프로젝트 설계
- **v0.2** (2024-01-XX): Title_1, Title_3 Agent 구현
- **v0.3** (2024-01-XX): Planner 설계
- **v1.0** (TBD): LangGraph 기반 Full Pipeline

---

## 📝 TODO

- [ ] LangGraph State Schema 정의
- [ ] Node 구현 (planner, executors, validator)
- [ ] Tool Registry 구축
- [ ] Semantic Matching Tool 구현
- [ ] Cartesian Product Generator 구현
- [ ] Schema Mapper 구현
- [ ] 재계획 로직 구현
- [ ] End-to-End 테스트
- [ ] 5개 샘플 파일 검증
- [ ] 문서화 완료

---

**문서 작성일**: 2025-01-XX
**작성자**: Project Team
**버전**: 1.0
