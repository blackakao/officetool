"""Explicit, reusable output column transformations."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata


def transform_value(value, mode):
    if mode == "off" or value is None or isinstance(value, str) and not value.strip():
        return value
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if mode == "letters":
        # A numbered qualification suffix belongs to the code, not the job name.
        text = re.sub(r"\s*[0-9]+\s*급\s*$", "", text)
        return " ".join("".join(char for char in text if char.isalpha() or char.isspace()).split())
    if mode == "hours":
        if isinstance(value, bool):
            raise ValueError("시간·분 값이 아닙니다.")
        match = re.fullmatch(r"(?:(\d+)\s*시간)?\s*(?:(\d+)\s*분)?", text)
        try:
            if match and any(match.groups()):
                hours = Decimal(match[1] or 0) + Decimal(match[2] or 0) / 60
            else:
                # Already numeric values are interpreted as decimal hours.
                hours = Decimal(text)
            if not hours.is_finite() or hours < 0:
                raise InvalidOperation
            return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        except InvalidOperation as exc:
            raise ValueError("시간·분 형식을 확인해 주세요. 예: 160시간20분") from exc
    raise ValueError("알 수 없는 값 변환 방식입니다.")
