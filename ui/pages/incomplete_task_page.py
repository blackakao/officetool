import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.pages.document_tool import read_json_file, write_json_file
from ui.pages.memo_page import content_preview


EMPTY_TASK_DATA = {"version": 1, "tasks": []}


def normalize_task_data(data):
    if not isinstance(data, dict):
        return dict(EMPTY_TASK_DATA)
    tasks = []
    for task in data.get("tasks", []):
        if not isinstance(task, dict):
            continue
        tasks.append({
            "id": str(task.get("id") or uuid.uuid4().hex),
            "title": str(task.get("title", "")).strip(),
            "content": str(task.get("content", "")),
            "created_at": str(task.get("created_at", "")),
            "completed_at": str(task.get("completed_at", "")),
        })
    return {"version": 1, "tasks": tasks}


def filter_tasks(tasks, query="", completed=False):
    keyword = query.strip().casefold()
    return [
        task for task in tasks
        if bool(task.get("completed_at")) == completed
        and (not keyword or keyword in " ".join((
            str(task.get("title", "")), str(task.get("content", ""))
        )).casefold())
    ]


class IncompleteTaskEditorDialog(QDialog):
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.task = task or {}
        self.setWindowTitle("미비된일 수정" if task else "미비된일 추가")
        self.resize(650, 500)

        self.title_edit = QLineEdit(str(self.task.get("title", "")))
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(str(self.task.get("content", "")))

        form = QFormLayout()
        form.addRow("제목", self.title_edit)
        form.addRow("내용", self.content_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept_if_valid(self):
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "입력 확인", "제목을 입력해 주세요.")
            return
        self.accept()

    def get_data(self):
        return {
            "id": self.task.get("id") or uuid.uuid4().hex,
            "title": self.title_edit.text().strip(),
            "content": self.content_edit.toPlainText(),
            "created_at": self.task.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M"),
            "completed_at": self.task.get("completed_at", ""),
        }


class IncompleteTaskPage(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "incomplete_tasks.json"

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("제목, 내용 검색")
        self.completed_filter = QRadioButton("완료된 업무")
        self.completed_filter.setAutoExclusive(False)
        self.search_edit.textChanged.connect(self.load_data)
        self.completed_filter.toggled.connect(self.load_data)

        add_button = QPushButton("미비된일 추가")
        delete_button = QPushButton("삭제")
        add_button.clicked.connect(self.add_task)
        delete_button.clicked.connect(self.delete_task)

        tools = QHBoxLayout()
        tools.addWidget(self.search_edit, 1)
        tools.addWidget(self.completed_filter)
        tools.addWidget(add_button)
        tools.addWidget(delete_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["제목", "내용 일부", "생성일", "완료일", "완료버튼"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.edit_task)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.table)
        self.load_data()

    def _load(self):
        return normalize_task_data(read_json_file(self.data_file, EMPTY_TASK_DATA))

    def _save(self, data):
        write_json_file(self.data_file, normalize_task_data(data))

    def load_data(self):
        completed = self.completed_filter.isChecked()
        tasks = filter_tasks(self._load()["tasks"], self.search_edit.text(), completed)
        tasks.sort(key=lambda task: task.get("completed_at" if completed else "created_at", ""), reverse=True)
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = (task["title"], content_preview(task["content"]), task["created_at"], task["completed_at"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, task["id"])
                self.table.setItem(row, column, item)
            complete_button = QPushButton("완료됨" if completed else "완료")
            complete_button.setEnabled(not completed)
            complete_button.clicked.connect(lambda _checked=False, task_id=task["id"]: self.complete_task(task_id))
            self.table.setCellWidget(row, 4, complete_button)

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def _selected_id(self, row=None):
        row = self.table.currentRow() if row is None else row
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else ""

    def add_task(self):
        dialog = IncompleteTaskEditorDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = self._load()
            data["tasks"].append(dialog.get_data())
            self._save(data)
            self.completed_filter.setChecked(False)
            self.load_data()

    def edit_task(self, row, _column=0):
        task_id = self._selected_id(row)
        data = self._load()
        index = next((i for i, task in enumerate(data["tasks"]) if task["id"] == task_id), -1)
        if index < 0:
            return
        dialog = IncompleteTaskEditorDialog(self, data["tasks"][index])
        if dialog.exec() == QDialog.Accepted:
            data["tasks"][index] = dialog.get_data()
            self._save(data)
            self.load_data()

    def complete_task(self, task_id):
        data = self._load()
        task = next((task for task in data["tasks"] if task["id"] == task_id), None)
        if not task or task.get("completed_at"):
            return
        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save(data)
        self.load_data()

    def delete_task(self):
        task_id = self._selected_id()
        if not task_id:
            QMessageBox.warning(self, "선택 확인", "삭제할 업무를 선택해 주세요.")
            return
        if QMessageBox.question(self, "삭제 확인", "선택한 업무를 삭제하시겠습니까?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        data = self._load()
        data["tasks"] = [task for task in data["tasks"] if task["id"] != task_id]
        self._save(data)
        self.load_data()
