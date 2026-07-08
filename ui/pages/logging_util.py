from datetime import datetime
import json
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "login.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_SETTINGS_FILE = LOG_FILE.parent / "log_settings.json"

DETAIL_LOG_PREFIXES = (
    "[table_click]",
    "[table_virtual]",
    "[table_debug]",
    "[table_scroll]",
    "[요소조회]",
)


def load_log_settings() -> dict:
    try:
        with open(LOG_SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            return settings if isinstance(settings, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_log_settings(settings: dict):
    try:
        with open(LOG_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def verbose_log_enabled() -> bool:
    return bool(load_log_settings().get("verbose", False))


def is_detail_message(message: str) -> bool:
    stripped = str(message).lstrip()
    return stripped.startswith(DETAIL_LOG_PREFIXES)


def should_log_message(message: str) -> bool:
    return verbose_log_enabled() or not is_detail_message(message)


def log(tool: str, message: str, level: str = "INFO") -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"{ts} [{level}] [{tool}] {message}"
    print(text, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    return text
