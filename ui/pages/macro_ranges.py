from datetime import date
import re


RANGE_TYPES = {"integer": "정수", "year": "연", "month": "연월", "day": "연월일"}


def range_values(settings):
    kind = settings.get("kind", "integer")
    if kind not in RANGE_TYPES:
        raise ValueError("반복값 종류를 확인하세요.")
    step = int(settings.get("step", 1))
    if step < 1:
        raise ValueError("반복 간격은 1 이상이어야 합니다.")
    direction = settings.get("direction", "descending")
    if direction not in {"ascending", "descending"}:
        raise ValueError("반복 방향을 확인하세요.")

    def parse(value):
        text = str(value).strip()
        if kind == "integer":
            if not re.fullmatch(r"-?\d+", text):
                raise ValueError("정수 시작값·종료값을 입력하세요.")
            return int(text)
        pattern = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}[kind]
        if not re.fullmatch(pattern, text):
            raise ValueError("연은 YYYY, 연월은 YYYY-MM, 연월일은 YYYY-MM-DD로 입력하세요.")
        parts = [int(part) for part in text.split("-")]
        parsed = date(*(parts + [1] * (3 - len(parts))))
        return parsed.year if kind == "year" else ((parsed.year - 1) * 12 + parsed.month - 1 if kind == "month" else parsed.toordinal())

    start, end = parse(settings.get("start", "")), parse(settings.get("end", ""))
    if direction == "descending":
        step = -step
    if (end - start) * step < 0:
        raise ValueError("시작값·종료값 순서와 반복 방향이 맞지 않습니다.")
    count = abs(end - start) // abs(step) + 1
    if count > 1_000_000:
        raise ValueError("반복 횟수가 100만 회를 초과합니다.")

    def format_value(value):
        if kind == "integer":
            return value
        if kind == "year":
            return f"{value:04d}"
        if kind == "month":
            year, month = divmod(value, 12)
            return f"{year + 1:04d}-{month + 1:02d}"
        return date.fromordinal(value).isoformat()

    return [format_value(start + index * step) for index in range(count)]
