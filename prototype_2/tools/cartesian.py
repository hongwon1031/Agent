"""
Tool for generating Cartesian product from extracted data.
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class GenerateCartesianTool(SimpleTool):
    """
    Generates Cartesian product of all combinations from extracted data.
    Uses LLM to understand table structure and generate combinations intelligently.
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_description(self) -> str:
        return "Generate Cartesian product of all definition combinations from structured data"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "header": {
                "type": "list",
                "description": "Column headers from extracted data",
                "required": True
            },
            "data": {
                "type": "list",
                "description": "Data rows from extracted data",
                "required": True
            },
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        try:
            header = params["header"]
            data = params["data"]
            custom_instruction = params.get("instruction", "")

            if not header or not data:
                return self._create_error("Header or data is empty")

            # LLM prompt for Cartesian product generation
            prompt = f"""다음은 보험 정의 테이블의 데이터입니다.

Header: {json.dumps(header, ensure_ascii=False)}

Data:
{json.dumps(data, ensure_ascii=False, indent=2)}

**목표**: 이 데이터에서 모든 가능한 조합(Cartesian Product)을 생성하세요.

**규칙**:
1. "명칭" 또는 유사한 컬럼 → "보종명" 필드
2. 다른 컬럼들 → "유형1", "유형2", "유형3", ... 필드
3. 슬래시(/)로 구분된 값들은 각각 분리하여 조합 생성
4. 줄바꿈(\\n)은 보종명에서는 유지, 유형에서는 제거
5. 모든 가능한 조합을 생성 (Cartesian Product)
6. 중복 제거

**예시**:
입력:
- Header: ["명칭", "유형"]
- Data: [["재해장해특약\\n(무배당)", "간편심사(315)형/간편심사(335)형"]]

출력:
[
  {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(315)형"}},
  {{"보종명": "재해장해특약\\n(무배당)", "유형1": "간편심사(335)형"}}
]

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "definitions": [
    {{"보종명": "...", "유형1": "...", "유형2": "...", ...}},
    ...
  ],
  "total_count": <생성된 조합 수>,
  "notes": "<처리 과정 설명>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("definitions"):
                return self._create_error(
                    f"LLM failed to generate combinations: {result.get('notes', 'Unknown error')}"
                )

            definitions = result["definitions"]

            # Validate basic structure
            if not all(isinstance(d, dict) for d in definitions):
                return self._create_error("Invalid definition format")

            if not all("보종명" in d and "유형1" in d for d in definitions):
                return self._create_error(
                    "All definitions must have '보종명' and '유형1'"
                )

            return self._create_success({
                "definitions": definitions,
                "total_count": len(definitions),
                "notes": result.get("notes", "")
            })

        except KeyError as e:
            return self._create_error(f"Missing required parameter: {str(e)}")
        except Exception as e:
            return self._create_error(f"GenerateCartesianTool error: {str(e)}")
