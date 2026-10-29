import copy
import os
from decimal import Decimal

import pytest

from business_planning.plans import (
    ACCOUNTS, CYCLES, PlanStore, new_plan, calculate_line, annual_count, totals,
)


@pytest.fixture
def plan():
    value = new_plan()
    value.update(category='수급자관리', title='급식', goal='균형 잡힌 식사', details='식사 제공', frequency=3)
    value['accounts'] = [dict(id='food', account_id='expense:311', description='식비', factors=[
        dict(label='입소자', value='10', unit='명'), dict(label='식비 단가', value='4500', unit='원')])]
    return value


def test_food_example_and_separate_totals(plan):
    amount, formula = calculate_line(plan, plan['accounts'][0])
    assert amount == Decimal('49275000')
    assert '입소자 10명 × 식비 단가 4,500원 × 365(일간/년) × 3회 = 49,275,000원' == formula
    income = copy.deepcopy(plan['accounts'][0])
    income['account_id'] = 'income:113'
    plan['accounts'].extend([income, copy.deepcopy(plan['accounts'][0])])
    assert totals(plan) == dict(income=Decimal('49275000'), expense=Decimal('98550000'))


@pytest.mark.parametrize('cycle,count', [('일간',365), ('주간',52), ('월간',12), ('연간',1), ('분기',4), ('반기',2)])
def test_annual_frequency(plan, cycle, count):
    plan['cycle'] = cycle
    assert annual_count(plan) == count * 3


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '1e3', '4,500', '', '2*3', '0.12345'])
def test_invalid_factor(plan, value):
    plan['accounts'][0]['factors'][0]['value'] = value
    with pytest.raises(ValueError):
        totals(plan)


def test_round_per_line(plan):
    plan.update(cycle='연간', frequency=1)
    line = plan['accounts'][0]
    line['factors'] = [dict(label='단가', value='1.5', unit='원')]
    plan['accounts'].append(copy.deepcopy(line))
    assert totals(plan)['expense'] == 4


@pytest.mark.parametrize('cycle', ['수시', '미정'])
def test_unscheduled_plans_preserve_content_without_invented_counts(tmp_path, plan, cycle):
    plan['cycle'] = cycle
    assert annual_count(plan) is None
    with pytest.raises(ValueError, match='정기 주기'):
        totals(plan)
    plan['accounts'] = []
    store = PlanStore(tmp_path)
    store.save(plan)
    assert store.list()[0]['cycle'] == cycle
    assert store.list()[0]['details'] == plan['details']


def test_unscheduled_ui(app, tmp_path, plan):
    from ui.pages.business_plan_page import BusinessPlanDialog, BusinessPlanPage
    plan.update(cycle='수시', accounts=[])
    store = PlanStore(tmp_path)
    store.save(plan)
    dialog = BusinessPlanDialog(store, plan)
    assert not dialog.frequency.isEnabled()
    assert '산정하지 않음' in dialog.count.text()
    page = BusinessPlanPage(store)
    assert page.table.item(0, 4).text() == '미산정'
    dialog.cycle.setCurrentText('월간')
    assert dialog.frequency.isEnabled()
    assert '36회' in dialog.count.text()
    dialog.deleteLater()
    page.deleteLater()


def test_store_crud_and_preserve_on_failure(tmp_path, plan, monkeypatch):
    store = PlanStore(tmp_path)
    assert store.list() == []
    store.save(plan)
    restored = store.list()[0]
    assert restored['accounts'] == plan['accounts']
    plan['title'] = '수정'
    store.save(plan)
    assert len(store.list()) == 1 and store.list()[0]['title'] == '수정'
    second = copy.deepcopy(plan)
    second['id'] = new_plan()['id']
    store.save(second)
    original = store.path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr('business_planning.minutes.os.replace', lambda *_: (_ for _ in ()).throw(OSError('disk')))
        with pytest.raises(OSError):
            store.delete(plan['id'])
    assert store.path.read_bytes() == original
    store.delete(plan['id'])
    assert [p['id'] for p in store.list()] == [second['id']]


def test_corrupt_store_not_overwritten(tmp_path, plan):
    store = PlanStore(tmp_path)
    store.path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        store.save(plan)
    assert store.path.read_text(encoding='utf-8') == '{broken'


@pytest.fixture
def app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_ui_edit_restore_calculate_search_delete(app, tmp_path, plan, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ui.pages.business_plan_page import BusinessPlanDialog, BusinessPlanPage
    store = PlanStore(tmp_path)
    dialog = BusinessPlanDialog(store, plan)
    assert '49,275,000원' in dialog.summary.text()
    dialog.editors[0].add_factor(dict(label='조정', value='2', unit='배'))
    assert '98,550,000원' in dialog.summary.text()
    dialog.title.setText('식사 지원')
    dialog.save()
    page = BusinessPlanPage(store)
    assert page.table.rowCount() == 1
    restored = BusinessPlanDialog(store, store.list()[0])
    assert restored.title.text() == '식사 지원'
    assert restored.editors[0].factors.rowCount() == 3
    page.search.setText('없는 제목')
    assert page.table.rowCount() == 0
    page.search.clear()
    page.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.Yes)
    page.delete()
    assert store.list() == [] and page.table.rowCount() == 0
    for widget in (dialog, restored, page):
        widget.deleteLater()


def test_editor_save_failure_keeps_input_and_cancel_checks(app, tmp_path, plan, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ui.pages.business_plan_page import BusinessPlanDialog
    store = PlanStore(tmp_path)
    dialog = BusinessPlanDialog(store, plan)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(store, 'save', lambda _: (_ for _ in ()).throw(OSError('disk full')))
    dialog.title.setText('보존할 편집')
    dialog.save()
    assert warnings == ['disk full'] and dialog.title.text() == '보존할 편집'
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: QMessageBox.No)
    dialog.show()
    dialog.reject()
    assert dialog.isVisible()
    dialog.deleteLater()
