# 📋 Planner 파이프라인 실행 가이드

## 🔄 전체 흐름

```
원본 JSON (_parsed.json)
    │
    ▼
┌─────────────────────────┐
│  only_doc.py            │  ← Document Analyzer
│  (문서 구조 분석)        │
└────────┬────────────────┘
         │
         │ 생성: document_analysis
         │       + location 정보
         │
         ▼
    only_doc/*.json
    {
        "document_analysis": {
            "definition_section": {
                "section_index": 0,
                "location": {...},  // ← 접근 경로
                "계층구조": [...]
            },
            "condition_section": {
                "section_index": 1,
                "location": {...},  // ← 접근 경로
                "condition_hierarchy": {...}
            }
        }
    }
         │
         ▼
┌─────────────────────────┐
│  only_plan.py           │  ← Pure Planner
│  (실행 계획 수립)        │
└────────┬────────────────┘
         │
         │ 생성: plan
         │       + metadata (접근 경로)
         │
         ▼
    only_plan/*.json
    {
        "plan": [
            {
                "step": 1,
                "tool": "DefinitionRule",
                "metadata": {
                    "section_index": 0,
                    "paragraph_index": 0,
                    "access_path": "...",  // ← Tool이 사용
                    "hierarchy_info": {...}
                }
            },
            ...
        ]
    }
         │
         ▼
┌─────────────────────────┐
│  Executor Agents        │  ← 실행
│  (Tool 실행)            │
└─────────────────────────┘
```

---

## 📂 디렉토리 구조

```
data/토이프로젝트_데이터/
├── 파싱결과/
│   ├── 신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json       ← 원본
│   │
│   ├── only_doc/                                                   ← Document Analyzer 출력
│   │   └── 신한SOL암보험(무배당, 해약환급금 미지급형)_parsed_plan.json
│   │       (document_analysis + location 정보)
│   │
│   └── only_plan/                                                  ← Pure Planner 출력
│       └── 신한SOL암보험(무배당, 해약환급금 미지급형)_parsed_execution_plan.json
│           (plan + metadata)
```

---

## 🚀 실행 순서

### 1️⃣ **Document Analyzer 실행** (`only_doc.py`)

```bash
python only_doc.py
```

**입력:**
- `data/토이프로젝트_데이터/파싱결과/*.json` (원본 JSON 문서)

**출력:**
- `data/토이프로젝트_데이터/파싱결과/only_doc/*_plan.json`

**출력 내용:**
```json
{
    "document_analysis": {
        "definition_section": {
            "section_index": 0,
            "location": {
                "paragraph_indices": {"tables": [0], "texts": [1]},
                "primary_table_index": 0
            },
            "sample_data": {
                "계층구조": [...]
            }
        },
        "condition_section": {
            "section_index": 1,
            "location": {
                "paragraph_map": [...]
            },
            "condition_hierarchy": {...}
        }
    }
}
```

---

### 2️⃣ **Pure Planner 실행** (`only_plan.py`)

```bash
python only_plan.py
```

**입력:**
- `data/토이프로젝트_데이터/파싱결과/only_doc/*_plan.json` (document_analysis)

**출력:**
- `data/토이프로젝트_데이터/파싱결과/only_plan/*_execution_plan.json`

**출력 내용:**
```json
{
    "plan": [
        {
            "step": 1,
            "tool": "DefinitionRule",
            "metadata": {
                "section_index": 0,
                "paragraph_index": 0,
                "access_path": "elements[0].paragraphs[0].table.table_elements",
                "hierarchy_info": {
                    "depth": 3,
                    "columns": ["구 분", "명칭", "보험종목"]
                },
                "target_columns": ["구 분", "명칭", "보험종목"]
            },
            "reason": "...",
            "expected_output": "정의 트리 (3단계 계층)"
        },
        {
            "step": 2,
            "tool": "ConditionRule",
            "metadata": {
                "section_index": 1,
                "subtitle_mappings": [...],
                "has_subtitles": true,
                "formula_present": true
            },
            "reason": "...",
            "expected_output": "조건 목록"
        },
        {
            "step": 3,
            "tool": "FormulaEvaluator",
            "metadata": {
                "formula_examples": ["만15세 ~ min{(80 – 년만기), 70}세"]
            },
            "reason": "...",
            "expected_output": "평가된 나이 범위"
        },
        {
            "step": 4,
            "tool": "Mapping",
            "metadata": {},
            "reason": "...",
            "expected_output": "정의 ↔ 조건 매핑"
        },
        {
            "step": 5,
            "tool": "CartesianProduct",
            "metadata": {},
            "reason": "...",
            "expected_output": "모든 경우의 수 배열"
        },
        {
            "step": 6,
            "tool": "Normalize",
            "metadata": {},
            "reason": "...",
            "expected_output": "스키마 형태 JSON"
        }
    ]
}
```

---

## 🔍 **Key Concepts**

### **metadata의 역할**

각 Tool은 `metadata`를 받아서 **정확한 위치에 접근**:

```python
# Executor Agent 예시
def execute_definition_rule(state, step):
    metadata = step["metadata"]
    raw_doc = state["raw_document"]

    # metadata로 정확한 위치 접근
    section = raw_doc[0]["elements"][metadata["section_index"]]
    table = section["paragraphs"][metadata["paragraph_index"]]["table"]["table_elements"]

    # 계층 정보 활용
    hierarchy_info = metadata["hierarchy_info"]

    return parse_definition_tree(table, hierarchy_info)
```

---

## ✅ **장점**

1. **역할 분리**
   - `only_doc.py`: 문서 구조 분석 (1회)
   - `only_plan.py`: 실행 계획 수립 (재계획 가능)
   - Executor: Tool 실행

2. **효율성**
   - 문서 분석은 1회만 (캐싱 효과)
   - 재계획 시 document_analysis 재활용

3. **정확성**
   - metadata로 정확한 접근 경로 제공
   - Tool이 탐색 없이 바로 데이터 추출

4. **재계획 용이**
   - Validation 실패 시 `only_plan.py`만 재실행
   - document_analysis는 그대로 사용

---

## 📊 **테스트**

```bash
# 1. Document Analysis 생성
python only_doc.py

# 2. Execution Plan 생성
python only_plan.py

# 3. 접근 경로 테스트
python test_location_access.py
```
