import os
import json
import time
from pathlib import Path
from textwrap import dedent

from dotenv import load_dotenv
from openai import OpenAI

from pydantic import ValidationError
from schemas import OnlyDocOutput

load_dotenv()

# GPT-4o 가격 (per 1M tokens, 2025년 1월 기준)
GPT4O_INPUT_PRICE = 2.50  # $2.50 per 1M input tokens
GPT4O_OUTPUT_PRICE = 10.00  # $10.00 per 1M output tokens

# 단순 Planner 실험용 Tool 목록 (type/latency/cost 메타 포함)


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
# gpt-5는 max_completion_tokens 사용,temperature 지원 x
# max_tokens -> max_completion_tokens
DEFAULT_MODEL = "gpt-4o"

BASE_INPUT_PATHS = [
    Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과")
]
MAX_CHARS = None  # 자르지 않고 전체 사용


def build_prompt(raw_json: str) -> str:
    
    schema_lines = "\n".join(f"- {field}" for field in TARGET_FIELDS)
    return dedent(
        f"""
        너는 Document Analyzer Agent이다. 아래 목표/스키마/도구와 원본 JSON을 참고하여
        가입가능조건 JSON을 생성하기 위한 계획을 작성하기 위해 원본 JSON의 구조를 파악해서 planner agent에게 전달해라.

        출력 형식:
        {{
            "document_analysis": {{
                "total_sections": 전체_섹션_수,
                "definition_section": {{
                    "section_index": 섹션인덱스,
                    "title": "제목",
                    "structure": "'표'/'텍스트'/'혼합'",
                    "table_count": 표_개수,
                    "columns": [컬럼명들],
                    "location": {{
                        "paragraph_indices": {{
                            "tables": [표가_있는_paragraph_인덱스들],
                            "texts": [텍스트가_있는_paragraph_인덱스들]
                        }},
                        "primary_table_index": 주요_정의_표의_paragraph_인덱스
                    }},
                    "sample_data": {{
                        "계층구조": [
                            {{
                                "level": 1,
                                "column_name": "1단계_컬럼명",
                                "values": ["1단계_모든_고유값"],
                                "description": "이_레벨의_의미"
                            }},
                            {{
                                "level": 2,
                                "column_name": "2단계_컬럼명",
                                "values": ["2단계_모든_고유값"],
                                "description": "이_레벨의_의미"
                            }},
                            {{
                                "level": 3,
                                "column_name": "3단계_컬럼명",
                                "values": ["3단계_모든_고유값"],
                                "description": "이_레벨의_의미"
                            }}
                            // 계층이 더 있으면 계속 추가
                        ],
                        "hierarchy_depth": 계층_깊이,
                        "hierarchy_tree_example": "Level1 → Level2 → Level3 → ... 형태로_실제_계층_예시"
                    }},
                    "특이사항": "구조적_특징_상세_설명",
                    "누락_위험": "누락될_수_있는_정보나_주의사항"
                }},
                "condition_section": {{
                    "section_index": 섹션인덱스,
                    "title": "제목",
                    "structure": "'표'/'텍스트'/'혼합'",
                    "table_count": 표_개수,
                    "location": {{
                        "paragraph_map": [
                            {{"index": paragraph_인덱스, "type": "title/table/text", "content": "내용_또는_table_title"}},
                            ...
                        ]
                    }},
                    "condition_hierarchy": {{
                        "has_subtitles": true/false,
                        "subtitle_mapping": [
                            {{
                                "subtitle": "소제목_내용",
                                "paragraph_index": 해당_소제목의_paragraph_인덱스,
                                "estimated_type": "이_소제목이_나타내는_유형",
                                "table_index": 바로_다음_표의_paragraph_인덱스,
                                "table_types": {{
                                    "유형1": ["표_안의_유형1_값들"],
                                    "유형2": ["표_안의_유형2_값들"],
                                    "유형3": ["표_안의_유형3_값들_있으면"]
                                }}
                            }},
                            ...
                        ],
                        "all_unique_types": {{
                            "from_subtitles": ["소제목에서_추출한_모든_유형"],
                            "from_table_column_유형1": ["표_컬럼_유형1의_모든_고유값"],
                            "from_table_column_유형2": ["표_컬럼_유형2의_모든_고유값"]
                        }},
                        "hierarchy_tree_example": "소제목 → 유형1 → 유형2 형태로_실제_계층_예시"
                    }},
                    "sample_conditions": {{
                        "보험기간": ["값1", "값2", ...],
                        "납입기간": ["값1", "값2", ...],
                        "나이_표현": ["남자나이", "여자나이", ...],
                        "has_formula": true/false,
                        "formula_examples": ["수식1", "수식2", ...]
                    }},
                    "특이사항": "조건_표현_방식_및_복잡도",
                    "누락_위험": "누락될_수_있는_조건이나_주의사항"
                }},
                "other_sections": [
                    {{"index": 인덱스, "title": "제목", "relevance": "관련성_설명"}},
                    ...
                ],
                "complexity": "단순/중간/복잡",
                "complexity_reason": "복잡도_판단_근거"
            }}
        }}

        ⚠️⚠️⚠️ 매우 중요 ⚠️⚠️⚠️

        1. definition_section 분석:

           A) location 정보 (필수!):
              - paragraphs를 순회하며 각 type(table/text)의 인덱스를 파악하라
              - primary_table_index: 주요 정의 표가 있는 paragraph 인덱스

              예시: elements[0].paragraphs가 [table, text]라면
              {{
                  "location": {{
                      "paragraph_indices": {{
                          "tables": [0],
                          "texts": [1]
                      }},
                      "primary_table_index": 0
                  }}
              }}

           B) 계층구조:
              - 표의 rowspan/colspan을 분석하여 계층이 몇 단계인지 파악
              - 각 레벨별로 column_name과 모든 고유값(values) 추출
              - 계층 레벨을 절대 섞지 말 것!

        2. condition_section 분석:

           A) location 정보 (필수!):
              - paragraph_map: 모든 paragraphs의 인덱스, 타입, 내용 나열

              예시: paragraphs가 [title("가. 주계약"), title("① 해약환급금..."), table, text]라면
              {{
                  "location": {{
                      "paragraph_map": [
                          {{"index": 0, "type": "title", "content": "가. 주계약"}},
                          {{"index": 1, "type": "title", "content": "① 해약환급금 미지급형"}},
                          {{"index": 2, "type": "table", "content": "가입가능 조건"}},
                          {{"index": 3, "type": "text", "content": "※ 보험료..."}}
                      ]
                  }}
              }}

           B) condition_hierarchy의 subtitle_mapping:
              - 각 소제목의 paragraph_index 명시
              - 바로 다음 표의 table_index 명시

              예시:
              {{
                  "subtitle": "가. 주계약",
                  "paragraph_index": 0,
                  "table_index": 2,
                  "table_types": {{...}}
              }}

        3. 접근 경로 예시:

           Definition Agent가 사용할 경로:
           ```python
           section = doc[0]["elements"][definition_section["section_index"]]
           table_idx = definition_section["location"]["primary_table_index"]
           table_elements = section["paragraphs"][table_idx]["table"]["table_elements"]
           ```

           Condition Agent가 사용할 경로:
           ```python
           section = doc[0]["elements"][condition_section["section_index"]]
           for mapping in condition_section["condition_hierarchy"]["subtitle_mapping"]:
               subtitle_para = section["paragraphs"][mapping["paragraph_index"]]
               table_para = section["paragraphs"][mapping["table_index"]]
           ```

        4. other_sections:
           - 정의/조건 섹션이 아닌 다른 섹션들도 모두 나열
           - 각 섹션이 가입조건 추출에 관련이 있는지 판단

        5. 누락_위험:
           ⚠️ 중요: 이 문서의 실제 구조적 위험 요소만 작성하라!

           정의 섹션 예시:
           - rowspan/colspan으로 계층 정보가 숨겨진 경우:
             "계층 레벨X가 rowspan으로 여러 행에 걸쳐 있어 누락 위험"
           - 컬럼명이 불명확한 경우:
             "컬럼명이 '보험종목_1' 등으로 중복되어 유형 구분 어려움"
           - 표와 텍스트가 혼합된 경우:
             "표 하단의 텍스트에 추가 정의가 있어 누락 가능"

           조건 섹션 예시:
           - "소제목과 표가 떨어져 있어 매핑 실수 가능"
           - "소제목마다 유형이 다를 수 있음"
           - "수식(min, max 등)이 복잡하여 파싱 실수 가능"
           - "여러 표로 분산되어 있어 조건 누락 위험"

        [목표]
        - '가입가능조건' JSON 생성

        [타겟 스키마]
        {schema_lines}

        [문서 원본]
        ```json
        {raw_json}
        ```
        """
    ).strip()


def collect_targets(paths):
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
        raw_text = path.read_text(encoding="utf-8")
        if MAX_CHARS and len(raw_text) > MAX_CHARS:
            raw_text = raw_text[:MAX_CHARS] + "\n... (truncated)"

        prompt = build_prompt(raw_text)

        # LLM 호출 (시간 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "꼼꼼한 Document Analyzer. 문서의 모든 paragraph 위치를 정확히 파악하여 접근 경로(location)를 제공한다."},
                {"role": "user", "content": prompt},
            ],
            temperature = 0.1,  # 더 정확한 위치 추출을 위해 낮춤
            max_tokens=4000,  # location 정보 추가로 더 증가
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
        print(f"\n{'='*60}")
        print(f"Processing: {path.name}")
        print(f"{'='*60}")
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

        print(f"\n=== Document Analysis for {path.name} ===")
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

        # 결과를 JSON 파일로 저장 (파싱 실패 시 원문 저장)
        result_dir = path.parent / "only_doc"
        result_dir.mkdir(exist_ok=True)

        out_path = result_dir / f"{path.stem}_plan.json"

        try:
            only_doc_model = OnlyDocOutput.model_validate_json(plan_text)

            # 모델을 dict로 변환하고 메타데이터 추가
            result_obj = only_doc_model.model_dump()
            result_obj["_metadata"] = {
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
                json.dumps(result_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✅ 스키마 검증된 Document Analysis 저장 성공: {out_path}")

        except ValidationError as e:
            print("\n⚠️  OnlyDocOutput 스키마 검증 실패:")
            # 에러 내용을 보기 좋게 출력
            try:
                err_obj = json.loads(e.json())
                print(json.dumps(err_obj, ensure_ascii=False, indent=2))
            except Exception:
                print(str(e))

            # 검증 실패해도 메타데이터는 추가
            try:
                result_obj = json.loads(plan_text)
                result_obj["_metadata"] = {
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
                    json.dumps(result_obj, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                out_path.write_text(plan_text, encoding="utf-8")
            print(f"   원문 저장: {out_path}")


if __name__ == "__main__":
    main()

