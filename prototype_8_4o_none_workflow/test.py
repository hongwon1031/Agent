# test_llm_table_split.py
import json
from tools.hybrid_tools import LLMTableSplitTool

def main():
    # 재해장해 예시와 비슷한 형태
    header = ["명칭", "보험종목", "보험종목_1"]
    data = [
        [
            "[3-100%장해형]재해장해특약 (무배당, 해약환급금 미지급형)",
            "해약환급금 미지급형",
            "간편A형/간편B형/간편C형/일반형",
        ],
        [
            "[3-100%장해형]재해장해특약(무배당)",
            "일반형",
            "간편A형/간편B형/간편C형/일반형",
        ],
    ]

    tool = LLMTableSplitTool()
    params = {
        "header": header,
        "data": data,
        # 필요하면 특정 row만:
        # "row_indices": [0],
        "instruction": "",  # 추가 지시 없으면 빈 문자열
    }

    result = tool.execute(doc=None, params=params)
    print("[SUCCESS]", result.success)
    if result.error:
        print("[ERROR]", result.error)
    else:
        print(json.dumps(result.data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
