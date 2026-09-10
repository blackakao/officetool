from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .engine import RuleTableDetector
from .models import header_key, text_key
from .normalize import normalize


def build_signature(workbook, template):
    source = next((sheet for sheet in workbook.sheets if sheet.name == template.sheet_name), None)
    if source is None:
        raise ValueError("기준 시트를 찾을 수 없습니다.")
    return {
        "headers": [text_key(column.header) for column in template.columns],
        "column_count": len(template.columns),
        "merges": [list(area) for area in source.merges],
        "sheet_names": [sheet.name for sheet in workbook.sheets],
        "sheet_count": len(workbook.sheets),
    }


@dataclass
class Match:
    template: object
    score: float
    header_score: float
    details: str
    usable: bool


@dataclass
class RecognitionResult:
    matches: list[Match]
    selected: object | None
    reason: str


class Recognizer(Protocol):
    def recognize(self, workbook, templates) -> RecognitionResult: ...


def _overlap(left, right):
    left, right = Counter(left), Counter(right)
    return sum((left & right).values()) / max(sum(left.values()), sum(right.values()), 1)


class RuleRecognizer:
    """Conservative matching; structural similarities cannot replace missing headers."""

    def recognize(self, workbook, templates):
        matches = []
        detector = RuleTableDetector()
        for template in templates:
            signature = template.signature
            expected = [header_key(column.header) for column in template.columns
                        if template.header_match == "all" or column.enabled]
            best = (0.0, 0.0, False)
            best_details = "대상 시트 없음 (기준 시트명 또는 숨김 시트 설정 확인)"
            for source in workbook.sheets:
                if source.hidden and not template.include_hidden_sheets:
                    continue
                if template.sheet_mode == "selected" and source.name != template.sheet_name:
                    continue
                sheet = normalize(source, template)
                locations = detector.locate(sheet, template)
                row_index = max(range(len(sheet.rows)), key=lambda i: sum((Counter(expected) & Counter(header_key(value) for value in sheet.rows[i])).values()), default=None)
                found = Counter(header_key(value) for value in sheet.rows[row_index]) if row_index is not None else Counter()
                matched = sum((Counter(expected) & found).values())
                header = matched / max(len(expected), 1)
                column_similarity = 0.0
                if locations:
                    location = locations[0]
                    positions = list(location.mapping.values())
                    width = max(positions) - min(positions) + 1
                    column_similarity = min(len(expected), width) / max(len(expected), width)
                merge_similarity = _overlap(
                    [tuple(area) for area in signature.get("merges", [])], source.merges,
                ) if source.merges or signature.get("merges") else 1.0
                expected_names = signature.get("sheet_names", [template.sheet_name])
                sheet_similarity = (
                    0.5 * _overlap(expected_names, [sheet.name for sheet in workbook.sheets])
                    + 0.5 * min(len(expected_names), len(workbook.sheets))
                    / max(len(expected_names), len(workbook.sheets), 1)
                )
                score = 0.65 * header + 0.15 * column_similarity + 0.10 * merge_similarity + 0.10 * sheet_similarity
                if (score, header, bool(locations)) > best:
                    best = (score, header, bool(locations))
                    missing = Counter(expected) - found
                    missing_text = ", ".join(f"{label} ×{count}" for label, count in missing.items()) or "없음"
                    best_details = (
                        f"시트 '{source.name}' / 헤더 후보 원본 {sheet.row_numbers[row_index] if row_index is not None else '-'}행\n"
                        f"헤더 {matched}/{len(expected)} ({header:.1%}), 열 구조 {column_similarity:.1%}, "
                        f"병합 구조 {merge_similarity:.1%}, 시트 구성 {sheet_similarity:.1%}\n"
                        f"누락·불일치 헤더: {missing_text}\n"
                        f"추출 가능한 헤더 구조: {'있음' if locations else '없음 (헤더 순서·중복 개수·숨김 열 확인)'}"
                    )
            matches.append(Match(template, best[0], best[1],
                                 f"유사도 {best[0]:.1%} (기준 80%)\n{best_details}", best[2]))
        matches.sort(key=lambda match: match.score, reverse=True)
        if not matches:
            return RecognitionResult([], None, "등록된 양식이 없습니다. 새 양식을 설정해 주세요.")
        best = matches[0]
        if best.score < 0.80 or not best.usable:
            causes = []
            if best.score < 0.80:
                causes.append(f"최고 점수 {best.score:.1%} < 기준 80%")
            if not best.usable:
                causes.append("추출 가능한 헤더 구조 없음")
            return RecognitionResult(matches, None, "자동 인식 기준 미달: " + " / ".join(causes))
        if len(matches) > 1 and best.score - matches[1].score < 0.06:
            return RecognitionResult(matches, None, f"유사한 양식이 여러 개입니다. 상위 후보 점수 차이 {best.score - matches[1].score:.1%} < 기준 6%. 사용할 양식을 직접 선택해 주세요.")
        return RecognitionResult(matches, best.template, f"자동 선택: {best.template.name} (유사도 {best.score:.1%})")


def recognition_log(result):
    return result.reason + "\n" + "\n".join(
        f"[후보 {index}: {match.template.name}] {match.details}"
        for index, match in enumerate(result.matches, 1)
    )
