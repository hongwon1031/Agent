# Prototype Agent for Definition Extraction

## 목표
보험 약관 문서에서 **정의 섹션의 모든 경우의 수를 고정 스키마로 추출**

## 입력 예시
```json
{
  "title": "1. 보험종목의 명칭",
  "paragraphs": [
    {
      "type": "table",
      "table": {
        "table_elements": [
          {
            "명칭": "[3-100%장해형]재해장해특약\n(무배당, 해약환급금 미지급형)",
            "보험종목": "해약환급금 미지급형",
            "보험종목_1": "간편심사(315)형\n/간편심사(335)형\n/간편심사(355)형\n/일반심사형"
          }
        ]
      }
    }
  ]
}
```

## 출력 예시
```json
[
  {
    "보종명": "[3-100%장해형]재해장해특약\n(무배당, 해약환급금 미지급형)",
    "유형1": "해약환급금 미지급형",
    "유형2": "간편심사(315)형"
  },
  {
    "보종명": "[3-100%장해형]재해장해특약\n(무배당, 해약환급금 미지급형)",
    "유형1": "해약환급금 미지급형",
    "유형2": "간편심사(335)형"
  },
  ...
]
```

## 구조

```
prototype/
├── tools.py          # 3가지 Tool 구현
├── executor.py       # Tool 실행 엔진
├── replanner.py      # LLM 기반 Planning/Replanning
├── agent.py          # 전체 Agent Loop
└── README.md         # 이 파일
```

## Tools

### 1. Simple Split
- 단순 `/` 분리만 수행
- Cartesian Product 미구현
- **사용 케이스**: 가장 단순한 테이블 (빠른 실행)

### 2. Column Cartesian
- 각 열을 독립적으로 `/` split
- 자동 키 매핑 (`명칭` → `보종명`)
- **Cartesian Product 생성** ✅
- **사용 케이스**: 표준 구조의 테이블 (대부분의 경우)

### 3. Row-aware Cartesian
- 행별로 다른 보종명 처리
- 사용자 정의 키 매핑
- `rowspan`/`colspan` 고려
- **사용 케이스**: 복잡한 구조의 테이블

## 실행 방법

### 1. 환경 설정
```bash
# ANTHROPIC_API_KEY 환경변수 설정
export ANTHROPIC_API_KEY="your-api-key"

# 또는 Windows
set ANTHROPIC_API_KEY=your-api-key
```

### 2. 실행
```bash
cd c:\Users\NT-165\Desktop\Project\Toy\prototype
python agent.py
```

### 3. 결과 확인
```bash
# result.json 생성됨
cat result.json
```

## Replanning Cycle

```
[Attempt 1]
  LLM: "일단 column_cartesian 시도"
  → Tool 실행
  → ✅ 성공 → 종료

또는

[Attempt 1]
  LLM: "simple_split 시도 (빠르니까)"
  → Tool 실행
  → ❌ 실패 (Cartesian Product 없음)

[Replan]
  LLM: "실패 이유: Cartesian Product 필요"
  LLM: "새 전략: column_cartesian 사용"

[Attempt 2]
  → column_cartesian 실행
  → ✅ 성공 → 종료
```

## 검증 방법

### 수동 검증
1. `result.json` 열기
2. `data.definitions` 배열 확인
3. 예상 조합 개수 확인:
   - 보종명 1개 × 유형1 2개 × 유형2 4개 = **8개 조합**

### 자동 검증 (추후 구현 가능)
```python
def validate_result(result):
    definitions = result["data"]["definitions"]

    # 1. 최소 1개 이상의 조합 존재
    assert len(definitions) > 0

    # 2. 모든 항목이 고정 스키마 준수
    for item in definitions:
        assert "보종명" in item
        assert "유형1" in item
        assert "유형2" in item

    # 3. 중복 없음
    unique_combos = set(tuple(d.items()) for d in definitions)
    assert len(unique_combos) == len(definitions)
```

## 평가 지표

| Metric | 설명 |
|--------|------|
| **Success Rate** | 최종 성공 여부 (True/False) |
| **Replan Count** | 재계획 횟수 (0, 1, 2) |
| **Combination Count** | 생성된 조합 개수 |
| **Expected Count** | 예상 조합 개수 (수동 계산) |

## 예상 실험 결과

```
Tool: simple_split
  Success Rate: 20% (Cartesian Product 없어서 대부분 실패)
  Replan Count: 1.5 (평균)

Tool: column_cartesian
  Success Rate: 90% (대부분 성공)
  Replan Count: 0.1 (평균)

Tool: row_aware_cartesian
  Success Rate: 95% (가장 정확)
  Replan Count: 0.05 (평균)
```

## 다음 단계

1. ✅ **Tool 구현 완료**
2. ✅ **Replanning Cycle 구현 완료**
3. ⬜ **실제 실행 및 검증**
4. ⬜ **다양한 Planner 비교 실험**
   - `plan_no_cot.py`
   - `plan.py`
   - `only_doc.py` + `only_plan.py`
5. ⬜ **성능 지표 수집**
   - Success Rate
   - Replan Count
   - Token Usage
   - Latency
