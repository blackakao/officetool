"""순수 워크플로 구조 검증과 값 해석. Qt·Selenium에 의존하지 않는다.

저장 검증과 실행 경계 탐색의 서로 다른 허용 범위와 호출 시점을 유지한다.
"""

import re


def find_repeat_end_index(items, start_index):
    depth = 0
    for index in range(start_index, len(items)):
        process_type = items[index][1].get("type", "element")
        if process_type == "repeat_start":
            depth += 1
        elif process_type == "repeat_end":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"반복지점 종료를 찾을 수 없습니다: {items[start_index][0]}")


def find_condition_indices(items, start_index):
    depth = 0
    true_index = None
    false_index = None
    for index in range(start_index, len(items)):
        process_type = items[index][1].get("type", "element")
        if process_type == "condition_start":
            depth += 1
        elif process_type == "condition_true" and depth == 1:
            true_index = index
        elif process_type == "condition_false" and depth == 1:
            false_index = index
        elif process_type == "condition_end":
            if depth == 1:
                if true_index is None or false_index is None:
                    raise ValueError(f"조건처리 참/거짓 구역을 찾을 수 없습니다: {items[start_index][0]}")
                return true_index, false_index, index
            depth -= 1
    raise ValueError(f"조건처리 종료를 찾을 수 없습니다: {items[start_index][0]}")


def parse_repeat_count(key, value):
    match = re.search(r"-?[\d,]+", value)
    if not match:
        raise ValueError(f"반복 횟수를 숫자로 변환할 수 없습니다: {key}={value}")
    count = int(match.group(0).replace(",", ""))
    if count < 0:
        raise ValueError(f"반복 횟수는 0 이상이어야 합니다: {key}={count}")
    return count


def evaluate_condition(key, action, actual, expected, repeat_number):
    if action == "field_empty":
        result = not actual
    elif action == "field_not_empty":
        result = bool(actual)
    elif action == "text_exists":
        result = bool(actual)
    elif action == "equals_value":
        result = actual == expected
    elif action == "contains_value":
        result = bool(expected) and expected in actual
    elif action == "equals_repeat_number":
        result = actual == repeat_number
    elif action == "contains_repeat_number":
        result = bool(repeat_number) and repeat_number in actual
    else:
        raise ValueError(f"지원하지 않는 조건처리 동작입니다: {key} ({action})")
    return result


def validate_workflow_structure(rows):
    stack = []
    for key, selector in rows:
        process_type = selector.get("type", "element")
        if process_type == "repeat_start":
            stack.append(("repeat_start", key))
        elif process_type == "condition_start":
            stack.append(("condition_start", key))
        elif process_type == "condition_true":
            if not stack or stack[-1][0] != "condition_start":
                raise ValueError(f"조건처리의 조건 없이 참 구역이 나타났습니다: {key}")
            stack.append(("condition_true", key))
        elif process_type == "condition_false":
            if not stack or stack[-1][0] != "condition_true":
                raise ValueError(f"조건처리-참 없이 거짓 구역이 나타났습니다: {key}")
            stack.pop()
            stack.append(("condition_false", key))
        elif process_type == "repeat_end":
            if not stack or stack[-1][0] != "repeat_start":
                raise ValueError(f"반복지점 종료에 맞는 시작이 없습니다: {key}")
            stack.pop()
        elif process_type == "condition_end":
            if not stack or stack[-1][0] != "condition_false":
                raise ValueError(f"조건처리-거짓 없이 종료가 나타났습니다: {key}")
            stack.pop()
            if not stack or stack[-1][0] != "condition_start":
                raise ValueError(f"조건처리 시작에 맞는 종료가 아닙니다: {key}")
            stack.pop()
    if stack:
        raise ValueError(f"시작에 맞는 종료가 없습니다: {stack[-1][1]}")
    return True
