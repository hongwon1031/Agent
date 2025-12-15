# test_grouping_prompt.py
from core.prompt import build_grouping_extraction_prompt_2,format_table_for_prompt,build_grouping_extraction_prompt_1

import os
from dotenv import load_dotenv
from openai import OpenAI
import json
import time


load_dotenv(r"c:\Users\NT-165\Desktop\Project\Toy\.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

definition_header = [
    "명칭",
    "보험종목",
    "보험종목_1",
    "보장계약"
]

definition_data = [
    [
        "[3-100%장해형]재해장해특약 (무배당, 해약환급금 미지급형)",
        "해약환급금 미지급형",
        [
            "간편심사(315)형/간편심사(335)형/간편심사(355)형",
            "일반심사형",
        ],
        "두경부암(전이포함), 위암 및 식도암(전이포함), 소장·대장·항문암 및 기타암(전이포함), 간·담낭·담도암 및 췌장암(전이포함), 폐암(전이포함), 흉곽내기관·중피성암 및 연조직암(전이포함), 골·피부 등 전신부위암(전이포함), 유방·비뇨기관·부신암 및 내분비선암(전이포함), 남성/여성생식기암(전이포함), 뇌암 및 중추신경계통암(전이포함), 혈액암(전이포함)",
    ],
    [
        "[3-100%장해형]재해장해특약 (무배당, 해약환급금 미지급형)",
        "일반형",
        [
            "간편심사(315)형/간편심사(335)형/간편심사(355)형",
            "일반심사형",
        ],
        "두경부암(전이포함), 위암 및 식도암(전이포함), 소장·대장·항문암 및 기타암(전이포함), 간·담낭·담도암 및 췌장암(전이포함), 폐암(전이포함), 흉곽내기관·중피성암 및 연조직암(전이포함), 골·피부 등 전신부위암(전이포함), 유방·비뇨기관·부신암 및 내분비선암(전이포함), 남성/여성생식기암(전이포함), 뇌암 및 중추신경계통암(전이포함), 혈액암(전이포함)",
    ],
    [
        "[3-100%장해형]재해장해특약(무배당)",
        "해약환급금 미지급형",
        [
            "간편심사(315)형/간편심사(335)형/간편심사(355)형",
            "일반심사형",
        ],
        "두경부암(전이포함), 위암 및 식도암(전이포함), 소장·대장·항문암 및 기타암(전이포함), 간·담낭·담도암 및 췌장암(전이포함), 폐암(전이포함), 흉곽내기관·중피성암 및 연조직암(전이포함), 골·피부 등 전신부위암(전이포함), 유방·비뇨기관·부신암 및 내분비선암(전이포함), 남성/여성생식기암(전이포함), 뇌암 및 중추신경계통암(전이포함), 혈액암(전이포함)",
    ],
    [
        "[3-100%장해형]재해장해특약(무배당)",
        "일반형",
        [
            "간편심사(315)형/간편심사(335)형/간편심사(355)형",
            "일반심사형",
        ],
        "두경부암(전이포함), 위암 및 식도암(전이포함), 소장·대장·항문암 및 기타암(전이포함), 간·담낭·담도암 및 췌장암(전이포함), 폐암(전이포함), 흉곽내기관·중피성암 및 연조직암(전이포함), 골·피부 등 전신부위암(전이포함), 유방·비뇨기관·부신암 및 내분비선암(전이포함), 남성/여성생식기암(전이포함), 뇌암 및 중추신경계통암(전이포함), 혈액암(전이포함)",
    ],
]

condition_header = [
    "유형0",
    "유형1",
    "유형2",
    "보험기간",
    "납입기간",
    "주피보험자최소가입연령",
    "주피보험자최대가입연령",
    "주피보험자최소가입연령구분코드",
    "주피보험자최대가입연령구분코드",
    "주피보험자가입성별",
]

condition_data = [
    [
        "해약환급금 미지급형",
        "간편심사형",
        "-",
        ["80세 만기", "90세 만기", "100세 만기", "종신"],
        ["10년납", "15년납", "20년납", "25년납", "30년납"],
        "만 15세",
        "min[세만기 - 년납, 90 - 년납, 80] 세",
        "(2)만연령",
        "(1)보험연령",
        ["남", "여"],
    ],
    [
        "해약환급금 미지급형",
        "일반심사형",
        "-",
        ["80세 만기", "90세 만기", "100세 만기", "종신"],
        ["10년납", "15년납", "20년납", "25년납", "30년납"],
        "만 15세",
        "min[세만기 - 년납, 90 - 년납, 70] 세",
        "(2)만연령",
        "(1)보험연령",
        ["남", "여"],
    ],
    [
        "일반형",
        "간편심사형",
        "-",
        ["25년 만기", "30년 만기", "80세 만기", "90세 만기", "100세 만기", "종신"],
        ["5년납", "7년납", "10년납", "15년납", "20년납", "25년납", "30년납"],
        "만 15세",
        "min[세만기 - 년납, 90 - 년납, 80] 세",
        "(2)만연령",
        "(1)보험연령",
        ["남", "여"],
    ],
    [
        "일반형",
        "일반심사형",
        "-",
        ["25년 만기", "30년 만기", "80세 만기", "90세 만기", "100세 만기", "종신"],
        ["5년납", "7년납", "10년납", "15년납", "20년납", "25년납", "30년납"],
        "만 15세",
        "min[세만기 - 년납, 90 - 년납, 70] 세",
        "(2)만연령",
        "(1)보험연령",
        ["남", "여"],
    ],
]

if __name__ == "__main__":
    print('p1 start')
    prompt_1 = build_grouping_extraction_prompt_1(
        definition_header=definition_header,
        definition_data=definition_data,
        condition_header=condition_header,
        condition_data=condition_data,
        instruction="",  # 필요하면 커스텀 지시 넣기
    )
    print('p2 start')
    prompt_2 = build_grouping_extraction_prompt_2(
        definition_header=definition_header,
        definition_data=definition_data,
        condition_header=condition_header,
        condition_data=condition_data,
        instruction="",  # 필요하면 커스텀 지시 넣기
    )

    print('t2 start')
    t2_start = time.perf_counter()
    response_2 = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt_2}],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4000
            )
    print('t2 end')
    t2_end = time.perf_counter()
    raw_2 = response_2.choices[0].message.content

    print(f"[P2] elapsed: {t2_end - t2_start:.2f}s")
    print("prompt_2 length:", len(prompt_2))
    print("raw_2 length:", len(raw_2))
    print("2️⃣" * 20)

    try:
        data_2 = json.loads(raw_2)
        with open("grouping_result_prompt2.json", "w", encoding="utf-8") as f:
            json.dump(data_2, f, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        with open("grouping_result_prompt2_raw.txt", "w", encoding="utf-8") as f:
            f.write(raw_2)

    # print('t1 start')
    # t1_start = time.perf_counter()
    # response_1 = client.chat.completions.create(
    #             model="gpt-4o",
    #             messages=[{"role": "user", "content": prompt_1}],
    #             response_format={"type": "json_object"},
    #             temperature=0,
    #             max_tokens=4000
    #         )
    # print('t1 end')
    # t1_end = time.perf_counter()
    # raw_1 = response_1.choices[0].message.content
   
    # print(f"[P1] elapsed: {t1_end - t1_start:.2f}s")
    # print("prompt_1 length:", len(prompt_1))
    # print("raw_1 length:", len(raw_1))
    # print("1️⃣" * 20)

    # try:
    #     data_1 = json.loads(raw_1)
    #     with open("grouping_result_prompt1.json", "w", encoding="utf-8") as f:
    #         json.dump(data_1, f, ensure_ascii=False, indent=2)
    # except json.JSONDecodeError:
    #     # 혹시 잘린 경우 raw 텍스트로라도 저장
    #     with open("grouping_result_prompt1_raw.txt", "w", encoding="utf-8") as f:
    #         f.write(raw_1)
    

    # def_table = format_table_for_prompt(definition_header, definition_data, max_rows=50)
    # cond_table = format_table_for_prompt(condition_header, condition_data, max_rows=20)
    # print(f'🚨def_table : {def_table}')
    # print('-'*20)
    # print(f'🚨cond_table : {cond_table}')
    # print('-'*20)
