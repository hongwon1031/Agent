"""
Smart Reference System: 동적 참조 시스템

복잡한 참조 패턴을 지원하는 유연한 참조 해석 시스템입니다.

지원 기능:
    - 중첩 경로: {{task1.data.items[0].name}}
    - 리스트 인덱싱: {{task1.results[0]}}
    - 옵셔널 체이닝: {{task1.data?.field}}
    - 필터링: {{task2.items | filter('valid')}}
    - 기본값: {{task1.data?.field | default('N/A')}}
"""

from typing import Dict, List, Any, Optional
import re


class SmartReference:
    """
    스마트 참조 표현

    Attributes:
        original: 원본 참조 문자열 (예: "{{task1.data[0].name}}")
        task_id: 참조하는 Task ID
        path: 접근 경로
        has_optional: 옵셔널 체이닝 포함 여부
        filters: 적용할 필터들
    """

    def __init__(self, reference_str: str):
        """
        Args:
            reference_str: 참조 문자열 (예: "{{task1.data[0].name}}")
        """
        self.original = reference_str
        self.task_id = None
        self.path = []
        self.has_optional = False
        self.filters = []

        self._parse(reference_str)

    def _parse(self, ref_str: str):
        """참조 문자열 파싱"""
        # {{...}} 제거
        if ref_str.startswith("{{") and ref_str.endswith("}}"):
            ref_str = ref_str[2:-2].strip()
        elif ref_str.startswith("{") and ref_str.endswith("}"):
            ref_str = ref_str[1:-1].strip()

        # 필터 분리 (| 기준)
        parts = ref_str.split("|")
        main_part = parts[0].strip()

        if len(parts) > 1:
            self.filters = [f.strip() for f in parts[1:]]

        # 옵셔널 체이닝 확인
        if "?." in main_part:
            self.has_optional = True
            main_part = main_part.replace("?.", ".")

        # Task ID 추출
        if main_part.startswith("task"):
            # task1.data[0].name 형태
            task_part = main_part.split(".", 1)[0]
            self.task_id = int(re.search(r'\d+', task_part).group())

            # 경로 파싱
            if "." in main_part:
                path_str = main_part.split(".", 1)[1]
                self.path = self._parse_path(path_str)
        else:
            # task 키워드 없이 경로만 있는 경우
            self.path = self._parse_path(main_part)

    def _parse_path(self, path_str: str) -> List[Any]:
        """
        경로 문자열을 파싱하여 리스트로 변환

        Examples:
            "data[0].name" → ["data", 0, "name"]
            "items[3].value" → ["items", 3, "value"]
            "results" → ["results"]
        """
        path = []

        # [숫자] 패턴을 구분자로 분리
        parts = re.split(r'(\[\d+\])', path_str)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 리스트 인덱스
            if part.startswith('[') and part.endswith(']'):
                index = int(part[1:-1])
                path.append(index)
            # 점으로 구분된 필드
            elif '.' in part:
                path.extend(part.split('.'))
            # 단일 필드
            else:
                if part:
                    path.append(part)

        return path


class ReferenceResolver:
    """
    참조 해석기

    이전 Task들의 결과를 참조하여 실제 값으로 변환합니다.

    사용 예시:
        resolver = ReferenceResolver(previous_results)

        # 단순 참조
        value = resolver.resolve("{{task1.data.location}}")

        # 복잡한 참조
        value = resolver.resolve("{{task2.items[0].name | default('Unknown')}}")

        # 파라미터 딕셔너리 전체 해석
        params = {"section_idx": "{{task1.location.index}}", "name": "fixed_value"}
        resolved = resolver.resolve_parameters(params)
    """

    def __init__(self, previous_results: Dict[int, Any]):
        """
        Args:
            previous_results: 이전 Task 결과들 (task_id → result data)
        """
        self.previous_results = previous_results

    def resolve(self, reference_str: str) -> Any:
        """
        단일 참조 해석

        Args:
            reference_str: 참조 문자열

        Returns:
            Any: 해석된 값

        Raises:
            ValueError: Task 결과가 없거나 경로가 잘못된 경우
        """
        # 참조가 아니면 그대로 반환
        if not self._is_reference(reference_str):
            return reference_str

        ref = SmartReference(reference_str)

        # Task 결과 가져오기
        if ref.task_id is None:
            raise ValueError(f"Cannot determine task_id from: {reference_str}")

        if ref.task_id not in self.previous_results:
            if ref.has_optional:
                # 옵셔널 체이닝: 결과 없으면 None
                return None
            raise ValueError(f"Task {ref.task_id} result not found")

        result = self.previous_results[ref.task_id]

        # 경로 탐색
        try:
            value = self._navigate_path(result, ref.path, ref.has_optional)
        except (KeyError, IndexError, TypeError) as e:
            if ref.has_optional:
                value = None
            else:
                raise ValueError(f"Cannot access path {ref.path} in task {ref.task_id} result: {e}")

        # 필터 적용
        for filter_expr in ref.filters:
            value = self._apply_filter(value, filter_expr)

        return value

    def _navigate_path(self, obj: Any, path: List[Any], optional: bool = False) -> Any:
        """
        경로를 따라 객체 탐색

        Args:
            obj: 시작 객체
            path: 탐색 경로
            optional: 옵셔널 체이닝 여부

        Returns:
            Any: 탐색 결과
        """
        current = obj

        for step in path:
            if current is None:
                if optional:
                    return None
                raise ValueError(f"Cannot access {step} on None")

            if isinstance(step, int):
                # 리스트 인덱싱
                if isinstance(current, list):
                    if step < len(current):
                        current = current[step]
                    else:
                        if optional:
                            return None
                        raise IndexError(f"Index {step} out of range (length: {len(current)})")
                else:
                    if optional:
                        return None
                    raise TypeError(f"Cannot index {type(current)} with {step}")

            elif isinstance(step, str):
                # 딕셔너리 접근
                if isinstance(current, dict):
                    if step in current:
                        current = current[step]
                    else:
                        if optional:
                            return None
                        raise KeyError(f"Key '{step}' not found")
                else:
                    # 객체 속성 접근 시도
                    if hasattr(current, step):
                        current = getattr(current, step)
                    else:
                        if optional:
                            return None
                        raise AttributeError(f"'{type(current).__name__}' has no attribute '{step}'")

        return current

    def _apply_filter(self, value: Any, filter_expr: str) -> Any:
        """
        필터 적용

        지원 필터:
            - default('value'): 값이 None이면 기본값 반환
            - filter('key'): 리스트 필터링
            - first: 리스트의 첫 번째 요소
            - last: 리스트의 마지막 요소
            - length: 리스트/문자열 길이
        """
        # default 필터
        if filter_expr.startswith("default"):
            match = re.search(r"default\(['\"](.+?)['\"]\)", filter_expr)
            if match:
                default_value = match.group(1)
                return value if value is not None else default_value

        # filter 필터
        if filter_expr.startswith("filter"):
            match = re.search(r"filter\(['\"](.+?)['\"]\)", filter_expr)
            if match and isinstance(value, list):
                filter_key = match.group(1)
                return [item for item in value if item.get(filter_key)]

        # first 필터
        if filter_expr == "first":
            if isinstance(value, list) and len(value) > 0:
                return value[0]

        # last 필터
        if filter_expr == "last":
            if isinstance(value, list) and len(value) > 0:
                return value[-1]

        # length 필터
        if filter_expr == "length":
            if isinstance(value, (list, str, dict)):
                return len(value)

        return value

    def resolve_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        파라미터 딕셔너리 전체 해석

        Args:
            params: 파라미터 (참조 포함 가능)

        Returns:
            Dict[str, Any]: 해석된 파라미터
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and self._is_reference(value):
                resolved[key] = self.resolve(value)
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 해석
                resolved[key] = self.resolve_parameters(value)
            elif isinstance(value, list):
                # 리스트 내 참조 해석
                resolved[key] = [
                    self.resolve(item) if isinstance(item, str) and self._is_reference(item) else item
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _is_reference(self, value: str) -> bool:
        """문자열이 참조 형식인지 확인"""
        if not isinstance(value, str):
            return False

        # {{...}} 또는 {task...} 형식
        return (
            (value.startswith("{{") and value.endswith("}}")) or
            (value.startswith("{") and value.endswith("}") and "task" in value)
        )
