"""Normalize explicit year-first birth dates without guessing ambiguous dates."""

from datetime import date, datetime
import math
import re
import unicodedata


def normalize_birthdate(value, mode="recent100", current_year=None):
    if value is None or isinstance(value, str) and not value.strip():
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        raise ValueError("생년월일로 변환할 수 없는 값입니다.")
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        value = int(value)
    text = unicodedata.normalize("NFKC", str(value)).strip()
    match = re.fullmatch(r"([0-9]{4}|[0-9]{2})([0-9]{2})([0-9]{2})", text)
    if match is None:
        match = re.fullmatch(r"([0-9]{4}|[0-9]{2})\s*[-./년\s]\s*([0-9]{1,2})\s*[-./월\s]\s*([0-9]{1,2})\s*일?\s*\.?", text)
    if match is None:
        # Only an explicit four-digit ISO date may carry a time component.
        if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]", text):
            try:
                return datetime.fromisoformat(text).date().isoformat()
            except ValueError:
                pass
        raise ValueError("생년월일 형식을 인식할 수 없습니다. 연-월-일 순서의 날짜를 확인해 주세요.")
    year_text, month, day = match.groups()
    year = int(year_text)
    if len(year_text) == 2:
        if mode == "1900":
            year += 1900
        else:
            reference = date.today().year if current_year is None else current_year
            year += reference // 100 * 100
            if year > reference:
                year -= 100
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError as exc:
        raise ValueError("존재하지 않는 생년월일입니다. 연·월·일을 확인해 주세요.") from exc
