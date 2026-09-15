from selenium.common.exceptions import NoAlertPresentException, UnexpectedAlertPresentException, WebDriverException
from selenium.webdriver.common.by import By


def dismiss_native_alert(driver, log):
    try:
        alert = driver.switch_to.alert
        text = alert.text
        alert.dismiss()
        log(f"[popup_recovery] alert/confirm/prompt 처리=dismiss(취소/닫기), 내용={str(text)[:200]}")
        return True
    except NoAlertPresentException:
        return False


def dismiss_blocking_popups(driver, protected_handles, locator, log):
    """Dismiss unexpected UI only; never accept a confirmation or submit a prompt."""
    changed = dismiss_native_alert(driver, log)
    # Absence of the current selector does not prove a new window is unrelated.
    # Report viewers may still be loading or contain the target in an iframe.
    targets = driver.find_elements(*locator) if locator else []
    dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], [role='alertdialog'], dialog[open], [aria-modal='true']")
    for dialog in dialogs:
        if not dialog.is_displayed():
            continue
        if any(driver.execute_script("return arguments[0].contains(arguments[1]);", dialog, target) for target in targets):
            continue
        buttons = dialog.find_elements(By.CSS_SELECTOR, "button, [role='button'], input[type='button']")
        for button in buttons:
            label = (button.get_attribute("aria-label") or button.text or button.get_attribute("value") or "").strip().lower()
            if label in {"닫기", "취소", "close", "cancel", "x", "×"} and button.is_displayed() and button.is_enabled():
                try:
                    driver.execute_script("arguments[0].click();", button)
                    log("[popup_recovery] 매크로 대상이 없는 화면 팝업의 닫기 버튼을 눌렀습니다.")
                    changed = True
                except WebDriverException:
                    pass
                break
    return changed


def find_clickable_context(driver, locator, log):
    """Search open windows and nested frames; retain the context only on success."""
    original = driver.current_window_handle
    handles = list(driver.window_handles)
    visited = 0
    diagnostics = []
    original_frames = []
    cached = driver.__dict__.get("_macro_found_context")
    if cached and cached[0] == original:
        try:
            if driver.find_element(By.TAG_NAME, "html") == cached[2]:
                original_frames = list(cached[1])
        except WebDriverException:
            pass
    frame_stack = []

    def search(depth, path):
        nonlocal visited
        visited += 1
        elements = driver.find_elements(*locator)
        for element in elements:
            if element.is_displayed() and element.is_enabled():
                # Save frame elements, not indices: sibling frame insertion can change indices.
                if hasattr(driver, "find_element"):
                    driver._macro_found_context = (driver.current_window_handle, list(frame_stack), driver.find_element(By.TAG_NAME, "html"))
                log(f"[target_context] 대상 발견: window={driver.current_window_handle}, frame={path or 'top'}")
                return element
        if depth >= 5 or visited >= 80:
            return None
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        for index, frame in enumerate(frames):
            if visited >= 80:
                break
            entered = False
            found = None
            try:
                driver.switch_to.frame(frame)
                frame_stack.append(frame)
                entered = True
                found = search(depth + 1, f"{path}/{index}")
                if found is not None:
                    return found
            finally:
                if entered and found is None:
                    driver.switch_to.parent_frame()
                    frame_stack.pop()
        return None

    found = None
    try:
        for handle in [original] + [item for item in handles if item != original]:
            try:
                if driver.current_window_handle != handle:
                    driver.switch_to.window(handle)
                driver.switch_to.default_content()
                frame_stack.clear()
                diagnostics.append(f"window={handle}, title={driver.title}")
                found = search(0, "")
                if found is not None:
                    return found
            except UnexpectedAlertPresentException:
                raise
            except WebDriverException as exc:
                diagnostics.append(f"window={handle}: {type(exc).__name__}")
        log("[target_context] 현재 열린 창·프레임에서 클릭 가능한 대상 없음: " + " | ".join(diagnostics))
        return None
    finally:
        if found is None and original in driver.window_handles:
            if driver.current_window_handle != original:
                driver.switch_to.window(original)
            driver.switch_to.default_content()
            try:
                for frame in original_frames:
                    driver.switch_to.frame(frame)
            except WebDriverException:
                driver.switch_to.default_content()
