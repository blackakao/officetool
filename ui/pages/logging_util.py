from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[2] / "data" / "login.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


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
