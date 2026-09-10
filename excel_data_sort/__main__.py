import argparse
import json

from .engine import convert_many
from .exporter import export_excel
from .models import Template
from .readers import read_workbook


def main():
    parser = argparse.ArgumentParser(description="저장된 양식으로 Excel 파일을 Dataset으로 변환합니다.")
    parser.add_argument("files", nargs="+", help="입력 .xlsx / .xls 파일")
    parser.add_argument("--template", required=True, help="앱에서 저장한 양식 JSON")
    parser.add_argument("--output", required=True, help="출력 .xlsx 파일 (기존 파일 덮어쓰기 불가)")
    args = parser.parse_args()
    from pathlib import Path

    if Path(args.output).exists():
        parser.error("출력 파일이 이미 있습니다. 새 경로를 지정해 주세요.")
    try:
        with open(args.template, encoding="utf-8") as handle:
            template = Template.from_dict(json.load(handle))
        jobs = [(read_workbook(path), template) for path in args.files]
        datasets, warnings = convert_many(jobs)
        export_excel(datasets, args.output, args.files)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"오류: {exc}\n")
    for warning in warnings:
        print(warning)
    print(f"저장 완료: {args.output} / {sum(len(dataset.rows) for dataset in datasets):,}행")


if __name__ == "__main__":
    main()
