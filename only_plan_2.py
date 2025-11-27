import os
import json
import time
from pathlib import Path
from textwrap import dedent

from dotenv import load_dotenv
from openai import OpenAI

from plan_tools import TOOLS

load_dotenv()

# GPT-4o 비용 (per 1M tokens)
GPT4O_INPUT_PRICE = 2.50
GPT4O_OUTPUT_PRICE = 10.00

TARGET_FIELDS = [
    "보종명",
    "유형1",
    "유형2",
    "유형3",
    "보험기간",
    "납입기간",
    "남자가입연령",
    "여자가입연령",
    "남자최대가입연령",
    "여자최대가입연령",
    "납입주기",
]

DEFAULT_MODEL = "gpt-4o"

# only_doc 결과가 들어있는 폴더 (문서 구조 요약)
BASE_INPUT_PATHS = [
    Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc")
]

# 프롬프트에 넣을 raw JSON 길이 제한
RAW_JSON_MAX_CHARS = 10_000


def build_prompt(doc_analysis: dict, raw_json: str) -> str:
    """
    document_analysis + raw parsed JSON 을 모두 보고
    실행 계획(plan)을 세우도록 하는 CoT 프롬프트 생성.
    """
    tool_lines = "\n".join(
        f"- {t['name']} (type={t['type']}, latency={t['latency']}, cost={t['cost']}): {t['description']}"
        for t in TOOLS
    )
    schema_lines = "\n".join(f"- {field}" for field in TARGET_FIELDS)

    doc_analysis_str = json.dumps(doc_analysis, ensure_ascii=False, indent=2)
    raw_snippet = (raw_json or "")[:RAW_JSON_MAX_CHARS]

    return dedent(
        f"""
        너는 Pure Planner Agent이다.

        - 입력 1: Document Analyzer Agent가 생성한 document_analysis (문서 구조 요약)
        - 입력 2: 원본 parsed JSON (표/텍스트 구조가 그대로 남아있는 데이터의 앞부분 일부)

        목표:
        - 정의(Definition) 섹션과 조건(Condition) 섹션에서 가입가능조건 JSON을 생성하기 위한
          전체 실행 계획(plan)을 수립한다.
        - 각 단계에서 어떤 Tool을 사용할지, 어떤 이유로 선택했는지,
          어떤 위치(access_path/section_index/paragraph_index)를 대상으로 할지까지 명시한다.

        출력 형식(JSON만 출력):
        {{
          "reasoning": {{
            "checklist": {{
              "언어": {{
                "check": "문서에 비한국어(중국어/영어/한자) 포함 여부 분석",
                "detected": "순수 한국어 / 혼합 / 중국어 / 영어 / 기타",
                "decision": "ChineseToKorean 필요 / EnglishToKorean 필요 / 불필요",
                "reason": "해당 결론에 도달한 근거"
              }},
              "수식": {{
                "check": "조건 섹션에 수식 또는 min/max 형태의 표현 존재 여부",
                "detected": "true / false",
                "decision": "FormulaEvaluator 필요 / 불필요",
                "reason": "해당 결론에 도달한 근거"
              }},
              "소제목": {{
                "check": "condition_hierarchy.has_subtitles 또는 실제 raw JSON에서 소제목 패턴 존재 여부",
                "detected": "true / false",
                "decision": "SubtitleMapper 계열 필요 / 불필요",
                "reason": "해당 결론에 도달한 근거"
              }},
              "복잡표": {{
                "check": "rowspan/colspan, 병합 셀, 깊은 계층 구조 여부",
                "detected": "단순 / 중간 / 복잡",
                "decision": "RowspanHandler/ColspanHandler/ComplexTableParser 중 어떤 것이 필요한지",
                "reason": "document_analysis와 raw JSON 테이블 구조를 함께 본 근거"
              }}
            }},
            "structure_analysis": {{
              "definition_complexity": "단순/중간/복잡",
              "definition_reasoning": "정의 섹션의 표/텍스트 구조 분석 근거",
              "condition_complexity": "단순/중간/복잡",
              "condition_reasoning": "조건 섹션의 표/텍스트/소제목 구조 분석 근거",
              "overall_strategy": "Rule 위주 / Hybrid 혼합 / LLM 중심 등 선택한 전반 전략"
            }},
            "tool_selection_reasoning": [
              {{
                "step": 1,
                "tool": "ToolName",
                "why": "이 Tool을 선택한 이유(문서 구조 + 비용/지연/정확도 관점)",
                "alternatives_considered": ["다른Tool1", "다른Tool2"],
                "confidence": "low/medium/high"
              }}
            ],
            "cost_latency_consideration": "각 Tool 조합에 따른 대략적인 비용/지연도 평가",
            "potential_risks": ["잠재 리스크1", "잠재 리스크2"]
          }},
          "plan": [
            {{
              "step": 1,
              "tool": "ToolName",
              "metadata": {{
                "section_index": 0,
                "paragraph_index": 0,
                "access_path": "elements[0].paragraphs[0].table.table_elements",
                "추가_필요_정보": "해당 Tool이 실행될 때 필요한 위치/컬럼/유형 정보 등"
              }},
              "reason": "이 단계에서 이 Tool을 사용하는 이유",
              "expected_output": "이 단계에서 기대하는 중간 산출물"
            }}
          ]
        }}

        ⚠️ 필수 단계 (역할만 고정, Tool은 자율 선택):
        - Definition 단계: 보종/유형 계층을 최소 한 번은 추출해야 한다.
        - Condition 단계: 보험기간/납입기간/연령/성별 조건을 최소 한 번은 추출해야 한다.
        - Mapping 단계: Definition과 Condition을 내부 스키마로 매핑해야 한다.
        - Product 단계: 가능한 모든 조합(보종×기간×납입기간×연령×성별)을 생성해야 한다.
        - Normalize/Validation/Final 단계: 중복 제거, 기본 검증, 최종 JSON 출력까지 마무리해야 한다.

        ⚠️ 단계 순서:
        - Definition/Condition/전처리(언어/수식/rowspan 등)는 문서 특성에 따라 순서를 바꿔도 된다.
        - 단, Mapping → CartesianProduct → Normalize → ValidationLight → FinalWriter 파이프라인은
          순서와 포함 여부를 반드시 지켜야 한다.

        [타겟 스키마 주요 필드]
        {schema_lines}

        [사용 가능한 Tool 목록]
        {tool_lines}

        [입력 1] Document Analysis (Document Analyzer 출력)
        ```json
        {doc_analysis_str}
        ```

        [입력 2] Raw Parsed JSON (일부, 구조 확인용)
        ```json
        {raw_snippet}
        ```

        위 두 입력을 모두 참고하여,
        - document_analysis의 요약 정보를 활용하되,
        - raw JSON의 실제 테이블/텍스트 구조를 직접 확인하면서
          최적의 Tool 조합과 실행 순서를 자유롭게 설계하라.
        출력은 반드시 위에서 정의한 JSON 형식만 반환하라.
        """
    ).strip()


def collect_targets(paths):
    """only_doc/ 디렉터리에서 *_plan.json 대상 파일 수집"""
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
        print("[WARN] 초기에 document_analysis 결과가 없습니다.")
        print("       먼저 only_doc.py를 실행해서 *_plan.json을 생성해 주세요.")
        print(f"       경로: {BASE_INPUT_PATHS[0]}")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    for path in targets:
        print(f"\n{'=' * 60}")
        print(f"Processing (only_plan_2, with raw): {path.name}")
        print(f"{'=' * 60}")

        # document_analysis JSON 로드
        try:
            doc_analysis = json.load(path.open("r", encoding="utf-8"))
        except Exception as e:
            print(f"[ERROR] JSON 로드 실패: {e}")
            continue

        # document_analysis 내부만 사용
        if "document_analysis" in doc_analysis:
            analysis_only = doc_analysis["document_analysis"]
        else:
            analysis_only = doc_analysis

        # 대응되는 원본 parsed JSON 경로 유추
        # 예: foo_parsed_plan.json -> foo_parsed.json
        base_name = path.stem.replace("_plan", "")
        raw_path = path.parent.parent / f"{base_name}.json"

        try:
            raw_text = raw_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"[WARN] Raw JSON not found: {raw_path}")
            raw_text = ""
        except Exception as e:
            print(f"[WARN] Raw JSON read error ({raw_path}): {e}")
            raw_text = ""

        # 프롬프트 생성
        prompt = build_prompt(analysis_only, raw_text)

        # LLM 호출
        start_time = time.time()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Pure Planner Agent. Chain-of-Thought 방식으로 충분한 내부 추론(reasoning)을 먼저 작성한 뒤, "
                        "그 추론을 바탕으로 실행 계획(plan)을 JSON 형식으로 출력한다. "
                        "체크리스트를 꼼꼼히 검토하고, 문서 구조와 원본 데이터를 모두 고려하여 "
                        "각 단계에 가장 적절한 Tool과 메타데이터를 선택하라."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=8000,
        )
        end_time = time.time()
        latency = end_time - start_time

        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens

        input_cost = (input_tokens / 1_000_000) * GPT4O_INPUT_PRICE
        output_cost = (output_tokens / 1_000_000) * GPT4O_OUTPUT_PRICE
        total_cost = input_cost + output_cost

        print(f"\n=== LLM 호출 결과 (only_plan_2) ===")
        print(f"- Latency: {latency:.2f}초")
        print(f"- Tokens: input={input_tokens:,}, output={output_tokens:,}, total={total_tokens:,}")
        print(f"- Cost  : input=${input_cost:.6f}, output=${output_cost:.6f}, total=${total_cost:.6f}")

        plan_text = response.choices[0].message.content

        print("\n=== Generated Plan (raw) ===")
        print(plan_text)

        # ```json 래핑 제거
        if plan_text.strip().startswith("```"):
            lines = plan_text.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            plan_text = "\n".join(lines)

        # 출력 디렉터리: 파싱결과/only_plan_2/
        result_dir = path.parent.parent / "only_plan_2"
        result_dir.mkdir(exist_ok=True)

        out_path = result_dir / f"{base_name}_execution_plan.json"

        try:
            plan_obj = json.loads(plan_text)

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
            print(f"\n✅ 실행 계획 저장 완료: {out_path}")
        except Exception as e:
            print(f"\n[WARN] JSON 파싱 실패, 원문 그대로 저장: {e}")
            out_path.write_text(plan_text, encoding="utf-8")
            print(f"      경로: {out_path}")


if __name__ == "__main__":
    main()

