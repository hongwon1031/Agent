"""
LLM 기반 정보 추출 검증 v2
- 전체 JSON 데이터를 LLM에게 제공
- 사람처럼 문서를 읽고 판단
- Few-shot 예제 포함
"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@dataclass
class DefinitionExtraction:
    """정의 섹션 추출 결과"""
    section_title: str
    section_index: int
    보종명: str
    유형_계층: List[Dict]
    confidence: float
    raw_data: Dict


@dataclass
class ConditionExtraction:
    """조건 섹션 추출 결과"""
    section_title: str
    section_index: int
    유형별_조건: List[Dict]
    confidence: float
    raw_data: Dict


@dataclass
class ExtractionResult:
    """전체 추출 결과"""
    filename: str
    definition: Optional[DefinitionExtraction]
    condition: Optional[ConditionExtraction]
    success: bool
    errors: List[str]


class LLMExtractor:
    def __init__(self, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def extract_definitions(self, document: Dict) -> Optional[DefinitionExtraction]:
        """
        LLM이 전체 문서를 읽고 정의 섹션을 찾아냄
        """
        # 문서 데이터를 JSON 문자열로 변환 (LLM이 읽기 쉽게)
        if isinstance(document, list):
            document = document[0] if document else {}

        doc_json = json.dumps(document, ensure_ascii=False, indent=2)

        # 토큰 제한을 위해 필요시 요약 (GPT-4o는 128k 토큰 지원하므로 대부분 OK)
        if len(doc_json) > 100000:
            doc_json = doc_json[:100000] + "\n... (truncated)"

        prompt = f"""당신은 보험 약관 문서 분석 전문가입니다.

다음 JSON 문서를 읽고 **보험 상품의 계층 구조(보종명, 유형1, 유형2 등)를 정의하는 섹션**을 찾아주세요.

문서:
```json
{doc_json}
```

찾아야 할 것:
1. 섹션 제목: "보험종목의 명칭", "보험상품의 정의" 등 (다양할 수 있음)
2. 보종명: 전체 상품명
3. 유형 계층: 유형1, 유형2 등의 계층 구조 (표 형태로 제공되는 경우 많음)

출력 형식 (JSON):
{{
  "section_title": "찾은 섹션의 제목",
  "section_index": 섹션의 인덱스 (elements 배열에서의 위치, 0부터 시작),
  "보종명": "전체 상품명",
  "유형_계층": [
    {{
      "유형1": "값1",
      "유형2": ["값2-1", "값2-2"],
      ...
    }}
  ],
  "confidence": 0.0에서 1.0 사이의 확신도
}}

예시:
만약 "1. 보험종목의 명칭" 섹션에 다음과 같은 표가 있다면:
| 명칭 | 명칭_1 | 보험종목 |
| 경증이상치매보장특약 | 경증이상치매 보장계약 | 해약환급금 미지급형 |
| 경증이상치매보장특약 | 경증이상치매 보장계약 | 일반형 |

출력:
{{
  "section_title": "1. 보험종목의 명칭",
  "section_index": 0,
  "보종명": "경증이상치매보장특약(무배당, 해약환급금 미지급형)",
  "유형_계층": [
    {{
      "유형1": "해약환급금 미지급형",
      "유형2": ["경증이상치매 보장계약"]
    }},
    {{
      "유형1": "일반형",
      "유형2": ["경증이상치매 보장계약"]
    }}
  ],
  "confidence": 0.95
}}

주의사항:
- 실제 문서에 존재하는 정보만 추출
- 표의 rowspan/colspan을 고려하여 계층 구조 파악
- 찾지 못한 경우 null 반환
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "보험 약관 문서 분석 전문가"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("section_title"):
                return None

            return DefinitionExtraction(
                section_title=result["section_title"],
                section_index=result.get("section_index", -1),
                보종명=result.get("보종명", ""),
                유형_계층=result.get("유형_계층", []),
                confidence=result.get("confidence", 0.0),
                raw_data=result
            )

        except Exception as e:
            print(f"[ERROR] Definition extraction failed: {e}")
            return None

    def extract_conditions(self, document: Dict) -> Optional[ConditionExtraction]:
        """
        LLM이 전체 문서를 읽고 가입 조건 섹션을 찾아냄
        """
        if isinstance(document, list):
            document = document[0] if document else {}

        doc_json = json.dumps(document, ensure_ascii=False, indent=2)

        if len(doc_json) > 100000:
            doc_json = doc_json[:100000] + "\n... (truncated)"

        prompt = f"""당신은 보험 약관 문서 분석 전문가입니다.

다음 JSON 문서를 읽고 **가입 가능 조건(보험기간, 납입기간, 가입 연령)을 담은 섹션**을 찾아주세요.

문서:
```json
{doc_json}
```

찾아야 할 것:
1. 섹션 제목: "보험기간, 보험료 납입기간...", "가입 조건" 등
2. 각 유형별 조건 정보:
   - 보험기간 (예: "90/100세만기, 종신")
   - 납입기간 (예: "10/15/20년납")
   - 가입 연령 (예: "만15세 - 70세")
   - 성별 구분 (남자나이, 여자나이)

출력 형식 (JSON):
{{
  "section_title": "찾은 섹션의 제목",
  "section_index": 섹션의 인덱스 (0부터 시작),
  "유형별_조건": [
    {{
      "유형1": "해약환급금 미지급형",
      "유형2": "-",
      "보험기간": "90/100세만기, 종신",
      "납입기간": "10/15/20/25/30년납",
      "남자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
      "여자나이": "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
      "납입주기": "월납"
    }}
  ],
  "confidence": 0.0에서 1.0 사이의 확신도
}}

주의사항:
- 소제목(예: "가. 해약환급금 미지급형")과 표를 매칭
- 수식이 포함된 경우 그대로 추출 (예: "min[...]")
- 찾지 못한 경우 null 반환
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "보험 약관 문서 분석 전문가"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("section_title"):
                return None

            return ConditionExtraction(
                section_title=result["section_title"],
                section_index=result.get("section_index", -1),
                유형별_조건=result.get("유형별_조건", []),
                confidence=result.get("confidence", 0.0),
                raw_data=result
            )

        except Exception as e:
            print(f"[ERROR] Condition extraction failed: {e}")
            return None

    def validate_extraction(
        self,
        definition: Optional[DefinitionExtraction],
        condition: Optional[ConditionExtraction]
    ) -> bool:
        """
        추출 결과 검증 (내용 기반 단순 체크)

        Note: 나중에 Validation Agent로 분리 예정
        지금은 LLM이 뭔가 찾았고 내용이 비어있지 않으면 성공
        """
        # 정의 섹션: 보종명과 유형 계층이 있으면 OK
        if definition:
            if not definition.보종명:
                print(f"[WARN] 보종명이 비어있음")
                return False

            if not definition.유형_계층:
                print(f"[WARN] 유형_계층이 비어있음")
                return False

            print(f"[OK] Definition 추출 성공: {definition.section_title}")

        # 조건 섹션: 유형별 조건이 있으면 OK
        if condition:
            if not condition.유형별_조건:
                print(f"[WARN] 유형별_조건이 비어있음")
                return False

            print(f"[OK] Condition 추출 성공: {condition.section_title}")

        return True

    def run_test(self, data_dir: str, test_files: List[str]):
        """
        5개 샘플 파일 테스트 실행
        """
        results = []

        for idx, filename in enumerate(test_files, 1):
            print(f"\n{'='*80}")
            print(f"Test {idx}/{len(test_files)}: {filename}")
            print(f"{'='*80}")

            try:
                # 파일 로드
                file_path = os.path.join(data_dir, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    document = json.load(f)

                print("\n[1/3] Extracting definitions...")
                definition = self.extract_definitions(document)

                if definition:
                    print(f"  ✓ Found: {definition.section_title}")
                    print(f"  ✓ 보종명: {definition.보종명}")
                    print(f"  ✓ 유형 계층: {len(definition.유형_계층)}개")
                    print(f"  ✓ Confidence: {definition.confidence:.2f}")
                else:
                    print("  ✗ Not found")

                print("\n[2/3] Extracting conditions...")
                condition = self.extract_conditions(document)

                if condition:
                    print(f"  ✓ Found: {condition.section_title}")
                    print(f"  ✓ 유형별 조건: {len(condition.유형별_조건)}개")
                    print(f"  ✓ Confidence: {condition.confidence:.2f}")
                else:
                    print("  ✗ Not found")

                print("\n[3/3] Validating...")
                is_valid = self.validate_extraction(definition, condition)

                success = definition is not None and condition is not None and is_valid

                result = ExtractionResult(
                    filename=filename,
                    definition=definition,
                    condition=condition,
                    success=success,
                    errors=[]
                )

                results.append(result)

                print(f"\n{'='*80}")
                print(f"Result: {'✓ SUCCESS' if success else '✗ FAILED'}")
                print(f"{'='*80}")

            except Exception as e:
                print(f"\n[ERROR] {e}")
                results.append(ExtractionResult(
                    filename=filename,
                    definition=None,
                    condition=None,
                    success=False,
                    errors=[str(e)]
                ))

        # 최종 요약
        self._print_summary(results)

        return results

    def _print_summary(self, results: List[ExtractionResult]):
        """
        테스트 결과 요약 출력
        """
        print(f"\n\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")

        total = len(results)
        success_count = sum(1 for r in results if r.success)
        fail_count = total - success_count

        print(f"\nTotal: {total}")
        print(f"Success: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"Success Rate: {(success_count / total * 100) if total > 0 else 0:.1f}%")

        print(f"\nDetailed Results:")
        for result in results:
            status = "✓" if result.success else "✗"
            print(f"  {status} {result.filename}")

            if result.definition:
                print(f"     - Definition: {result.definition.section_title} (conf: {result.definition.confidence:.2f})")
            else:
                print(f"     - Definition: NOT FOUND")

            if result.condition:
                print(f"     - Condition: {result.condition.section_title} (conf: {result.condition.confidence:.2f})")
            else:
                print(f"     - Condition: NOT FOUND")

        print(f"\n{'='*80}\n")


def main():
    data_dir = r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\test_cases"

    # test_files = [
    #     "(간편)[3-100%장해형]재해장해특약(무배당__해약환급금_미지급형)_parsed.json",
    #     "(간편)통합암(전이포함)진단특약TC(무배당, 해약환급금 미지급형)_parsed.json",
    #     "경증이상치매보장특약(무배당, 해약환급금 미지급형)_parsed.json",
    #     "신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json",
    #     "신한종신보험 패밀리케어(무배당, 해약환급금 일부지급형)_parsed.json"
    # ]
    test_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]

    print("="*80)
    print("LLM 기반 정보 추출 검증 v2")
    print("Model: gpt-4o")
    print("="*80)

    extractor = LLMExtractor(model="gpt-4o")
    results = extractor.run_test(data_dir, test_files)
    

    # 결과 저장
    output_file = "test_results_llm_extraction.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump([
            {
                "filename": r.filename,
                "success": r.success,
                "definition": {
                    "section_title": r.definition.section_title,
                    "보종명": r.definition.보종명,
                    "유형_계층": r.definition.유형_계층,
                    "confidence": r.definition.confidence
                } if r.definition else None,
                "condition": {
                    "section_title": r.condition.section_title,
                    "유형별_조건": r.condition.유형별_조건,
                    "confidence": r.condition.confidence
                } if r.condition else None,
                "errors": r.errors
            }
            for r in results
        ], f, ensure_ascii=False, indent=2)

    print(f"\n결과가 {output_file}에 저장되었습니다.")


if __name__ == "__main__":
    main()
