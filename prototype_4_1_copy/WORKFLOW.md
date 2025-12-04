# Prototype 4 - V2 Workflow 상세 가이드

## 📊 전체 파이프라인 개요

```
[문서 입력]
    ↓
[1. DocumentAccessor] - 섹션 추출
    ↓
[2. LLMPlanner] - 실행 계획 수립
    ↓
[3. Task Execution Loop]
    ├─ Task 1: SectionClassifierTool (섹션 분류)
    ├─ Task 2: DefinitionExtractToolV2 (정의 추출)
    └─ Task 3: RuleCartesianTool (조합 생성)
    ↓
[4. LLMValidator] - 각 Task 결과 검증
    ↓
[5. 최종 결과 출력]
```

---

## 🔧 모듈별 상세 설명

### 1. DocumentAccessor (섹션 추출기)

**위치:** `core/document_accessor.py`

**역할:**
- JSON 문서를 파싱하여 섹션 리스트로 변환
- 각 섹션의 content_summary 생성 (table/text 여부 등)

**입력:**
```python
doc = {
    "elements": [
        {
            "title": "1. 보험종목의 명칭",
            "paragraphs": [
                {"type": "table", "content": "<table>..."},
                {"type": "text", "content": "주석 내용"}
            ]
        },
        ...
    ]
}
```

**출력:**
```python
sections = [
    {
        "index": 0,
        "title": "1. 보험종목의 명칭",
        "content": [
            {
                "type": "table",
                "table": {"table_elements": [...]},
                "content": "<table>..."
            },
            {
                "type": "text",
                "content": "주석 내용",
                "table": {"table_elements": []}
            }
        ],
        "content_summary": {
            "has_table": True,
            "has_text": True,
            "primary_type": "mixed"
        }
    },
    ...
]
```

**주요 메서드:**
- `get_sections()`: 섹션 리스트 반환
- `get_summary()`: 문서 전체 요약 (섹션별 형식 분포 등)

---

### 2. LLMPlanner (계획 수립기)

**위치:** `core/llm_planner.py`

**역할:**
- 문서 특성을 분석하여 적절한 도구 선택
- Task 실행 순서와 파라미터 의존성 정의

**입력:**
```python
# DocumentAccessor의 summary
doc_summary = {
    "sections_by_format": {
        "table_only": [0, 3],
        "text_only": [1, 2],
        "mixed": []
    }
}

# 사용자 요청
task_description = "보험 상품 정의 조합을 추출하세요"
```

**출력:**
```python
plan = {
    "tasks": [
        {
            "task_id": 1,
            "tool_name": "section_classifier",
            "description": "모든 섹션을 4가지 카테고리로 분류",
            "parameters": {
                "sections": "$sections"
            },
            "depends_on": None
        },
        {
            "task_id": 2,
            "tool_name": "definition_extract_v2",
            "description": "분류된 정의 섹션에서 데이터 추출",
            "parameters": {
                "sections": "$sections",
                "core_indices": "{{task1.definition_core}}",
                "annotation_indices": "{{task1.definition_annotation}}"
            },
            "depends_on": 1
        },
        {
            "task_id": 3,
            "tool_name": "rule_cartesian",
            "description": "정의 조합 생성",
            "parameters": {
                "header": "{{task2.header}}",
                "data": "{{task2.data}}"
            },
            "depends_on": 2
        }
    ]
}
```

**도구 선택 전략:**
- V2 workflow 우선 (section_classifier + definition_extract_v2)
- Table-heavy 문서 → rule_cartesian 우선
- Text-only 문서 → llm_cartesian 고려

---

### 3. Task Execution (도구 실행)

#### 3-1. SectionClassifierTool (Task 1)

**위치:** `tools/hybrid_tools.py` (class SectionClassifierTool)

**역할:**
- 모든 섹션을 의미 기반으로 4가지 카테고리로 분류
- LLM 기반 semantic classification (100% recall 보장)

**입력:**
```python
params = {
    "sections": [
        {
            "index": 0,
            "title": "1. 보험종목의 명칭",
            "content_summary": {"has_table": True, ...}
        },
        {
            "index": 1,
            "title": "2. 특약의 부가대상",
            "content_summary": {"has_text": True, ...}
        },
        ...
    ]
}
```

**처리 과정:**
1. 각 섹션의 title + content_preview 요약 생성
2. LLM에게 전체 섹션 요약 전달
3. Multi-class classification 수행

**LLM 프롬프트:**
```
다음 섹션들을 4가지 카테고리로 분류하세요:
- definition_core: 핵심 정의 테이블 (보험종목, 명칭 등)
- definition_annotation: 정의 주석/설명
- condition: 계약조건 섹션
- other: 기타

섹션 요약:
[{"index": 0, "title": "...", "has_table": true, ...}, ...]

JSON 형식으로 반환:
{
  "definition_core": [0],
  "definition_annotation": [1],
  "condition": [],
  "other": [2, 3]
}
```

**출력:**
```python
{
    "definition_core": [0],
    "definition_annotation": [],
    "condition": [1],
    "other": [2, 3, 4]
}
```

**현재 이슈:**
- ⚠️ 조건 섹션을 정의로 오분류하는 경우 있음
- ⚠️ 섹션 내부의 text 요소는 분류 불가 (섹션 레벨만)

---

#### 3-2. DefinitionExtractToolV2 (Task 2)

**위치:** `tools/hybrid_tools.py` (class DefinitionExtractToolV2)

**역할:**
- 분류된 core 섹션에서 정의 테이블 추출
- annotation 섹션과 병합 (현재 미구현)

**입력:**
```python
params = {
    "sections": [...],  # 전체 섹션 리스트
    "core_indices": [0],  # task1 결과
    "annotation_indices": []  # task1 결과
}
```

**처리 과정:**
1. `_extract_from_cores()`: core 섹션에서 base table 추출
   - 섹션의 content를 순회
   - **table 요소만** 찾아서 RuleExtractTool로 파싱
   - ⚠️ **현재: text 요소는 무시됨**

2. `_merge_with_annotations()`: annotation 병합 (선택적)
   - annotation_indices가 비어있지 않으면 실행
   - ⚠️ **현재: 미구현 상태**

**출력:**
```python
{
    "header": ["명칭", "보험종목", "보험종목_1", "보장계약"],
    "data": [
        [
            "통합암(전이포함)진단특약TC\n(무배당, 해약환급금 미지급형)",
            "해약환급금\n미지급형",
            "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형",
            "두경부암(전이포함),\n위암(전이포함),\n..."
        ],
        [...]
    ],
    "extraction_method": "v2_classifier_based"
}
```

**현재 이슈:**
- ⚠️ 섹션 내부의 text 요소 ("315형→555형 변경")가 수집 안됨
- ⚠️ annotation 병합 로직 미구현

---

#### 3-3. RuleCartesianTool / LLMCartesianTool (Task 3)

**위치:** `tools/hybrid_tools.py`

**역할:**
- header/data에서 Cartesian product 생성
- 모든 가능한 정의 조합 생성

**입력:**
```python
params = {
    "header": ["명칭", "보험종목", "보험종목_1", "보장계약"],
    "data": [
        [
            "통합암특약(무배당, 미지급형)",
            "해약환급금미지급형",
            "간편심사(315)형/간편심사(335)형/일반심사형",
            "두경부암,위암,남성/여성생식기암"
        ]
    ]
}
```

**RuleCartesianTool 처리:**
1. 컬럼별 주 구분자 파악 (⚠️ **미구현 - 현재는 둘 다 분리**)
   - 각 컬럼의 `/`, `,` 빈도 계산
   - 더 많은 구분자를 primary로 선택
2. 주 구분자로 값 분리
3. `itertools.product`로 조합 생성

**LLMCartesianTool 처리 (2단계):**
1. **Step 1 (LLM)**: 값 분리만 담당
   - 컬럼별 주 구분자 파악 규칙 적용
   - 문맥 기반으로 정확히 분리
   ```python
   # LLM 출력
   {
       "parsed_rows": [
           [
               ["통합암특약(무배당, 미지급형)"],
               ["해약환급금미지급형"],
               ["간편심사(315)형", "간편심사(335)형", "일반심사형"],
               ["두경부암", "위암", "남성/여성생식기암"]
           ]
       ]
   }
   ```

2. **Step 2 (Python)**: `itertools.product`로 조합
   ```python
   for combo in product(*row):
       definition = {
           "보종명": combo[0],
           "유형1": combo[1],
           "유형2": combo[2],
           "유형3": combo[3]
       }
   ```

**출력:**
```python
{
    "definitions": [
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "두경부암"
        },
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "위암"
        },
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "남성/여성생식기암"  # 분리 안함 (주 구분자가 ,)
        },
        ...
    ],
    "total_count": 12
}
```

---

### 4. LLMValidator (검증기)

**위치:** `core/llm_validator.py`

**역할:**
- 각 Task 결과를 검증
- 실패 시 replan instruction 제공

#### 4-1. validate_classify (Task 1 검증)

**입력:**
```python
task_output = {
    "definition_core": [0],
    "definition_annotation": [],
    "condition": [1],
    "other": [2, 3]
}
```

**검증 로직:**
- Shape-level 검사만 수행 (LLM 호출 X)
- 필수 키 존재 확인
- 리스트 타입 확인

**출력:**
```python
{
    "is_valid": True,
    "confidence": 1.0,
    "errors": [],
    "suggestions": []
}
```

---

#### 4-2. validate_extract (Task 2 검증)

**입력:**
```python
task_output = {
    "header": ["명칭", "보험종목", ...],
    "data": [[...], ...]
}

context = {
    "classification": {
        "definition_core": [0],
        ...
    }
}
```

**검증 로직:**
- V2 결과는 완화된 검증 (header/data 존재만 확인)
- 계층 깊이 동적 파악 (3단계 강제 X)

**출력:**
```python
{
    "is_valid": True,
    "confidence": 0.9,
    "errors": [],
    "suggestions": []
}
```

---

#### 4-3. validate_transform (Task 3 검증)

**입력:**
```python
task_output = {
    "definitions": [...],
    "total_count": 88
}

context = {
    "extracted_data": {
        "header": [...],
        "data": [...]
    }
}
```

**검증 로직:**
1. 원본 데이터에서 기대 조합 수 계산
2. LLM으로 결과 검증
   - 컬럼별 주 구분자 패턴 분석
   - 중복/누락 확인

**LLM 프롬프트 (핵심 규칙):**
```
**슬래시(/)나 콤마(,) 구분 판단 (매우 중요!)**:
원본 Data의 각 컬럼을 관찰하여:
- 컬럼 전체에서 `/`와 `,` 중 어느 것이 **더 자주** 등장하는지 확인
- **더 자주 등장하는 구분자**가 실제 구분자 (primary delimiter)
- **덜 등장하는 구분자**는 내용의 일부로 취급

예시 1: "두경부암,위암,남성/여성생식기암"
→ `,`가 여러 번 등장, `/`는 한 번
→ 주 구분자: `,`
→ "남성/여성생식기암"을 분리하지 않은 것이 **정답**
```

**출력:**
```python
{
    "is_valid": True,
    "confidence": 0.95,
    "errors": [],
    "suggestions": [],
    "actual_count": 88
}
```

---

## 🔄 전체 실행 흐름 예시

### 입력 문서
```json
{
  "elements": [
    {
      "title": "1. 보험종목의 명칭",
      "paragraphs": [
        {
          "type": "table",
          "table": {
            "table_elements": [
              {
                "명칭": "통합암특약(무배당, 미지급형)",
                "보험종목": "해약환급금미지급형",
                "보험종목_1": "간편심사(315)형/간편심사(335)형",
                "보장계약": "두경부암,위암,남성/여성생식기암"
              }
            ]
          }
        },
        {
          "type": "text",
          "content": "간편심사(315)형은 간편심사(555)형으로 변경되었다"
        }
      ]
    }
  ]
}
```

### Step 1: DocumentAccessor
```python
sections = [
    {
        "index": 0,
        "title": "1. 보험종목의 명칭",
        "content": [
            {"type": "table", "table": {...}},
            {"type": "text", "content": "315형→555형"}
        ],
        "content_summary": {"has_table": True, "has_text": True}
    }
]
```

### Step 2: LLMPlanner
```python
plan = {
    "tasks": [
        {"task_id": 1, "tool_name": "section_classifier", ...},
        {"task_id": 2, "tool_name": "definition_extract_v2", ...},
        {"task_id": 3, "tool_name": "rule_cartesian", ...}
    ]
}
```

### Step 3: Task 1 - SectionClassifier
```python
# Input: sections
# Output:
{
    "definition_core": [0],
    "definition_annotation": [],
    "condition": [],
    "other": []
}
```

### Step 4: Task 2 - DefinitionExtractToolV2
```python
# Input:
#   sections = [...]
#   core_indices = [0]
#   annotation_indices = []

# Processing:
#   1. sections[0] 접근
#   2. content[0] (table) 추출 → RuleExtractTool
#   3. content[1] (text) **무시됨** ⚠️

# Output:
{
    "header": ["명칭", "보험종목", "보험종목_1", "보장계약"],
    "data": [
        [
            "통합암특약(무배당, 미지급형)",
            "해약환급금미지급형",
            "간편심사(315)형/간편심사(335)형",
            "두경부암,위암,남성/여성생식기암"
        ]
    ]
}
```

### Step 5: Task 3 - RuleCartesianTool (또는 LLMCartesian)
```python
# Input: header, data

# RuleCartesian (현재):
#   - `/`와 `,` 둘 다로 분리 ⚠️
#   - "남성/여성생식기암"도 분리됨 (잘못)

# LLMCartesian (개선):
#   Step 1 (LLM): 컬럼별 주 구분자 파악
#     - "보험종목_1": `/`가 주 구분자
#     - "보장계약": `,`가 주 구분자 → `/`는 내용
#   Step 2 (Python): itertools.product

# Output:
{
    "definitions": [
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "두경부암"
        },
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "위암"
        },
        {
            "보종명": "통합암특약(무배당, 미지급형)",
            "유형1": "해약환급금미지급형",
            "유형2": "간편심사(315)형",
            "유형3": "남성/여성생식기암"
        },
        ...
    ],
    "total_count": 6
}
```

### Step 6: Validation
- Task 1: ✓ Pass (shape valid)
- Task 2: ✓ Pass (header/data exist)
- Task 3: ✓ Pass (expected 6, got 6)

### Step 7: 최종 결과
```json
{
  "success": true,
  "final_data": {
    "definitions": [...],
    "total_count": 6
  }
}
```

---

## 🚨 현재 알려진 이슈

### 1. SectionClassifier 오분류
- **증상**: 조건 섹션을 `definition_core`로 잘못 분류
- **원인**: 문맥 정보 부족, 테이블 구조 유사성
- **영향**: 잘못된 섹션에서 정의 추출 시도 → 실패

### 2. 섹션 내 text 요소 무시
- **증상**: "315형→555형 변경" 같은 주석이 반영 안됨
- **원인**: `_extract_from_cores`가 table만 추출, text 무시
- **영향**: 정의 값 변경/주석 정보 손실

### 3. Annotation 병합 미구현
- **증상**: `annotation_indices`를 받아도 병합 안됨
- **원인**: `_merge_with_annotations` 미구현
- **영향**: 별도 섹션의 주석 정보 활용 불가

### 4. RuleCartesianTool 구분자 로직
- **증상**: `/`와 `,` 모두로 분리 → 불필요한 조합 생성
- **원인**: 컬럼별 주 구분자 파악 로직 미구현
- **영향**: "남성/여성생식기암" 잘못 분리

---

## 📝 참조 파일

- **Agent**: `agent.py` - 전체 오케스트레이션
- **Planner**: `core/llm_planner.py`
- **Validator**: `core/llm_validator.py`
- **DocumentAccessor**: `core/document_accessor.py`
- **Tools**: `tools/hybrid_tools.py`
- **Tool Schemas**: `tools/tool_schemas.py`
