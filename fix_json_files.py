"""
기존에 마크다운 코드 블록으로 감싸진 JSON 파일들을 수정하는 스크립트
"""
import json
from pathlib import Path


def fix_json_file(file_path: Path):
    """마크다운 코드 블록 제거 및 JSON 재포맷"""
    content = file_path.read_text(encoding="utf-8")

    # 마크다운 코드 블록 제거
    if content.strip().startswith("```"):
        lines = content.strip().split("\n")
        # 첫 줄이 ```json 또는 ``` 인 경우 제거
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 마지막 줄이 ``` 인 경우 제거
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    # JSON 파싱 및 재저장
    try:
        data = json.loads(content)
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"✅ 수정 완료: {file_path.name}")
        return True
    except Exception as e:
        print(f"❌ 수정 실패: {file_path.name} - {e}")
        return False


def main():
    base_dir = Path(r"C:\Users\NT-165\Desktop\Project\Toy\data\토이프로젝트_데이터\파싱결과\only_doc")

    if not base_dir.exists():
        print(f"❌ 디렉토리가 존재하지 않습니다: {base_dir}")
        return

    json_files = list(base_dir.glob("*_plan.json"))

    if not json_files:
        print("처리할 파일이 없습니다.")
        return

    print(f"\n총 {len(json_files)}개 파일 수정 시작...\n")

    success_count = 0
    for file_path in json_files:
        if fix_json_file(file_path):
            success_count += 1

    print(f"\n완료: {success_count}/{len(json_files)} 파일 수정 성공")


if __name__ == "__main__":
    main()
