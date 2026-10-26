"""Document-folder migration without modifying legacy documents."""

import json
from pathlib import Path

from data_paths import _copy_if_missing, runtime_directory


def unified_document_folder(root):
    root = Path(root)
    folder = root / "document"
    folder.mkdir(parents=True, exist_ok=True)
    legacy = root / "document_hwp"
    if not legacy.is_dir():
        return folder

    state_path = runtime_directory(root) / "document_folder_migration.json"
    if state_path.exists():
        with state_path.open(encoding="utf-8") as stream:
            state = json.load(stream)
    else:
        state = {"files": {}}

    sources = sorted(
        path for path in legacy.rglob("*")
        if path.is_file() and (
            (path.parent == legacy and path.suffix.lower() == ".hwp")
            or path.relative_to(legacy).parts[0] == "maked"
        )
    )
    for source in sources:
        relative = source.relative_to(legacy)
        key = relative.as_posix()
        if key in state["files"]:
            continue
        target = folder / relative
        # The unified template takes precedence. Keep the legacy original as
        # backup; never rename a template and break its settings/history key.
        if relative.parts[0] == "maked":
            number = 1
            while target.exists() and target.read_bytes() != source.read_bytes():
                target = folder / relative.parent / f"{source.stem}({number}){source.suffix}"
                number += 1
        _copy_if_missing(source, target)
        state["files"][key] = target.relative_to(folder).as_posix()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
        temporary.replace(state_path)
    return folder
