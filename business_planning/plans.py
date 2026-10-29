"""사업계획 계산 및 원자적 저장. UI와 독립적으로 사용한다."""
import copy
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path

from business_planning.minutes import atomic_json
from data_paths import runtime_directory

with Path(__file__).with_name('accounts.json').open(encoding='utf-8') as source:
    CONFIG = json.load(source)
CYCLES = CONFIG['annual_cycles']
ACCOUNTS = {}
for direction, label in [('income', '세입'), ('expense', '세출')]:
    for code, name in CONFIG[direction].items():
        ACCOUNTS[f'{direction}:{code}'] = dict(direction=direction, code=code, name=f'{label}-{name}')
        if direction == 'expense' and code in CONFIG['personnel_subdivisions']:
            for key, part in [('direct', '직접비'), ('indirect', '간접비')]:
                ACCOUNTS[f'{direction}:{code}:{key}'] = dict(
                    direction=direction, code=code, subdivision=key, name=f'{label}-{name}({part})')


def new_plan():
    return dict(version=1, id=uuid.uuid4().hex, category='', title='', goal='', details='',
                cycle='일간', frequency=1, period_years=1, accounts=[])


def number(value):
    text = str(value).strip()
    # No expressions, exponents or ambiguous comma placement in stored values.
    if not re.fullmatch(r'\d{1,12}(?:\.\d{1,4})?', text):
        raise ValueError('값은 0 이상의 숫자(정수 12자리, 소수 4자리 이내)로 입력하세요.')
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('숫자를 확인하세요.') from exc


def fmt(value):
    return format(Decimal(value), ',f').rstrip('0').rstrip('.') if '.' in str(value) else format(Decimal(value), ',f')


def annual_count(plan):
    frequency = plan['frequency']
    if type(frequency) is not int or not 1 <= frequency <= 10000 or plan['cycle'] not in CYCLES:
        raise ValueError('주기와 제공횟수(1~10,000)를 확인하세요.')
    if plan.get('period_years') != 1:
        raise ValueError('현재 사업기간은 1년만 지원합니다.')
    cycles = CYCLES[plan['cycle']]
    return None if cycles is None else cycles * frequency


def calculate_line(plan, line):
    count = annual_count(plan)
    if count is None:
        raise ValueError('수시·미정 사업은 정기 주기와 제공횟수를 정한 후 금액을 계산할 수 있습니다.')
    if line['account_id'] not in ACCOUNTS:
        raise ValueError('계정과목을 선택하세요.')
    if not line['factors'] or len(line['factors']) > 20:
        raise ValueError('계정과목마다 계산 항목을 1~20개 입력하세요.')
    values, labels = [], []
    for factor in line['factors']:
        if not factor['label'].strip():
            raise ValueError('계산 항목명을 입력하세요. 예: 입소자, 식비 단가')
        value = number(factor['value'])
        values.append(value)
        labels.append(f"{factor['label']} {fmt(value)}{factor.get('unit', '')}")
    with localcontext() as context:
        context.prec = 400
        amount = Decimal(count)
        for value in values:
            amount *= value
        if amount > Decimal('999999999999999'):
            raise ValueError('계정과목별 산출액이 허용 범위(999조 원)를 초과했습니다.')
        amount = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    formula = ' × '.join(labels + [f"{CYCLES[plan['cycle']]}({plan['cycle']}/년)",
                                  f"{plan['frequency']}회"])
    return amount, f'{formula} = {fmt(amount)}원'


def totals(plan):
    result = dict(income=Decimal(0), expense=Decimal(0))
    for line in plan['accounts']:
        amount, _ = calculate_line(plan, line)
        result[ACCOUNTS[line['account_id']]['direction']] += amount
    return result


def validate_plan(plan):
    try:
        if plan['version'] != 1 or not re.fullmatch(r'[a-f0-9]{32}', plan['id']):
            raise ValueError('지원하지 않는 사업계획 형식입니다.')
        for key in ('category', 'title', 'goal', 'details'):
            if not isinstance(plan[key], str) or not plan[key].strip():
                raise ValueError('구분, 사업명, 목표, 세부내용을 입력하세요.')
        annual_count(plan)
        if not isinstance(plan['accounts'], list):
            raise ValueError('계정과목 형식을 확인하세요.')
        totals(plan)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('사업계획 데이터 형식을 확인하세요.') from exc


class PlanStore:
    def __init__(self, directory=None):
        self.path = Path(directory or runtime_directory() / 'business_planning') / 'plans.json'

    def list(self):
        if not self.path.exists():
            return []
        try:
            with self.path.open(encoding='utf-8') as source:
                data = json.load(source)
            if data['version'] != 1 or not isinstance(data['plans'], list):
                raise ValueError('지원하지 않는 저장 형식입니다.')
            ids = set()
            for plan in data['plans']:
                validate_plan(plan)
                if plan['id'] in ids:
                    raise ValueError('중복 사업 ID입니다.')
                ids.add(plan['id'])
            return data['plans']
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('사업계획 저장 파일을 읽을 수 없습니다. 기존 파일은 보존됩니다.') from exc

    def save(self, plan):
        validate_plan(plan)
        records = self.list()
        record = copy.deepcopy(plan)
        record['updated_at'] = datetime.now().isoformat(timespec='seconds')
        records = [record if old['id'] == record['id'] else old for old in records]
        if not any(old['id'] == record['id'] for old in records):
            records.append(record)
        atomic_json(self.path, dict(version=1, plans=records))

    def delete(self, plan_id):
        records = self.list()
        atomic_json(self.path, dict(version=1, plans=[p for p in records if p['id'] != plan_id]))
