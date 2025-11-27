"""
Tool Input Schemas

각 도구의 입력 파라미터 스키마를 정의합니다.
Planner가 이 스키마를 참고하여 올바른 parameters를 생성합니다.

Special tokens:
    "$sections" - runtime에 sections 리스트로 치환
    "$doc" - runtime에 전체 문서로 치환
    "{{taskN.field}}" - 이전 task 결과 참조
"""

TOOL_SCHEMAS = {
    "rule_search": {
        "description": "Rule-based keyword matching search in sections",
        "parameters": {
            "keywords": {
                "type": "list[string]",
                "description": "Keywords to search for in section titles",
                "required": True,
                "example": ["보험종목", "명칭"]
            },
            "sections": {
                "type": "list[dict]",
                "description": "List of sections to search in",
                "required": True,
                "value": "$sections"  # Runtime injection
            }
        },
        "returns": {
            "found_table": "dict - The table/content found in the matching section",
            "section_title": "string - Title of the matched section"
        }
    },

    "llm_search": {
        "description": "LLM-based semantic search in sections",
        "parameters": {
            "goal": {
                "type": "string",
                "description": "Description of what section to find",
                "required": True,
                "example": "보험 상품의 정의/명칭 정보를 담고 있는 섹션"
            },
            "sections": {
                "type": "list[dict]",
                "description": "List of sections to analyze",
                "required": True,
                "value": "$sections"  # Runtime injection
            },
            "context": {
                "type": "string",
                "description": "Additional context or hints",
                "required": False,
                "example": "테이블 형태로 되어 있을 가능성이 높음"
            }
        },
        "returns": {
            "found_table": "dict - The table/content found",
            "section_title": "string - Title of the matched section"
        }
    },

    "rule_extract": {
        "description": "Rule-based table data extraction",
        "parameters": {
            "content": {
                "type": "dict",
                "description": "Table content to extract from",
                "required": True,
                "example": "{{task1.found_table}}"
            }
        },
        "returns": {
            "header": "list[string] - Column headers",
            "data": "list[list[string]] - Table rows"
        }
    },

    "llm_extract": {
        "description": "LLM-based intelligent data extraction",
        "parameters": {
            "content": {
                "type": "dict",
                "description": "Content to extract from",
                "required": True,
                "example": "{{task1.found_table}}"
            },
            "instruction": {
                "type": "string",
                "description": "Specific extraction instructions",
                "required": True,
                "example": "테이블에서 보험명, 유형 정보를 추출하세요"
            }
        },
        "returns": {
            "header": "list[string] - Extracted field names",
            "data": "list[list[string]] - Extracted data rows"
        }
    },

    "rule_cartesian": {
        "description": "Fast rule-based Cartesian product generation",
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Column names",
                "required": True,
                "example": ["명칭", "보험종목", "보험종목_1"]
            },
            "data": {
                "type": "list[list[string]]",
                "description": "Data rows to expand",
                "required": True,
                "example": "{{task2.data}}"
            }
        },
        "returns": {
            "definitions": "list[dict] - All combinations as definition objects",
            "total_count": "int - Total number of definitions"
        }
    },

    "llm_cartesian": {
        "description": "LLM-based intelligent combination generation",
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Column names",
                "required": True,
                "example": ["명칭", "보험종목", "보험종목_1"]
            },
            "data": {
                "type": "list[list[string]]",
                "description": "Data rows to expand",
                "required": True,
                "example": "{{task2.data}}"
            },
            "instruction": {
                "type": "string",
                "description": "How to generate combinations",
                "required": False,
                "example": "슬래시(/)로 구분된 값들을 각각 분리하여 조합"
            }
        },
        "returns": {
            "definitions": "list[dict] - All combinations as definition objects",
            "total_count": "int - Total number of definitions"
        }
    }
}


def get_schema_prompt() -> str:
    """
    Planner LLM에게 전달할 schema 설명 생성

    Returns:
        str: Schema 전체 설명
    """
    prompt = "**Available Tools and Their Input Schemas:**\n\n"

    for tool_name, schema in TOOL_SCHEMAS.items():
        prompt += f"### {tool_name}\n"
        prompt += f"**Description:** {schema['description']}\n\n"
        prompt += "**Parameters:**\n"

        for param_name, param_info in schema['parameters'].items():
            required = "Required" if param_info['required'] else "Optional"
            prompt += f"- `{param_name}` ({param_info['type']}, {required})\n"
            prompt += f"  - {param_info['description']}\n"

            if 'value' in param_info:
                prompt += f"  - **Use value:** `\"{param_info['value']}\"`\n"
            elif 'example' in param_info:
                if isinstance(param_info['example'], str):
                    prompt += f"  - Example: `\"{param_info['example']}\"`\n"
                else:
                    prompt += f"  - Example: `{param_info['example']}`\n"

        prompt += f"\n**Returns:** {schema['returns']}\n\n"
        prompt += "---\n\n"

    return prompt


def validate_tool_parameters(tool_name: str, parameters: dict) -> tuple[bool, str]:
    """
    도구 파라미터가 스키마에 맞는지 검증

    Args:
        tool_name: 도구 이름
        parameters: 파라미터 딕셔너리

    Returns:
        (is_valid, error_message)
    """
    if tool_name not in TOOL_SCHEMAS:
        return False, f"Unknown tool: {tool_name}"

    schema = TOOL_SCHEMAS[tool_name]

    # Required 파라미터 체크
    for param_name, param_info in schema['parameters'].items():
        if param_info['required'] and param_name not in parameters:
            # Runtime injection 파라미터는 예외
            if 'value' not in param_info:
                return False, f"Missing required parameter: {param_name}"

    return True, ""
