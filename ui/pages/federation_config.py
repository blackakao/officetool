"""공단 매크로 설정, 기본 템플릿 및 순수 값 변환. UI와 실행부에 의존하지 않는다."""

import hashlib
import json
import re
from pathlib import Path

from selenium.webdriver.common.by import By


BY_TYPES = {
    "xpath": By.XPATH,
    "css": By.CSS_SELECTOR,
    "id": By.ID,
    "name": By.NAME,
    "class": By.CLASS_NAME,
    "tag": By.TAG_NAME,
}


ACTION_TYPES = {
    "click": "클릭",
    "hover": "호버",
    "hover_click": "호버 후 클릭",
}

REPEAT_MODES = {
    "fixed": "고정 반복",
    "increment": "증가 반복",
    "range": "값 범위 반복 (시작·종료값)",
}

PROCESS_TYPES = {
    "url_navigation": "URL 이동",
    "element": "엘레멘트",
    "table": "테이블",
    "text_assert": "텍스트 검증",
    "alert": "alert",
    "confirm": "confirm",
    "prompt": "prompt",
    "window": "새창/팝업창",
    "legacy_action": "레거시 동작",
    "condition_start": "조건처리의 조건",
    "condition_true": "조건처리-참",
    "condition_false": "조건처리-거짓",
    "condition_end": "조건처리 종료",
    "repeat_start": "반복지점 시작",
    "repeat_end": "반복지점 종료",
}

PROCESS_ACTIONS = {
    "url_navigation": {"navigate": "이동"},
    "element": {**ACTION_TYPES, "input_text": "값 입력 (검증)", "select_text": "텍스트로 옵션 선택 (검증)", "pointer_click": "마우스로 클릭 후 화면 확인"},
    "table": {"verify_click_increment": "증가 검증 후 클릭"},
    "text_assert": {
        "equals_repeat_number": "반복번호와 일치",
        "contains_repeat_number": "반복번호 포함",
        "equals_repeat_text": "반복번호 텍스트 일치",
        "text_exists": "텍스트 존재",
    },
    "alert": {"accept": "확인/수락", "dismiss": "취소/닫기", "accept_if_present": "확인/수락 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "confirm": {"accept": "확인/수락", "dismiss": "취소/닫기", "accept_if_present": "확인/수락 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "prompt": {"accept": "텍스트 입력 후 확인", "dismiss": "취소/닫기", "accept_if_present": "텍스트 입력 후 확인 (없으면 계속)", "dismiss_if_present": "취소/닫기 (없으면 계속)"},
    "window": {"keep": "유지", "switch_last": "마지막 창으로 전환", "close_extra": "추가 창 닫기"},
    "legacy_action": {
        "last_table_click": "마지막 테이블 행 다시 클릭",
        "last_table_next_row_click": "마지막 테이블의 다음 행 클릭",
        "last_table_previous_row_click": "마지막 테이블의 이전 행 클릭",
        "last_table_double_click": "마지막 테이블 행 더블클릭",
        "last_table_force_click": "마지막 테이블 행 강제 클릭",
        "last_table_force_double_click": "마지막 테이블 행 강제 더블클릭",
        "short_wait": "짧은 대기",
        "wait_loading_done": "로딩 사라짐 대기",
    },
    "condition_start": {
        "field_empty": "필드값 비어 있음",
        "field_not_empty": "필드값 있음",
        "text_exists": "텍스트 존재",
        "equals_value": "조건값과 일치",
        "contains_value": "조건값 포함",
        "equals_repeat_number": "반복번호와 일치",
        "contains_repeat_number": "반복번호 포함",
    },
    "condition_true": {"branch": "참 구역"},
    "condition_false": {"branch": "거짓 구역"},
    "condition_end": {"end": "종료"},
    "repeat_start": REPEAT_MODES,
    "repeat_end": {"end": "종료"},
}

SELECTOR_TEMPLATE = {
    "version": 1,
    "timeouts": {"default": 20, "short": 3, "long": 60, "loading": 120},
    "browser": {"window_index": -1},
    "selectors": {
        "layer_popup_close": {"label": "레이어 팝업 닫기", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "layer_popup_confirm": {"label": "레이어 팝업 확인", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "browser_popup_close_button": {"label": "브라우저 팝업 닫기 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "main_menu": {"label": "상단 메뉴 - 급여비용청구", "type": "element", "by": "xpath", "value": "", "required": True, "action": "hover_click"},
        "payroll_claim_dropdown": {"label": "드롭다운 메뉴 - 급여비용청구", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "claim_page_warning_close": {"label": "급여비용청구 페이지 경고 모달 닫기/확인", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "operation_guide_close": {"label": "운영안내 팝업 닫기", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "claim_button": {"label": "우측 주황색 청구하기 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "entry_notice_tab": {"label": "원청구 모달 탭 - 입퇴소신고내용관리", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "entry_notice_rows": {"label": "입소신고자 테이블 행 목록", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "recipient_select_all_checkbox": {"label": "수급자명 테이블 상단 전체 체크박스", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "recipient_checkboxes": {"label": "수급자명 테이블 개별 체크박스 목록", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "add_recipient_button": {"label": "청구대상자로 넘기는 > 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "confirm_add_recipient": {"label": "청구대상자로 추가 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "loading_canvas": {"label": "진행중 캔버스/로딩 요소", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "claim_target_created_message": {"label": "청구대상자가 생성되었습니다 알림/확인", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "salary_data_tab": {"label": "원청구 모달 탭 - 급여내용 자료 관리", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "search_button": {"label": "급여내용 자료 관리 조회 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "claim_target_rows": {"label": "청구대상자 테이블 행 목록", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "save_button": {"label": "저장 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "confirm_save": {"label": "급여자료 저장 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "save_completed_confirm": {"label": "저장되었습니다 알림 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "generate_statement_button": {"label": "명세서자동생성 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "statement_register_complete_button": {"label": "자식 모달 - 명세서 등록완료 버튼", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "pay_result_select": {"label": "급여제공결과등록 - 급여제공결과 셀렉트", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
        "pay_result_continue_option": {"label": "급여제공결과 셀렉트 옵션 - 계속", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "pay_result_save_button": {"label": "급여제공결과등록 저장 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "confirm_pay_result_save": {"label": "급여제공결과 저장 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "statement_completed_confirm": {"label": "명세서가 등록완료되었습니다 확인 버튼", "type": "element", "by": "xpath", "value": "", "required": False, "action": "click"},
        "statement_auto_modal_close": {"label": "시설/단기보호 청구명세서 자동생성 닫기", "type": "element", "by": "xpath", "value": "", "required": True, "action": "click"},
    },
    "popup_close_selectors": [
        {"label": "공통 버튼 - 닫기", "by": "xpath", "value": "//button[normalize-space(.)='닫기']"},
        {"label": "공통 버튼 - 확인", "by": "xpath", "value": "//button[normalize-space(.)='확인']"},
        {"label": "공통 링크 - 닫기", "by": "xpath", "value": "//a[normalize-space(.)='닫기']"},
        {"label": "공통 링크 - 확인", "by": "xpath", "value": "//a[normalize-space(.)='확인']"},
    ],
}


EMPTY_SELECTOR_TEMPLATE = {
    "version": 1,
    "timeouts": {"default": 20, "short": 3, "long": 60, "loading": 120},
    "browser": {"window_index": -1},
    "selectors": {},
    "popup_close_selectors": [
        {"label": "공통 버튼 - 닫기", "by": "xpath", "value": "//button[normalize-space(.)='닫기']"},
        {"label": "공통 버튼 - 확인", "by": "xpath", "value": "//button[normalize-space(.)='확인']"},
        {"label": "공통 링크 - 닫기", "by": "xpath", "value": "//a[normalize-space(.)='닫기']"},
        {"label": "공통 링크 - 확인", "by": "xpath", "value": "//a[normalize-space(.)='확인']"},
    ],
}


DEFAULT_TASK_CONFIGS = {
    "invoice": {"label": "청구 명세서 만들기", "config_file": "federation_selectors_invoice.json", "template": SELECTOR_TEMPLATE, "implemented": True},
    "long_service": {"label": "장기근속수당 입력하기", "config_file": "federation_selectors_long_service.json", "template": EMPTY_SELECTOR_TEMPLATE, "implemented": True},
}


def task_template(task_config: dict) -> dict:
    template_name = task_config.get("template_name", "empty")
    if template_name == "selector":
        return SELECTOR_TEMPLATE
    return EMPTY_SELECTOR_TEMPLATE


def normalize_task_configs(configs: dict | None, deleted_task_keys: set[str] | None = None) -> dict:
    deleted_task_keys = deleted_task_keys or set()
    result = {}
    for task_key, task_config in DEFAULT_TASK_CONFIGS.items():
        if task_key in deleted_task_keys:
            continue
        normalized = dict(task_config)
        normalized.setdefault("template_name", "selector" if task_key == "invoice" else "empty")
        result[task_key] = normalized

    for task_key, task_config in (configs or {}).items():
        if not isinstance(task_config, dict):
            continue
        label = str(task_config.get("label", "")).strip()
        config_file = str(task_config.get("config_file", "")).strip()
        if not task_key or not label or not config_file:
            continue
        normalized = {
            "label": label,
            "config_file": config_file,
            "template_name": task_config.get("template_name", "empty"),
            "implemented": bool(task_config.get("implemented", True)),
        }
        normalized["template"] = task_template(normalized)
        result[task_key] = normalized

    for task_config in result.values():
        task_config["template"] = task_template(task_config)
        task_config["implemented"] = bool(task_config.get("implemented", True))
    return result

def ensure_selector_config(path: Path, template: dict | None = None) -> dict:
    template = template or SELECTOR_TEMPLATE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        data = json.loads(json.dumps(template, ensure_ascii=False))
        save_selector_config(path, data)
        return data

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    data.setdefault("version", template["version"])
    data.setdefault("timeouts", {})
    data.setdefault("browser", {})
    data.setdefault("selectors", {})
    data.setdefault("popup_close_selectors", [])
    data.setdefault("deleted_selector_keys", [])

    for key, value in template["timeouts"].items():
        if key not in data["timeouts"]:
            data["timeouts"][key] = value
            changed = True

    for key, value in template.get("browser", {}).items():
        if key not in data["browser"]:
            data["browser"][key] = value
            changed = True

    deleted_selector_keys = set(data.get("deleted_selector_keys", []))
    for key, selector in template["selectors"].items():
        if key in deleted_selector_keys:
            continue
        if key not in data["selectors"]:
            data["selectors"][key] = selector
            changed = True
        else:
            data["selectors"][key].setdefault("label", selector["label"])
            data["selectors"][key].setdefault("type", selector.get("type", "element"))
            data["selectors"][key].setdefault("by", selector["by"])
            data["selectors"][key].setdefault("value", "")
            data["selectors"][key].setdefault("required", selector["required"])
            data["selectors"][key].setdefault("action", selector.get("action", "click"))

    for selector in data["selectors"].values():
        selector.setdefault("type", "element")
        selector.setdefault("action", "click")
        if selector.get("type") == "delay":
            selector["type"] = "legacy_action"
            selector["action"] = "short_wait"
            selector.setdefault("label", "짧은 대기")
            changed = True

    if not data["popup_close_selectors"]:
        data["popup_close_selectors"] = template["popup_close_selectors"]
        changed = True

    if changed:
        save_selector_config(path, data)

    return data


def save_selector_config(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def build_locator(selector: dict):
    by = selector.get("by", "xpath")
    value = selector.get("value", "").strip()
    if not value:
        return None
    if by not in BY_TYPES:
        raise ValueError(f"지원하지 않는 선택자 유형입니다: {by}")
    return BY_TYPES[by], value


def apply_runtime_context(selector: dict, context: dict | None = None) -> dict:
    if not context:
        return selector

    result = dict(selector)
    value = result.get("value", "")
    if isinstance(value, str):
        def replace_expression(match):
            name = match.group(1)
            operator = match.group(2)
            amount = int(match.group(3) or 0)
            if not operator:
                return str(context.get(name, 0))
            base = int(context.get(name, 0))
            if operator == "-":
                return str(base - amount)
            return str(base + amount)

        value = re.sub(
            r"\{(repeat_index|repeat_number)(?:([+-])(\d+))?\}",
            replace_expression,
            value,
        )
        replacements = {
            "{repeat_value}": str(context.get("repeat_value", context.get("repeat_number", ""))),
            "{repeat_index}": str(context.get("repeat_index", 0)),
            "{repeat_number}": str(context.get("repeat_number", 1)),
        }
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        result["value"] = value
    return result


def english_task_stem(label):
    words = {
        "장기근속수당": "long_service_allowance", "본인부담금": "copayment",
        "급여제공": "care_provision", "명세서": "statement", "입소자": "resident",
        "수급자": "recipient", "출근부": "attendance", "프로그램": "program",
        "기관기호": "organization_code", "청구": "claim", "공단": "federation",
        "명단": "roster", "급여": "payroll", "의료비": "medical_expense",
        "만들기": "create", "생성": "create", "입력하기": "entry", "입력": "entry",
        "조회": "search", "등록": "register", "수정": "update", "저장": "save",
        "다운로드": "download", "업로드": "upload", "검토": "review", "확인": "check",
        "발송": "send", "월간": "monthly", "일간": "daily", "연간": "annual",
        "업무": "task", "작업": "task", "복사": "copy", "테스트": "test",
        "삭제": "delete", "관리": "management", "결정요청": "decision_request",
    }
    translated = label.lower()
    for korean in sorted(words, key=len, reverse=True):
        translated = translated.replace(korean, f" {words[korean]} ")
    tokens = re.findall(r"[a-z0-9_]+", translated)
    stem = "_".join(tokens).strip("_")[:90] or "task"
    if re.search(r"[가-힣]", translated):
        stem += "_" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return stem
