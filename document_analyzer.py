"""
DocumentAnalyzerAgent - 문서 구조 분석 전담 Agent

역할:
- 전체 JSON 문서를 받아 LLM으로 구조 분석
- information_requirements를 기반으로 필요한 섹션 위치 탐지
- Planner가 사용할 수 있는 구조적 정보 반환

Phase 2: Planner와 분리된 독립 Agent
"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SectionLocation:
    """섹션 위치 정보"""
    section_index: int
    section_title: str
    confidence: float
    table_location: Optional[Dict] = None
    subsections: Optional[List[Dict]] = None
    raw_data: Optional[Dict] = None


@dataclass
class AnalysisResult:
    """문서 구조 분석 결과"""
    requirement_key: str  # "product_hierarchy", "enrollment_conditions" 등
    location: Optional[SectionLocation]
    success: bool
    error: Optional[str] = None


class DocumentAnalyzerAgent:
    """
    문서 구조 분석 전담 Agent

    Planner로부터 information_requirements를 받아서
    원본 JSON 문서에서 해당 정보가 어디에 있는지 LLM으로 찾아냄
    """

    def __init__(self, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def analyze_structure(
        self,
        document: Dict,
        info_requirements: Dict[str, Any]
    ) -> Dict[str, AnalysisResult]:
        """
        메인 진입점: 문서 구조 분석

        Args:
            document: 원본 JSON 문서 (전체)
            info_requirements: Planner가 생성한 정보 요구사항
                예시: {
                    "product_hierarchy": {
                        "description": "...",
                        "keywords": [...],
                        "purpose": "..."
                    },
                    "enrollment_conditions": {...}
                }

        Returns:
            각 requirement별 섹션 위치 정보
        """
        print(f"\n{'='*80}")
        print("DocumentAnalyzerAgent - 문서 구조 분석 시작")
        print(f"{'='*80}")

        results = {}

        for req_key, req_info in info_requirements.items():
            print(f"\n[분석 중] {req_key}: {req_info.get('description', '')}")

            try:
                location = self._analyze_single_requirement(document, req_key, req_info)

                if location:
                    print(f"  ✓ 발견: {location.section_title} (confidence: {location.confidence:.2f})")
                    results[req_key] = AnalysisResult(
                        requirement_key=req_key,
                        location=location,
                        success=True
                    )
                else:
                    print(f"  ✗ 찾지 못함")
                    results[req_key] = AnalysisResult(
                        requirement_key=req_key,
                        location=None,
                        success=False,
                        error="Section not found"
                    )

            except Exception as e:
                print(f"  ✗ 오류: {e}")
                results[req_key] = AnalysisResult(
                    requirement_key=req_key,
                    location=None,
                    success=False,
                    error=str(e)
                )

        print(f"\n{'='*80}")
        print("문서 구조 분석 완료")
        print(f"{'='*80}\n")

        return results

    def _analyze_single_requirement(
        self,
        document: Dict,
        req_key: str,
        req_info: Dict
    ) -> Optional[SectionLocation]:
        """
        단일 requirement에 대한 섹션 찾기
        """
        # 문서를 JSON 문자열로 변환
        if isinstance(document, list):
            document = document[0] if document else {}

        doc_json = json.dumps(document, ensure_ascii=False, indent=2)

        # 토큰 제한 처리
        if len(doc_json) > 100000:
            doc_json = doc_json[:100000] + "\n... (truncated)"

        # LLM 프롬프트 생성
        prompt = self._build_analysis_prompt(doc_json, req_key, req_info)

        # LLM 호출
        result = self._call_llm(prompt)

        if not result or not result.get("section_title"):
            return None

        # SectionLocation 객체 생성
        return SectionLocation(
            section_index=result.get("section_index", -1),
            section_title=result["section_title"],
            confidence=result.get("confidence", 0.0),
            table_location=result.get("table_location"),
            subsections=result.get("subsections"),
            raw_data=result
        )

    def _build_analysis_prompt(
        self,
        doc_json: str,
        req_key: str,
        req_info: Dict
    ) -> str:
        """
        LLM 프롬프트 생성

        requirement별로 맞춤형 프롬프트 생성
        """
        description = req_info.get("description", "")
        keywords = req_info.get("keywords", [])
        purpose = req_info.get("purpose", "")

        # 기본 템플릿
        base_prompt = f"""당신은 보험 약관 문서 분석 전문가입니다.

다음 JSON 문서를 읽고 **{description}** 정보를 담고 있는 섹션을 찾아주세요.

문서:
```json
{doc_json}
```

목적: {purpose}

관련 키워드: {', '.join(keywords)}

찾아야 할 것:
1. 섹션 제목 (예: "1. 보험종목의 명칭", "3. 보험기간, ..." 등)
2. 섹션 인덱스 (elements 배열에서의 위치, 0부터 시작)
3. 표가 있다면 표의 위치 정보
4. 하위 섹션이 있다면 하위 섹션 정보

출력 형식 (JSON):
{{
  "section_title": "찾은 섹션의 제목",
  "section_index": 섹션의 인덱스 (0부터 시작),
  "confidence": 0.0에서 1.0 사이의 확신도,
  "table_location": {{
    "element_index": 표가 있는 element의 인덱스,
    "type": "table"
  }},
  "subsections": [
    {{
      "title": "하위 섹션 제목",
      "element_index": 인덱스
    }}
  ]
}}

주의사항:
- 실제 문서에 존재하는 정보만 추출
- 찾지 못한 경우 null 반환
- 확신도는 정확히 평가
"""

        # requirement별 특화 프롬프트 추가
        if req_key == "product_hierarchy":
            specialized_prompt = """
예시:
만약 "1. 보험종목의 명칭" 섹션에 다음과 같은 표가 있다면:
| 명칭 | 명칭_1 | 보험종목 |
| 경증이상치매보장특약 | 경증이상치매 보장계약 | 해약환급금 미지급형 |

출력:
{{
  "section_title": "1. 보험종목의 명칭",
  "section_index": 0,
  "confidence": 0.95,
  "table_location": {{
    "element_index": 2,
    "type": "table"
  }}
}}
"""
            return base_prompt + specialized_prompt

        elif req_key == "enrollment_conditions":
            specialized_prompt = """
예시:
만약 "3. 보험기간, 보험료 납입기간..." 섹션에:
- 가. 해약환급금 미지급형
- 나. 일반형
이러한 하위 섹션이 있고 각각 표가 있다면:

출력:
{{
  "section_title": "3. 보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
  "section_index": 2,
  "confidence": 0.90,
  "subsections": [
    {{"title": "가. 해약환급금 미지급형", "element_index": 5}},
    {{"title": "나. 일반형", "element_index": 8}}
  ]
}}
"""
            return base_prompt + specialized_prompt

        else:
            # 기타 requirement는 기본 템플릿만 사용
            return base_prompt

    def _call_llm(self, prompt: str) -> Optional[Dict]:
        """
        LLM 호출 및 결과 파싱
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "보험 약관 문서 구조 분석 전문가"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            print(f"[ERROR] LLM 호출 실패: {e}")
            return None

    def _validate_result(self, result: Dict[str, AnalysisResult]) -> bool:
        """
        분석 결과 검증

        모든 필수 requirement가 성공적으로 찾아졌는지 확인
        """
        required_keys = ["product_hierarchy", "enrollment_conditions"]

        for key in required_keys:
            if key not in result or not result[key].success:
                print(f"[WARN] 필수 정보 누락: {key}")
                return False

        return True


def test_document_analyzer():
    """
    DocumentAnalyzerAgent 독립 테스트
    """
    print("="*80)
    print("DocumentAnalyzerAgent 독립 테스트")
    print("="*80)

    # 테스트 데이터 로드
    data_dir = r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과"
    test_file = "신한SOL암보험(무배당, 해약환급금 미지급형)_parsed.json"

    file_path = os.path.join(data_dir, test_file)

    with open(file_path, 'r', encoding='utf-8') as f:
        document = json.load(f)

    # Information requirements 정의 (Planner가 생성한 것처럼)
    info_requirements = {
        "product_hierarchy": {
            "description": "보험 상품의 계층 구조 (명칭, 유형 분류)",
            "keywords": ["보험종목", "명칭", "상품", "유형", "종목", "정의", "구조"],
            "purpose": "정의 섹션을 찾아 상품의 계층 구조를 파악"
        },
        "enrollment_conditions": {
            "description": "가입 가능 조건 (기간, 연령, 성별)",
            "keywords": ["가입", "조건", "보험기간", "납입기간", "연령", "나이", "피보험자", "기간"],
            "purpose": "조건 섹션을 찾아 가입 가능 조건을 추출"
        }
    }

    # DocumentAnalyzerAgent 실행
    analyzer = DocumentAnalyzerAgent(model="gpt-4o")
    results = analyzer.analyze_structure(document, info_requirements)

    # 결과 출력
    print("\n" + "="*80)
    print("분석 결과")
    print("="*80)

    for req_key, analysis_result in results.items():
        print(f"\n[{req_key}]")

        if analysis_result.success:
            loc = analysis_result.location
            print(f"  ✓ 성공")
            print(f"  - 섹션: {loc.section_title}")
            print(f"  - 인덱스: {loc.section_index}")
            print(f"  - Confidence: {loc.confidence:.2f}")

            if loc.table_location:
                print(f"  - 표 위치: element[{loc.table_location.get('element_index')}]")

            if loc.subsections:
                print(f"  - 하위 섹션: {len(loc.subsections)}개")
                for subsec in loc.subsections:
                    print(f"    - {subsec.get('title')}")
        else:
            print(f"  ✗ 실패: {analysis_result.error}")

    # 검증
    is_valid = analyzer._validate_result(results)
    print(f"\n{'='*80}")
    print(f"전체 검증 결과: {'✓ 성공' if is_valid else '✗ 실패'}")
    print(f"{'='*80}\n")

    return results


if __name__ == "__main__":
    test_document_analyzer()
