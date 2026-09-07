import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from ui.pages.federation_tool import InvoiceProcessor


def processor(element):
    runner = InvoiceProcessor.__new__(InvoiceProcessor)
    runner.driver = Mock()
    runner.driver.find_element.return_value = element
    runner.timeout = 0
    runner.config = {}
    runner.status_callback = Mock()
    runner.pointer_click = Mock(side_effect=lambda element, key: element.click())
    return runner


def field(tag='div', text='', value=''):
    element = Mock()
    element.tag_name = tag
    element.text = text
    element.get_attribute.return_value = value
    element.find_elements.return_value = []
    element.is_displayed.return_value = True
    element.is_enabled.return_value = True
    return element


@pytest.mark.parametrize('tag,text,value,empty', [
    ('div', ' \u00a0 ', '', True),
    ('div', '계속', '', False),
    ('div', '퇴소', '', False),
    ('input', '', '계속', False),
    ('input', '', '', True),
])
def test_empty_field_condition(tag, text, value, empty):
    runner = processor(field(tag, text, value))
    assert runner.condition_result('check', {
        'by': 'xpath', 'value': '//field', 'action': 'field_empty',
    }) is empty


def test_visible_editor_value_takes_precedence():
    element = field(text='other text')
    editor = field('input', value='')
    editor.is_displayed.return_value = True
    element.find_elements.return_value = [editor]
    assert processor(element).field_text(element) == ''


@pytest.mark.parametrize('current,selects', [('', True), ('계속', False), ('퇴소', False)])
def test_invoice_branch_precedes_save(current, selects):
    config = json.loads((Path(__file__).resolve().parents[1] /
                         'data/federation_selectors_invoice.json').read_text(encoding='utf-8'))
    items = list(config['selectors'].items())
    start = next(i for i, (_, step) in enumerate(items) if step.get('action') == 'field_empty')
    end = next(i for i in range(start, len(items)) if items[i][1].get('type') == 'condition_end') + 1
    runner = processor(field(text=current))
    runner.run_selector_step = Mock()
    runner.run_workflow_items_once(items[start:end + 1])
    keys = [call.args[0] for call in runner.run_selector_step.call_args_list]
    select_key = next(key for key, step in items if step.get('action') == 'select_text')
    save_key = items[end][0]
    assert keys == ([select_key, save_key] if selects else [save_key])
    assert config['selectors'][select_key]['expected_value'] == '계속'


@pytest.mark.parametrize('applied', [True, False])
def test_custom_option_requires_value_to_be_applied(applied):
    element = field()
    option = field(text='계속')
    option.id = 'continue-option'
    runner = processor(element)
    popup = Mock()
    popup.find_elements.return_value = [option]
    runner.driver.find_elements.return_value = [popup]

    def click(target):
        if target is option and applied:
            element.text = '계속'

    option.click.side_effect = lambda: click(option)
    selector = {'by': 'xpath', 'value': '//field', 'expected_value': '계속'}
    if applied:
        assert runner.select_field_text('select', selector)
    else:
        with pytest.raises(TimeoutException, match='검증 실패'):
            runner.select_field_text('select', selector)


def test_missing_field_is_not_treated_as_empty():
    runner = processor(None)
    with pytest.raises(TimeoutException):
        runner.condition_result('check', {'by': 'xpath', 'value': '//field', 'action': 'field_empty'})


def test_dropdown_button_is_clicked_instead_of_field_container():
    element, button, option = field(), field(), field(text='계속')
    option.id = 'option'
    popup = Mock()
    popup.find_elements.return_value = [option]
    element.find_elements.side_effect = lambda by, value: [button] if 'dropbutton' in value else []
    runner = processor(element)
    runner.driver.find_elements.return_value = [popup]
    option.click.side_effect = lambda: setattr(element, 'text', '계속')
    assert runner.select_field_text('select', {'by': 'xpath', 'value': '//field', 'expected_value': '계속'})
    button.click.assert_called_once()
    element.click.assert_not_called()


def test_timing_logs_failure_and_fixed_wait():
    from unittest.mock import patch
    runner = processor(None)
    with pytest.raises(TimeoutException):
        runner.condition_result('empty_check', {'by': 'xpath', 'value': '//field', 'action': 'field_empty'})
    messages = [call.args[0] for call in runner.status_callback.call_args_list]
    assert any('step=empty_check kind=element_wait' in line and 'outcome=TimeoutException' in line for line in messages)
    assert any('kind=condition' in line and 'elapsed_ms=' in line for line in messages)
    with patch('ui.pages.federation_tool.time.sleep'):
        runner.sleep(0.3)
    assert 'requested_ms=300.0' in runner.status_callback.call_args.args[0]


def test_explicit_dropdown_xpath_is_used():
    element, button, option = field(), field(), field(text='계속')
    option.id = 'option'
    popup = Mock()
    popup.find_elements.return_value = [option]
    runner = processor(element)
    runner.driver.find_element.side_effect = lambda by, value: button if value == '//exact-button' else element
    runner.driver.find_elements.return_value = [popup]
    option.click.side_effect = lambda: setattr(element, 'text', '계속')
    assert runner.select_field_text('select', {
        'by': 'xpath', 'value': '//field', 'expected_value': '계속', 'dropdown_xpath': '//exact-button',
    })
    button.click.assert_called_once()
    element.click.assert_not_called()


def test_pointer_click_checks_hit_target_and_sends_mouse_sequence():
    from unittest.mock import patch
    runner = processor(field())
    target = field()
    runner.driver.execute_script.return_value = {'ready': True}
    with patch('ui.pages.federation_tool.ActionChains') as actions:
        InvoiceProcessor.pointer_click(runner, target, 'dropdown')
    actions.return_value.move_to_element.assert_called_once_with(target)
    actions.return_value.move_to_element.return_value.click_and_hold.assert_called_once()


def test_generation_waits_for_next_screen_after_pointer_click():
    runner = processor(field())
    runner.timeouts = {'long': 0}
    runner._run_selector_step('generate', {
        'type': 'element', 'action': 'pointer_click', 'by': 'xpath',
        'value': '//generate', 'expected_visible_xpath': '//next-screen',
    })
    runner.pointer_click.assert_called_once()
    assert runner.driver.find_element.call_args.args == ('xpath', '//next-screen')


def test_pointer_does_not_click_through_overlay():
    from unittest.mock import patch
    runner = processor(field())
    runner.driver.execute_script.return_value = {'ready': False, 'hit': 'loading-overlay'}
    with patch('ui.pages.federation_tool.ActionChains') as actions:
        with pytest.raises(TimeoutException):
            InvoiceProcessor.pointer_click(runner, field(), 'generate')
    actions.assert_not_called()


def test_generation_timeout_does_not_send_duplicate_click():
    runner = processor(field())
    runner.timeouts = {'long': 0}
    hidden = field()
    hidden.is_displayed.return_value = False
    runner.driver.find_element.side_effect = lambda by, value: hidden if value == '//next-screen' else field()
    with pytest.raises(TimeoutException):
        runner._run_selector_step('generate', {
            'type': 'element', 'action': 'pointer_click', 'by': 'xpath',
            'value': '//generate', 'expected_visible_xpath': '//next-screen',
        })
    runner.pointer_click.assert_called_once()


@pytest.mark.parametrize('reaches_target,commits', [(True, True), (False, False), (True, False)])
def test_keyboard_selection_stops_at_expected_and_verifies_commit(reaches_target, commits):
    from unittest.mock import patch
    from selenium.webdriver.common.keys import Keys
    element = field()
    runner = processor(element)
    sent = []
    def press(key):
        sent.append(key)
        if key == Keys.ARROW_DOWN:
            element.text = '계속' if reaches_target and sent.count(key) == 2 else '다른 항목'
        elif key == Keys.ENTER and not commits:
            element.text = ''
        return Mock()
    selector = {'by': 'xpath', 'value': '//field', 'expected_value': '계속',
                'selection_method': 'keyboard', 'max_key_steps': 3}
    with patch('ui.pages.federation_tool.ActionChains') as actions, patch('ui.pages.federation_tool.time.sleep'):
        actions.return_value.send_keys.side_effect = press
        if reaches_target and commits:
            assert runner.select_field_text('select', selector)
        else:
            with pytest.raises(TimeoutException):
                runner.select_field_text('select', selector)
    if reaches_target:
        assert sent == [Keys.ARROW_DOWN, Keys.ARROW_DOWN, Keys.ENTER]
    else:
        assert sent == [Keys.ARROW_DOWN] * 3
    runner.pointer_click.assert_called_once_with(element, 'select')
