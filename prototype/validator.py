"""
Simple Validator for Prototype Agent
"""
from typing import Dict, List


class SimpleValidator:
    """
    Tool 실행 결과 검증
    """
    def validate(self, result_data: Dict) -> Dict:
        """
        결과 검증
        Returns: {"is_valid": bool, "errors": List[str]}
        """
        errors = []

        # 1. definitions 키 존재 확인
        if "definitions" not in result_data:
            errors.append("Missing 'definitions' key in result")
            return {"is_valid": False, "errors": errors}

        definitions = result_data["definitions"]

        # 2. 최소 1개 이상의 조합
        if not definitions or len(definitions) == 0:
            errors.append("No definitions found")
            return {"is_valid": False, "errors": errors}

        # 3. 모든 항목이 최소 스키마 준수 (보종명, 유형1은 필수, 유형2+ 선택적)
        required_keys = {"보종명", "유형1"}
        for i, item in enumerate(definitions):
            missing_keys = required_keys - set(item.keys())
            if missing_keys:
                errors.append(f"Item {i}: Missing required keys {missing_keys}")

        # 4. 보종명이 비정상적으로 잘렸는지 확인 (더 정교한 휴리스틱)
        for i, item in enumerate(definitions):
            보종명 = item.get("보종명", "")

            # 명백한 truncation 패턴 확인:
            # - 5자 미만 (너무 짧음)
            # - "(" 로 시작하지만 ")" 없음 (괄호 불완전)
            # - 줄바꿈이나 슬래시로 끝남 (중간에 잘린 것)
            is_truncated = False
            reason = ""

            if len(보종명.strip()) < 5:
                is_truncated = True
                reason = "too short (< 5 chars)"
            elif 보종명.count("(") != 보종명.count(")"):
                is_truncated = True
                reason = "unbalanced parentheses"
            elif 보종명.strip().endswith(("\n", "/", "\\")):
                is_truncated = True
                reason = "ends with separator"

            if is_truncated:
                errors.append(f"Item {i}: '보종명' appears truncated ({reason})")
                errors.append(f"  Value: '{보종명}'")
                errors.append(f"  Expected: Complete name")

        # 5. 중복 제거 확인 (선택적) - 모든 키 포함
        unique_combos = set(
            tuple(sorted(d.items()))  # 모든 키-값 쌍을 정렬된 튜플로 변환
            for d in definitions
        )
        if len(unique_combos) != len(definitions):
            errors.append(f"Duplicate combinations found: {len(definitions)} total, {len(unique_combos)} unique")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }
