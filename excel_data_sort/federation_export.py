"""Apply user-saved templates to federation exports without changing originals."""

from dataclasses import replace
import json
from pathlib import Path

from .engine import convert
from .exporter import export_excel
from .models import ColumnRule, Dataset, Template, WorkbookData, text_key
from .readers import read_workbook


def sort_federation_export(path, mapping, log, branch_name='', template_dir=None):
    path = Path(path)
    template_dir = Path(template_dir) if template_dir else Path(__file__).resolve().parents[1] / 'data' / 'excel_templates'
    workbook = read_workbook(path)
    datasets = []
    for sheet in workbook.sheets:
        template_name = mapping.get(sheet.name)
        if not template_name:
            datasets.append(Dataset('원본_' + sheet.name, sheet.rows[0], sheet.rows[1:]))
            log(f'[table_sort] {sheet.name}: 연결 양식 없음, 원본 시트 보존')
            continue
        try:
            # Match registered names, never interpret a mapping as a file path.
            candidates = {p.stem: p for p in template_dir.glob('*.json')}
            with candidates[template_name].open(encoding='utf-8') as handle:
                template = Template.from_dict(json.load(handle))
            template = replace(template, sheet_name=sheet.name, sheet_mode='selected')
            headers = sheet.rows[0] if sheet.rows else []
            # Extraction combines stacked headers ("상위 / 하위"). Adapt only
            # unique parent-label matches; leave ambiguous labels to the engine.
            adapted = []
            for column in template.columns:
                exact = [value for value in headers if text_key(value) == text_key(column.header)]
                expanded = [value for value in headers if value and
                            text_key(str(value).split(' / ')[0]) == text_key(column.header)]
                adapted.append(replace(column, header=str(expanded[0]))
                               if not exact and len(expanded) == 1 else column)
            template = replace(template, columns=adapted)
            if any(text_key(value) == text_key('지점명') for value in headers):
                if not any(column.output_name == '지점명' and column.enabled for column in template.columns):
                    branch = ColumnRule(max((c.source_column for c in template.columns), default=0) + 1,
                                        '지점명', '지점명')
                    template = replace(template, columns=[branch, *template.columns])
            result = convert(WorkbookData(workbook.path, [sheet]), template)
            for dataset in result.datasets:
                if branch_name and '지점명' not in dataset.columns:
                    dataset.columns.insert(0, '지점명')
                    dataset.rows = [[branch_name, *row] for row in dataset.rows]
                datasets.append(dataset)
                log(f'[table_sort] {sheet.name} → {template.name}: {len(dataset.rows)}행')
        except (KeyError, ValueError, OSError, TypeError) as exc:
            datasets.append(Dataset('미정렬_' + sheet.name, sheet.rows[0], sheet.rows[1:]))
            log(f'[table_sort_warning] {sheet.name}: {exc}; 미정렬 시트로 원본 보존')
    output = path.with_name(path.stem + '_정렬.xlsx')
    export_excel(datasets, output, source_paths=[path])
    log(f'[table_sort_complete] 등록 양식 정렬 결과: {output}')
    return output
