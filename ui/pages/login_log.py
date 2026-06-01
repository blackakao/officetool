import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QHBoxLayout


class LoginLogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.log_file = Path(__file__).resolve().parents[2] / "data" / "login.log"
        layout = QVBoxLayout()
        self.setLayout(layout)

        buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.load_logs)
        self.clear_button = QPushButton("전체 삭제")
        self.clear_button.clicked.connect(self.clear_logs)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addWidget(self.clear_button)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

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
            scroll_bar = self.text.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())
        except Exception as e:
            self.text.setPlainText(f"로그를 읽는 중 오류: {e}")

    def clear_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8"):
                pass
        except Exception:
            pass
        self.text.clear()
