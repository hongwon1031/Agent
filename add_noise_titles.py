"""
테스트 케이스에 노이즈 Title 추가 스크립트
"""
import json
import os
from pathlib import Path

# 노이즈 Title 템플릿
NOISE_TITLES_BEFORE = [
    {"title": "용어의 정의", "paragraphs": [{"type": "text", "content": "이 약관에서 사용하는 용어를 정의합니다."}]},
    {"title": "계약의 성립", "paragraphs": [{"type": "text", "content": "계약은 청약과 승낙으로 이루어집니다."}]},
    {"title": "청약의 철회", "paragraphs": [{"type": "text", "content": "청약일로부터 15일 이내 철회 가능합니다."}]},
]

NOISE_TITLES_MIDDLE = [
    {"title": "보험금 지급사유", "paragraphs": [{"type": "text", "content": "약관에 정한 사유 발생 시 보험금을 지급합니다."}]},
    {"title": "보험금 지급 제한", "paragraphs": [{"type": "text", "content": "면책 사유에 해당하는 경우 지급이 제한됩니다."}]},
]

NOISE_TITLES_AFTER = [
    {"title": "배당", "paragraphs": [{"type": "text", "content": "무배당 상품입니다."}]},
    {"title": "해지환급금", "paragraphs": [{"type": "text", "content": "해지 시 환급금이 지급됩니다."}]},
    {"title": "계약대출", "paragraphs": [{"type": "text", "content": "해약환급금 범위 내에서 대출 가능합니다."}]},
    {"title": "분쟁의 조정", "paragraphs": [{"type": "text", "content": "분쟁 발생 시 금융감독원에 조정 신청할 수 있습니다."}]},
]

def add_noise_titles(file_path):
    """파일에 노이즈 Title 추가"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data or not data[0].get("elements"):
        return

    elements = data[0]["elements"]

    # 이미 많은 Title이 있으면 스킵
    if len(elements) >= 8:
        print(f"  [SKIP] {file_path.name} - already has {len(elements)} titles")
        return

    # 새로운 elements 생성
    new_elements = []

    # 앞에 노이즈 추가
    new_elements.extend(NOISE_TITLES_BEFORE)

    # 기존 elements의 첫 번째 (정의 섹션 추정)
    if len(elements) > 0:
        new_elements.append(elements[0])

    # 중간 노이즈 추가
    new_elements.extend(NOISE_TITLES_MIDDLE)

    # 기존 elements의 나머지 (조건 섹션 등)
    new_elements.extend(elements[1:])

    # 뒤에 노이즈 추가
    new_elements.extend(NOISE_TITLES_AFTER)

    # 업데이트
    data[0]["elements"] = new_elements

    # 저장
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  [OK] {file_path.name} - {len(elements)} -> {len(new_elements)} titles")

def main():
    test_cases_dir = Path(r"c:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\test_cases")

    print("Adding noise titles to test cases...")
    print("="*60)

    for json_file in sorted(test_cases_dir.glob("*.json")):
        # 이미 수정한 파일은 스킵
        if json_file.name in ["test_title_order_changed.json", "test_no_title_numbers.json"]:
            print(f"  [SKIP] {json_file.name} - already modified")
            continue

        add_noise_titles(json_file)

    print("="*60)
    print("Done!")

if __name__ == "__main__":
    main()
