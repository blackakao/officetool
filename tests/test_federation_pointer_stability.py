from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException

from ui.pages import federation_tool as module


@pytest.mark.parametrize("interruption", ["overlay", "move", "disabled"])
def test_pointer_rechecks_after_hover_and_waits_through_interruption(monkeypatch, interruption):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner.timeout = 20
    owner._log = Mock()
    target = Mock()
    target.is_enabled.return_value = True
    state = {"ready": True, "rect": [10, 10, 100, 30]}
    changed = dict(state)
    if interruption == "move":
        changed["rect"] = [10, 50, 100, 30]
    else:
        changed["ready"] = False
        changed["hit"] = "loading" if interruption == "overlay" else "disabled"
    settled = changed if interruption == "move" else state
    states = [state, state, changed, settled, settled, settled]
    if interruption == "move":
        states.pop()
    clock = [0.0]
    actions = Mock()
    monkeypatch.setattr(module, "ActionChains", actions)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    calls = []

    def inspect(*args):
        calls.append(len(calls))
        # Only after the final inspection may a mouse-down be emitted.
        actions.return_value.click_and_hold.assert_not_called()
        return states[len(calls) - 1]

    owner.driver.execute_script.side_effect = inspect

    class PollWait:
        def __init__(self, owner, timeout):
            pass

        def until(self, condition):
            for index in range(len(states)):
                clock[0] = index * 0.5
                if condition(owner.driver):
                    return True
            raise TimeoutException()

    monkeypatch.setattr(module, "TimedWebDriverWait", PollWait)
    owner.pointer_click(target, "button")
    assert len(calls) == len(states)
    assert actions.return_value.move_to_element.call_count == 2
    actions.return_value.click_and_hold.assert_called_once_with()
    actions.return_value.click_and_hold.return_value.pause.return_value.release.return_value.perform.assert_called_once()


def test_permanent_overlay_after_hover_never_presses_button(monkeypatch):
    owner = module.InvoiceProcessor.__new__(module.InvoiceProcessor)
    owner.driver = Mock()
    owner.timeout = 20
    owner._log = Mock()
    target = Mock()
    state = {"ready": True, "rect": [10, 10, 100, 30]}
    owner.driver.execute_script.side_effect = [state, state, {"ready": False}, {"ready": False}]
    clock = [0.0]
    actions = Mock()
    monkeypatch.setattr(module, "ActionChains", actions)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    class PollWait:
        def __init__(self, owner, timeout):
            pass

        def until(self, condition):
            for index in range(4):
                clock[0] = index * 0.5
                if condition(owner.driver):
                    return True
            raise TimeoutException()

    monkeypatch.setattr(module, "TimedWebDriverWait", PollWait)
    with pytest.raises(TimeoutException):
        owner.pointer_click(target, "button")
    actions.return_value.move_to_element.assert_called_once_with(target)
    actions.return_value.click_and_hold.assert_not_called()
