"""
Tool Input Schemas (prototype_4_1)

현재 워크플로우에서 실제 사용하는 도구만 정의합니다.
Planner는 이 스키마를 참고해 task.parameters를 구성합니다.

Special tokens:
    "$sections" - runtime 에서 전체 sections 리스트로 치환
    "$doc"      - runtime 에서 전체 문서 객체로 치환
    "{{taskN.field}}" - 이전 task 결과 참조
"""

TOOL_SCHEMAS = {
    "section_classifier": {
        "description": "LLM-based 4-way section classifier (definition_core / definition_annotation / condition / other)",
        "supported_formats": ["table", "text", "mixed"],
        "parameters": {
            "sections": {
                "type": "list[dict]",
                "description": "List of ALL sections to classify",
                "required": True,
                "value": "$sections",
            }
        },
        "returns": {
            "definition_core": "list[int] - Indices of core definition sections",
            "definition_annotation": "list[int] - Indices of annotation sections",
            "condition": "list[int] - Indices of condition sections",
            "other": "list[int] - Indices of other sections",
            "reasoning": "string - Classification reasoning",
        },
    },
    "definition_extract_v2": {
        "description": "Extract definition table from classified sections (works with section_classifier result)",
        "supported_formats": ["table", "text", "mixed"],
        "parameters": {
            "sections": {
                "type": "list[dict]",
                "description": "List of all sections (from DocumentAccessor)",
                "required": True,
                "value": "$sections",
            },
            "core_indices": {
                "type": "list[int]",
                "description": "Indices of definition_core sections (from section_classifier)",
                "required": True,
                "example": "{{task0.data.definition_core}}",
            },
            "annotation_indices": {
                "type": "list[int]",
                "description": "Indices of definition_annotation sections (optional)",
                "required": False,
                "example": "{{task0.data.definition_annotation}}",
            },

        },
        "returns": {
            "header": "list[string] - Table headers",
            "data": "list[list[any]] - Table rows",
            "extraction_method": "string - Extraction method used (e.g. 'v2_classifier_based')",
        },
    },
    "rule_cartesian": {
        "description": "Fast rule-based Cartesian product generation from header/data",
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Column names (e.g. ['명칭', '보험종목', '보험종목_1'])",
                "required": True,
                "example": ["명칭", "보험종목", "보험종목_1"],
            },
            "data": {
                "type": "list[list[string]]",
                "description": "Data rows to expand into combinations",
                "required": True,
                "example": "{{task2.data}}",
            },
        },
        "returns": {
            "definitions": "list[dict] - All combinations as definition objects",
            "total_count": "int - Total number of definitions",
        },
    },
    "llm_cartesian": {
        "description": "LLM-based intelligent combination generation (parsing + Python Cartesian)",
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Column names",
                "required": True,
                "example": ["명칭", "보험종목", "보험종목_1"],
            },
            "data": {
                "type": "list[list[string]]",
                "description": "Data rows to expand",
                "required": True,
                "example": "{{task2.data}}",
            },
            "instruction": {
                "type": "string",
                "description": "Additional guidance for resolving errors from previous attempts",
                "required": False,
            },
        },
        "returns": {
            "definitions": "list[dict] - All combinations as definition objects",
            "total_count": "int - Total number of definitions",
            "notes": "string - Optional notes from LLM parsing",
        },
    },
    "condition_extract": {
        "description": "Extract condition table from classified condition sections (가입조건 추출)",
        "supported_formats": ["table", "text", "mixed"],
        "parameters": {
            "sections": {
                "type": "list[dict]",
                "description": "List of all sections (from DocumentAccessor)",
                "required": True,
                "value": "$sections",
            },
            "condition_indices": {
                "type": "list[int]",
                "description": "Indices of condition sections (from section_classifier)",
                "required": True,
                "example": "{{task0.data.condition}}",
            },
            "instruction": {
                "type": "string",
                "description": "Additional guidance for extraction",
                "required": False,
            },
        },
        "returns": {
            "header": "list[string] - Normalized column names (e.g., 유형1, 유형2, 보험기간, 납입기간)",
            "data": "list[list[any]] - Condition rows",
            "extraction_method": "string - Method used (e.g., 'rule_based' or 'llm_based')",
        },
    },

    "grouping_logic_extractor": {
        "description": "Extract grouping logic for definition-condition matching (LLM-based)",
        "supported_formats": ["table"],
        "parameters": {
            "definition_header": {
                "type": "list[str]",
                "description": "Normalized definition table header",
                "required": True,
                "example": "{{task2.data.header}}",
            },
            "definition_data": {
                "type": "list[list[any]]",
                "description": "Normalized definition table data (no combinations, raw table)",
                "required": True,
                "example": "{{task2.data.data}}",
            },
            "condition_header": {
                "type": "list[str]",
                "description": "Normalized condition table header",
                "required": True,
                "example": "{{task4.data.header}}",
            },
            "condition_data": {
                "type": "list[list[any]]",
                "description": "Normalized condition table data (no combinations, raw table)",
                "required": True,
                "example": "{{task4.data.data}}",
            },
            "instruction": {
                "type": "string",
                "description": "Additional guidance for grouping logic extraction",
                "required": False,
            },
        },
        "returns": {
            "column_mapping": "dict - {join_keys: list[str], value_columns: list[str]}",
            "groups": "list[dict] - each group: {definition_indices: list[int], "
                      "matched_list_items: list[int|None], condition_index: int, ...}",
            "unmatched": "dict - {definition_indices: list[int], condition_indices: list[int]}",
            "summary": "dict - Statistics summary (total counts, coverage ratio)",
        },
    },
    "combination_generator": {
        "description": "Generate final combinations based on grouping logic (Python-based, no LLM)",
        "supported_formats": ["table"],
        "parameters": {
            "definition_header": {
                "type": "list[str]",
                "description": "Split definition table header from task2 (llm_table_split)",
                "required": True,
                "example": "{{task2.data.header}}",
            },
            "definition_data": {
                "type": "list[list[str]]",
                "description": "Split definition table data from task2 (llm_table_split)",
                "required": True,
                "example": "{{task2.data.data}}",
            },
            "condition_header": {
                "type": "list[str]",
                "description": "Transformed condition table header from task4 (condition_transform)",
                "required": True,
                "example": "{{task4.data.header}}",
            },
            "condition_data": {
                "type": "list[list[str]]",
                "description": "Transformed condition table data from task4 (condition_transform)",
                "required": True,
                "example": "{{task4.data.data}}",
            },
            "grouping_logic": {
                "type": "dict",
                "description": "Grouping logic with matched_list_items from task5 (grouping_logic_extractor)",
                "required": True,
                "example": "{{task5.data}}",
            },
        },
        "returns": {
            "definitions": "list[dict] - Final merged definitions with condition columns",
            "total_count": "int - Total number of final definitions",
            "generation_stats": "dict - {groups_processed, matched_definitions, unmatched_definitions, total_generated}",
        },
    },
    "llm_table_split": {
        "description": "LLM-based semantic splitting of multi-value cells in Definition table (Task2 전용, header 유지)",
        "supported_formats": ["table"],
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Definition table header from task1",
                "required": True,
                "example": "{{task1.data.header}}",
            },
            "data": {
                "type": "list[list[any]]",
                "description": "Definition table data from task1",
                "required": True,
                "example": "{{task1.data.data}}",
            },
            "row_indices": {
                "type": "list[int]",
                "description": "Specific row indices to process (optional, if None = all rows)",
                "required": False,
                "example": "[0, 2, 5]",
            },
            "instruction": {
                "type": "string",
                "description": "Additional guidance for splitting (optional)",
                "required": False,
            },
        },
        "returns": {
            "header": "list[string] - Same as input header",
            "data": "list[list[any]] - Data with cells split into lists where appropriate",
            "notes": "string - Splitting notes",
        },
    },
    "condition_transform": {
        "description": "Transform condition table: split values + parse age formulas + map to standard schema (Task4 전용)",
        "supported_formats": ["table"],
        "parameters": {
            "header": {
                "type": "list[string]",
                "description": "Condition table header from task3 (condition_extract)",
                "required": True,
                "example": "{{task3.data.header}}",
            },
            "data": {
                "type": "list[list[any]]",
                "description": "Condition table data from task3 (condition_extract)",
                "required": True,
                "example": "{{task3.data.data}}",
            },
            "instruction": {
                "type": "string",
                "description": "Additional transformation guidance (optional)",
                "required": False,
            },
        },
        "returns": {
            "header": "list[string] - Transformed header with standard schema: "
                     "['보험기간', '납입기간', '주피보험자최소가입연령', '주피보험자최대가입연령', "
                     "'주피보험자최소가입연령구분코드', '주피보험자최대가입연령구분코드', '주피보험자가입성별', ...]",
            "data": "list[list[any]] - Transformed data with split values (lists) and parsed formulas (strings)",
            "notes": "string - Transformation notes",
        },
    },

}


def get_schema_prompt() -> str:
    """
    Planner LLM에게 넘길 schema 설명 문자열 생성.
    """
    prompt = "**Available Tools and Their Input Schemas:**\n\n"

    for tool_name, schema in TOOL_SCHEMAS.items():
        prompt += f"### {tool_name}\n"
        prompt += f"**Description:** {schema['description']}\n"

        if "supported_formats" in schema:
            prompt += (
                f"**Supported Formats:** "
                f"{', '.join(schema['supported_formats'])}\n"
            )

        prompt += "\n**Parameters:**\n"
        for param_name, param_info in schema["parameters"].items():
            required = "Required" if param_info["required"] else "Optional"
            prompt += f"- `{param_name}` ({param_info['type']}, {required})\n"
            prompt += f"  - {param_info['description']}\n"

            if "default" in param_info:
                prompt += f"  - Default: `{param_info['default']}`\n"
            if "value" in param_info:
                prompt += f"  - **Use value:** `\"{param_info['value']}\"`\n"
            elif "example" in param_info:
                example = param_info["example"]
                if isinstance(example, str):
                    prompt += f"  - Example: `\"{example}\"`\n"
                else:
                    prompt += f"  - Example: `{example}`\n"

        prompt += f"\n**Returns:** {schema['returns']}\n\n"
        prompt += "---\n\n"

    return prompt


def validate_tool_parameters(tool_name: str, parameters: dict) -> tuple[bool, str]:
    """
    Planner → Agent 전달 시, 파라미터가 스키마에 맞는지 최소한으로 검증.
    """
    if tool_name not in TOOL_SCHEMAS:
        return False, f"Unknown tool: {tool_name}"

    schema = TOOL_SCHEMAS[tool_name]

    for param_name, param_info in schema["parameters"].items():
        if param_info["required"] and param_name not in parameters:
            # Runtime injection(value)이 있는 경우는 누락 허용
            if "value" not in param_info:
                return False, f"Missing required parameter: {param_name}"

    return True, ""


