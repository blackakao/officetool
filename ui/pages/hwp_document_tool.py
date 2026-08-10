import re
from pathlib import Path

from PySide6.QtCore import QDate

from ui.pages.document_tool import ContentControlDialog, DocumentTool
from ui.pages.logging_util import log


class HwpAutomation:
    """한컴오피스 한글의 Windows COM 자동화를 작은 범위로 감싼다."""

    def __init__(self):
        self.hwp = None
        self.pythoncom = None

    def __enter__(self):
        try:
            import pythoncom
            import win32com.client
        except ImportError as error:
            raise RuntimeError(
                "HWP 자동화에 필요한 pywin32가 설치되어 있지 않습니다."
            ) from error

        self.pythoncom = pythoncom
        pythoncom.CoInitialize()
        try:
            self.hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
            try:
                self.hwp.XHwpWindows.Item(0).Visible = False
            except Exception:
                pass
            try:
                self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            except Exception:
                pass
            return self
        except Exception as error:
            pythoncom.CoUninitialize()
            raise RuntimeError(
                "한컴오피스 한글을 실행할 수 없습니다. 한글 설치 상태를 확인해 주세요."
            ) from error

    def __exit__(self, exc_type, exc_value, traceback):
        if self.hwp is not None:
            try:
                self.hwp.Clear(1)
            except Exception:
                pass
            try:
                self.hwp.Quit()
            except Exception:
                pass
        if self.pythoncom is not None:
            self.pythoncom.CoUninitialize()

    def open(self, file_path):
        opened = self.hwp.Open(str(Path(file_path).resolve()), "HWP", "forceopen:true")
        if opened is False:
            raise RuntimeError(f"HWP 문서를 열 수 없습니다: {file_path}")

    @staticmethod
    def _base_field_name(name):
        return re.sub(r"\{\{\d+\}\}$", "", str(name)).strip()

    def field_names(self):
        raw = self.hwp.GetFieldList(0, "") or ""
        names = []
        for name in re.split(r"[\x02\r\n]+", str(raw)):
            name = self._base_field_name(name)
            if name and name not in names:
                names.append(name)
        return names

    def field_text(self, field_name):
        try:
            return str(self.hwp.GetFieldText(field_name) or "")
        except Exception:
            return ""

    def put_text(self, field_name, value):
        self.hwp.PutFieldText(field_name, str(value))

    def put_image(self, field_name, value):
        image_path = Path(value.get("path", ""))
        if not image_path.is_file():
            return
        if not self.hwp.MoveToField(field_name, True, True, False):
            raise RuntimeError(f"이미지를 넣을 HWP 필드를 찾을 수 없습니다: {field_name}")

        width = float(value.get("width", 30) or 30)
        height = float(value.get("height", 30) or 30)
        try:
            self.hwp.InsertPicture(
                str(image_path.resolve()), True, 3, False, False, 0, width, height
            )
        except TypeError:
            # 오래된 한글 버전은 폭/높이 인수가 없는 형식을 사용한다.
            self.hwp.InsertPicture(str(image_path.resolve()), True, 2)

    def save_pdf(self, output_path):
        saved = self.hwp.SaveAs(str(Path(output_path).resolve()), "PDF", "")
        if saved is False:
            raise RuntimeError(f"PDF로 저장하지 못했습니다: {output_path}")


class HwpContentControlDialog(ContentControlDialog):
    settings_filename = "hwp_document_field_settings.json"

    def _collect_controls(self, _document):
        controls = {}
        with HwpAutomation() as automation:
            automation.open(self.file_path)
            for index, field_name in enumerate(automation.field_names()):
                controls[field_name] = {
                    "tag": field_name,
                    "alias": "",
                    "placeholder": "",
                    "current_text": automation.field_text(field_name),
                    "indices": [index],
                }
        return controls

    def _resolved_hwp_values(self, values_dict):
        values = dict(values_dict)

        def resolve_date(field_key, visited=None):
            visited = set(visited or ())
            if field_key in visited:
                return None
            visited.add(field_key)
            setting = self.settings.get("fields", {}).get(field_key, {})
            if setting.get("type") != "date":
                return None
            if setting.get("date_default_type", "today") != "field_calculation":
                return self._parse_date_or_none(values.get(field_key, "")) or QDate.currentDate()
            source_date = resolve_date(setting.get("source_date_field", ""), visited)
            if not source_date:
                return None
            sign = int(setting.get("date_offset_sign", 1) or 1)
            days = int(setting.get("date_offset_days", 0) or 0)
            return source_date.addDays(sign * days)

        for field_key, setting in self.settings.get("fields", {}).items():
            if setting.get("type") == "date" and setting.get("date_default_type") == "field_calculation":
                calculated = resolve_date(field_key)
                values[field_key] = (
                    calculated.toString(setting.get("date_format", "yyyy-MM-dd"))
                    if calculated
                    else ""
                )
        for field_key, setting in self.settings.get("fields", {}).items():
            if setting.get("type") == "folder":
                values[field_key] = self._folder_image_value(
                    setting,
                    values.get(setting.get("value_field", ""), ""),
                )
        return values

    def _create_pdf(self, values_dict, output_title=None, ask_on_duplicate=False, status_callback=None):
        def report(step, message):
            if status_callback:
                status_callback(step, message)

        report(1, "HWP 문서를 열고 있습니다...")
        values = self._resolved_hwp_values(values_dict)
        maked_folder = self.file_path.parent / "maked"
        maked_folder.mkdir(exist_ok=True)
        output_path = self._resolve_output_pdf_path(
            maked_folder,
            output_title or f"{self.file_path.stem}_filled",
            ask_on_duplicate,
        )
        if output_path is None:
            return None

        with HwpAutomation() as automation:
            automation.open(self.file_path)
            report(2, "HWP 필드 값을 적용하고 있습니다...")
            for field_name, value in values.items():
                if field_name not in self.controls:
                    continue
                if isinstance(value, dict) and value.get("type") == "image":
                    automation.put_image(field_name, value)
                else:
                    automation.put_text(field_name, value)
            report(3, "한글에서 PDF로 저장하고 있습니다...")
            automation.save_pdf(output_path)

        report(4, "PDF 저장을 완료하고 있습니다...")
        log("HwpDocumentTool", f"PDF 생성 완료: {output_path}", level="INFO")
        return output_path


class HwpDocumentTool(DocumentTool):
    document_folder_name = "document_hwp"
    document_pattern = "*.hwp"
    settings_filename = "hwp_document_field_settings.json"
    tool_title = "문서 작성 도구(한글)"

    def _create_dialog(self, file_path, mode):
        return HwpContentControlDialog(self, None, file_path, mode=mode)

