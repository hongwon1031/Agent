# Prototype 2: Generalized Multi-Step Agent

완전히 일반화된 Multi-Agent 시스템으로 보험 문서에서 정의 조합을 추출합니다.

## 주요 특징

### 1. **Document Analysis 불필요**
- 원본 JSON 문서만 입력
- Agent가 자동으로 정의 섹션 탐색

### 2. **Multi-Step Planning**
```
Step 1: Search → 정의 섹션 찾기
Step 2: Extract → 데이터 추출
Step 3: Cartesian → 조합 생성
```

### 3. **LLM-based Validator**
- Rule-based 검증의 한계 극복
- 원본 문서와 비교하여 정확성 검증
- 구체적인 에러 메시지 생성 → Replanner에 전달

### 4. **Intelligent Replanning**
- Validation 실패시 자동으로 재계획
- Tool 전환: Rule-based → LLM-based
- Custom instruction 생성으로 문제 해결

### 5. **Hybrid Tool Strategy**
- **Rule-based tools**: 빠르고 저렴 (첫 시도)
- **LLM-based tools**: 느리지만 유연 (복잡한 케이스)

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        MultiStepAgent                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐       │
│  │  Planner   │───▶│  Executor  │───▶│ Validator  │       │
│  └────────────┘    └────────────┘    └────────────┘       │
│        │                                     │              │
│        │                                     ▼              │
│        │                              Success / Fail        │
│        │                                     │              │
│        └─────────────────────────────────────┘              │
│                  Replanner (if failed)                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 디렉토리 구조

```
prototype_2/
├── tools/
│   ├── __init__.py
│   ├── base.py          # SimpleTool, ToolResult
│   ├── search.py        # RuleSearchTool, LLMSearchTool
│   ├── extract.py       # RuleExtractTool, LLMExtractTool
│   └── cartesian.py     # GenerateCartesianTool
├── agent.py             # Main orchestration loop
├── planner.py           # MultiStepPlanner with replanning
├── executor.py          # ToolExecutor
├── validator.py         # LLMValidator
├── main.py              # Entry point
├── requirements.txt
└── README.md
```

## 사용법

### 1. 설치
```bash
pip install -r requirements.txt
```

### 2. .env 파일 설정
```
OPENAI_API_KEY=your_api_key_here
```

### 3. 실행
```bash
python main.py <document_path> [output_path]
```

**예시**:
```bash
python main.py "C:/Users/NT-165/Desktop/Project/Toy/data/토이프로젝트_데이터/파싱결과/신한SOL암보험(무배당, 해약환급금 미지급형).json"
```

## Tools 설명

### Search Tools
- **RuleSearchTool**: 키워드 매칭으로 "정의" 섹션 찾기
- **LLMSearchTool**: 컨텍스트 이해를 통한 정의 섹션 찾기

### Extract Tools
- **RuleExtractTool**: 표준 테이블 구조에서 데이터 추출
- **LLMExtractTool**: 복잡한 형태 (텍스트, 주석, 특수문자) 처리

### Transform Tool
- **GenerateCartesianTool**: Cartesian Product 생성

## Replanning 전략

### Tool 실패시
```
RuleSearchTool 실패
  → LLMSearchTool with custom instruction
  → 여전히 실패시 max_replan 도달
```

### Validation 실패시
```
Validator: "주석 행이 데이터로 포함됨"
  → Replanner: "주석 제거하라"는 instruction 추가
  → Tool 재실행
```

## 예시: 문제 해결 Flow

**문제**: 표가 아닌 텍스트로 정의 제공
```
1차 시도: RuleExtractTool
  → 실패: "No table found"

Replan:
  → LLMExtractTool
  → instruction: "표가 아닌 텍스트 형태. '명칭:', '유형:' 패턴으로 파싱"
  → 성공
```

**문제**: 주석 정보 포함
```
1차 시도: RuleExtractTool
  → 성공: 데이터 추출
  → Validator: "주석 행(※)이 포함됨"

Replan:
  → LLMExtractTool
  → instruction: "※, 주:, * 로 시작하는 주석 행 제거"
  → 성공 + Validation 통과
```

## 출력 형식

```json
{
  "success": true,
  "final_data": {
    "definitions": [
      {
        "보종명": "재해장해특약\n(무배당, 해약환급금 미지급형)",
        "유형1": "간편심사(315)형",
        "유형2": "1종"
      },
      ...
    ],
    "total_count": 24
  },
  "execution_log": [
    {
      "task_id": 1,
      "description": "정의 섹션 찾기",
      "attempts": [...]
    },
    ...
  ],
  "error": null
}
```

## Prototype 1과의 차이

| 특성 | Prototype 1 | Prototype 2 |
|------|-------------|-------------|
| Document Analysis | 필요 (only_doc 사전 실행) | 불필요 (Agent가 자동 탐색) |
| Validator | Rule-based (하드코딩) | LLM-based (유연) |
| Planning | Single-step | Multi-step (Search→Extract→Cartesian) |
| Tool 전략 | 고정 | Dynamic (Rule→LLM fallback) |
| Instruction | 없음 | Custom instruction 지원 |
| 일반화 | 제한적 | 완전 일반화 목표 |

## 성능 고려사항

### 속도
- Rule-based 우선: 빠른 응답
- LLM fallback: 필요시에만 사용

### 비용
- Validator는 매 task마다 LLM 호출
- 관련 문서 부분만 전달하여 토큰 절약

### 정확도
- LLM Validator로 false positive/negative 최소화
- 구체적인 에러 메시지로 효과적인 replanning

## 다음 단계

1. **Batch Processing**: 여러 문서 동시 처리
2. **Tool Expansion**: 더 많은 특수 케이스 처리 tool 추가
3. **성능 최적화**: Validator 토큰 사용량 최적화
4. **Evaluation**: Ground truth와 비교하여 정확도 측정
