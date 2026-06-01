import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QDialog,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
    QLabel,
    QSizePolicy,
    QHeaderView,
)


LOGIN_TYPES = ["케어포", "롱텀"]


class BranchDialog(QDialog):
    def __init__(self, parent=None, branch_data=None):
        super().__init__(parent)
        self.setWindowTitle("지점 추가" if branch_data is None else "지점 수정")

        self.organization_code_edit = QLineEdit()
        self.organization_name_edit = QLineEdit()
        self.branch_name_edit = QLineEdit()
        self.corporation_name_edit = QLineEdit()
        self.owner_name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.login_type_combo = QComboBox()
        self.login_id_edit = QLineEdit()
        self.login_password_edit = QLineEdit()

        self.setMinimumWidth(760)
        self.login_type_combo.addItems(LOGIN_TYPES)
        self.login_password_edit.setEchoMode(QLineEdit.Normal)
        # 허용 문자: ASCII 공백(0x20)부터 물결(0x7E)까지 — 영어, 숫자, 특수문자 포함, 한글 제외
        self.login_password_edit.setValidator(QRegularExpressionValidator(r"[ -~]*"))

        # 기존 데이터가 있으면 채우기
        if branch_data:
            self.organization_code_edit.setText(branch_data.get("organization_code", ""))
            self.organization_name_edit.setText(branch_data.get("organization_name", ""))
            self.branch_name_edit.setText(branch_data.get("branch_name", ""))
            self.corporation_name_edit.setText(branch_data.get("corporation_name", ""))
            self.owner_name_edit.setText(branch_data.get("owner_name", ""))
            self.address_edit.setText(branch_data.get("address", ""))
            self.login_type_combo.setCurrentText(branch_data.get("login_type", LOGIN_TYPES[0]))
            self.login_id_edit.setText(branch_data.get("login_id", branch_data.get("owner_name", "")))
            self.login_password_edit.setText(branch_data.get("login_password", ""))
        else:
            self.login_type_combo.setCurrentText(LOGIN_TYPES[0])
            self.login_id_edit.setText("")
            self.login_password_edit.setText("")

        form_layout = QFormLayout()
        form_layout.addRow("기관기호:", self.organization_code_edit)
        form_layout.addRow("기관명:", self.organization_name_edit)
        form_layout.addRow("지점명:", self.branch_name_edit)
        form_layout.addRow("법인명:", self.corporation_name_edit)
        form_layout.addRow("대표자명:", self.owner_name_edit)
        form_layout.addRow("주소:", self.address_edit)
        form_layout.addRow("로그인 유형:", self.login_type_combo)

        # 로그인 입력 칸: 라벨을 동적으로 변경할 수 있도록 QLabel을 사용
        self.login_id_label = QLabel("로그인 아이디:")
        self.login_password_label = QLabel("로그인 비밀번호:")
        form_layout.addRow(self.login_id_label, self.login_id_edit)
        form_layout.addRow(self.login_password_label, self.login_password_edit)

        # 로그인 유형 변경 시 라벨 업데이트
        self.login_type_combo.currentTextChanged.connect(self._on_login_type_changed)
        # 초기 라벨 상태 설정
        self._on_login_type_changed(self.login_type_combo.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_data(self):
        return {
            "organization_code": self.organization_code_edit.text().strip(),
            "organization_name": self.organization_name_edit.text().strip(),
            "branch_name": self.branch_name_edit.text().strip(),
            "corporation_name": self.corporation_name_edit.text().strip(),
            "owner_name": self.owner_name_edit.text().strip(),
            "address": self.address_edit.text().strip(),
            "login_type": self.login_type_combo.currentText(),
            "login_id": self.login_id_edit.text().strip(),
            "login_password": self.login_password_edit.text(),
        }

    def _on_login_type_changed(self, text: str):
        """로그인 유형에 따라 라벨과 비밀번호 입력 모드를 변경합니다."""
        if text == "롱텀":
            self.login_id_label.setText("인증서명:")
            self.login_password_label.setText("인증서 비밀번호:")
            # 롱텀은 기존 케어포 비밀번호 입력창과 동일하게 보이도록 설정
            self.login_password_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.login_id_label.setText("로그인 아이디:")
            self.login_password_label.setText("로그인 비밀번호:")
            self.login_password_edit.setEchoMode(QLineEdit.Normal)


class BranchPage(QWidget):

    def __init__(self):
        super().__init__()

        self.data_file = Path(__file__).resolve().parents[2] / "data" / "branches.json"
        self.selected_row = -1

        layout = QVBoxLayout()
        self.setLayout(layout)

        # =================================================
        # 상단 버튼 영역
        # =================================================
        button_layout = QHBoxLayout()

        add_button = QPushButton("추가")
        self.edit_button = QPushButton("수정")
        self.delete_button = QPushButton("삭제")

        button_layout.addWidget(add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.delete_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # =================================================
        # 테이블
        # =================================================
        self.table = QTableWidget()

        self.table.setColumnCount(6)
        # 테이블이 가능한 가로 공간을 모두 사용하도록 설정
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.table.setHorizontalHeaderLabels([
            "지점명",
            "기관기호",
            "기관명",
            "법인명",
            "대표자명",
            "주소",
        ])

        # 행 전체 선택 모드 설정
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        
        # 테이블 셀 읽기 전용 설정
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)

        layout.addWidget(self.table)

        # =================================================
        # 버튼 이벤트 연결
        # =================================================
        add_button.clicked.connect(self.add_branch)
        self.edit_button.clicked.connect(self.edit_branch)
        self.delete_button.clicked.connect(self.delete_branch)
        
        # 테이블 행 선택 이벤트
        self.table.itemClicked.connect(self.on_row_selected)

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

    def on_row_selected(self):
        """행이 선택되었을 때 호출"""
        self.selected_row = self.table.currentRow()

    def on_login_tool_changed(self, row):
        """로그인툴 콤보 변경 시 로그인 정보 팝업을 엽니다."""
        data = self._load_data()
        if row < 0 or row >= len(data):
            return

        branch_data = data[row]
        dialog = BranchDialog(self, branch_data)
        if dialog.exec() != QDialog.Accepted:
            self.load_data()
            return

        updated_data = dialog.get_data()
        data[row] = updated_data
        self._save_data(data)
        self.load_data()
        self.table.selectRow(row)

    def add_branch(self):
        dialog = BranchDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        new_branch = dialog.get_data()
        
        # 지점명과 법인명 필수 입력 확인
        if not new_branch["branch_name"] or not new_branch["corporation_name"]:
            QMessageBox.warning(self, "입력 오류", "지점명과 법인명은 필수 입력 항목입니다.")
            return

        data = self._load_data()
        data.append(new_branch)
        self._save_data(data)
        self.load_data()
        self.table.selectRow(self.table.rowCount() - 1)

    def edit_branch(self):
        """선택된 행 수정"""
        if self.selected_row < 0:
            QMessageBox.warning(self, "선택 오류", "수정할 항목을 선택해주세요.")
            return

        data = self._load_data()
        branch_data = data[self.selected_row]
        
        dialog = BranchDialog(self, branch_data)
        if dialog.exec() != QDialog.Accepted:
            return

        updated_data = dialog.get_data()
        
        # 지점명과 법인명 필수 입력 확인
        if not updated_data["branch_name"] or not updated_data["corporation_name"]:
            QMessageBox.warning(self, "입력 오류", "지점명과 법인명은 필수 입력 항목입니다.")
            return

        data[self.selected_row] = updated_data
        self._save_data(data)
        self.load_data()
        self.table.selectRow(self.selected_row)

    def delete_branch(self):
        """선택된 행 삭제"""
        if self.selected_row < 0:
            QMessageBox.warning(self, "선택 오류", "삭제할 항목을 선택해주세요.")
            return

        # 삭제 확인 팝업
        reply = QMessageBox.question(self, "삭제 확인", "삭제하시겠습니까?", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        data = self._load_data()
        del data[self.selected_row]
        self._save_data(data)
        self.load_data()

    def load_data(self):
        data = self._load_data()

        self.table.setRowCount(len(data))

        for row, item in enumerate(data):
            login_type = item.get("login_type", LOGIN_TYPES[0])

            # 지점명
            branch_item = QTableWidgetItem(item.get("branch_name", ""))
            branch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            branch_item.setFlags(branch_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, branch_item)
            
            # 기관기호
            org_code_item = QTableWidgetItem(item.get("organization_code", ""))
            org_code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            org_code_item.setFlags(org_code_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, org_code_item)
            
            # 기관명
            org_name_item = QTableWidgetItem(item.get("organization_name", ""))
            org_name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            org_name_item.setFlags(org_name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, org_name_item)
            
            # 법인명
            corp_item = QTableWidgetItem(item["corporation_name"])
            corp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            corp_item.setFlags(corp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, corp_item)
            
            # 대표자명
            owner_item = QTableWidgetItem(item["owner_name"])
            owner_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            owner_item.setFlags(owner_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 4, owner_item)
            
            # 주소
            address_item = QTableWidgetItem(item["address"])
            address_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            address_item.setFlags(address_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 5, address_item)

