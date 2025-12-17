# test_condition_transform_multiline_formula.py
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
# ✅ 너 프로젝트에서 가져오기 (경로만 맞춰줘)
# from tools.prompts import build_condition_transform_prompt
from core.prompt import build_condition_transform_prompt  


def main():
    # ----------------------------
    # 1) 입력 (원본 Condition Extract 결과 형태)
    # ----------------------------
    load_dotenv()
    header = [
        "유형1",
        "유형2",
        "유형3",
        "보험기간",
        "납입기간",
        "가입나이_남",
        "가입나이_여",
        "납입주기",
    ]

    data = [
        [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "해약환급금 미지급형",
            "간편심사형",
            "80/90/100세 만기, 종신",
            "10/15/20/25/30년납",
            "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세",
            "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세",
            "월납",
        ],
        [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "해약환급금 미지급형",
            "일반심사형",
            "80/90/100세 만기, 종신",
            "10/15/20/25/30년납",
            "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
            "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세",
            "월납",
        ],
        [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "일반형",
            "간편심사형",
            "25/30년 만기, 80/90/100세 만기, 종신",
            "5/7/10/15/20/25/30년납",
            "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세\n만15세 - min[100 - 년만기, 90 - 년납, 80] 세",
            "만15세 - min[세만기 - 년납, 90 - 년납, 80] 세\n만15세 - min[100 - 년만기, 90 - 년납, 80] 세",
            "월납",
        ],
        [
            "보험기간, 보험료 납입기간, 피보험자 가입나이 및 보험료 납입주기",
            "일반형",
            "일반심사형",
            "25/30년 만기, 80/90/100세 만기, 종신",
            "5/7/10/15/20/25/30년납",
            "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세\n만15세 - min[100 - 년만기, 90 - 년납, 70] 세",
            "만15세 - min[세만기 - 년납, 90 - 년납, 70] 세\n만15세 - min[100 - 년만기, 90 - 년납, 70] 세",
            "월납",
        ],
    ]

    # ----------------------------
    # 2) 프롬프트 생성 (핵심 instruction)
    # ----------------------------
    instruction = ""

    prompt = build_condition_transform_prompt(
        header=header,
        data=data,
        instruction=instruction,
    )

    # ----------------------------
    # 3) LLM 호출
    # ----------------------------
    # 환경변수 OPENAI_API_KEY 필요
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=4000,
    )

    content = resp.choices[0].message.content
    result = json.loads(content)

    # ----------------------------
    # 4) 기본 스키마 체크
    # ----------------------------
    assert "header" in result and "data" in result, "❌ 응답 JSON에 header/data가 없음"
    out_header = result["header"]
    out_data = result["data"]
    assert isinstance(out_header, list) and isinstance(out_data, list), "❌ header/data 타입이 아님(list expected)"

    required_cols = [
        "주피보험자최소가입연령",
        "주피보험자최대가입연령",
        "주피보험자최소가입연령구분코드",
        "주피보험자최대가입연령구분코드",
        "주피보험자가입성별",
        "보험기간",
        "납입기간",
    ]
    missing = [c for c in required_cols if c not in out_header]
    assert not missing, f"❌ 필수 컬럼 누락: {missing}"

    idx_max = out_header.index("주피보험자최대가입연령")

    # ----------------------------
    # 5) 핵심 검증: '두 줄 수식' 보존 여부
    # ----------------------------
    in_idx_m = header.index("가입나이_남")
    in_idx_f = header.index("가입나이_여")

    failed = []

    for i, (in_row, out_row) in enumerate(zip(data, out_data)):
        in_m = in_row[in_idx_m] or ""
        in_f = in_row[in_idx_f] or ""
        in_has_multiline = ("\n" in str(in_m)) or ("\n" in str(in_f))

        max_age = out_row[idx_max]

        # (1) 최대가입연령 타입은 str이어야 함 (리스트화 금지)
        if not isinstance(max_age, str):
            failed.append((i, "type", f"type={type(max_age)}"))
            continue

        # (2) 원본에 multiline이면 결과에도 multiline이어야 함
        if in_has_multiline and ("\n" not in max_age):
            failed.append((i, "multiline_lost", max_age))

        # (3) 원본에 '년만기'가 있으면 결과에도 있어야 함 (정보 손실 방지)
        if in_has_multiline and ("년만기" in (in_m + in_f)) and ("년만기" not in max_age):
            failed.append((i, "token_lost_년만기", max_age))

        # (4) 원본에 '세만기'가 있으면 결과에도 있어야 함
        if in_has_multiline and ("세만기" in (in_m + in_f)) and ("세만기" not in max_age):
            failed.append((i, "token_lost_세만기", max_age))

    if failed:
        print("\n❌ FAIL: condition transform에서 수식 보존 문제가 발견됨\n")
        for row_i, kind, detail in failed:
            print(f"- row {row_i} / {kind}: {detail}\n")
        raise SystemExit(1)

    # ----------------------------
    # 6) 샘플 출력
    # ----------------------------
    print("\n✅ PASS: multiline formula preserved\n")
    for i in range(min(4, len(out_data))):
        print(f"[ROW {i}] 최대가입연령:")
        print(out_data[i][idx_max])
        print("-" * 60)


if __name__ == "__main__":
    main()
