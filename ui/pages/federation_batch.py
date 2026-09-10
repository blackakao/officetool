from copy import deepcopy

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class BranchBatchDialog(QDialog):
    def __init__(self, parent, branches):
        super().__init__(parent)
        self.branches = deepcopy(branches)
        self.setWindowTitle("다중 지점 선택")
        self.resize(560, 540)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("선택한 지점을 위에서부터 순서대로 실행합니다.\n각 지점의 브라우저를 종료한 뒤 다음 지점을 시작합니다."))
        self.table = QTableWidget(len(branches), 2)
        self.table.setHorizontalHeaderLabels(["지점목록 / 실행 여부", "기관기호"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, branch in enumerate(branches):
            name = QTableWidgetItem(branch.get("branch_name", ""))
            name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            name.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, name)
            code = QTableWidgetItem(str(branch.get("organization_code", "")))
            code.setFlags(Qt.ItemIsEnabled)
            code.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, code)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for title, checked in (("모두 선택", True), ("모두 해제", False)):
            button = QPushButton(title)
            button.clicked.connect(lambda _=False, value=checked: self.set_all(value))
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("선택 지점 실행")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all(self, checked):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def selected_branches(self):
        return [branch for row, branch in enumerate(self.branches)
                if self.table.item(row, 0).checkState() == Qt.Checked]

    def accept(self):
        if not self.selected_branches():
            QMessageBox.warning(self, "지점 선택", "실행할 지점을 하나 이상 선택하세요.")
            return
        super().accept()


class BranchBatchThread(QThread):
    status_signal = Signal(str)
    summary_signal = Signal(object)

    def __init__(self, branches, login_class, process_class, config_path, template, start_number, invoice=False):
        super().__init__()
        self.branches = deepcopy(branches)
        self.login_class = login_class
        self.process_class = process_class
        self.config_path = config_path
        self.template = deepcopy(template)
        self.start_number = start_number
        self.invoice = invoice

    def run(self):
        results = []
        for index, branch in enumerate(self.branches, 1):
            if self.isInterruptionRequested():
                break
            name = branch.get("branch_name", "")
            self.status_signal.emit(f"[{index}/{len(self.branches)}] {name}: 로그인 시작 (시작번호 {self.start_number})")
            login = None
            outcome = ["로그인 결과를 받지 못했습니다.", False]
            close_failed = False
            try:
                # Run both stages in this worker, waiting for run() to fully return.
                login = self.login_class(branch)
                login.finished_signal.connect(lambda message, ok: outcome.__setitem__(slice(None), [message, ok]), Qt.DirectConnection)
                login.run()
                if not outcome[1] or not getattr(login, "driver", None):
                    raise ValueError(outcome[0])
                process = self.process_class(login.driver, branch, self.config_path, self.template,
                                             use_invoice_fallback=self.invoice, start_number=self.start_number)
                outcome[:] = ["매크로 결과를 받지 못했습니다.", False]
                process.status_signal.connect(self.status_signal.emit, Qt.DirectConnection)
                process.finished_signal.connect(lambda message, ok: outcome.__setitem__(slice(None), [message, ok]), Qt.DirectConnection)
                process.run()
            except Exception as exc:
                outcome[:] = [str(exc), False]
            finally:
                driver = getattr(login, "driver", None)
                if driver is not None:
                    try:
                        driver.quit()
                        self.status_signal.emit(f"[{name}] 브라우저 종료 완료")
                    except Exception as exc:
                        close_failed = True
                        outcome[:] = [f"브라우저 종료 실패, 다음 지점 실행 중단: {exc}", False]
            results.append({"branch": name, "success": outcome[1], "message": outcome[0]})
            self.status_signal.emit(f"[{name}] {'완료' if outcome[1] else '실패'}: {outcome[0]}")
            if close_failed:
                break
        self.summary_signal.emit(results)
