"""
Tools for searching and locating definition sections in insurance documents.
"""

import os
import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv
from .base import SimpleTool, ToolResult


class RuleSearchTool(SimpleTool):
    """
    Rule-based tool to find definition sections in document.
    Looks for common patterns like "정의", "용어의 정의", etc.
    """

    def get_description(self) -> str:
        return "Rule-based search for definition sections using keyword matching"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "keywords": {
                "type": "list",
                "description": "Keywords to search for (default: ['정의', '용어'])",
                "required": False
            },
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        try:
            keywords = params.get("keywords", ["정의", "용어의 정의", "용어", "명칭", "보험종목"])

            # Search through document structure
            # doc[0]["elements"][section_index]["title"] or ["paragraphs"][i]["text"]

            found_locations = []

            if not doc or len(doc) == 0:
                return self._create_error("Document is empty")

            elements = doc[0].get("elements", [])

            for section_idx, section in enumerate(elements):
                # Check section title
                title = section.get("title", "")

                for keyword in keywords:
                    if keyword in title:
                        # Found in title, look for paragraphs with tables
                        paragraphs = section.get("paragraphs", [])
                        for para_idx, para in enumerate(paragraphs):
                            if "table" in para:
                                found_locations.append({
                                    "section_index": section_idx,
                                    "paragraph_index": para_idx,
                                    "title": title,
                                    "match_type": "title",
                                    "keyword": keyword
                                })

            if not found_locations:
                return self._create_error(
                    f"No definition sections found with keywords: {keywords}"
                )

            # Return the first match (can be extended to return all)
            return self._create_success({
                "location": found_locations[0],
                "all_matches": found_locations
            })

        except Exception as e:
            return self._create_error(f"RuleSearchTool error: {str(e)}")


class LLMSearchTool(SimpleTool):
    """
    LLM-based tool to find definition sections.
    More flexible than rule-based, can understand context.
    """

    def __init__(self):
        super().__init__()
        load_dotenv(dotenv_path=r"c:\Users\NT-165\Desktop\Project\Toy\.env")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_description(self) -> str:
        return "LLM-based search for definition sections with context understanding"

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "instruction": {
                "type": "string",
                "description": "Optional custom instruction from replanner",
                "required": False
            }
        }

    def execute(self, doc: List[Dict], params: Dict[str, Any]) -> ToolResult:
        try:
            custom_instruction = params.get("instruction", "")

            # Extract document structure for LLM
            if not doc or len(doc) == 0:
                return self._create_error("Document is empty")

            elements = doc[0].get("elements", [])

            # Create simplified structure for LLM
            doc_structure = []
            for idx, section in enumerate(elements):
                title = section.get("title", "")
                para_count = len(section.get("paragraphs", []))
                has_tables = any("table" in p for p in section.get("paragraphs", []))

                doc_structure.append({
                    "section_index": idx,
                    "title": title,
                    "paragraph_count": para_count,
                    "has_tables": has_tables
                })

            # LLM prompt
            prompt = f"""다음은 보험 문서의 섹션 구조입니다.

문서 구조:
{doc_structure}

**목표**: "정의" 또는 "용어의 정의"에 해당하는 섹션을 찾아 section_index를 반환하세요.
일반적으로 정의 섹션은 표(table)를 포함하고 있습니다.

{f"**특별 지시사항**: {custom_instruction}" if custom_instruction else ""}

다음 JSON 형식으로 반환:
{{
  "section_index": <섹션 인덱스>,
  "paragraph_index": <표가 있는 paragraph 인덱스>,
  "reasoning": "<선택 이유>"
}}

정의 섹션을 찾을 수 없으면:
{{
  "section_index": null,
  "paragraph_index": null,
  "reasoning": "<이유>"
}}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            result = json.loads(response.choices[0].message.content)

            if result["section_index"] is None:
                return self._create_error(
                    f"LLM could not find definition section: {result['reasoning']}"
                )

            # Find paragraph with table
            section = elements[result["section_index"]]
            paragraphs = section.get("paragraphs", [])

            table_para_idx = None
            for idx, para in enumerate(paragraphs):
                if "table" in para:
                    table_para_idx = idx
                    break

            if table_para_idx is None:
                return self._create_error(
                    f"Section {result['section_index']} has no table"
                )

            return self._create_success({
                "location": {
                    "section_index": result["section_index"],
                    "paragraph_index": table_para_idx,
                    "title": section.get("title", ""),
                    "reasoning": result["reasoning"]
                }
            })

        except Exception as e:
            return self._create_error(f"LLMSearchTool error: {str(e)}")
