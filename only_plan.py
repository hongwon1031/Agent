import os
import json
import time
from pathlib import Path
from textwrap import dedent
from plan_tools import TOOLS
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# GPT-4o 가격 (per 1M tokens, 2025년 1월 기준)
GPT4O_INPUT_PRICE = 2.50  # $2.50 per 1M input tokens
GPT4O_OUTPUT_PRICE = 10.00  # $10.00 per 1M output tokens

# Tool 목록 (type/latency/cost 메타 포함)

TARGET_FIELDS = [
    "보종명",
    "유형1",
    "유형2",
    "유형3",
    "보험기간",
    "납입기간",
    "주피보험자최소가입연령",
    "주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드",
    "주피보험자최대가입연령구분코드",
    "주피보험자가입성별",
]

DEFAULT_MODEL = "gpt-4o"

BASE_INPUT_PATHS = [
    Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc")
]


def build_prompt(doc_analysis: dict) -> str:
    """document_analysis를 받아서 plan만 생성하는 프롬프트 (CoT 방식)"""
    tool_lines = "\n".join(
        f"- {t['name']} (type={t['type']}, latency={t['latency']}, cost={t['cost']}): {t['description']}"
        for t in TOOLS
    )
    schema_lines = "\n".join(f"- {field}" for field in TARGET_FIELDS)

    doc_analysis_str = json.dumps(doc_analysis, ensure_ascii=False, indent=2)

    return dedent(
        f"""
        너는 Pure Planner Agent이다.
        이미 Document Analyzer가 문서 구조를 분석한 결과(document_analysis)가 주어졌다.
        이제 이 정보를 바탕으로 **실행 계획(plan)을 수립**하라.

        출력 형식:
        {{
            "reasoning": {{
                "checklist": {{
                    "언어": {{
                        "check": "문서에 비한국어(중국어/영어/한자) 포함 여부 분석",
                        "detected": "중국어 컬럼명 다수 발견 / 순수 한국어 / 영어 혼재",
                        "decision": "ChineseToKorean 필요 / EnglishToKorean 필요 / 불필요",
                        "reason": "상세한 판단 근거"
                    }},
                    "수식": {{
                        "check": "sample_conditions.has_formula 확인",
                        "detected": "true / false",
                        "decision": "FormulaEvaluator 필요 / 불필요",
                        "reason": "상세한 판단 근거"
                    }},
                    "소제목": {{
                        "check": "condition_hierarchy.has_subtitles 확인",
                        "detected": "true / false",
                        "decision": "SubtitleMapper 계열 필요 / 불필요",
                        "reason": "상세한 판단 근거"
                    }},
                    "복잡표": {{
                        "check": "rowspan/colspan 복잡도, 특이사항 분석",
                        "detected": "복잡함 / 단순함 / 언급 없음",
                        "decision": "RowspanHandler/ColspanHandler 필요 / 불필요",
                        "reason": "상세한 판단 근거"
                    }}
                }},
                "structure_analysis": {{
                    "definition_complexity": "단순/중간/복잡",
                    "definition_reasoning": "판단 근거 (표 개수, 계층 깊이, 컬럼명 명확성)",
                    "condition_complexity": "단순/중간/복잡",
                    "condition_reasoning": "판단 근거 (소제목 유무, 표 개수, 텍스트 비중)",
                    "overall_strategy": "Rule 기반 우선 / Hybrid 혼합 / LLM 위주"
                }},
                "tool_selection_reasoning": [
                    {{
                        "step": 1,
                        "tool": "ToolName",
                        "why": "이 Tool을 선택한 이유 (체크리스트/구조 분석 결과 기반)",
                        "alternatives_considered": ["다른Tool: 왜 제외했는지"],
                        "confidence": "low/medium/high"
                    }},
                    ...
                ],
                "cost_latency_consideration": "예상 비용 및 지연 분석 (Rule X개, Hybrid Y개, LLM Z개)",
                "potential_risks": ["잠재적 실패 가능성 1", "잠재적 실패 가능성 2", ...]
            }},
            "plan": [
                {{
                    "step": 번호,
                    "tool": "툴이름",
                    "metadata": {{
                        "section_index": 섹션_인덱스,
                        "paragraph_index": paragraph_인덱스,
                        "access_path": "elements[X].paragraphs[Y].table.table_elements",
                        "target_columns": ["컬럼명1", "컬럼명2"],
                        "hierarchy_info": {{
                            "depth": 계층_깊이,
                            "columns": ["컬럼명들"]
                        }},
                        "additional_context": {{추가_필요_정보}}
                    }},
                    "reason": "reasoning에서 도출된 결론 간략 요약",
                    "expected_output": "이_단계에서_추출될_정보"
                }},
                ...
            ]
        }}

        ⚠️⚠️⚠️ 계획 수립 프로세스 (5단계) ⚠️⚠️⚠️

        [1단계: 체크리스트 검토]
        다음 항목들을 순서대로 확인하고, reasoning.checklist에 분석 결과를 작성하라:

        □ [언어]
          - document_analysis의 doc_title, definition_section.title, definition_section.columns,
            condition_section.title 등을 확인
          - 중국어(中/險/種/額/期 등), 영어(Insurance/Premium/Period 등), 한자 포함 여부 분석
          - 감지 결과:
            * 비한국어 30% 이상 → ChineseToKorean / EnglishToKorean 강력 권장
            * 비한국어 10~30% → 상황에 따라 선택적 사용
            * 순수 한국어 → 생략 가능

        □ [수식]
          - condition_section.sample_conditions.has_formula 확인
          - formula_examples의 복잡도 분석 (min[...], max[...], 계산식 등)
          - true이고 복잡도 높음 → FormulaEvaluator 필수
          - true이지만 단순함 → 선택적 사용
          - false → 생략

        □ [소제목]
          - condition_section.condition_hierarchy.has_subtitles 확인
          - subtitle_mapping 개수 및 구조 분석
          - true이고 여러 소제목 → SubtitleMapper 또는 관련 Tool 필요
          - false → 생략

        □ [복잡표]
          - definition_section.특이사항, condition_section.특이사항,
            definition_section.누락_위험, condition_section.누락_위험 확인
          - "rowspan", "colspan", "병합", "복잡" 등 키워드 탐지
          - 언급됨 → RowspanHandler / ColspanHandler / ComplexTableParser 고려
          - 언급 없음 → 생략

        [2단계: 구조 복잡도 분석]
        reasoning.structure_analysis에 다음을 작성:

        - Definition 섹션 복잡도:
          * 단순: 표 1개 + 계층 ≤2 + 명확한 컬럼 → DefinitionSimpleTableRule / DefinitionRule
          * 중간: 계층 3단 or 멀티컬럼 → DefinitionMultiColumnRule / DefinitionDeepHierarchyHybrid
          * 복잡: 텍스트 혼재 or 계층 불명확 → DefinitionHybrid / DefinitionTextOnlyLLM

        - Condition 섹션 복잡도:
          * 단순: 표 1~2개 + 소제목 없음 → ConditionSimpleTableRule / ConditionRule
          * 중간: 소제목 + 다중 표 → ConditionSubtitleHybrid
          * 복잡: 텍스트 위주 → ConditionTextOnlyLLM / ConditionHybrid

        - 전체 전략:
          * 단순 → Rule 기반 위주 (빠르고 저렴)
          * 중간 → Rule + Hybrid 혼합
          * 복잡 → Hybrid + LLM 사용

        [3단계: Tool 선택 추론]
        reasoning.tool_selection_reasoning 배열에 각 step마다 다음을 작성:

        - 왜 이 Tool을 선택했는가? (체크리스트/구조 분석 결과 기반)
        - 다른 대안은 무엇이었고 왜 제외했는가?
        - 비용/지연 관점에서 적절한가?
        - 확신도는? (low/medium/high)

        예시:
        {{
          "step": 2,
          "tool": "DefinitionSimpleTableRule",
          "why": "체크리스트 결과 한국어 문서이고, 구조 분석 결과 단순 표(계층 2단, 컬럼 3개). Rule로 충분히 처리 가능",
          "alternatives_considered": [
            "DefinitionHybrid: 불필요한 LLM 비용 발생",
            "DefinitionLLM: 단순 구조에 과도한 Tool"
          ],
          "confidence": "high"
        }}

        [4단계: 비용/위험 평가]
        reasoning에 다음을 추가:

        - cost_latency_consideration:
          * Rule 기반 Tool 개수 × 저비용
          * Hybrid Tool 개수 × 중비용
          * LLM Tool 개수 × 고비용
          * 전체 예상 비용: 낮음/중간/높음

        - potential_risks:
          * 각 단계에서 실패 가능성이 있는 부분 명시
          * 예: "중국어 번역 품질 이슈", "복잡한 수식 파싱 실패 가능", "소제목-표 매핑 오류"

        [5단계: 최종 Plan 생성]
        위 reasoning 결과를 바탕으로 plan 배열을 생성하라.

        ⚠️ 필수 단계 (역할만 고정, 구체적 Tool은 자율 선택):

        [전처리 단계] - 선택적
        - 목적: 언어 정규화, 수식 처리, 복잡한 표 구조 처리 등
        - 판단 기준: 체크리스트 분석 결과에 따라 필요 시에만 추가
        - 삽입 위치: Definition/Condition 추출 전/중/후 어디든 가능
        - Tool 선택: 문서 특성에 맞는 적절한 Tool을 자율적으로 선택
          (예: 언어 이슈 → 번역 Tool, 수식 → 수식 처리 Tool, rowspan → 표 처리 Tool)

        [Definition 추출 단계] - 필수
        - 목적: 보종명, 유형1/2/3 등의 계층 구조 추출
        - 최소 요구: 정의 섹션에서 보험 상품의 계층 정보를 최소 1회 추출해야 함
        - Tool 선택: 문서 구조 복잡도에 맞는 적절한 Tool을 자율적으로 선택
          (표 구조, 계층 깊이, 텍스트 혼재 여부 등을 고려)

        [Condition 추출 단계] - 필수
        - 목적: 보험기간, 납입기간, 가입연령, 성별 등의 조건 추출
        - 최소 요구: 조건 섹션에서 가입 조건 정보를 최소 1회 추출해야 함
        - Tool 선택: 문서 구조 복잡도에 맞는 적절한 Tool을 자율적으로 선택
          (소제목 유무, 표 개수, 텍스트 비중 등을 고려)

        [후처리 파이프라인] - 필수 (순서 고정, Tool 고정)
        1. Mapping: 추출된 Definition과 Condition을 타겟 스키마에 맞게 필드명 매핑
        2. CartesianProduct: 보종 × 기간 × 납입기간 × 연령 × 성별의 모든 조합 생성
        3. Normalize: 중복 제거 및 데이터 정규화
        4. ValidationLight: 필수 필드 존재 여부 및 기본 범위 검사
        5. FinalWriter: 최종 가입가능조건 JSON 파일 출력

        ⚠️ 중요: 후처리 파이프라인(Mapping ~ FinalWriter)은 반드시 포함하고 순서를 지켜야 한다!

        각 step의 reason은 reasoning.tool_selection_reasoning에서 도출된 결론을 간략히 요약.

        metadata 필드 작성 규칙:

           A) Definition 추출 단계:
              {{
                  "section_index": doc_analysis.definition_section.section_index,
                  "paragraph_index": doc_analysis.definition_section.location.primary_table_index,
                  "access_path": "elements[X].paragraphs[Y].table.table_elements",
                  "hierarchy_info": {{
                      "depth": doc_analysis.definition_section.sample_data.hierarchy_depth,
                      "columns": doc_analysis.definition_section.columns
                  }},
                  "target_columns": doc_analysis.definition_section.columns
              }}

              ⚠️ target_columns는 반드시 doc_analysis.definition_section.columns를 사용하라!
              ⚠️ access_path의 X, Y는 실제 section_index, paragraph_index로 치환하라!

           B) Condition 추출 단계:
              {{
                  "section_index": doc_analysis.condition_section.section_index,
                  "access_path": "elements[X].paragraphs",
                  "subtitle_mappings": doc_analysis.condition_section.condition_hierarchy.subtitle_mapping,
                  "paragraph_map": doc_analysis.condition_section.location.paragraph_map,
                  "has_subtitles": doc_analysis.condition_section.condition_hierarchy.has_subtitles,
                  "formula_present": doc_analysis.condition_section.sample_conditions.has_formula
              }}

              ⚠️ access_path의 X는 실제 section_index로 치환하라!
              ⚠️ subtitle_mapping의 각 table_index를 사용하여 개별 표에 접근하라!

        ⚠️ 중요:
        - reasoning은 내부 사고 과정이므로 매우 상세하게 작성
        - plan은 실행용이므로 간결하게 작성
        - reasoning 없이 plan만 작성하지 말 것!
        - 체크리스트 항목은 모두 확인하되, "강력 권장"이지 "강제"는 아님
        - 문서 특성상 불필요하다고 판단되면 생략해도 됨 (단, reasoning에서 근거 명시)

        [시스템 전체 목표]
        - 가입가능조건 JSON 생성 (아래 타겟 스키마 형식)

        [Planner(너)의 역할]
        - 위 목표를 달성하기 위해 Executor가 실행할 plan(Tool 목록 + metadata)을 수립
        - 출력: reasoning + plan (가입가능조건 JSON이 아님!)

        [Executor의 역할] (참고용)
        - Planner가 수립한 plan을 단계별로 실행
        - 출력: 가입가능조건 JSON (타겟 스키마 형식)

        [타겟 스키마] (Executor가 최종 생성할 형식)
        {schema_lines}

        [사용 가능한 Tool]
        {tool_lines}

        [Document Analysis (Document Analyzer가 생성)]
        ```json
        {doc_analysis_str}
        ```

        위 document_analysis의 location 정보를 활용하여,
        각 Tool이 정확한 위치(section_index, paragraph_index)에 접근할 수 있도록
        metadata를 상세히 작성하라.
        한국어로 작성하라.
        """
    ).strip()


def collect_targets(paths):
    """only_doc/ 디렉토리에서 *_plan.json 파일 수집"""
    targets = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            targets.extend(sorted(path.glob("*_plan.json")))
        elif path.exists():
            targets.append(path)
        else:
            print(f"[SKIP] {path} (존재하지 않는 경로)")
    return targets


def main():
    targets = collect_targets(BASE_INPUT_PATHS)
    if not targets:
        print("[WARN] 처리할 document_analysis 파일이 없습니다.")
        print(f"      먼저 only_doc.py를 실행하여 *_plan.json을 생성하세요.")
        print(f"      경로: {BASE_INPUT_PATHS[0]}")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    for path in targets:
        print(f"\n{'='*60}")
        print(f"Processing: {path.name}")
        print(f"{'='*60}")

        # document_analysis JSON 로드
        try:
            doc_analysis = json.load(path.open("r", encoding="utf-8"))
        except Exception as e:
            print(f"[ERROR] JSON 로드 실패: {e}")
            continue

        # document_analysis만 추출 (plan 제외)
        if "document_analysis" in doc_analysis:
            analysis_only = doc_analysis["document_analysis"]
        else:
            analysis_only = doc_analysis

        # Planner 프롬프트 생성
        prompt = build_prompt(analysis_only)

        # LLM 호출 (시간 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Pure Planner Agent. Chain-of-Thought 방식으로 사고 과정(reasoning)을 먼저 상세히 작성한 뒤, 그 결과를 바탕으로 실행 계획(plan)을 수립한다. 체크리스트를 꼼꼼히 확인하고, 대안을 검토하며, 각 선택의 근거를 명확히 한다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8000,  # CoT reasoning + plan이 길어질 수 있으므로 증가
        )
        end_time = time.time()
        latency = end_time - start_time

        # Token 사용량 및 비용 계산
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens

        input_cost = (input_tokens / 1_000_000) * GPT4O_INPUT_PRICE
        output_cost = (output_tokens / 1_000_000) * GPT4O_OUTPUT_PRICE
        total_cost = input_cost + output_cost

        # 결과 출력
        print(f"\n📊 === LLM 호출 통계 ===")
        print(f"⏱️  Latency: {latency:.2f}초")
        print(f"🎫 Token 사용량:")
        print(f"   - Input:  {input_tokens:,} tokens")
        print(f"   - Output: {output_tokens:,} tokens")
        print(f"   - Total:  {total_tokens:,} tokens")
        print(f"💰 비용:")
        print(f"   - Input:  ${input_cost:.6f}")
        print(f"   - Output: ${output_cost:.6f}")
        print(f"   - Total:  ${total_cost:.6f}")

        plan_text = response.choices[0].message.content

        print(f"\n=== Generated Plan ===")
        print(plan_text)

        # 마크다운 코드 블록 제거
        if plan_text.strip().startswith("```"):
            lines = plan_text.strip().split("\n")
            # 첫 줄이 ```json 또는 ``` 인 경우 제거
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 마지막 줄이 ``` 인 경우 제거
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            plan_text = "\n".join(lines)

        # 결과 저장 (only_plan/ 디렉토리)
        result_dir = path.parent.parent / "only_plan"
        result_dir.mkdir(exist_ok=True)

        # 원본 파일명에서 _plan 제거하고 _execution_plan 추가
        base_name = path.stem.replace("_plan", "")
        out_path = result_dir / f"{base_name}_execution_plan.json"

        try:
            plan_obj = json.loads(plan_text)

            # 메타데이터 추가
            plan_obj["_metadata"] = {
                "model": DEFAULT_MODEL,
                "latency_seconds": round(latency, 2),
                "token_usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                "cost_usd": {
                    "input_cost": round(input_cost, 6),
                    "output_cost": round(output_cost, 6),
                    "total_cost": round(total_cost, 6),
                },
                "pricing_per_1m_tokens": {
                    "input": GPT4O_INPUT_PRICE,
                    "output": GPT4O_OUTPUT_PRICE,
                },
            }

            out_path.write_text(
                json.dumps(plan_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✅ 실행 계획 저장 성공: {out_path}")
        except Exception as e:
            print(f"\n⚠️  JSON 파싱 실패, 원문 저장: {e}")
            out_path.write_text(plan_text, encoding="utf-8")
            print(f"   원문 저장: {out_path}")


if __name__ == "__main__":
    main()
