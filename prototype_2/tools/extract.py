"""
Tools for extracting structured data from definition tables or text.
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class RuleExtractTool(SimpleTool):
    """
    Rule-based extraction from tables.
    Assumes standard table structure with rows and cells.
    """

    def get_description(self) -> str:
        return "Rule-based data extraction from tables with standard structure"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "section_index": {
                "type": "int",
                "description": "Section index in document",
                "required": True
            },
            "paragraph_index": {
                "type": "int",
                "description": "Paragraph index containing the table",
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
            section_idx = params["section_index"]
            para_idx = params["paragraph_index"]

            # Access table
            section = doc[0]["elements"][section_idx]
            paragraph = section["paragraphs"][para_idx]

            if "table" not in paragraph:
                return self._create_error(
                    f"No table found at section {section_idx}, paragraph {para_idx}"
                )

            table = paragraph["table"]
            table_elements = table.get("table_elements", [])

            if not table_elements:
                return self._create_error("Table is empty")

            # Extract data - handle both parsed dict format and cells format
            if table_elements and isinstance(table_elements[0], dict):
                # Check if it's already parsed as dict (keys are column names)
                if "cells" not in table_elements[0]:
                    # Already parsed format: [{"명칭": "...", "보험종목": "...", ...}, ...]
                    header = list(table_elements[0].keys())
                    data = [list(row.values()) for row in table_elements]
                else:
                    # Cells format: [{"cells": [{"text": "..."}, ...]}, ...]
                    data_rows = []

                    for row in table_elements:
                        cells = row.get("cells", [])
                        if not cells:
                            continue

                        # Check if this is a comment row
                        first_cell = cells[0].get("text", "").strip()
                        if first_cell.startswith(("※", "주:", "주)", "* ", "- ")):
                            continue  # Skip comment rows

                        # Extract cell texts
                        row_data = [cell.get("text", "").strip() for cell in cells]
                        data_rows.append(row_data)

                    if len(data_rows) < 2:
                        return self._create_error(
                            "Not enough data rows (need at least header + 1 data row)"
                        )

                    # First row as header
                    header = data_rows[0]
                    data = data_rows[1:]
            else:
                return self._create_error("Invalid table format")

            return self._create_success({
                "header": header,
                "data": data,
                "row_count": len(data)
            })

        except KeyError as e:
            return self._create_error(f"Invalid document structure: {str(e)}")
        except Exception as e:
            return self._create_error(f"RuleExtractTool error: {str(e)}")


class LLMExtractTool(SimpleTool):
    """
    LLM-based extraction from tables or text.
    Can handle non-standard formats, comments, special characters, etc.
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_description(self) -> str:
        return "LLM-based data extraction handling complex formats and edge cases"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "section_index": {
                "type": "int",
                "description": "Section index in document",
                "required": True
            },
            "paragraph_index": {
                "type": "int",
                "description": "Paragraph index containing data",
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
            section_idx = params["section_index"]
            para_idx = params["paragraph_index"]
            custom_instruction = params.get("instruction", "")

            # Access data
            section = doc[0]["elements"][section_idx]
            paragraph = section["paragraphs"][para_idx]

            # Extract content (table or text)
            content = None
            content_type = None

            if "table" in paragraph:
                content = paragraph["table"].get("table_elements", [])
                content_type = "table"
            elif "text" in paragraph:
                content = paragraph["text"]
                content_type = "text"
            else:
                return self._create_error("Paragraph has neither table nor text")

            # Prepare content for LLM
            if content_type == "table":
                # Serialize table structure
                table_data = []
                for row in content:
                    cells = row.get("cells", [])
                    row_texts = [cell.get("text", "") for cell in cells]
                    table_data.append(row_texts)
                content_str = json.dumps(table_data, ensure_ascii=False, indent=2)
            else:
                content_str = content

            # LLM prompt
            prompt = f"""다음은 보험 문서의 정의 데이터입니다.

콘텐츠 타입: {content_type}

데이터:
{content_str}

**목표**: 이 데이터에서 header와 data rows를 추출하세요.

**주의사항**:
1. 주석 행은 제외 (※, 주:, 주), * , - 등으로 시작하는 행)
2. ASCII 코드 형태의 특수문자는 원래 문자로 변환
3. Header는 첫 번째 의미있는 행
4. Data는 실제 정의 항목들

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "header": ["컬럼1", "컬럼2", ...],
  "data": [
    ["값1", "값2", ...],
    ["값1", "값2", ...],
    ...
  ],
  "excluded_rows": ["제외된 행1", "제외된 행2", ...],
  "notes": "<처리 과정 설명>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=3000
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("header") or not result.get("data"):
                return self._create_error(
                    f"LLM failed to extract data: {result.get('notes', 'Unknown error')}"
                )

            return self._create_success({
                "header": result["header"],
                "data": result["data"],
                "row_count": len(result["data"]),
                "excluded_rows": result.get("excluded_rows", []),
                "notes": result.get("notes", "")
            })

        except KeyError as e:
            return self._create_error(f"Invalid document structure: {str(e)}")
        except Exception as e:
            return self._create_error(f"LLMExtractTool error: {str(e)}")
