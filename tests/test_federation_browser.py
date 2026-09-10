"""Opt-in real Chrome check, using only local HTML and an installed driver."""
import os
from urllib.parse import quote

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from ui.pages.federation_tool import InvoiceProcessor
from ui.pages.macro_popup_recovery import find_clickable_context


@pytest.mark.skipif(not os.environ.get("MYTOOL_CHROMEDRIVER"), reason="Opt-in local Chrome integration test")
def test_real_chrome_preserves_report_frame(tmp_path):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--user-data-dir={tmp_path / 'chrome-profile'}")
    driver = webdriver.Chrome(service=Service(os.environ["MYTOOL_CHROMEDRIVER"]), options=options)
    commands = []
    execute = driver.execute

    def trace(command, params=None):
        if command in {"switchToFrame", "switchToParentFrame", "switchToWindow"}:
            commands.append(command)
        return execute(command, params)

    driver.execute = trace
    try:
        driver.get("data:text/html," + quote('<iframe srcdoc="<p>unrelated</p>"></iframe><iframe id="report"></iframe>'))
        driver.execute_script("""
            document.querySelector('#report').srcdoc = `<button id="download" onclick="setTimeout(() => {
                const button = document.createElement('button'); button.id = 'options';
                button.textContent = 'Options'; document.body.appendChild(button);
            }, 1500)">Download</button>`;
        """)
        owner = InvoiceProcessor.__new__(InvoiceProcessor)
        owner.driver = driver
        owner.config = {"performance": {"poll_interval": 0.1}}
        owner.timeout = 5
        owner.status_callback = lambda message: None
        download = owner.wait_clickable_context("download", (By.ID, "download"))
        download.click()
        commands.clear()
        assert owner.wait_clickable_context("options", (By.ID, "options")).text == "Options"
        assert commands == [], f"Unnecessary frame switches: {commands}"
        assert find_clickable_context(driver, (By.ID, "missing"), lambda message: None) is None
        assert driver.find_element(By.ID, "options").text == "Options", "Failed scan left the report frame"
        print("Real Chrome: delayed button found with 0 frame switches; failed search restored report frame.")
    finally:
        driver.quit()
