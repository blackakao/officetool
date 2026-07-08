from ui.pages.logging_util import (
    LOG_FILE,
    is_detail_message,
    load_log_settings,
    save_log_settings,
)

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QHBoxLayout, QCheckBox


class LoginLogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.log_file = LOG_FILE
        self.settings = load_log_settings()
        layout = QVBoxLayout()
        self.setLayout(layout)

        buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.load_logs)
        self.clear_button = QPushButton("전체 삭제")
        self.clear_button.clicked.connect(self.clear_logs)
        self.verbose_check = QCheckBox("상세 로그")
        self.verbose_check.setChecked(bool(self.settings.get("verbose", False)))
        self.verbose_check.stateChanged.connect(self.save_verbose_setting)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addWidget(self.clear_button)
        buttons_layout.addWidget(self.verbose_check)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        self.load_logs()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_logs()

    def load_logs(self):
        if not self.log_file.exists():
            self.text.setPlainText("로그 파일이 없습니다.")
            return
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not self.verbose_check.isChecked():
                lines = [
                    line
                    for line in lines
                    if not self.line_is_detail_log(line)
                ]
            self.text.setPlainText("".join(lines))
            self.scroll_to_latest()
        except Exception as e:
            self.text.setPlainText(f"로그를 읽는 중 오류: {e}")

    def scroll_to_latest(self):
        def _scroll():
            scroll_bar = self.text.verticalScrollBar()
            scroll_bar.setValue(scroll_bar.maximum())
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text.setTextCursor(cursor)
        QTimer.singleShot(0, _scroll)

    def line_is_detail_log(self, line):
        marker = "] [FederationTool] "
        if marker in line:
            return is_detail_message(line.split(marker, 1)[1])
        return False

    def save_verbose_setting(self):
        self.settings["verbose"] = self.verbose_check.isChecked()
        save_log_settings(self.settings)
        self.load_logs()

    def clear_logs(self):
        try:
            with open(self.log_file, "w", encoding="utf-8"):
                pass
        except Exception:
            pass
        self.text.clear()
