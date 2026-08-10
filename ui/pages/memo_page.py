import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.pages.document_tool import read_json_file, write_json_file


EMPTY_MEMO_DATA = {"version": 1, "tags": [], "memos": []}


def normalize_memo_data(data):
    if not isinstance(data, dict):
        return {"version": 1, "tags": [], "memos": []}
    tags = []
    for tag in data.get("tags", []):
        name = str(tag).strip()
        if name and name not in tags:
            tags.append(name)
    memos = []
    for memo in data.get("memos", []):
        if not isinstance(memo, dict):
            continue
        memos.append({
            "id": str(memo.get("id") or uuid.uuid4().hex),
            "title": str(memo.get("title", "")).strip(),
            "tag": str(memo.get("tag", "")).strip(),
            "content": str(memo.get("content", "")),
            "created_at": str(memo.get("created_at", "")),
        })
    return {"version": 1, "tags": tags, "memos": memos}


def content_preview(content, length=10):
    text = " ".join(str(content).split())
    return text if len(text) <= length else f"{text[:length]}…"


def filter_memos(memos, query="", tag=""):
    keyword = query.strip().casefold()
    return [
        memo for memo in memos
        if (not tag or memo.get("tag", "") == tag)
        and (not keyword or keyword in " ".join((
            str(memo.get("title", "")),
            str(memo.get("tag", "")),
            str(memo.get("content", "")),
        )).casefold())
    ]


class MemoEditorDialog(QDialog):
    def __init__(self, parent=None, memo=None, tags=None):
        super().__init__(parent)
        self.memo = memo or {}
        self.setWindowTitle("메모 수정" if memo else "메모 추가")
        self.resize(650, 500)

        self.title_edit = QLineEdit(str(self.memo.get("title", "")))
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("태그 없음", "")
        for tag in tags or []:
            self.tag_combo.addItem(tag, tag)
        current_tag = str(self.memo.get("tag", ""))
        index = self.tag_combo.findData(current_tag)
        self.tag_combo.setCurrentIndex(max(0, index))
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(str(self.memo.get("content", "")))

        form = QFormLayout()
        form.addRow("제목", self.title_edit)
        form.addRow("태그", self.tag_combo)
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
            "id": self.memo.get("id") or uuid.uuid4().hex,
            "title": self.title_edit.text().strip(),
            "tag": self.tag_combo.currentData() or "",
            "content": self.content_edit.toPlainText(),
            "created_at": self.memo.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


class TagManagerDialog(QDialog):
    def __init__(self, parent=None, tags=None):
        super().__init__(parent)
        self.original_tags = list(tags or [])
        self.rename_map = {}
        self.setWindowTitle("태그 관리")
        self.resize(420, 430)

        self.tag_list = QListWidget()
        self.tag_list.addItems(self.original_tags)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("태그 이름")
        self.tag_list.currentTextChanged.connect(self.name_edit.setText)

        add_button = QPushButton("추가")
        rename_button = QPushButton("이름 변경")
        delete_button = QPushButton("삭제")
        add_button.clicked.connect(self._add)
        rename_button.clicked.connect(self._rename)
        delete_button.clicked.connect(self._delete)

        tools = QHBoxLayout()
        tools.addWidget(self.name_edit)
        tools.addWidget(add_button)
        tools.addWidget(rename_button)
        tools.addWidget(delete_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("메모를 분류하고 검색할 태그를 관리합니다."))
        layout.addLayout(tools)
        layout.addWidget(self.tag_list)
        layout.addWidget(buttons)

    def _names(self):
        return [self.tag_list.item(i).text() for i in range(self.tag_list.count())]

    def _validated_name(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 확인", "태그 이름을 입력해 주세요.")
        return name

    def _add(self):
        name = self._validated_name()
        if not name:
            return
        if name in self._names():
            QMessageBox.warning(self, "입력 확인", "이미 존재하는 태그입니다.")
            return
        self.tag_list.addItem(name)
        self.name_edit.clear()

    def _rename(self):
        item = self.tag_list.currentItem()
        name = self._validated_name()
        if not item or not name:
            return
        old_name = item.text()
        if name != old_name and name in self._names():
            QMessageBox.warning(self, "입력 확인", "이미 존재하는 태그입니다.")
            return
        item.setText(name)
        for original, current in list(self.rename_map.items()):
            if current == old_name:
                self.rename_map[original] = name
                break
        else:
            if old_name in self.original_tags:
                self.rename_map[old_name] = name

    def _delete(self):
        row = self.tag_list.currentRow()
        if row >= 0:
            self.tag_list.takeItem(row)
            self.name_edit.clear()

    def get_changes(self):
        tags = self._names()
        mapping = {}
        for original in self.original_tags:
            mapped = self.rename_map.get(original, original)
            mapping[original] = mapped if mapped in tags else ""
        return tags, mapping


class MemoPage(QWidget):
    def __init__(self):
        super().__init__()
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "memos.json"

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("제목, 태그, 내용 검색")
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("전체 태그", "")
        self.search_edit.textChanged.connect(self.load_data)
        self.tag_filter.currentIndexChanged.connect(self.load_data)

        add_button = QPushButton("메모 추가")
        edit_button = QPushButton("수정")
        delete_button = QPushButton("삭제")
        tag_button = QPushButton("태그 관리")
        add_button.clicked.connect(self.add_memo)
        edit_button.clicked.connect(self.edit_selected_memo)
        delete_button.clicked.connect(self.delete_memo)
        tag_button.clicked.connect(self.manage_tags)

        tools = QHBoxLayout()
        tools.addWidget(self.search_edit, 2)
        tools.addWidget(self.tag_filter, 1)
        tools.addWidget(add_button)
        tools.addWidget(edit_button)
        tools.addWidget(delete_button)
        tools.addWidget(tag_button)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["제목", "태그", "내용 일부", "생성일"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.edit_memo)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.table)
        self._refresh_tag_filter()
        self.load_data()

    def _load(self):
        return normalize_memo_data(read_json_file(self.data_file, EMPTY_MEMO_DATA))

    def _save(self, data):
        write_json_file(self.data_file, normalize_memo_data(data))

    def _refresh_tag_filter(self):
        selected = self.tag_filter.currentData() or ""
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("전체 태그", "")
        for tag in self._load()["tags"]:
            self.tag_filter.addItem(tag, tag)
        index = self.tag_filter.findData(selected)
        self.tag_filter.setCurrentIndex(max(0, index))
        self.tag_filter.blockSignals(False)

    def load_data(self):
        memos = filter_memos(
            self._load()["memos"], self.search_edit.text(), self.tag_filter.currentData() or ""
        )
        memos.sort(key=lambda memo: memo.get("created_at", ""), reverse=True)
        self.table.setRowCount(len(memos))
        for row, memo in enumerate(memos):
            values = (memo["title"], memo["tag"], content_preview(memo["content"]), memo["created_at"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, memo["id"])
                self.table.setItem(row, column, item)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_tag_filter()
        self.load_data()

    def _selected_id(self, row=None):
        row = self.table.currentRow() if row is None else row
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else ""

    def add_memo(self):
        data = self._load()
        dialog = MemoEditorDialog(self, tags=data["tags"])
        if dialog.exec() == QDialog.Accepted:
            data["memos"].append(dialog.get_data())
            self._save(data)
            self.load_data()

    def edit_selected_memo(self):
        self.edit_memo(self.table.currentRow())

    def edit_memo(self, row, _column=0):
        memo_id = self._selected_id(row)
        data = self._load()
        index = next((i for i, memo in enumerate(data["memos"]) if memo["id"] == memo_id), -1)
        if index < 0:
            QMessageBox.warning(self, "선택 확인", "수정할 메모를 선택해 주세요.")
            return
        dialog = MemoEditorDialog(self, data["memos"][index], data["tags"])
        if dialog.exec() == QDialog.Accepted:
            data["memos"][index] = dialog.get_data()
            self._save(data)
            self.load_data()

    def delete_memo(self):
        memo_id = self._selected_id()
        if not memo_id:
            QMessageBox.warning(self, "선택 확인", "삭제할 메모를 선택해 주세요.")
            return
        if QMessageBox.question(self, "삭제 확인", "선택한 메모를 삭제하시겠습니까?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        data = self._load()
        data["memos"] = [memo for memo in data["memos"] if memo["id"] != memo_id]
        self._save(data)
        self.load_data()

    def manage_tags(self):
        data = self._load()
        dialog = TagManagerDialog(self, data["tags"])
        if dialog.exec() != QDialog.Accepted:
            return
        data["tags"], mapping = dialog.get_changes()
        for memo in data["memos"]:
            if memo["tag"] in mapping:
                memo["tag"] = mapping[memo["tag"]]
        self._save(data)
        self._refresh_tag_filter()
        self.load_data()
