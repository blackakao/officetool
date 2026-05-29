import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit


class LoginLogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.log_file = Path(__file__).resolve().parents[2] / "data" / "login.log"
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.load_logs)
        layout.addWidget(self.refresh_button)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        self.load_logs()

    def load_logs(self):
        if not self.log_file.exists():
            self.text.setPlainText("로그 파일이 없습니다.")
            return
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                self.text.setPlainText(f.read())
        except Exception as e:
            self.text.setPlainText(f"로그를 읽는 중 오류: {e}")
