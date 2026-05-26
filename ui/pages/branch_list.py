import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
)


class BranchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("지점 추가")

        self.branch_name_edit = QLineEdit()
        self.corporation_name_edit = QLineEdit()
        self.owner_name_edit = QLineEdit()
        self.address_edit = QLineEdit()

        form_layout = QFormLayout()
        form_layout.addRow("지점명:", self.branch_name_edit)
        form_layout.addRow("법인명:", self.corporation_name_edit)
        form_layout.addRow("대표자명:", self.owner_name_edit)
        form_layout.addRow("주소:", self.address_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_data(self):
        return {
            "branch_name": self.branch_name_edit.text().strip(),
            "corporation_name": self.corporation_name_edit.text().strip(),
            "owner_name": self.owner_name_edit.text().strip(),
            "address": self.address_edit.text().strip(),
        }


class BranchPage(QWidget):

    def __init__(self):
        super().__init__()

        self.data_file = Path(__file__).resolve().parents[2] / "data" / "branches.json"

        layout = QVBoxLayout()
        self.setLayout(layout)

        # =================================================
        # 상단 버튼 영역
        # =================================================
        button_layout = QHBoxLayout()

        add_button = QPushButton("추가")
        edit_button = QPushButton("수정")
        delete_button = QPushButton("삭제")
        refresh_button = QPushButton("새로고침")

        button_layout.addWidget(add_button)
        button_layout.addWidget(edit_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(refresh_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # =================================================
        # 테이블
        # =================================================
        self.table = QTableWidget()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "연번",
            "지점명",
            "법인명",
            "대표자명",
            "주소",
        ])

        layout.addWidget(self.table)

        # =================================================
        # 버튼 이벤트 연결
        # =================================================
        add_button.clicked.connect(self.add_branch)
        refresh_button.clicked.connect(self.load_data)

        # =================================================
        # 데이터 로드
        # =================================================
        self.load_data()

    def _load_data(self):
        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_data(self, data):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def add_branch(self):
        dialog = BranchDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        new_branch = dialog.get_data()
        if not all(new_branch.values()):
            QMessageBox.warning(self, "입력 오류", "모든 항목을 입력해주세요.")
            return

        data = self._load_data()
        data.append(new_branch)
        self._save_data(data)
        self.load_data()
        self.table.selectRow(self.table.rowCount() - 1)

    def load_data(self):
        data = self._load_data()

        self.table.setRowCount(len(data))

        for row, item in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(item["branch_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["corporation_name"]))
            self.table.setItem(row, 3, QTableWidgetItem(item["owner_name"]))
            self.table.setItem(row, 4, QTableWidgetItem(item["address"]))
