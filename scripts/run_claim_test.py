import sys
import json
from pathlib import Path

# Ensure workspace root is on sys.path so local packages can be imported
workspace_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_root))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.pages.federation_tool import FederationTool


def main():
    app = QApplication(sys.argv)
    tool = FederationTool()
    target_branch_name = sys.argv[1] if len(sys.argv) > 1 else "화성점"

    data_file = Path(__file__).resolve().parents[1] / "data" / "branches.json"
    if not data_file.exists():
        print("branches.json 파일을 찾을 수 없습니다:", data_file)
        return

    with open(data_file, "r", encoding="utf-8") as f:
        branches = json.load(f)

    target = None
    for b in branches:
        if b.get("branch_name") == target_branch_name:
            target = b
            break

    if not target and branches:
        print(f"{target_branch_name}이 없어 첫 번째 지점으로 대체합니다:", branches[0].get('branch_name'))
        target = branches[0]

    if not target:
        print("테스트할 지점 데이터가 없습니다.")
        return

    print("선택된 지점:", target.get('branch_name'))
    tool.on_branch_clicked(target)

    timeout_ms = 60000
    QTimer.singleShot(timeout_ms, app.quit)
    print(f"자동화 시작 - 최대 {timeout_ms // 1000}초 동안 대기합니다...")
    app.exec()
    print("스크립트 종료")


if __name__ == '__main__':
    main()
