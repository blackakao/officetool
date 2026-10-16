"""Shared runtime storage; legacy files are copied, never moved or overwritten."""

import os
from pathlib import Path
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULTS_DIRECTORY = PROJECT_ROOT / "data" / "defaults"
USER_DATA_FILES = frozenset({
    "branches.json", "branch_fields.json", "branch_task_settings.json",
    "memos.json", "monthly_work_check.json", "incomplete_tasks.json",
    "document_field_settings.json", "hwp_document_field_settings.json",
    "document_generation_history.json", "table_lists.json",
    "labor_cost_ratio.json", "service_fee.json", "log_settings.json",
})


def runtime_directory(root=None):
    return Path(root or PROJECT_ROOT) / "data" / "runtime"


def _copy_if_missing(source, destination):
    """Publish a complete byte-for-byte copy without replacing an existing file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(source.read_bytes())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            pass  # Another process initialized the file first.
    finally:
        temporary.unlink()


def user_data_path(name, root=None):
    """Existing runtime > legacy data > shipped default, with no JSON rewriting.

    Unreadable sources raise an error rather than silently resetting user data.
    The optional project root keeps callers and tests independent of cwd.
    """
    if name not in USER_DATA_FILES:
        raise ValueError(f"Unknown user data file: {name}")
    root = Path(root or PROJECT_ROOT)
    destination = runtime_directory(root) / name
    if not destination.exists():
        legacy = root / "data" / name
        source = legacy if legacy.exists() else DEFAULTS_DIRECTORY / name
        _copy_if_missing(source, destination)
    return destination


def user_image_directory(root=None):
    # Legacy JSON may contain paths to data/branch_images. Keep those originals
    # in place; newly selected images go into runtime without changing JSON.
    directory = runtime_directory(root) / "branch_images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
