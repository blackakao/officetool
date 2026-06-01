import json
import os
import time
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class LoginTool(QWidget):
    def __init__(self):
        super().__init__()
        
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "branches.json"
        self.log_file = Path(__file__).resolve().parents[2] / "data" / "login.log"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        
        self.current_login_type = "케어포"
        self.login_type_buttons = []
        
        self.refresh_buttons()
    
    def refresh_buttons(self):
        """버튼 목록 새로고침"""
        # 기존 레이아웃 삭제
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # ===== L1: 로그인 유형 =====
        login_type_label = QLabel("로그인 유형")
        self.main_layout.addWidget(login_type_label)
        
        login_type_layout = QHBoxLayout()
        self.login_type_buttons = []
        for login_type in ["케어포", "롱텀"]:
            button = QPushButton(login_type)
            button.setCheckable(True)
            button.clicked.connect(self.on_login_type_clicked)
            self.login_type_buttons.append(button)
            login_type_layout.addWidget(button)
        login_type_layout.addStretch()
        self.main_layout.addLayout(login_type_layout)
        self._update_login_type_buttons()
        
        # ===== L2: 지점 목록 =====
        # 그리드 레이아웃 생성 (5개씩 배치)
        grid_layout = QGridLayout()
        
        # branches.json에서 지점 목록 읽기
        branches = self._load_branches()
        
        # 버튼 생성 (5개씩 행으로 배치)
        for index, branch in enumerate(branches):
            row = index // 5  # 행 계산 (5개씩)
            col = index % 5   # 열 계산
            
            button = QPushButton(branch["branch_name"])
            button.clicked.connect(lambda _, b=branch: self.on_branch_clicked(b))
            grid_layout.addWidget(button, row, col)
        
        self.main_layout.addLayout(grid_layout)
        self.main_layout.addStretch()
    
    def on_login_type_clicked(self):
        """로그인 유형 버튼 클릭"""
        sender = self.sender()
        if sender:
            self.current_login_type = sender.text()
            self._update_login_type_buttons()
    
    def _update_login_type_buttons(self):
        """로그인 유형 버튼 상태 업데이트"""
        for button in self.login_type_buttons:
            button.setChecked(button.text() == self.current_login_type)

    def _log(self, message, level="INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts} [{level}] {message}\n")
        except Exception:
            pass

    def on_branch_clicked(self, branch):
        """지점 버튼 클릭 시 케어포 로그인 페이지를 열고 로그인 필드를 채웁니다."""
        if self.current_login_type != "케어포":
            self._log("롱텀 로그인은 아직 지원되지 않습니다.", level="INFO")
            return

        branch_code = branch.get("organization_code", "")
        if not branch_code:
            self._log(f"지점 '{branch.get('branch_name','')}'의 기관기호가 없습니다.", level="WARNING")
            return

        self._log(f"[{branch.get('branch_name','')}] 로그인 시도, 기관기호={branch_code}")
        self.login_thread = CareforLoginThread(branch)
        self.login_thread.finished_signal.connect(self.on_login_finished)
        self.login_thread.start()

    def on_login_finished(self, message, success):
        level = "INFO" if success else "ERROR"
        self._log(message, level=level)

    def showEvent(self, event):
        """페이지가 보여질 때마다 새로고침"""
        super().showEvent(event)
        self.refresh_buttons()
    
    def _load_branches(self):
        """branches.json에서 지점 목록 읽기"""
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []


class CareforLoginThread(QThread):
    finished_signal = Signal(str, bool)

    def __init__(self, branch: dict):
        super().__init__()
        self.branch = branch
        self.url = "https://www.carefor.co.kr/login.php"
        self.driver = None

    def run(self):
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")

            driver_path = Path(ChromeDriverManager().install())
            if not driver_path.name.lower().endswith(".exe"):
                expected_driver = driver_path.parent / ("chromedriver.exe" if os.name == "nt" else "chromedriver")
                if expected_driver.exists():
                    driver_path = expected_driver
                else:
                    driver_files = list(driver_path.parent.glob("**/*chromedriver*.exe" if os.name == "nt" else "**/*chromedriver*"))
                    if driver_files:
                        driver_path = driver_files[0]
                    else:
                        raise FileNotFoundError(f"chromedriver 실행 파일을 찾을 수 없습니다: {driver_path.parent}")

            self.driver = webdriver.Chrome(
                service=ChromeService(str(driver_path)),
                options=options,
            )

            self.driver.get(self.url)
            wait = WebDriverWait(self.driver, 30)

            element = wait.until(EC.presence_of_element_located((By.NAME, "ctmnumb")))
            start = time.time()
            while time.time() - start < 30:
                try:
                    if element.is_enabled():
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            element = self.driver.find_element(By.NAME, "ctmnumb")
            element.clear()
            element.send_keys(self.branch.get("organization_code", ""))

            id_value = self.branch.get("login_id", "")
            pass_value = self.branch.get("login_password", "")

            if id_value:
                id_field = wait.until(EC.presence_of_element_located((By.NAME, "stmiden")))
                id_field.clear()
                id_field.send_keys(id_value)

            if pass_value:
                pass_field = wait.until(EC.presence_of_element_located((By.NAME, "stmpass")))
                pass_field.clear()
                pass_field.send_keys(pass_value)

            login_button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "btn")))
            login_button.click()

            self.finished_signal.emit("케어포 로그인 필드 입력 및 버튼 클릭을 완료했습니다.", True)
        except TimeoutException:
            self.finished_signal.emit("페이지 로딩 또는 입력 필드 활성화에 실패했습니다.", False)
        except FileNotFoundError as e:
            self.finished_signal.emit(f"ChromeDriver 실행 파일을 찾을 수 없습니다: {e}", False)
        except WebDriverException as e:
            self.finished_signal.emit(f"Chrome 자동화 실패: {e}", False)
        except Exception as e:
            self.finished_signal.emit(f"알 수 없는 오류: {e}", False)

