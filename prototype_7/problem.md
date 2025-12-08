1. Parameters 할루시네이션 (가장 심각)

  # LLM이 한번에 생성해야 하는 것:
  {
    "tasks": [
      {"task_id": "task0", "parameters": {...}},
      {"task_id": "task1", "parameters": {
          "core_indices": "{{task0.data.definition_core}}"  # ← 추측!
      }},
      {"task_id": "task2", ...}
    ]
  }

  문제: task0이 실행되기 전에 task1의 parameters를 작성
  - LLM이 definition_core라는 필드명을 "추측"으로 맞춰야 함
  - 실제 tool output: {"core_sections": [...]} ← 다를 수 있음!
  - 이게 지금 에러의 주범입니다

  2. 동적 조정 불가

  task0 실행 → condition section 없음 발견
  하지만 task3(extract_condition)는 이미 계획에 포함됨 → 불필요한 실행

  사용자 제안: 매 step마다 planner

  Execute task0 → Validate → PLANNER (다음 task 결정)
                               ↓
                            Execute task1 → Validate → PLANNER
                               ↓
                            ...

  ✅ 장점:

  1. 할루시네이션 완전 제거:
    - task0 실행 후 → 실제 output 보고 → task1 parameters 작성
    - 필드명 추측 불필요
  2. 진정한 동적 실행:
    - 결과 보고 다음 단계 결정
    - 불필요한 task 스킵 가능
    - 예상치 못한 상황에 유연 대응
  3. 컨텍스트 단순화:
    - 한번에 1개 task만 계획
    - 프롬프트 짧아짐 → LLM 정확도 증가

  ❌ 단점:

  1. LLM 호출 증가:
    - 기존: Plan 1회 + Replan ~2회 = 3회
    - 제안: Plan 57회 (task마다) = 57회
    - 비용 약 2배 증가
  2. 전체 계획 부재:
    - 사용자가 "앞으로 몇 단계 남았나?" 모름
    - 디버깅 시 전체 흐름 파악 어려움
  3. 일관성 문제:
    - 매번 다르게 판단할 수 있음

  🎯 객관적 평가:

  현재 방식이 실패한 이유:

  - Parameters를 미리 예측하는 것 자체가 불가능함
  - Tool output 구조가 복잡하고 가변적
  - Template 문법 ({{task0.data.field}})이 정확해야 하는데, 추측으로는 못 맞춤

  사용자 제안의 타당성:

  매우 합리적입니다. 특히:
  1. 할루시네이션 제거 ← 현재 가장 큰 문제 해결
  2. 진정한 동적 계획 ← Prototype 7의 원래 목표
  3. ReAct 패턴과 유사 ← 증명된 방법론

  💡 추천 옵션 (3가지):

  Option A: 사용자 제안 그대로

  매 step마다 planner 호출 → 다음 1개 task만 생성
  - 언제: 정확도가 최우선, 비용 OK
  - trade-off: LLM 호출 2배, 비용 증가

  Option B: 하이브리드 (초기 계획 + JIT parameters)

  1. 초기: 전체 task_type만 계획 (parameters는 비워둠)
  2. 각 execute 직전: 해당 task의 parameters만 생성
  3. Validate 후: 계획 수정 여부 결정
  - 장점: 전체 흐름 보임 + parameters 정확
  - 단점: 구현 복잡

  Option C: Tool output schema 강화

  각 tool의 output을 강제로 표준화
  section_classifier는 반드시:
  {
    "definition_core": [...],
    "definition_annotation": [...],
    ...
  }
  - 장점: 현재 구조 유지
  - 단점: 근본 해결 아님

  🔥 결론:

  사용자 제안(Option A)이 가장 합리적입니다.

  이유:
  1. 현재 할루시네이션 문제가 너무 심각함 ← 이게 치명적
  2. LLM 비용 2배는 감수할 만한 가치
  3. Prototype 7의 본래 목표 (동적 실행) 달성
  4. ReAct/Step-by-step planning은 증명된 방법

  구현하시겠습니까? 변경 사항:
  - plan_node: 전체 plan 대신 다음 1개 task만 생성
  - p7_router: validate 후 항상 planner로 복귀
  - LLM prompt: "지금까지 결과 보고 다음 task 1개 결정"