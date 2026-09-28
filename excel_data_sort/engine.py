from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Protocol

from .models import ConversionResult, Dataset, Template, header_key, is_empty, text_key
from .normalize import normalize, expand_record_rows
from .branch_lookup import load_branch_data, lookup_branch


def added_column_value(workbook, current_sheet, column, branch_data=None):
    value = added_column_raw_value(workbook, current_sheet, column)
    return mapped_column_value(value, column, branch_data)


def mapped_column_value(value, column, branch_data=None):
    if column.branch_lookup:
        return lookup_branch(value, column.branch_lookup, branch_data)[1]
    return column.value_mapping.get("" if value is None else str(value), value)


def added_column_raw_value(workbook, current_sheet, column):
    if column.mode == "fixed":
        return column.value
    from openpyxl.utils.cell import coordinate_to_tuple

    source = next((sheet for sheet in workbook.sheets if sheet.name == column.sheet_name), None) if column.sheet_name else current_sheet
    if source is None:
        raise ValueError(f"추가 컬럼 '{column.name}': 참조 시트 '{column.sheet_name}'가 없습니다.")
    values = []
    for address in column.cell_addresses():
        row, col = coordinate_to_tuple(address)
        for r0, r1, c0, c1 in source.merges:
            if r0 <= row <= r1 and c0 <= col <= c1:
                row, col = r0, c0
                break
        value = None if row > len(source.rows) or col > len(source.rows[row - 1]) else source.rows[row - 1][col - 1]
        values.append(value)
    if len(values) == 1:
        return values[0]
    return column.separator.join(str(value) for value in values if not is_empty(value))


@dataclass
class HeaderLocation:
    row_index: int
    # Template source column -> normalized column index (supports reordered columns).
    mapping: dict[int, int]


class TableDetector(Protocol):
    """An AI detector can implement this interface without changing the exporter/UI."""

    def locate(self, sheet, template: Template) -> list[HeaderLocation]: ...


class RuleTableDetector:
    def locate(self, sheet, template):
        if template.record_rows > 1:
            width = len(sheet.column_numbers) // template.record_rows
            bands = {}
            for offset in sorted({column.row_offset for column in template.columns
                                  if template.header_match == "all" or column.enabled}):
                rules = [replace(column, row_offset=0) for column in template.columns
                         if column.row_offset == offset]
                band = replace(sheet, rows=[row[offset * width:(offset + 1) * width] for row in sheet.rows],
                               column_numbers=sheet.column_numbers[:width])
                by_row = defaultdict(list)
                for location in self.locate(band, replace(template, record_rows=1, columns=rules)):
                    by_row[location.row_index].append(location)
                bands[offset] = by_row
            locations = []
            if not bands:
                return locations
            for row_index in sorted(set.intersection(*(set(band) for band in bands.values()))):
                counts = {len(band[row_index]) for band in bands.values()}
                if len(counts) != 1:
                    continue
                for block in range(counts.pop()):
                    mapping = {key + offset * 16_384: value + offset * width
                               for offset, band in bands.items()
                               for key, value in band[row_index][block].mapping.items()}
                    locations.append(HeaderLocation(row_index, mapping))
            return locations
        rules = sorted(
            [column for column in template.columns if template.header_match == "all" or column.enabled],
            key=lambda column: column.source_key,
        )
        required = Counter((column.row_offset, header_key(column.header)) for column in rules)
        locations = []
        for row_index, row in enumerate(sheet.rows):
            found = defaultdict(list)
            for column_index, value in enumerate(row):
                key = ((sheet.column_numbers[column_index] - 1) // 16_384, header_key(value))
                if key not in required:
                    continue
                # A repeated partial header starts a new candidate block.
                if len(found[key]) == required[key]:
                    found = defaultdict(list)
                found[key].append(column_index)
                if all(len(found[label]) == count for label, count in required.items()):
                    occurrences = Counter()
                    mapping = {}
                    for rule in rules:
                        label = (rule.row_offset, header_key(rule.header))
                        mapping[rule.source_key] = found[label][occurrences[label]]
                        occurrences[label] += 1
                    locations.append(HeaderLocation(row_index, mapping))
                    found = defaultdict(list)
        return locations


def convert(workbook, template, detector=None):
    template.validate()
    detector = detector or RuleTableDetector()
    selected = [column for column in template.columns if column.enabled]
    output_columns = [column.output_name.strip() for column in selected]
    additions = sorted(template.added_columns, key=lambda column: column.position)
    branch_data = load_branch_data() if any(column.branch_lookup for column in [*selected, *additions]) else None
    for column in additions:
        output_columns.insert(column.position - 1, column.name.strip())
    if template.include_source:
        output_columns += ["_원본파일", "_원본시트", "_원본행", "_테이블"]
    normalized, grouped = [], {}
    warnings = list(workbook.warnings)
    offset = template.data_start_row - template.header_row
    stop_values = {text_key(value) for value in template.stop_values if not is_empty(value)}
    for original in workbook.sheets:
        if original.hidden and not template.include_hidden_sheets:
            warnings.append(f"{original.name}: 숨김 시트 제외")
            continue
        if template.sheet_mode == "selected" and original.name != template.sheet_name:
            continue
        sheet = normalize(original, template)
        normalized.append(sheet)
        sheet = expand_record_rows(sheet, template.record_rows)
        locations = detector.locate(sheet, template)
        if not locations:
            warnings.append(f"{sheet.name}: 일치하는 헤더가 없어 제외")
            continue
        extra_values = [added_column_value(workbook, original, column, branch_data) for column in additions]
        for table_index, location in enumerate(locations, 1):
            if template.table_mode == "first" and table_index > 1:
                break
            first_row = sheet.row_numbers[location.row_index] + offset
            end_row = (sheet.row_numbers[location.row_index] + template.data_end_row - template.header_row
                       if template.data_end_row else None)
            positions = [location.mapping[column.source_key] for column in selected]
            region = set(location.mapping.values())
            next_header = next((candidate.row_index for candidate in locations
                                if candidate.row_index > location.row_index
                                and region.intersection(candidate.mapping.values())), len(sheet.rows))
            key = [template.name]
            if template.sheet_mode == "separate" or template.table_mode == "separate":
                key.append(sheet.name)
            if template.table_mode == "separate":
                key.append(str(table_index))
            group_key = tuple(key)
            dataset = grouped.setdefault(group_key, Dataset(" · ".join(key), output_columns))
            previous_row = first_row - 1
            for index in range(location.row_index + 1, next_header):
                row_number = sheet.row_numbers[index]
                if row_number < first_row:
                    continue
                if (row_number - first_row) % template.record_rows:
                    continue
                if end_row and row_number > end_row:
                    break
                if template.stop_at_blank and any(
                    number in sheet.blank_rows for number in range(previous_row + 1, row_number)
                ):
                    break
                previous_row = row_number + template.record_rows - 1
                row = sheet.rows[index]
                # Check the full matched table, including columns excluded from output.
                if any(text_key(row[position]) in stop_values for position in region):
                    break
                if template.record_rows > 1:
                    last_row = row_number + template.record_rows - 1
                    boundary = sheet.row_numbers[next_header] if next_header < len(sheet.rows) else len(original.rows) + 1
                    if last_row >= boundary or end_row and last_row > end_row:
                        raise ValueError(f"{sheet.name}: {row_number}행의 데이터 묶음이 {template.record_rows}행보다 짧습니다.")
                    if not template.include_hidden_rows and any(r in original.hidden_rows for r in range(row_number, last_row + 1)):
                        continue
                values = [row[position] for position in positions]
                if all(is_empty(row[position]) for position in region):
                    if template.stop_at_blank:
                        break
                    continue
                if all(is_empty(value) for value in values):
                    continue
                values = [mapped_column_value(value, column, branch_data) for value, column in zip(values, selected)]
                for column, value in zip(additions, extra_values):
                    values.insert(column.position - 1, value)
                if template.include_source:
                    values += [workbook.path.name, sheet.name, row_number, table_index]
                dataset.rows.append(values)
    datasets = [dataset for dataset in grouped.values() if dataset.rows]
    if not datasets:
        raise ValueError("추출된 데이터가 없습니다. 헤더·시트·시작행·숨김 옵션·종료 조건을 확인해 주세요.")
    return ConversionResult(normalized, datasets, warnings)


def convert_many(jobs, detector=None):
    """Combine compatible datasets; fail the batch if any input cannot convert."""
    grouped, warnings, errors = {}, [], []
    for book, template in jobs:
        try:
            result = convert(book, template, detector)
            warnings.extend(f"{book.path.name}: {warning}" for warning in result.warnings)
            for dataset in result.datasets:
                key = (dataset.name, tuple(dataset.columns))
                if template.table_mode == "separate" or template.sheet_mode == "separate":
                    key += (str(book.path),)
                target = grouped.setdefault(key, Dataset(dataset.name, dataset.columns))
                target.rows.extend(dataset.rows)
        except (ValueError, KeyError) as exc:
            errors.append(f"{book.path.name}: {exc}")
    if errors:
        raise ValueError("저장하지 않았습니다. 다음 파일의 설정을 확인해 주세요:\n" + "\n".join(errors))
    return list(grouped.values()), warnings
