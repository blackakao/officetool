"""희망이음 보안 프로그램 다운로드와 Windows 설치 마법사 처리."""

import json
import os
import re
from pathlib import Path
import subprocess
import time

from selenium.webdriver.support.ui import WebDriverWait


def wait_for_installer(directory, started_at, timeout=120):
    previous = {}

    def completed(_):
        candidates = sorted(Path(directory).glob("nos_setup*.exe"),
                            key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            stat = path.stat()
            if stat.st_mtime < started_at or stat.st_size == 0:
                continue
            if path.with_name(path.name + ".crdownload").exists():
                continue
            fingerprint = (stat.st_size, stat.st_mtime_ns)
            if previous.get(path) == fingerprint:
                return path
            previous[path] = fingerprint
        return False

    return WebDriverWait(None, timeout, poll_frequency=1).until(
        completed, "희망이음 보안 프로그램 다운로드가 완료되지 않았습니다."
    )


def verify_installer(path):
    # 경로는 환경변수로 전달하여 PowerShell 코드에 삽입하지 않습니다.
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $env:MYTOOL_NOS_INSTALLER; "
        "@{status=$s.Status.ToString();subject=$s.SignerCertificate.Subject} "
        "| ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "MYTOOL_NOS_INSTALLER": str(path)},
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    signature = json.loads(result.stdout)
    if signature["status"] != "Valid" or "INCA Internet Co.,Ltd." not in signature.get("subject", ""):
        raise RuntimeError("설치 파일의 INCA Internet 전자서명을 확인할 수 없습니다.")


def install_nprotect(path, report, timeout=300):
    if os.name != "nt":
        raise RuntimeError("보안 프로그램 자동 설치는 Windows에서만 지원합니다.")
    import pythoncom
    pythoncom.CoInitialize()
    try:
        _run_install_wizard(path, report, timeout)
    finally:
        pythoncom.CoUninitialize()


def _run_install_wizard(path, report, timeout):
    try:
        from pywinauto import Desktop
    except ImportError as error:
        raise RuntimeError("pywinauto가 필요합니다. requirements.txt의 의존성을 설치해주세요.") from error
    verify_installer(path)
    desktop = Desktop(backend="win32")
    title = r"^nProtect Online Security.*$"
    report("보안 프로그램 설치를 시작합니다. Windows 관리자 권한 요청이 뜨면 '예'를 눌러주세요.")
    if desktop.windows(title_re=title):
        report("이미 열린 nProtect 설치 창에서 설치를 이어갑니다.")
    else:
        os.startfile(str(path))
    state = {"seen": False, "finished": False}

    def advance(_):
        windows = desktop.windows(title_re=title, visible_only=True)
        if not windows:
            return state["seen"] and state["finished"]
        state["seen"] = True
        for window in windows:
            for text in window.descendants(class_name="Static"):
                if re.search(r"설치가 완료|설치를 완료|설치 완료|설치되었습니다", text.window_text()):
                    state["finished"] = True
            for button in window.descendants(class_name="Button"):
                label = button.window_text().replace("&", "").strip()
                label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip().strip("<> ")
                if label not in ("동의함", "다음", "설치", "마침", "완료", "닫기", "Finish", "Close"):
                    continue
                if button.is_visible() and button.is_enabled():
                    if label in ("마침", "완료", "닫기", "Finish", "Close"):
                        state["finished"] = True
                    try:
                        button.click()
                    except PermissionError as error:
                        raise RuntimeError(
                            "설치 창이 관리자 권한으로 실행되어 버튼을 제어할 수 없습니다. "
                            "현재 설치 창에서 설치를 완료하거나 MyTool을 관리자 권한으로 실행해주세요."
                        ) from error
                    return False
        return False

    WebDriverWait(None, timeout, poll_frequency=0.5).until(
        advance, "설치 완료를 확인하지 못했습니다. 설치 창 또는 관리자 권한 요청을 확인해주세요."
    )
    report("보안 프로그램 설치 창 처리를 완료했습니다. 희망이음에서 설치 상태를 다시 확인합니다.")
