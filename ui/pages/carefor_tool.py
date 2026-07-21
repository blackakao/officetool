from ui.pages.federation_tool import FederationTool
from ui.pages.login_tool import CareforLoginThread


class CareforTool(FederationTool):
    """케어포 로그인 후 설정된 매크로 작업을 실행하는 도구 페이지."""

    def __init__(self):
        super().__init__(
            tool_name="케어포툴",
            task_config_name="carefor_tasks.json",
            legacy_selector_name="carefor_selectors.json",
            login_thread_class=CareforLoginThread,
            login_label="케어포",
            log_source="CareforTool",
        )
