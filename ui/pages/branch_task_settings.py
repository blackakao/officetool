import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


BRANCH_TASKS = {
    "login": "로그인툴",
    "document": "문서작성툴",
    "monthly_work": "월간업무체크",
    "federation": "공단툴",
    "carefor": "케어포툴",
}


def branch_key(branch):
    return str(branch.get("organization_code") or branch.get("branch_name") or "").strip()


def load_task_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def filter_branches_for_task(branches, task_key, settings_path):
    active = [branch for branch in branches if branch.get("active", True)]
    settings = load_task_settings(settings_path)
    enabled_keys = settings.get("tasks", {}).get(task_key)
    if enabled_keys is None:
        return active
    enabled_keys = {str(key) for key in enabled_keys}
    return [branch for branch in active if branch_key(branch) in enabled_keys]


class BranchTaskSettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        root = Path(__file__).resolve().parents[2]
        self.branches_path = root / "data" / "branches.json"
        self.settings_path = root / "data" / "branch_task_settings.json"

        layout = QVBoxLayout(self)
        description = QLabel(
            "업무별로 화면에 표시할 지점을 선택합니다. 지점 관리에서 비활성화된 지점은 체크 여부와 관계없이 표시되지 않습니다."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QTableWidget()
        self.table.setColumnCount(1 + len(BRANCH_TASKS))
        self.table.setHorizontalHeaderLabels(["지점"] + list(BRANCH_TASKS.values()))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        save_button = QPushButton("설정 저장")
        save_button.clicked.connect(self.save_settings)
        layout.addWidget(save_button)
        self.load_settings()

    def _load_branches(self):
        try:
            with open(self.branches_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def load_settings(self):
        branches = self._load_branches()
        settings = load_task_settings(self.settings_path)
        configured_tasks = settings.get("tasks", {})
        self.table.setRowCount(len(branches))
        for row, branch in enumerate(branches):
            name_item = QTableWidgetItem(branch.get("branch_name", ""))
            name_item.setData(Qt.UserRole, branch_key(branch))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            for column, task_key in enumerate(BRANCH_TASKS, 1):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                enabled = configured_tasks.get(task_key)
                checked = enabled is None or branch_key(branch) in {str(key) for key in enabled}
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self.table.setItem(row, column, item)

    def save_settings(self):
        tasks = {task_key: [] for task_key in BRANCH_TASKS}
        for row in range(self.table.rowCount()):
            key = self.table.item(row, 0).data(Qt.UserRole)
            for column, task_key in enumerate(BRANCH_TASKS, 1):
                if self.table.item(row, column).checkState() == Qt.Checked:
                    tasks[task_key].append(key)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "tasks": tasks}, file, ensure_ascii=False, indent=4)
        QMessageBox.information(self, "저장 완료", "업무별 지점 설정을 저장했습니다.")

    def showEvent(self, event):
        super().showEvent(event)
        self.load_settings()
