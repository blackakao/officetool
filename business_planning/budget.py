"""저장된 사업의 산출내역을 관·항·목별로 집계한다."""
from decimal import Decimal

from business_planning.plans import ACCOUNTS, calculate_line, validate_plan

# 별표 1·2의 항 코드와 상위 관. 목 코드의 마지막 자리를 제외하면 항 코드이다.
GROUPS = {
    'income': {
        '11': ('입소자(이용자)부담금 수입', '입소(이용)비용수입'),
        '21': ('사업수입', '사업수입'), '31': ('과년도수입', '과년도수입'),
        '41': ('보조금수입', '보조금수입'), '51': ('후원금수입', '후원금수입'),
        '61': ('요양 급여수입', '요양 급여수입'), '71': ('차입금', '차입금'),
        '81': ('전입금', '전입금'), '91': ('이월금', '이월금'),
        '101': ('잡수입', '잡수입'),
        '111': ('적립금 및 준비금(특별회계)', '운영충당 적립금 및 환경개선준비금'),
    },
    'expense': {
        '11': ('사무비', '인건비'), '12': ('사무비', '업무추진비'), '13': ('사무비', '운영비'),
        '21': ('재산조성비', '시설비'), '31': ('사업비', '운영비'),
        '33': ('사업비', '○○사업비'), '34': ('사업비', '복지용구취득비'),
        '41': ('전출금', '전출금'), '51': ('과년도지출', '과년도지출'),
        '61': ('상환금', '부채상환금'), '71': ('잡지출', '잡지출'),
        '81': ('예비비 및 기타', '예비비 및 기타'),
        '91': ('적립금 및 준비금', '운영충당 적립금 및 환경개선준비금'),
        '101': ('적립금 및 준비금 지출(특별회계)', '운영충당 적립금 지출 및 환경개선준비금 지출'),
    },
}


def aggregate_budget(plans):
    rows = {}
    summary = {direction: {code: Decimal(0) for code in groups} for direction, groups in GROUPS.items()}
    totals = dict(income=Decimal(0), expense=Decimal(0))
    for key, account in ACCOUNTS.items():
        group = account['code'][:-1]
        guan, hang = GROUPS[account['direction']][group]
        rows[key] = dict(account_id=key, direction=account['direction'], group=group,
                         guan=guan, hang=hang, name=account['name'].split('-', 1)[1],
                         amount=Decimal(0), contributions={})
    for plan in plans:
        validate_plan(plan)
        for line in plan['accounts']:
            amount, formula = calculate_line(plan, line)
            row = rows[line['account_id']]
            row['amount'] += amount
            summary[row['direction']][row['group']] += amount
            totals[row['direction']] += amount
            contribution = row['contributions'].setdefault(plan['id'], dict(plan=plan, amount=Decimal(0), lines=[]))
            contribution['amount'] += amount
            contribution['lines'].append(dict(description=line.get('description', ''), formula=formula))
    return dict(rows=list(rows.values()), summary=summary, totals=totals)
