from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re


def text_key(value):
    """Ignore case and whitespace when comparing header labels."""
    return re.sub(r"\s+", "", "" if value is None else str(value)).casefold()


def is_empty(value):
    return value is None or isinstance(value, str) and not value.strip()


def header_key(value):
    key = text_key(value)
    match = re.fullmatch(r"(0?[1-9]|[12][0-9]|3[01])\([월화수목금토일]\)", key)
    return f"{int(match.group(1))}(요일)" if match else key


@dataclass
class SheetData:
    name: str
    rows: list[list]
    # All coordinates are one-based and inclusive, including merged ranges.
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)
    hidden_rows: set[int] = field(default_factory=set)
    hidden_columns: set[int] = field(default_factory=set)
    hidden: bool = False


@dataclass
class WorkbookData:
    path: Path
    sheets: list[SheetData]
    warnings: list[str] = field(default_factory=list)


@dataclass
class NormalizedSheet:
    name: str
    rows: list[list]
    row_numbers: list[int]
    column_numbers: list[int]
    # Retain blank boundaries even though Normalize removes the rows themselves.
    blank_rows: set[int]


@dataclass
class ColumnRule:
    source_column: int
    header: str
    output_name: str
    enabled: bool = True


@dataclass
class AddedColumn:
    name: str
    position: int = 1  # One-based position in the final output, before source metadata.
    mode: str = "fixed"
    value: str = ""
    sheet_name: str = ""  # Empty means the sheet currently being converted.
    cell: str = "A1"
    value_mapping: dict[str, str] = field(default_factory=dict)
    branch_lookup: dict[str, str] = field(default_factory=dict)


@dataclass
class Template:
    name: str
    sheet_name: str
    header_row: int = 1
    data_start_row: int = 2
    data_end_row: int = 0
    header_start_column: int = 1
    header_end_column: int = 0
    columns: list[ColumnRule] = field(default_factory=list)
    merge_mode: str = "fill"  # fill, anchor
    include_hidden_rows: bool = False
    include_hidden_columns: bool = False
    include_hidden_sheets: bool = False
    table_mode: str = "merge"  # merge, separate, first
    sheet_mode: str = "matching"  # matching, separate, selected
    header_match: str = "all"  # all configured headers or selected headers
    stop_at_blank: bool = False
    stop_values: list[str] = field(default_factory=list)
    include_source: bool = True
    signature: dict = field(default_factory=dict)
    version: int = 1
    added_columns: list[AddedColumn] = field(default_factory=list)

    def validate(self):
        for name in ("name", "sheet_name", "merge_mode", "table_mode", "sheet_mode", "header_match"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name}: 문자열 설정이 필요합니다.")
        for name in ("version", "header_row", "data_start_row", "data_end_row", "header_start_column", "header_end_column"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name}: 정수 설정이 필요합니다.")
        for name in ("include_hidden_rows", "include_hidden_columns", "include_hidden_sheets", "stop_at_blank", "include_source"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name}: true 또는 false 설정이 필요합니다.")
        if not isinstance(self.signature, dict) or not isinstance(self.stop_values, list) or any(
            not isinstance(value, str) for value in self.stop_values
        ):
            raise ValueError("인식 특징 또는 종료 값 설정을 확인해 주세요.")
        for column in self.columns:
            if (type(column.source_column) is not int or type(column.enabled) is not bool
                    or not isinstance(column.header, str) or not isinstance(column.output_name, str)):
                raise ValueError("컬럼 설정의 자료형을 확인해 주세요.")
        if self.version != 1:
            raise ValueError("지원하지 않는 양식 버전입니다.")
        if not self.name.strip() or re.search(r'[<>:"/\\|?*\x00-\x1f]', self.name):
            raise ValueError("양식 이름에는 파일명에 사용할 수 없는 문자를 넣을 수 없습니다.")
        if self.name.rstrip(" .") != self.name or self.name in {".", ".."}:
            raise ValueError("양식 이름의 끝에 공백이나 마침표를 사용할 수 없습니다.")
        if self.name.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }:
            raise ValueError("Windows 예약 파일명은 양식 이름으로 사용할 수 없습니다.")
        if not self.sheet_name or self.header_row < 1 or self.data_start_row <= self.header_row:
            raise ValueError("데이터 시작행은 헤더행보다 커야 합니다.")
        if not 1 <= self.header_row < self.data_start_row <= 1_048_576:
            raise ValueError("행 번호는 Excel 범위 안에서 헤더행 < 시작행 순서로 지정해 주세요.")
        if self.data_end_row < 0 or self.data_end_row > 1_048_576:
            raise ValueError("끝행은 0 또는 Excel 범위의 행 번호여야 합니다.")
        if self.data_end_row and self.data_end_row < self.data_start_row:
            raise ValueError("데이터 끝행은 시작행 이상이어야 합니다. 자동이면 0을 입력합니다.")
        if not 1 <= self.header_start_column <= 16_384 or not 0 <= self.header_end_column <= 16_384:
            raise ValueError("기준 테이블 열 범위가 Excel 범위를 벗어났습니다.")
        if self.header_end_column and self.header_end_column < self.header_start_column:
            raise ValueError("기준 테이블의 끝 열은 첫 열 이상이어야 합니다.")
        for value, allowed in (
            (self.merge_mode, {"fill", "anchor"}),
            (self.table_mode, {"merge", "separate", "first"}),
            (self.sheet_mode, {"matching", "separate", "selected"}),
            (self.header_match, {"all", "selected"}),
        ):
            if value not in allowed:
                raise ValueError(f"알 수 없는 설정 값: {value}")
        selected = [column for column in self.columns if column.enabled]
        if not selected:
            raise ValueError("사용할 컬럼을 하나 이상 선택해 주세요.")
        if any(column.source_column < 1 or not column.header.strip() for column in self.columns):
            raise ValueError("원본 컬럼 번호와 헤더명을 확인해 주세요.")
        positions = [column.source_column for column in self.columns]
        if len(set(positions)) != len(positions):
            raise ValueError("원본 컬럼 번호가 중복되었습니다.")
        names = [column.output_name.strip() for column in selected]
        added_positions = []
        for column in self.added_columns:
            if not isinstance(column, AddedColumn) or any(
                not isinstance(getattr(column, key), str)
                for key in ("name", "mode", "value", "sheet_name", "cell")
            ):
                raise ValueError("추가 컬럼 설정의 자료형을 확인해 주세요.")
            if type(column.position) is not int or not 1 <= column.position <= len(selected) + len(self.added_columns):
                raise ValueError("추가 컬럼 위치는 최종 출력 컬럼 범위 안이어야 합니다.")
            if column.mode not in {"fixed", "cell"}:
                raise ValueError("추가 컬럼의 값 방식을 확인해 주세요.")
            if column.mode == "cell":
                from openpyxl.utils.cell import coordinate_to_tuple

                if not re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]{0,6}", column.cell):
                    raise ValueError("참조 셀은 A1 같은 원본 Excel 주소로 입력해 주세요.")
                row, col = coordinate_to_tuple(column.cell)
                if row > 1_048_576 or col > 16_384:
                    raise ValueError("참조 셀이 Excel 범위를 벗어났습니다.")
            added_positions.append(column.position)
            if not isinstance(column.branch_lookup, dict) or column.branch_lookup and (
                set(column.branch_lookup) != {"match_field", "return_field"}
                or any(not isinstance(value, str) or not value for value in column.branch_lookup.values())
            ):
                raise ValueError("지점 조회의 조회 필드와 가져올 필드를 지정해 주세요.")
            if not isinstance(column.value_mapping, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in column.value_mapping.items()
            ):
                raise ValueError("값 매핑은 인식값과 변경값을 문자열로 지정해 주세요.")
            names.append(column.name.strip())
        if len(set(added_positions)) != len(added_positions):
            raise ValueError("추가 컬럼 위치가 중복되었습니다.")
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("출력 컬럼명은 비어 있거나 중복될 수 없습니다.")
        if self.include_source and set(names) & {"_원본파일", "_원본시트", "_원본행", "_테이블"}:
            raise ValueError("출처 표시용 컬럼명(_원본파일, _원본시트, _원본행, _테이블)은 사용할 수 없습니다.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        payload = dict(data)
        payload["columns"] = [ColumnRule(**column) for column in payload.get("columns", [])]
        payload["added_columns"] = [AddedColumn(**column) for column in payload.get("added_columns", [])]
        template = cls(**payload)
        template.validate()
        return template


class TemplateStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def load_all(self):
        templates, errors = [], []
        for path in sorted(self.directory.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as handle:
                    template = Template.from_dict(json.load(handle))
                if template.name != path.stem:
                    raise ValueError("파일명과 양식 이름이 일치하지 않습니다.")
                templates.append(template)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{path.name}: {exc}")
        return templates, errors

    def save(self, template):
        template.validate()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{template.name}.json"
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(template.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
        return path


@dataclass
class Dataset:
    name: str
    columns: list[str]
    rows: list[list] = field(default_factory=list)


@dataclass
class ConversionResult:
    normalized: list[NormalizedSheet]
    datasets: list[Dataset]
    warnings: list[str] = field(default_factory=list)
