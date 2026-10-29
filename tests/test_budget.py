import copy
import os
from decimal import Decimal

import pytest

from business_planning.budget import aggregate_budget, GROUPS
from business_planning.plans import new_plan, PlanStore, ACCOUNTS


def sample(title='식사 지원', account='expense:311', value='4500'):
    plan = new_plan()
    plan.update(title=title, category='생활지원', goal='건강한 식사', details='하루 세 끼 제공', frequency=3)
    plan['accounts'] = [dict(account_id=account, factors=[dict(label='인원', value='10', unit='명'),
                                                       dict(label='단가', value=value, unit='원')])]
    return plan


def test_aggregation_groups_duplicate_lines_and_separates_directions():
    first = sample()
    first['accounts'].append(copy.deepcopy(first['accounts'][0]))
    second = sample('다른 사업')
    income = sample('식재료비 수입', 'income:113')
    original = copy.deepcopy([first, second, income])
    result = aggregate_budget(original)
    assert result['totals'] == dict(income=Decimal('49275000'), expense=Decimal('147825000'))
    row = next(r for r in result['rows'] if r['account_id'] == 'expense:311')
    assert len(row['contributions']) == 2
    assert len(row['contributions'][first['id']]['lines']) == 2
    assert row['guan'] == '사업비' and row['hang'] == '운영비'
    assert original == [first, second, income]
    for direction in ('income', 'expense'):
        assert sum(result['summary'][direction].values()) == result['totals'][direction]
    assert all(a['code'][:-1] in GROUPS[a['direction']] for a in ACCOUNTS.values())


def test_personnel_and_special_accounts_do_not_double_count():
    plans = [sample(account=key, value='0.05') for key in
             ['expense:111', 'expense:111:direct', 'expense:111:indirect', 'expense:1011', 'income:1111']]
    for plan in plans:
        plan.update(cycle='연간', frequency=1)
    result = aggregate_budget(plans)
    assert result['summary']['expense']['11'] == 3
    assert result['summary']['expense']['101'] == 1
    assert result['summary']['income']['111'] == 1


@pytest.fixture
def app():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_filters_buttons_modal_and_reload(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from ui.pages.budget_page import BudgetPage, BudgetPlanSummary
    store = PlanStore(tmp_path)
    plan = sample()
    store.save(plan)
    before = store.path.read_bytes()
    page = BudgetPage(store)
    assert page.tabs.tabText(0) == '예산총괄표'
    assert page.tabs.tabText(1) == '예산서내역'
    page.direction.setCurrentIndex(page.direction.findData('expense'))
    page.guan.setCurrentIndex(page.guan.findData('사업비'))
    page.hang.setCurrentIndex(page.hang.findData('운영비'))
    page.mok.setCurrentIndex(page.mok.findData('expense:311'))
    assert page.details.rowCount() == 1
    assert page.details.item(0, 5).text() == '49,275,000원'
    clicked = []
    monkeypatch.setattr(page, 'open_summary', lambda p, key: clicked.append((p['id'], key)))
    page.details.cellWidget(0, 6).findChild(QPushButton).click()
    assert clicked == [(plan['id'], 'expense:311')]
    modal = BudgetPlanSummary(plan, 'expense:311')
    assert '49,275,000원' in modal.content.toPlainText()
    assert plan['goal'] in modal.content.toPlainText()
    assert modal.content.isReadOnly()
    assert store.path.read_bytes() == before
    plan['frequency'] = 1
    store.save(plan)
    page.show()
    app.processEvents()
    assert page.details.item(0, 5).text() == '16,425,000원'
    store.delete(plan['id'])
    page.reload()
    assert page.details.item(0, 5).text() == '0원'
    assert page.details.cellWidget(0, 6) is None
    page.deleteLater()
    modal.deleteLater()


def test_empty_and_corrupt_data(app, tmp_path):
    from ui.pages.budget_page import BudgetPage
    store = PlanStore(tmp_path)
    page = BudgetPage(store)
    assert '전체 0개' in page.status.text()
    store.path.write_text('{broken', encoding='utf-8')
    page.reload()
    assert '불러오지 못했습니다' in page.status.text()
    assert page.details.rowCount() == 0
    assert all(t.rowCount() == 0 for t in page.summary_tables.values())
    assert store.path.read_text(encoding='utf-8') == '{broken'
    page.deleteLater()
