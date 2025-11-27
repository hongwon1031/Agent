"""
Simple Replanner for Prototype Agent
"""
from openai import OpenAI
import json
import os
from typing import List, Dict
from executor import ToolCall
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")


class SimpleReplanner:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def create_initial_plan(self, doc: List[Dict], doc_analysis: Dict = None) -> List[ToolCall]:
        """최초 Plan 생성"""

        # Location 정보 추출
        location_info = ""
        if doc_analysis and "document_analysis" in doc_analysis:
            def_section = doc_analysis["document_analysis"].get("definition_section", {})
            location = def_section.get("location", {})

            location_info = f"""
# Location 정보 (document_analysis에서 추출)
- section_index: {def_section.get('section_index', 0)}
- primary_table_index: {location.get('primary_table_index', 0)}
- table paragraph indices: {location.get('paragraph_indices', {}).get('tables', [])}

**중요**: 위 location 정보를 Tool의 parameters로 사용하세요!
예: {{"section_index": {def_section.get('section_index', 0)}, "paragraph_index": {location.get('primary_table_index', 0)}}}
"""

        prompt = f"""
당신은 보험 약관 문서에서 정의 섹션의 모든 경우의 수를 추출하는 Planner입니다.

# 사용 가능한 Tools

1. **simple_split**: 단순 / 분리만 수행 (Cartesian Product 없음)
   - params: {{"section_index": int, "paragraph_index": int}}
   - 장점: 가장 빠름
   - 단점: 모든 경우의 수를 생성하지 못함

2. **column_cartesian**: 각 열을 독립적으로 / split 후 Cartesian Product 생성
   - params: {{"section_index": int, "paragraph_index": int}}
   - ⚠️ **파라미터 주의**: section_index와 paragraph_index만 사용! key_map, replace_newline 같은 파라미터는 존재하지 않음
   - 장점: 자동으로 키 매핑, Cartesian Product 생성
   - 단점: \\n을 /로 치환해서 보종명이 잘릴 수 있음

3. **row_aware_cartesian**: 행별 보종명 + rowspan 고려한 정확한 조합
   - params: {{"section_index": int, "paragraph_index": int, "key_mapping": {{...}}}}
   - 장점: 사용자 정의 키 매핑 가능
   - 단점: \\n을 /로 치환해서 보종명이 잘릴 수 있음

4. **llm_cartesian**: LLM 기반 테이블 파싱 및 Cartesian Product 생성
   - params: {{"section_index": int, "paragraph_index": int}}
   - ⚠️ **파라미터 주의**: section_index와 paragraph_index만 사용! input_data, output_schema 같은 파라미터는 존재하지 않음
   - 올바른 예시: {{"tool_name": "llm_cartesian", "parameters": {{"section_index": 0, "paragraph_index": 0}}}}
   - 잘못된 예시: {{"tool_name": "llm_cartesian", "parameters": {{"input_data": ..., "output_schema": ...}}}}
   - 장점: 가장 정확, 문맥 이해, \\n 처리 완벽, 예외 케이스 자동 대응
   - 단점: 느림, 비용 높음 (gpt-4o 사용)
   - **사용 시기**: Rule-based Tool 실패 시 최후 수단으로 사용

{location_info}

# 문서 구조 미리보기
{json.dumps(self._get_document_preview(doc, doc_analysis), ensure_ascii=False, indent=2)}

# Task
"1. 보험종목의 명칭" 섹션의 테이블에서 고정 스키마(보종명, 유형1, 유형2)로 모든 경우의 수를 추출하세요.

**중요**: "간편심사(315)형/간편심사(335)형/..." 같은 슬래시 구분 값을 파싱해서 Cartesian Product 생성이 핵심입니다.

# 예상 출력 형태
[
  {{"보종명": "...", "유형1": "해약환급금 미지급형", "유형2": "간편심사(315)형"}},
  {{"보종명": "...", "유형1": "해약환급금 미지급형", "유형2": "간편심사(335)형"}},
  ...
]

# 출력 형식 (JSON만 반환)
{{
  "reasoning": "도구 선택 근거 (어떤 섹션/테이블을 사용할지, 왜 이 Tool을 선택했는지)",
  "plan": [
    {{"tool_name": "column_cartesian", "parameters": {{"section_index": 0, "paragraph_index": 0}}}}
  ]
}}
"""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a planner that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ]
        )

        result = json.loads(response.choices[0].message.content)
        print(f"\n📋 [Initial Plan Reasoning]\n{result['reasoning']}\n")

        return [ToolCall(**tc) for tc in result["plan"]]

    def replan(self, doc: List[Dict], doc_analysis: Dict, execution_log: List[Dict]) -> List[ToolCall]:
        """실패한 실행 기록을 바탕으로 재계획"""
        prompt = f"""
이전 실행이 실패했습니다. 다른 접근 방법으로 재계획하세요.

# 실행 기록
{json.dumps(execution_log, ensure_ascii=False, indent=2)}

# 문서 구조
{json.dumps(self._get_document_preview(doc), ensure_ascii=False, indent=2)}

# Task
실패 원인을 분석하고, 다른 Tool이나 다른 parameters로 재시도하세요.

**목표**: 고정 스키마(보종명, 유형1, 유형2)로 모든 경우의 수 생성

# 사용 가능한 Tools
1. simple_split:
   - params: {{"section_index": int, "paragraph_index": int}}

2. column_cartesian:
   - params: {{"section_index": int, "paragraph_index": int}}
   - ⚠️ key_map, replace_newline 같은 파라미터는 존재하지 않음!

3. row_aware_cartesian:
   - params: {{"section_index": int, "paragraph_index": int, "key_mapping": {{...}}}}

4. llm_cartesian: **Validation 실패 시 권장**
   - params: {{"section_index": int, "paragraph_index": int}}
   - ⚠️ input_data, output_schema 같은 파라미터는 존재하지 않음!
   - 올바른 예: {{"tool_name": "llm_cartesian", "parameters": {{"section_index": 0, "paragraph_index": 0}}}}

# 출력 형식 (JSON만 반환)
{{
  "failure_analysis": "실패 원인 분석",
  "new_strategy": "새로운 접근 전략 (왜 이 Tool을 선택했는지)",
  "plan": [
    {{"tool_name": "...", "parameters": {{...}}}}
  ]
}}
"""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a planner that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ]
        )

        result = json.loads(response.choices[0].message.content)
        print(f"\n🔄 [Replan Analysis]\n{result['failure_analysis']}")
        print(f"\n🎯 [New Strategy]\n{result['new_strategy']}\n")

        return [ToolCall(**tc) for tc in result["plan"]]

    def _get_document_preview(self, doc: List[Dict], doc_analysis: Dict = None) -> Dict:
        """문서 구조 미리보기"""

        # doc_analysis가 있으면 그것을 우선 사용
        if doc_analysis and "document_analysis" in doc_analysis:
            def_section = doc_analysis["document_analysis"].get("definition_section", {})
            return {
                "from_doc_analysis": {
                    "section_index": def_section.get("section_index"),
                    "title": def_section.get("title"),
                    "columns": def_section.get("columns", []),
                    "location": def_section.get("location", {}),
                    "hierarchy_depth": def_section.get("sample_data", {}).get("hierarchy_depth")
                }
            }

        # doc_analysis가 없으면 원본 문서에서 추출
        preview = []
        if not doc or len(doc) == 0:
            return {"error": "Empty document"}

        for i, section in enumerate(doc[0].get("elements", [])[:3]):  # 첫 3개 섹션만
            section_info = {
                "section_index": i,
                "title": section.get("title", "Unknown"),
                "paragraphs": []
            }

            for j, para in enumerate(section.get("paragraphs", [])):
                para_info = {
                    "paragraph_index": j,
                    "type": para.get("type", "unknown")
                }

                if para["type"] == "table" and para.get("table", {}).get("table_elements"):
                    # 테이블 첫 행만 미리보기
                    first_row = para["table"]["table_elements"][0]
                    para_info["table_preview"] = {
                        "keys": list(first_row.keys()),
                        "first_row_sample": {
                            k: v[:50] + "..." if len(v) > 50 else v
                            for k, v in first_row.items()
                        },
                        "total_rows": len(para["table"]["table_elements"])
                    }

                section_info["paragraphs"].append(para_info)

            preview.append(section_info)

        return {"from_original_doc": preview}
