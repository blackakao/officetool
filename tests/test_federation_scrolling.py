from unittest.mock import Mock, patch

import pytest

from ui.pages.federation_tool import InvoiceProcessor


def runner():
    obj = InvoiceProcessor.__new__(InvoiceProcessor)
    obj.config = {'start_number': 19, 'table_scroll': {'by': 'xpath', 'value': '//grid'}}
    obj.driver = Mock()
    obj.status_callback = Mock()
    return obj


def test_resume_uses_original_numbers_and_stops_at_total():
    obj = runner()
    obj.repeat_count = Mock(return_value=21)
    obj.run_selector_step = Mock()
    obj.run_workflow_items_once([
        ('start', {'type': 'repeat_start', 'repeat_mode': 'increment'}),
        ('row', {'type': 'table'}), ('end', {'type': 'repeat_end'}),
    ])
    assert [c.kwargs['context']['repeat_number'] for c in obj.run_selector_step.call_args_list] == [19, 20, 21]


def test_resume_out_of_range_stops_before_work():
    obj = runner()
    obj.repeat_count = Mock(return_value=10)
    obj.run_selector_step = Mock()
    with pytest.raises(ValueError):
        obj.run_workflow_items_once([
            ('start', {'type': 'repeat_start', 'repeat_mode': 'increment'}),
            ('row', {'type': 'table'}), ('end', {'type': 'repeat_end'}),
        ])
    obj.run_selector_step.assert_not_called()


def test_search_scrolls_until_target_is_visible():
    obj = runner()
    obj.visible_table_rows = Mock(side_effect=[[1, 2], [1, 2], [3, 4]])
    obj.table_visible_signature = Mock(side_effect=['1|2', '1|2', '3|4'])
    obj.table_row_number_text = Mock(side_effect=lambda row, _: (str(row), row))
    obj.table_number_cell_selector = Mock(return_value='number')
    obj.scroll_virtual_table = Mock(return_value=True)
    # Lightweight row objects retain their number while supplying DOM metadata.
    rows = {n: Mock(text=str(n)) for n in range(1, 5)}
    obj.visible_table_rows.side_effect = [[rows[1], rows[2]], [rows[1], rows[2]], [rows[3], rows[4]]]
    obj.table_row_number_text.side_effect = lambda row, _: (row.text, int(row.text))
    found, _, _ = obj.find_virtual_table_row_for_number({}, 4)
    assert found is rows[4]
    assert obj.scroll_virtual_table.call_count == 2


def test_empty_view_uses_grid_as_wheel_origin():
    obj = runner()
    obj.driver.execute_script.return_value = {'x': 100, 'y': 200}
    with patch('ui.pages.federation_tool.ActionChains') as actions, patch('ui.pages.federation_tool.time.sleep'):
        assert obj.scroll_virtual_table('table', {}, [])
    obj.driver.find_element.assert_called_once_with('xpath', '//grid')
    actions.return_value.scroll_from_origin.assert_called_once()
    actions.return_value.move_to_element.assert_not_called()


def test_displayed_but_clipped_row_is_rejected():
    obj = runner()
    row = Mock()
    row.is_displayed.return_value = True
    obj.driver.execute_script.return_value = False
    assert not obj.table_row_in_view(row)


def test_distant_target_uses_large_wheel_instead_of_arrow():
    obj = runner()
    row = Mock()
    obj.driver.execute_script.return_value = {'x': 100, 'y': 200}
    obj.table_row_number_text = Mock(return_value=('20', 20))
    obj.visible_table_rows = Mock(return_value=[row])
    obj.table_click_target = Mock(return_value=row)
    with patch('ui.pages.federation_tool.ActionChains') as actions, patch('ui.pages.federation_tool.time.sleep'):
        obj.scroll_virtual_table('table', {'_expected_number': 72}, [row])
    actions.return_value.move_to_element.assert_not_called()
    assert actions.return_value.scroll_from_origin.call_count == 8
    assert actions.return_value.scroll_from_origin.call_args.args[2] == 120


def test_search_reverses_direction_after_overshooting():
    obj = runner()
    row = Mock(text='80')
    target = Mock(text='72')
    obj.visible_table_rows = Mock(side_effect=[[row], [target]])
    obj.table_visible_signature = Mock(side_effect=['80', '72'])
    obj.table_row_number_text = Mock(side_effect=lambda item, _: (item.text, int(item.text)))
    obj.table_number_cell_selector = Mock(return_value='number')
    obj.scroll_virtual_table = Mock(return_value=True)
    found, _, _ = obj.find_virtual_table_row_for_number({}, 72)
    assert found is target
    assert obj.scroll_virtual_table.call_args.kwargs['direction'] == -1


def test_near_target_uses_single_wheel_event():
    obj = runner()
    row = Mock()
    obj.table_row_number_text = Mock(return_value=('71', 71))
    obj.table_click_target = Mock(return_value=row)
    obj.driver.execute_script.return_value = {'x': 100, 'y': 200}
    with patch('ui.pages.federation_tool.ActionChains') as actions, patch('ui.pages.federation_tool.time.sleep'):
        obj.scroll_virtual_table('table', {'_expected_number': 72}, [row])
    actions.return_value.scroll_from_origin.assert_called_once()


def test_no_progress_stops_without_restarting_search():
    from selenium.common.exceptions import TimeoutException
    obj = runner()
    obj.visible_table_rows = Mock(return_value=[])
    obj.table_visible_signature = Mock(return_value='')
    obj.table_number_cell_selector = Mock(return_value='number')
    obj.scroll_virtual_table = Mock(return_value=True)
    with pytest.raises(TimeoutException):
        obj.find_virtual_table_row_for_number({}, 111)
    assert obj.scroll_virtual_table.call_count == 8


def test_unchanged_rows_keep_scrolling():
    obj = runner()
    row = Mock(text='21')
    obj.visible_table_rows = Mock(side_effect=[[]] * 5 + [[row]])
    obj.table_visible_signature = Mock(side_effect=[''] * 5 + ['21'])
    obj.table_row_number_text = Mock(return_value=('21', 21))
    obj.table_number_cell_selector = Mock(return_value='number')
    obj.scroll_virtual_table = Mock(return_value=True)
    found, _, _ = obj.find_virtual_table_row_for_number({}, 21)
    assert found is row
    assert obj.scroll_virtual_table.call_count == 5
    assert obj.scroll_virtual_table.call_args_list[-1].args[1]['_expected_number'] == 21


def test_overshoot_reduces_wheel_burst():
    obj = runner()
    rows = [Mock(text=str(number)) for number in (20, 80, 72)]
    obj.visible_table_rows = Mock(side_effect=[[row] for row in rows])
    obj.table_visible_signature = Mock(side_effect=['20', '80', '72'])
    obj.table_row_number_text = Mock(side_effect=lambda row, _: (row.text, int(row.text)))
    obj.table_number_cell_selector = Mock(return_value='number')
    obj.scroll_virtual_table = Mock(return_value=True)
    assert obj.find_virtual_table_row_for_number({}, 72)[0] is rows[-1]
    calls = obj.scroll_virtual_table.call_args_list
    assert calls[0].args[1]['_wheel_burst_limit'] == 8
    assert calls[1].args[1]['_wheel_burst_limit'] == 4
    assert calls[1].kwargs['direction'] == -1


def test_execution_captures_user_start_number():
    from ui.pages.federation_tool import FederationTool
    tool = Mock()
    tool.current_task = 'invoice'
    tool.selector_config_file = 'macro.json'
    tool.run_start_number_spin.value.return_value = 37
    tool.login_threads = []
    FederationTool.on_branch_clicked(tool, {'branch_name': 'test'})
    login = tool.login_thread_class.return_value
    assert login.macro_start_number == 37
    login.start.assert_called_once()


def test_missing_xpath_candidates_do_not_wait_two_seconds_each():
    obj = runner()
    obj.table_xpath_candidates = Mock(return_value=['//missing1', '//missing2'])
    obj.driver.find_elements.return_value = []
    obj.find_virtual_table_row_for_number = Mock(return_value=(None, None, None))
    with patch('ui.pages.federation_tool.TimedWebDriverWait') as wait:
        assert obj.find_table_row_for_number({'by': 'xpath', 'value': '//row[1]'}, 114) == (None, None, None)
    wait.assert_not_called()
    assert obj.driver.find_elements.call_count == 2


def test_closed_window_is_not_swallowed_by_candidate_search():
    from selenium.common.exceptions import NoSuchWindowException
    obj = runner()
    obj.table_xpath_candidates = Mock(return_value=['//row1', '//row2'])
    obj.driver.find_elements.side_effect = NoSuchWindowException()
    with pytest.raises(NoSuchWindowException):
        obj.find_table_row_for_number({'by': 'xpath', 'value': '//row[1]'}, 114)
    assert obj.driver.find_elements.call_count == 1


def test_obstructed_wheel_rechecks_fresh_table_before_scrolling():
    obj = runner()
    obj.timeout = 0
    obj.driver.execute_script.side_effect = [None, {'x': 100, 'y': 200}]
    obj.visible_table_rows = Mock(return_value=[])
    with patch('ui.pages.federation_tool.ActionChains') as actions, patch('ui.pages.federation_tool.time.sleep'):
        assert obj.scroll_virtual_table('table', {}, [])
    assert obj.driver.find_element.call_count == 2
    actions.return_value.scroll_from_origin.assert_called_once()


def test_persistent_obstruction_stops_before_xpath_fallback():
    from selenium.common.exceptions import TimeoutException
    obj = runner()
    obj.timeout = 0
    obj.driver.execute_script.return_value = None
    obj.visible_table_rows = Mock(return_value=[])
    obj.table_visible_signature = Mock(return_value='')
    obj.find_table_row_for_number = Mock()
    with pytest.raises(TimeoutException, match='가려져'):
        obj.run_table_step('table', {'by': 'xpath', 'value': '//row[1]'}, {'repeat_number': 114})
    obj.find_table_row_for_number.assert_not_called()


def test_batch_visibility_uses_one_browser_script_for_all_rows():
    obj = runner()
    obj.config['performance'] = {'batch_visibility': True}
    rows = [Mock(), Mock(), Mock()]
    obj.driver.find_elements.return_value = rows
    obj.driver.execute_script.return_value = rows[:1]
    obj.table_row_in_view = Mock()
    assert obj.visible_table_rows({'by': 'xpath', 'value': '//row[1]'}) == rows[:1]
    obj.driver.execute_script.assert_called_once()
    assert obj.driver.execute_script.call_args.args[1] is rows
    obj.table_row_in_view.assert_not_called()


def test_hidden_diagnostics_do_not_query_browser():
    obj = runner()
    row = Mock()
    with patch('ui.pages.federation_tool.should_log_message', return_value=False):
        obj.log_table_click_state('table', row, {}, 'before')
    assert not row.mock_calls
    assert not obj.driver.mock_calls


def test_faster_polling_keeps_original_timeout():
    from ui.pages.federation_tool import TimedWebDriverWait
    obj = runner()
    obj.config['performance'] = {'poll_interval': 0.15}
    wait = TimedWebDriverWait(obj, 60)
    assert wait._poll == 0.15
    assert wait._timeout == 60


def test_restored_target_is_clicked_without_unnecessary_wheel():
    obj = runner()
    obj.timeout = 0
    obj.config['performance'] = {'wait_for_rows': True}
    row = Mock(text='49')
    obj.visible_table_rows = Mock(side_effect=[[], [row]])
    obj.table_row_number_text = Mock(return_value=('49', 49))
    obj.scroll_virtual_table = Mock()
    assert obj.find_virtual_table_row_for_number({}, 49)[0] is row
    obj.scroll_virtual_table.assert_not_called()
    obj.table_row_number_text.assert_called_once_with(row, {})


def test_restored_view_scrolls_if_target_is_still_outside():
    obj = runner()
    obj.timeout = 0
    obj.config['performance'] = {'wait_for_rows': True}
    row, target = Mock(text='48'), Mock(text='49')
    obj.visible_table_rows = Mock(side_effect=[[], [row], [target]])
    obj.table_row_number_text = Mock(side_effect=lambda item, _: (item.text, int(item.text)))
    obj.scroll_virtual_table = Mock(return_value=True)
    assert obj.find_virtual_table_row_for_number({}, 49)[0] is target
    obj.scroll_virtual_table.assert_called_once()


def test_start_number_setting_round_trip(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    from ui.pages.federation_tool import SelectorConfigDialog

    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    source = Path(__file__).resolve().parents[1] / 'data/federation_selectors_invoice.json'
    config = json.loads(source.read_text(encoding='utf-8'))
    path = tmp_path / 'macro.json'
    path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    dialog = SelectorConfigDialog(None, path)
    assert dialog.start_number_spin.value() == 1
    dialog.start_number_spin.setValue(25)
    with patch('ui.pages.federation_tool.QMessageBox.information'):
        dialog.save()
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['start_number'] == 25
    assert saved['table_scroll'] == config['table_scroll']
    original = next(s for s in config['selectors'].values() if s.get('action') == 'select_text')
    selected = next(s for s in saved['selectors'].values() if s.get('action') == 'select_text')
    assert selected['dropdown_xpath'] == original['dropdown_xpath']
    assert selected['selection_method'] == 'keyboard'
    assert selected['max_key_steps'] == 10
    assert not any(s.get('action') == 'last_table_next_row_click' for s in saved['selectors'].values())
    dialog.close()
