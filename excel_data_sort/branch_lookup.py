import json
from pathlib import Path


DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
BASE_FIELDS = {
    "organization_code": "기관기호", "organization_name": "기관명",
    "branch_name": "지점명", "corporation_name": "법인명",
    "owner_name": "대표자명", "address": "주소",
}


def load_branch_data():
    try:
        branches = json.loads((DATA_DIRECTORY / "branches.json").read_text(encoding="utf-8"))
        path = DATA_DIRECTORY / "branch_fields.json"
        custom = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(branches, list) or any(not isinstance(row, dict) for row in branches):
            raise ValueError("지점 목록 형식이 올바르지 않습니다.")
        fields = dict(BASE_FIELDS)
        fields.update({field["key"]: field["label"] for field in custom if field.get("type", "text") == "text"})
        return branches, fields
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"지점 관리 데이터를 읽을 수 없습니다: {exc}") from exc


def field_value(branch, key):
    return branch.get(key) if key in BASE_FIELDS else branch.get("custom_fields", {}).get(key)


def lookup_key(value):
    # Excel may store identifiers as numbers; preserve leading zeros in text IDs.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "" if value is None else str(value).strip()


def lookup_branch(value, settings, data=None):
    branches, fields = data if data is not None else load_branch_data()
    match_field, return_field = settings["match_field"], settings["return_field"]
    if match_field not in fields or return_field not in fields:
        raise ValueError("지점 관리 조회 필드가 삭제되었거나 지원하지 않는 필드입니다. 매핑 설정을 확인해 주세요.")
    key = lookup_key(value)
    matches = [branch for branch in branches if key and lookup_key(field_value(branch, match_field)) == key]
    if not matches:
        raise ValueError(f"지점 조회: {fields[match_field]}에서 '{key}'와 일치하는 지점이 없습니다.")
    if len(matches) > 1:
        raise ValueError(f"지점 조회: {fields[match_field]}의 '{key}'가 {len(matches)}개 지점과 중복됩니다.")
    branch = matches[0]
    return branch, field_value(branch, return_field)
