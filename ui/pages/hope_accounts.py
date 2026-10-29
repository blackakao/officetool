"""희망이음 대표자 계정 설정 화면."""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLineEdit,
    QPushButton, QMessageBox,
)

from data_paths import user_data_path


def load_hope_accounts():
    with open(user_data_path("hope_accounts.json"), encoding="utf-8") as stream:
        accounts = json.load(stream)
    if not isinstance(accounts, list) or any(not isinstance(a, dict) for a in accounts):
        raise ValueError("희망이음 계정 설정 형식이 올바르지 않습니다.")
    return accounts


class HopeAccountsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.accounts = load_hope_accounts()
        self.fields = []
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        for account in self.accounts:
            page = QWidget()
            form = QFormLayout(page)
            fields = {}
            for key, label in [
                ("owner_name", "대표자명"), ("login_id", "로그인 ID"),
                ("login_password", "로그인 비밀번호"),
                ("certificate_name", "인증서명"),
                ("certificate_password", "인증서 비밀번호"),
            ]:
                edit = QLineEdit(account.get(key, ""))
                if "password" in key:
                    edit.setEchoMode(QLineEdit.Password)
                if key == "owner_name":
                    edit.setReadOnly(True)
                fields[key] = edit
                form.addRow(label, edit)
            self.fields.append(fields)
            tabs.addTab(page, account["owner_name"])
        save = QPushButton("희망이음 설정 저장")
        save.clicked.connect(self.save_accounts)
        layout.addWidget(save)

    def save_accounts(self):
        accounts = []
        for original, fields in zip(self.accounts, self.fields):
            account = dict(original)
            account.update({key: edit.text() if "password" in key else edit.text().strip()
                            for key, edit in fields.items()})
            if not all(account.get(key) for key in fields):
                QMessageBox.warning(self, "입력 오류", "모든 계정 정보를 입력해주세요.")
                return
            accounts.append(account)
        try:
            path = user_data_path("hope_accounts.json")
            temporary = path.with_suffix(".tmp")
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(accounts, stream, ensure_ascii=False, indent=4)
            temporary.replace(path)
        except OSError:
            QMessageBox.warning(self, "저장 실패", "희망이음 설정 파일을 저장할 수 없습니다.")
            return
        self.accounts = accounts
        QMessageBox.information(self, "저장 완료", "희망이음 대표자 설정을 저장했습니다.")
