import json
import os
import time
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from ui.pages.logging_util import log


class LoginTool(QWidget):
    def __init__(self):
        super().__init__()
        
        self.data_file = Path(__file__).resolve().parents[2] / "data" / "branches.json"
        self.log_file = Path(__file__).resolve().parents[2] / "data" / "login.log"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.current_login_type = "케어포"
        self.login_type_buttons = []
        self.branch_grid_layout = QGridLayout()
        self.login_threads = []

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.main_layout)

        # 로그인 유형 선택 버튼
        login_type_label = QLabel("로그인 유형")
        self.main_layout.addWidget(login_type_label)

        login_type_layout = QHBoxLayout()
        for login_type in ["케어포", "롱텀"]:
            button = QPushButton(login_type)
            button.setCheckable(True)
            button.clicked.connect(self.on_login_type_clicked)
            self.login_type_buttons.append(button)
            login_type_layout.addWidget(button)
        login_type_layout.addStretch()
        self.main_layout.addLayout(login_type_layout)
        self._update_login_type_buttons()

        # 지점 목록
        self.main_layout.addLayout(self.branch_grid_layout)

        self.refresh_buttons()
    
    def refresh_buttons(self):
        """지점 버튼 목록 새로고침"""
        while self.branch_grid_layout.count():
            child = self.branch_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        branches = self._load_branches()
        for index, branch in enumerate(branches):
            row = index // 5
            col = index % 5
            button = QPushButton(branch["branch_name"])
            button.clicked.connect(lambda _, b=branch: self.on_branch_clicked(b))
            self.branch_grid_layout.addWidget(button, row, col)
    
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
        log("LoginTool", message, level=level)

    def on_branch_clicked(self, branch):
        """지점 버튼 클릭 시 로그인 페이지를 열고 로그인 필드를 채웁니다."""
        branch_code = branch.get("organization_code", "")
        if not branch_code:
            self._log(f"지점 '{branch.get('branch_name','')}'의 기관기호가 없습니다.", level="WARNING")
            return

        self._log(f"[{branch.get('branch_name','')}] 로그인 시도, 기관기호={branch_code}, 타입={self.current_login_type}")
        if self.current_login_type == "롱텀":
            login_thread = LongtermLoginThread(branch)
        else:
            login_thread = CareforLoginThread(branch)

        login_thread.finished_signal.connect(self.on_login_finished)
        login_thread.start()
        self.login_threads.append(login_thread)

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
                return [
                    branch
                    for branch in json.load(f)
                    if branch.get("active", True)
                ]
        except FileNotFoundError:
            return []


class BaseLoginThread(QThread):
    finished_signal = Signal(str, bool)

    def __init__(self, branch: dict, url: str, profile_path: Path | None = None):
        super().__init__()
        self.branch = branch
        self.url = url
        self.driver = None
        self.profile_path = profile_path

    def _create_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")

        if self.profile_path:
            self.profile_path.mkdir(parents=True, exist_ok=True)
            options.add_argument(f"--user-data-dir={self.profile_path}")

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

        return webdriver.Chrome(
            service=ChromeService(str(driver_path)),
            options=options,
        )

    def run(self):
        self.success = False
        try:
            self.driver = self._create_driver()
            self.driver.get(self.url)
            wait = WebDriverWait(self.driver, 30)
            self.perform_login(wait)
            self.success = True
        except TimeoutException:
            self.finished_signal.emit("페이지 로딩 또는 입력 필드 활성화에 실패했습니다.", False)
        except FileNotFoundError as e:
            self.finished_signal.emit(f"ChromeDriver 실행 파일을 찾을 수 없습니다: {e}", False)
        except WebDriverException as e:
            self.finished_signal.emit(f"Chrome 자동화 실패: {e}", False)
        except Exception as e:
            self.finished_signal.emit(f"알 수 없는 오류: {e}", False)
        finally:
            if self.driver and not getattr(self, "success", False):
                try:
                    self.driver.quit()
                except Exception:
                    pass

    def _wait_and_click(self, wait, locator):
        element = wait.until(EC.element_to_be_clickable(locator))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except Exception:
                raise
        return element

    def perform_login(self, wait):
        raise NotImplementedError("Subclasses must implement perform_login")


class CareforLoginThread(BaseLoginThread):
    def __init__(self, branch: dict):
        super().__init__(branch, "https://www.carefor.co.kr/login.php")

    def perform_login(self, wait):
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

        # 새 구조에서 credentials 읽기, 호환성을 위해 기존 구조도 지원
        credentials = self.branch.get("credentials", {})
        carefor_creds = credentials.get("carefor", {})
        id_value = carefor_creds.get("login_id") or self.branch.get("login_id", "")
        pass_value = carefor_creds.get("login_password") or self.branch.get("login_password", "")

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


class LongtermLoginThread(BaseLoginThread):
    def __init__(self, branch: dict):
        profile_path = Path(__file__).resolve().parents[2] / "data" / "chrome_profiles" / "gongdan"
        super().__init__(branch, "https://www.longtermcare.or.kr/npbs/auth/login/loginForm.web?menuId=npe0000002840&rtnUrl=&zoomSize=", profile_path=profile_path)

    def perform_login(self, wait):
        longterm_no = self.branch.get("organization_code", "")
        # 새 구조에서 credentials 읽기, 호환성을 위해 기존 구조도 지원
        credentials = self.branch.get("credentials", {})
        longterm_creds = credentials.get("longterm", {})
        certificate_name = longterm_creds.get("certificate_name") or self.branch.get("certificate_name") or self.branch.get("login_id", "")
        certificate_password = longterm_creds.get("certificate_password") or self.branch.get("certificate_password") or self.branch.get("login_password", "")

        label = self._wait_and_click(wait, (By.CSS_SELECTOR, 'label[for="chkTouchEn"]'))

        try:
            alert = wait.until(EC.alert_is_present())
            alert.accept()
        except TimeoutException:
            pass

        self._wait_and_click(wait, (By.ID, 'tab_login_02'))

        user_no = wait.until(EC.element_to_be_clickable((By.ID, 'userNo')))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", user_no)
        user_no.clear()
        user_no.send_keys(longterm_no)

        self._wait_and_click(wait, (By.ID, 'btn_login_A2_A'))

        self._wait_and_click(wait, (By.ID, 'xwup_media_hdd'))

        escaped_certificate_name = certificate_name.replace('"', '\\"')
        css_selector = f'div[title="{escaped_certificate_name}"]'
        self._wait_and_click(wait, (By.CSS_SELECTOR, css_selector))

        user_pwd = wait.until(EC.element_to_be_clickable((By.ID, 'xwup_certselect_tek_input1')))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", user_pwd)
        user_pwd.click()
        webdriver.ActionChains(self.driver).send_keys_to_element(user_pwd, certificate_password).perform()

        self._wait_and_click(wait, (By.ID, 'xwup_OkButton'))
        try:
            WebDriverWait(self.driver, 2).until(
                lambda d: d.find_elements(By.XPATH, "//*[contains(@id, 'mainframe.VFrameSet.frameTop')]")
            )
        except TimeoutException:
            log("LoginTool", "공단 메인 프레임 확인 대기 2초 초과 - 자동화 단계로 계속 진행합니다.", level="WARNING")

        self.finished_signal.emit("롱텀 공단 로그인 절차를 완료했습니다.", True)

