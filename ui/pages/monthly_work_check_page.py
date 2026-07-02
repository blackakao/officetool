import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


DEFAULT_TASKS = [
    "출근부 검토",
    "공단 결정요청",
    "공단 청구",
    "프로그램비 검토",
    "본인부담금 발송",
    "의료비 검토",
]


class TaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("업무 추가")

        self.task_name_edit = QLineEdit()

        form_layout = QFormLayout()
        form_layout.addRow("업무명:", self.task_name_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_task_name(self):
        return self.task_name_edit.text().strip()


class MonthlyWorkCheckPage(QWidget):
    def __init__(self):
        super().__init__()

        self.base_dir = Path(__file__).resolve().parents[2]
        self.data_file = self.base_dir / "data" / "monthly_work_check.json"
        self.branches_file = self.base_dir / "data" / "branches.json"

        layout = QVBoxLayout()
        self.setLayout(layout)

        month_layout = QHBoxLayout()
        self.year_combo = QComboBox()
        self.month_combo = QComboBox()
        self._setup_month_picker()
        month_layout.addWidget(self.year_combo)
        month_layout.addWidget(self.month_combo)
        month_layout.addStretch()
        layout.addLayout(month_layout)

        task_layout = QHBoxLayout()
        self.task_combo = QComboBox()
        self.add_task_button = QPushButton("업무 추가")
        task_layout.addWidget(self.task_combo)
        task_layout.addWidget(self.add_task_button)
        task_layout.addStretch()
        layout.addLayout(task_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["지점목록", "완료 시간"])
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(self.table.SelectionMode.NoSelection)
        layout.addWidget(self.table)

        self._ensure_data_file()
        self._load_tasks_to_combo()
        self.load_data()

        self.year_combo.currentIndexChanged.connect(self.load_data)
        self.month_combo.currentIndexChanged.connect(self.load_data)
        self.task_combo.currentTextChanged.connect(self.load_data)
        self.add_task_button.clicked.connect(self.add_task)

    def _setup_month_picker(self):
        current_year = datetime.now().year
        current_month = datetime.now().month

        for year in range(current_year - 5, current_year + 6):
            self.year_combo.addItem(f"{year}년", year)

        for month in range(1, 13):
            self.month_combo.addItem(f"{month:02d}월", month)

        self.year_combo.setCurrentIndex(self.year_combo.findData(current_year))
        self.month_combo.setCurrentIndex(self.month_combo.findData(current_month))

    def _ensure_data_file(self):
        if self.data_file.exists():
            return

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tasks": DEFAULT_TASKS,
            "records": {},
        }
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _load_data(self):
        with open(self.data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            data = {}

        data.setdefault("tasks", DEFAULT_TASKS.copy())
        data.setdefault("records", {})
        return data

    def _save_data(self, data):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _load_branches(self):
        if not self.branches_file.exists():
            return []

        with open(self.branches_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_tasks_to_combo(self):
        current_task = self.task_combo.currentText()
        data = self._load_data()

        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        self.task_combo.addItems(data["tasks"])

        if current_task:
            index = self.task_combo.findText(current_task)
            if index >= 0:
                self.task_combo.setCurrentIndex(index)

        self.task_combo.blockSignals(False)

    def _month_key(self):
        return f"{self.year_combo.currentData():04d}-{self.month_combo.currentData():02d}"

    def _branch_key(self, branch):
        return branch.get("organization_code") or branch.get("branch_name", "")

    def _selected_task(self):
        return self.task_combo.currentText()

    def _completed_at(self, data, branch_key):
        return (
            data.get("records", {})
            .get(self._month_key(), {})
            .get(self._selected_task(), {})
            .get(branch_key, "")
        )

    def add_task(self):
        dialog = TaskDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        task_name = dialog.get_task_name()
        if not task_name:
            QMessageBox.warning(self, "입력 오류", "업무명을 입력해주세요.")
            return

        data = self._load_data()
        if task_name in data["tasks"]:
            QMessageBox.warning(self, "입력 오류", "이미 등록된 업무입니다.")
            return

        data["tasks"].append(task_name)
        self._save_data(data)
        self._load_tasks_to_combo()
        self.task_combo.setCurrentText(task_name)
        self.load_data()

    def toggle_completion(self, branch_key):
        data = self._load_data()
        records = data.setdefault("records", {})
        month_records = records.setdefault(self._month_key(), {})
        task_records = month_records.setdefault(self._selected_task(), {})

        if branch_key in task_records:
            del task_records[branch_key]
        else:
            task_records[branch_key] = datetime.now().strftime("%Y-%m-%d %H:%M")

        self._save_data(data)
        self.load_data()

    def load_data(self):
        if self.task_combo.count() == 0:
            return

        data = self._load_data()
        branches = self._load_branches()

        self.table.setRowCount(len(branches))

        for row, branch in enumerate(branches):
            branch_key = self._branch_key(branch)
            completed_at = self._completed_at(data, branch_key)

            branch_button = QPushButton(branch.get("branch_name", ""))
            branch_button.setStyleSheet(
                "QPushButton {"
                f"background-color: {'#2563eb' if completed_at else '#dc2626'};"
                "color: white;"
                "font-weight: 600;"
                "padding: 6px 10px;"
                "}"
            )
            branch_button.clicked.connect(lambda checked=False, key=branch_key: self.toggle_completion(key))
            self.table.setCellWidget(row, 0, branch_button)

            completed_item = QTableWidgetItem(completed_at)
            completed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, completed_item)
