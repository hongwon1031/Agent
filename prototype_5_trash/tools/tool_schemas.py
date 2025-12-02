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
    "section_classifier": {
        "description": "LLM-based 4-way section classifier (RECOMMENDED for definition extraction)",
        "supported_formats": ["table", "text", "mixed"],
        "parameters": {
            "sections": {
                "type": "list[dict]",
                "description": "List of ALL sections to classify",
                "required": True,
                "value": "$sections"  # Runtime injection
            }
        },
        "returns": {
            "definition_core": "list[int] - Indices of core definition sections",
            "definition_annotation": "list[int] - Indices of annotation sections",
            "condition": "list[int] - Indices of condition sections",
            "other": "list[int] - Indices of other sections",
            "reasoning": "string - Classification reasoning"
        }
    },

    "definition_extract_v2": {
        "description": "Extract definition table from classified sections (works with section_classifier)",
        "supported_formats": ["table", "text", "mixed"],
        "parameters": {
            "sections": {
                "type": "list[dict]",
                "description": "List of all sections",
                "required": True,
                "value": "$sections"  # Runtime injection
            },
            "core_indices": {
                "type": "list[int]",
                "description": "Indices of definition_core sections (from section_classifier)",
                "required": True,
                "example": "{{task1.definition_core}}"
            },
            "annotation_indices": {
                "type": "list[int]",
                "description": "Indices of definition_annotation sections (optional)",
                "required": False,
                "example": "{{task1.definition_annotation}}"
            }
        },
        "returns": {
            "header": "list[string] - Table headers",
            "data": "list[list[string]] - Table rows",
            "extraction_method": "string - Extraction method used"
        }
    },

    

    

    "rule_extract": {
        "description": "Rule-based data extraction (table or text)",
        "supported_formats": ["table", "text"],  # 새로 추가
        "parameters": {
            "content": {
                "type": "dict or string",
                "description": "Content to extract from (table dict or text string)",
                "required": True,
                "example": "{{task1.found_content}}"
            },
            "content_type": {
                "type": "string",
                "description": "'table' or 'text' - type of content",
                "required": False,
                "example": "{{task1.content_type}}",
                "default": "table"
            }
        },
        "returns": {
            "header": "list[string] - Column headers",
            "data": "list[list[string]] - Data rows",
            "extraction_method": "string - 'table_parsing' or 'text_parsing'"
        }
    },

    "llm_extract": {
        "description": "LLM-based intelligent data extraction",
        "supported_formats": ["table", "text", "mixed"],  # 새로 추가
        "parameters": {
            "content": {
                "type": "dict or string",
                "description": "Content to extract from (table dict or text string)",
                "required": True,
                "example": "{{task1.found_content}}"
            },
            "content_type": {
                "type": "string",
                "description": "'table' or 'text' - type of content",
                "required": False,
                "example": "{{task1.content_type}}"
            },
            "instruction": {
                "type": "string",
                "description": "Specific extraction instructions",
                "required": False,
                "example": "테이블에서 보험명, 유형 정보를 추출하세요"
            }
        },
        "returns": {
            "header": "list[string] - Extracted field names",
            "data": "list[list[string]] - Extracted data rows",
            "extraction_method": "string - 'table' or 'text'"
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
        prompt += f"**Description:** {schema['description']}\n"

        # supported_formats 추가
        if 'supported_formats' in schema:
            prompt += f"**Supported Formats:** {', '.join(schema['supported_formats'])}\n"

        prompt += "\n**Parameters:**\n"

        for param_name, param_info in schema['parameters'].items():
            required = "Required" if param_info['required'] else "Optional"
            prompt += f"- `{param_name}` ({param_info['type']}, {required})\n"
            prompt += f"  - {param_info['description']}\n"

            if 'default' in param_info:
                prompt += f"  - Default: `{param_info['default']}`\n"
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
