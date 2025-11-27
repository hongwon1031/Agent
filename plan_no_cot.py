import os
import json
import time
from pathlib import Path
from plan_tools import TOOLS
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# GPT-4o 가격 (per 1M tokens, 2025년 1월 기준)
GPT4O_INPUT_PRICE = 2.50  # $2.50 per 1M input tokens
GPT4O_OUTPUT_PRICE = 10.00  # $10.00 per 1M output tokens

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
    Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과")
]
MAX_CHARS = None


def build_prompt(raw_json: str) -> str:
    """raw JSON에서 직접 plan만 생성하는 프롬프트 (CoT 없음)"""
    tool_lines = "\n".join(
        f"- {t['name']} (type={t['type']}, latency={t['latency']}, cost={t['cost']}): {t['description']}"
        for t in TOOLS
    )
    schema_lines = "\n".join(f"- {field}" for field in TARGET_FIELDS)

    prompt_template = """
        너는 Direct Planner Agent이다.
        원본 JSON 문서를 직접 받아서 가입가능조건 JSON을 생성하기 위한 실행 계획(plan)을 수립하라.

        ⚠️ Document Analysis 단계는 생략하고, 원본 문서를 직접 분석하여 계획을 세워라.
        ⚠️ Reasoning 과정은 생략하고, plan만 바로 출력하라.

        출력 형식:
        {
            "plan": [
                {
                    "step": 번호,
                    "tool": "툴이름",
                    "metadata": {
                        "section_index": 섹션_인덱스,
                        "paragraph_index": paragraph_인덱스,
                        "access_path": "elements[X].paragraphs[Y].table.table_elements",
                        "target_columns": ["컬럼명1", "컬럼명2"],
                        "hierarchy_info": {
                            "depth": 계층_깊이,
                            "columns": ["컬럼명들"]
                        },
                        "additional_context": {추가_필요_정보}
                    },
                    "reason": "이 Tool을 선택한 간략한 이유",
                    "expected_output": "이_단계에서_추출될_정보"
                },
                ...
            ]
        }

        ⚠️⚠️⚠️ 계획 수립 가이드라인 ⚠️⚠️⚠️

        [문서 분석]
        원본 JSON을 직접 분석하여:
        1. 정의(definition) 섹션 찾기: 보종명, 유형1/2/3 등의 계층 구조
        2. 조건(condition) 섹션 찾기: 보험기간, 납입기간, 가입연령, 성별 등

        [언어 처리]
        - 중국어/영어 컬럼명이 많으면 ChineseToKorean / EnglishToKorean 사용
        - 순수 한국어면 생략

        [Tool 선택 원칙]
        - 단순한 표 구조 → Rule 기반 Tool (DefinitionSimpleTableRule, ConditionSimpleTableRule)
        - 복잡한 구조 → Hybrid 또는 LLM Tool
        - 소제목이 있으면 → SubtitleMapper 계열
        - 수식(min, max)이 있으면 → FormulaEvaluator

        [일반적인 플로우]
        1. (필요시) 언어 정규화 (ChineseToKorean / EnglishToKorean)
        2. Definition 추출 (DefinitionRule/LLM/Hybrid 중 선택)
        3. Condition 추출 (ConditionRule/LLM/Hybrid 중 선택)
        4. 필요시 추가 처리 (FormulaEvaluator, RowspanHandler 등)
        5. 매핑 & 생성 (Mapping, CartesianProduct)
        6. 정규화 & 검증 (CodeNormalizer, UnitConverter, Normalize, ValidationLight)
        7. 최종 출력 (FinalWriter)

        metadata 필드 작성 규칙:

           A) Definition 추출 단계:
              - 원본 JSON의 elements를 순회하며 정의 섹션 찾기
              - 해당 섹션의 index, paragraph_index 파악
              {
                  "section_index": 정의_섹션의_인덱스,
                  "paragraph_index": 주요_표의_paragraph_인덱스,
                  "access_path": "elements[X].paragraphs[Y].table.table_elements",
                  "hierarchy_info": {
                      "depth": 계층_깊이_예상값,
                      "columns": ["컬럼명들"]
                  },
                  "target_columns": ["컬럼명들"]
              }

              ⚠️ access_path의 X, Y는 실제 section_index, paragraph_index로 치환하라!

           B) Condition 추출 단계:
              - 원본 JSON에서 조건 섹션 찾기
              {
                  "section_index": 조건_섹션의_인덱스,
                  "access_path": "elements[X].paragraphs",
                  "has_subtitles": true/false,
                  "formula_present": true/false
              }

              ⚠️ access_path의 X는 실제 section_index로 치환하라!

        [시스템 전체 목표]
        - 가입가능조건 JSON 생성 (아래 타겟 스키마 형식)

        [Planner(너)의 역할]
        - 위 목표를 달성하기 위해 Executor가 실행할 plan(Tool 목록 + metadata)을 수립
        - 출력: plan만 (reasoning 없이!)

        [Executor의 역할] (참고용)
        - Planner가 수립한 plan을 단계별로 실행
        - 출력: 가입가능조건 JSON (타겟 스키마 형식)

        [타겟 스키마] (Executor가 최종 생성할 형식)
        %SCHEMA_LINES%

        [사용 가능한 Tool]
        %TOOL_LINES%

        [문서 원본]
        ```json
        %RAW_JSON%
        ```

        위 원본 문서를 직접 분석하여 plan만 생성하라. reasoning은 생략하라.
        한국어로 작성하라.
        """

    # 템플릿 변수 치환
    prompt = prompt_template.replace("%SCHEMA_LINES%", schema_lines)
    prompt = prompt.replace("%TOOL_LINES%", tool_lines)
    prompt = prompt.replace("%RAW_JSON%", raw_json)

    return prompt.strip()


def collect_targets(paths):
    """JSON 파일 수집"""
    targets = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            targets.extend(sorted(path.glob("*.json")))
        elif path.exists():
            targets.append(path)
        else:
            print(f"[SKIP] {path} (존재하지 않는 경로)")
    return targets


def main():
    targets = collect_targets(BASE_INPUT_PATHS)
    if not targets:
        print("[WARN] 처리할 JSON 파일이 없습니다.")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    for path in targets:
        print(f"\n{'='*60}")
        print(f"Processing: {path.name}")
        print(f"{'='*60}")

        raw_text = path.read_text(encoding="utf-8")
        if MAX_CHARS and len(raw_text) > MAX_CHARS:
            raw_text = raw_text[:MAX_CHARS] + "\n... (truncated)"

        prompt = build_prompt(raw_text)

        # LLM 호출 (시간 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Direct Planner Agent (No CoT). 원본 JSON을 직접 받아 추론 과정 없이 실행 계획(plan)만 바로 생성한다. 간결하고 효율적인 계획을 수립한다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=6000,  # CoT 없으므로 더 적은 토큰
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

        result_text = response.choices[0].message.content

        print(f"\n=== Generated Plan (No CoT) ===")
        print(result_text)

        # 마크다운 코드 블록 제거
        if result_text.strip().startswith("```"):
            lines = result_text.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result_text = "\n".join(lines)

        # 결과 저장 (plan_no_cot/ 디렉토리)
        result_dir = path.parent / "plan_no_cot"
        result_dir.mkdir(exist_ok=True)

        out_path = result_dir / f"{path.stem}_plan_no_cot.json"

        try:
            result_obj = json.loads(result_text)

            # 메타데이터 추가
            result_obj["_metadata"] = {
                "model": DEFAULT_MODEL,
                "method": "direct_plan_no_cot",
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
                json.dumps(result_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✅ Plan (No CoT) 저장 성공: {out_path}")
        except Exception as e:
            print(f"\n⚠️  JSON 파싱 실패, 원문 저장: {e}")
            out_path.write_text(result_text, encoding="utf-8")
            print(f"   원문 저장: {out_path}")


if __name__ == "__main__":
    main()
