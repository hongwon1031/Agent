# Prototype 3: Fully Generalized Multi-Agent System

완전히 일반화된 Multi-Agent 시스템으로 **모든 형태의 보험 문서**에서 정의 조합을 추출합니다.

## 🎯 Prototype 2와의 핵심 차이점

### Prototype 2의 주요 문제점
1. ❌ 문서 구조 하드코딩 (`doc[0]["elements"][idx]`)
2. ❌ 처음 10개 섹션만 분석
3. ❌ 고정된 3단계 계획
4. ❌ Validator가 샘플 3개만 검증
5. ❌ Cartesian Product 계산 오류
6. ❌ Tool 출력 형식 고정
7. ❌ Task ID 기반 분기
8. ❌ Rule/LLM Tool 파라미터 동일
9. ❌ 주석 처리 불완전
10. ❌ 참조 시스템 취약

### Prototype 3의 해결책
1. ✅ **Document Accessor**: 구조 독립적 문서 접근
2. ✅ **전체 문서 분석**: 모든 섹션 탐색
3. ✅ **동적 계획**: LLM이 문서에 맞게 N단계 계획 수립
4. ✅ **완전 검증**: 전체 데이터 검증 + 행별 인덱스 추적
5. ✅ **정확한 Cartesian**: 행별 독립 계산
6. ✅ **유연한 출력**: Tool이 상황에 맞게 출력 구조 결정
7. ✅ **타입 기반 시스템**: 의미적 타입으로 분기
8. ✅ **Tool별 최적화**: 각 Tool 특성에 맞는 파라미터
9. ✅ **고급 주석 처리**: 패턴 학습 및 동적 인식
10. ✅ **스마트 참조**: 동적 경로 + 리스트 인덱싱

## 🏗️ 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                     MultiAgentSystem                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐    ┌────────────────┐                  │
│  │ DocumentAccessor│◄──│  FlexibleTool  │                  │
│  └────────────────┘    └────────────────┘                  │
│         │                      │                            │
│         ▼                      ▼                            │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐       │
│  │DynamicPlanner◄──│TypedValidator──▶│SmartExecutor│       │
│  └────────────┘    └────────────┘    └────────────┘       │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                     Orchestrator                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 📦 디렉토리 구조

```
prototype_3/
├── core/
│   ├── __init__.py
│   ├── document_accessor.py    # 구조 독립적 문서 접근
│   ├── flexible_result.py      # 유연한 결과 형식
│   └── smart_reference.py      # 동적 참조 시스템
├── tools/
│   ├── __init__.py
│   ├── base.py                 # 기본 Tool 인터페이스
│   ├── search_tools.py         # 유연한 Search
│   ├── extract_tools.py        # 유연한 Extract
│   └── transform_tools.py      # Cartesian 등
├── planning/
│   ├── __init__.py
│   ├── dynamic_planner.py      # N단계 동적 계획
│   └── replanner.py            # 고급 재계획
├── validation/
│   ├── __init__.py
│   ├── typed_validator.py      # 타입 기반 검증
│   └── validators/
│       ├── search_validator.py
│       ├── extract_validator.py
│       └── transform_validator.py
├── execution/
│   ├── __init__.py
│   └── smart_executor.py       # 스마트 실행기
├── agent.py                    # 최상위 오케스트레이터
├── main.py                     # 진입점
├── requirements.txt
└── README.md
```

## 🔑 핵심 개념

### 1. Document Accessor
```python
# 문서 구조에 관계없이 접근
accessor = DocumentAccessor(doc)
sections = accessor.find_sections(criteria={"contains": "정의"})
content = accessor.extract_content(section, content_type="table")
```

### 2. Flexible Tool Result
```python
# Tool이 자유롭게 출력 구조 결정
result = FlexibleToolResult(
    success=True,
    data={"found_items": [...]},
    metadata={
        "output_schema": {...},
        "access_hints": {"how_to_use": "..."}
    }
)
```

### 3. Dynamic Planning
```python
# LLM이 문서 전체를 보고 N단계 계획 수립
plan = planner.create_plan(doc)
# → 3단계일 수도, 5단계일 수도, 7단계일 수도...
```

### 4. Typed Validation
```python
# Task 타입으로 자동 Validator 선택
validator = TypedValidator.get_validator(task.type)
result = validator.validate(output, context)
```

### 5. Smart Reference
```python
# 복잡한 참조도 지원
"{{task1.data[0].location.path}}"  # 리스트 인덱싱
"{{task2.results?.items}}"         # 옵셔널 체이닝
"{{task3.output | filter('valid')}}"  # 필터링
```

## 🚀 사용법

### 설치
```bash
pip install -r requirements.txt
```

### 실행
```bash
python main.py <document_path> [output_path]
```

**예시**:
```bash
python main.py "../data/토이프로젝트_데이터/파싱결과/신한SOL암보험.json"
```

## 🆚 Prototype 2 vs 3 비교

| 특성 | Prototype 2 | Prototype 3 |
|------|-------------|-------------|
| 문서 구조 | 하드코딩 (`doc[0]["elements"]`) | 동적 접근 (DocumentAccessor) |
| 문서 분석 범위 | 처음 10개 섹션 | 전체 문서 |
| 계획 유연성 | 고정 3단계 | 동적 N단계 |
| Validator | 샘플 3개만 검증 | 전체 검증 + 인덱스 추적 |
| Cartesian 계산 | 전체 고유값 (오류) | 행별 독립 계산 (정확) |
| Tool 출력 | 고정 형식 | 유연한 구조 |
| Task 분기 | ID 기반 | 타입 기반 |
| 참조 시스템 | 단순 경로 | 동적 경로 + 리스트 + 옵셔널 |
| 주석 처리 | 고정 패턴 | 패턴 학습 + 동적 인식 |
| 일반화 수준 | 제한적 | 완전 일반화 |

## 🎯 지원하는 문서 형식

### Prototype 2가 실패하는 케이스들
```python
# Case 1: 다른 최상위 키
{"document": {"sections": [...]}}  # ❌ Prototype 2 실패

# Case 2: 페이지 기반 구조
{"pages": [{"content": [...]}]}  # ❌ Prototype 2 실패

# Case 3: 정의가 11번째 섹션
{"elements": [... 35개 섹션, 정의는 25번째]}  # ❌ Prototype 2 실패

# Case 4: 여러 테이블에 분산
정의가 3개 테이블에 나뉘어 있음  # ❌ Prototype 2 실패

# Case 5: 테이블이 아닌 텍스트 정의
"명칭: 상품A, 유형: 1형/2형"  # ❌ Prototype 2 실패
```

### Prototype 3는 모두 처리 가능
```python
# ✅ 모든 케이스 지원
# DocumentAccessor가 구조를 자동으로 파악하고 접근
```

## 📊 성능 개선

### 비용 최적화
- **Rule-based 우선**: 빠른 규칙 먼저 시도
- **LLM on-demand**: 필요시에만 LLM 호출
- **샘플링 옵션**: 큰 데이터는 샘플 검증 후 전체 검증

### 정확도 향상
- **완전 검증**: 모든 행 검증
- **행별 추적**: 문제 발생 인덱스 정확히 파악
- **정확한 계산**: Cartesian 행별 계산

### 확장성
- **플러그인 시스템**: 새 Tool/Validator 쉽게 추가
- **타입 레지스트리**: 자동 등록 및 선택
- **동적 계획**: 문서에 맞게 유연한 전략

## 🔄 실행 흐름

```
1. DocumentAccessor가 문서 구조 분석
   ↓
2. DynamicPlanner가 전체 문서 보고 N단계 계획 수립
   ↓
3. SmartExecutor가 각 Task 실행
   ↓
4. TypedValidator가 타입별 완전 검증
   ↓
5. 실패 시 Replanner가 구조적 재계획
   ↓
6. 최종 결과 반환
```

## 📝 출력 형식

```json
{
  "success": true,
  "document_structure": {
    "detected_format": "standard_elements",
    "total_sections": 35,
    "analyzed_range": "all"
  },
  "execution_plan": {
    "total_tasks": 4,
    "tasks": [...]
  },
  "final_data": {
    "definitions": [...],
    "total_count": 24
  },
  "validation_report": {
    "all_rows_validated": true,
    "invalid_indices": [],
    "quality_score": 1.0
  },
  "execution_log": [...]
}
```

## 🎓 다음 단계

1. **성능 모니터링**: 비용, 속도, 정확도 추적
2. **에러 분석**: 실패 케이스 패턴 학습
3. **자동 최적화**: Tool 선택 전략 학습
4. **배치 처리**: 여러 문서 동시 처리
5. **UI/API**: 웹 인터페이스 및 API 제공
