"""User menu placement, independent of page widgets."""

import json
import os
import tempfile
from pathlib import Path


def validate_groups(groups):
    if not isinstance(groups, list) or not groups:
        raise ValueError("대메뉴가 하나 이상 필요합니다.")
    ids, names, pages = set(), set(), set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("잘못된 대메뉴 설정입니다.")
        key, name, entries = group.get("id"), group.get("name"), group.get("pages")
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError("대메뉴 식별자가 중복되거나 비어 있습니다.")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
            raise ValueError("대메뉴 이름은 비어 있거나 중복될 수 없습니다.")
        if not isinstance(entries, list):
            raise ValueError("잘못된 하위 메뉴 목록입니다.")
        ids.add(key)
        names.add(name)
        for page in entries:
            if not isinstance(page, str) or not page or page in pages:
                raise ValueError("하위 메뉴가 중복되거나 잘못되었습니다.")
            pages.add(page)


def reconcile_groups(saved, defaults):
    """Keep placement and add newly registered pages without duplicating them."""
    validate_groups(saved)
    known = {page for group in defaults for page in group['pages']}
    result = [dict(id=g['id'], name=g['name'], pages=[p for p in g['pages'] if p in known])
              for g in saved]
    assigned = {p for g in result for p in g['pages']}
    for default in defaults:
        missing = [p for p in default['pages'] if p not in assigned]
        if not missing:
            continue
        target = next((g for g in result if g['id'] == default['id']), None)
        if target is None:
            target = next((g for g in result if g['name'] == default['name']), None)
        if target is None:
            target = dict(id=default['id'], name=default['name'], pages=[])
            result.append(target)
        target['pages'].extend(missing)
        assigned.update(missing)
    return result


def load_layout(path, defaults):
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return reconcile_groups(defaults, defaults)
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError("지원하지 않는 메뉴 설정입니다.")
    # The shipped empty setting means use the current registered defaults.
    groups = data.get('groups')
    return reconcile_groups(defaults if groups == [] else groups, defaults)


def save_layout(path, groups):
    validate_groups(groups)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(dict(version=1, groups=groups), file, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
