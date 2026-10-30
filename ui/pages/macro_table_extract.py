"""브라우저 DOM 표 읽기와 값 전용 XLSX 저장. 로그인/UI와 독립적이다."""

from datetime import datetime
from pathlib import Path
import re
from uuid import uuid4

from excel_data_sort.exporter import export_excel
from excel_data_sort.models import Dataset


GRID_ROOT_SCRIPT = r"""
let root = arguments[0];
// A saved XPath may point at a body/row that is recycled during scrolling.
// Limit expansion to its own grid, never the enclosing page or another table.
for (let p = root; p && p !== document.body; p = p.parentElement) {
    if (p.matches('[role="grid"], [role="treegrid"]') || /(?:^|\s)Grid(?:\s|$)/.test(p.className || '')) {
        root = p;
        break;
    }
}
"""


TABLE_SCRIPT = GRID_ROOT_SCRIPT + r"""
const visible = el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    for (let p = el; p; p = p.parentElement) {
        const s = getComputedStyle(p);
        if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return false;
        const box = p.getBoundingClientRect();
        if (p !== el && /(hidden|auto|scroll|clip)/.test(s.overflowY) && (r.bottom <= box.top || r.top >= box.bottom)) return false;
        if (p !== el && /(hidden|auto|scroll|clip)/.test(s.overflowX) && (r.right <= box.left || r.left >= box.right)) return false;
    }
    return true;
};
const text = el => {
    const value = (el.innerText || '').replace(/\r/g, '').trim();
    if (value) return value;
    const images = [...el.querySelectorAll('img')].map(img => img.alt || img.title || '').filter(Boolean);
    return images.join(' ') || el.getAttribute('aria-label') || '';
};
const table = root.matches('table') ? root : root.querySelector('table');
if (table && visible(table)) {
    const rows = [];
    let header = false;
    const spans = new Map();
    for (const tr of table.rows) {
        if (!visible(tr)) continue;
        const values = [];
        let col = 0;
        const skipSpans = () => {
            while (spans.has(col)) {
                values[col] = '';
                const remaining = spans.get(col) - 1;
                if (remaining) spans.set(col, remaining); else spans.delete(col);
                col++;
            }
        };
        for (const cell of tr.cells) {
            if (!visible(cell)) continue;
            skipSpans();
            for (let i = 0; i < cell.colSpan; i++) {
                values[col] = i ? '' : text(cell);
                if (cell.rowSpan > 1) spans.set(col, cell.rowSpan - 1);
                col++;
            }
        }
        skipSpans();
        if (values.length) {
            if (!rows.length) header = !!tr.querySelector('th');
            rows.push(values);
        }
    }
    return {rows, header, mode: 'html', scope: 'rendered_dom'};
}
// Nexacro cells have nested :text elements. Keep one outer cell, including blanks.
const selector = '[role="gridcell"],[role="columnheader"],[role="cell"],[id*="cell_"]';
let candidates = [...root.querySelectorAll(selector)].filter(visible);
if (root.matches(selector)) candidates.unshift(root);
let cells = candidates.filter(el => !candidates.some(parent => parent !== el && parent.contains(el)));
let mode = 'grid';
if (!cells.length) {
    // Generic positioned div tables: use text leaves, never concatenate the whole table.
    cells = [...root.querySelectorAll('*')].filter(el => visible(el) && text(el) &&
        ![...el.children].some(child => visible(child) && text(child)));
    mode = 'positioned_text';
}
const items = cells.map(el => {
    const r = el.getBoundingClientRect();
    return {x: r.left, y: r.top, text: text(el), header: el.getAttribute('role') === 'columnheader' || /(?:head|header)/i.test(el.id)};
}).sort((a,b) => a.y - b.y || a.x - b.x);
const bands = [];
for (const item of items) {
    let band = bands.find(b => Math.abs(b.y - item.y) <= 4);
    if (!band) { band = {y: item.y, cells: []}; bands.push(band); }
    band.cells.push(item);
}
const xs = [];
for (const item of items) if (!xs.some(x => Math.abs(x - item.x) <= 4)) xs.push(item.x);
xs.sort((a,b) => a-b);
const rows = bands.map(b => {
    const row = Array(xs.length).fill('');
    for (const cell of b.cells.sort((a,b) => a.x-b.x)) {
        const index = xs.findIndex(x => Math.abs(x - cell.x) <= 4);
        row[index] = row[index] ? row[index] + '\n' + cell.text : cell.text;
    }
    return row;
});
let headerRows = 0;
for (const band of bands) {
    if (!band.cells.some(c => c.header)) break;
    headerRows++;
}
return {rows, header: headerRows > 0, header_rows: headerRows, mode, scope: 'rendered_dom'};
"""


SCROLL_SCRIPT = GRID_ROOT_SCRIPT + r"""
const direction = arguments[1];
const shown = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
};
const native = el => shown(el) && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1 &&
    /(auto|scroll)/.test(getComputedStyle(el).overflowY);
let scroller = [root, ...root.querySelectorAll('*')].find(native);
// An ordinary HTML table can be inside a native overflow wrapper.
if (!scroller && root.matches('table')) {
    for (let p = root.parentElement; p && p !== document.body; p = p.parentElement) {
        if (native(p)) { scroller = p; break; }
        if (p.matches('table,[role="dialog"]')) break;
    }
}
if (scroller) {
    const max = scroller.scrollHeight - scroller.clientHeight;
    const before = scroller.scrollTop;
    if (direction) scroller.scrollTop = direction < 0 ? 0 : Math.min(max, before + Math.max(24, scroller.clientHeight * 0.8));
    return {kind: 'native', position: scroller.scrollTop, top: scroller.scrollTop <= 1,
        bottom: scroller.scrollTop >= max - 0.01, max};
}
const bar = [...root.querySelectorAll('[role="scrollbar"], [id$=".vscrollbar"], [id$=".vscrollbar:container"]')]
    .find(el => shown(el) && el.getAttribute('aria-orientation') !== 'horizontal' && el.getBoundingClientRect().height > el.getBoundingClientRect().width);
if (!bar) return {kind: 'none', top: true, bottom: true};
let top = null, bottom = null, position = null;
if (bar.hasAttribute('aria-valuenow') && bar.hasAttribute('aria-valuemax')) {
    position = Number(bar.getAttribute('aria-valuenow'));
    top = position <= Number(bar.getAttribute('aria-valuemin') || 0);
    bottom = position >= Number(bar.getAttribute('aria-valuemax'));
} else {
    const thumb = bar.querySelector('[id$=".trackbar"], [id$=".thumb"], [role="slider"]');
    const dec = bar.querySelector('[id$=".decbutton"]');
    const inc = bar.querySelector('[id$=".incbutton"]');
    if (thumb && shown(thumb) && dec && inc) {
        const r = thumb.getBoundingClientRect();
        const start = dec.getBoundingClientRect().bottom, end = inc.getBoundingClientRect().top;
        position = r.top - start;
        top = r.top <= start + 1;
        bottom = r.bottom >= end - 0.01;
    }
}
const r = root.getBoundingClientRect();
return {kind: 'wheel', top, bottom, position,
    x: Math.round(Math.max(1, Math.min(innerWidth - 2, r.left + r.width / 2))),
    y: Math.round(Math.max(1, Math.min(innerHeight - 2, r.top + r.height / 2))),
    delta: 120};
"""


def merge_table_rows(existing, incoming):
    """Join overlapping viewport slices without removing legitimate equal rows."""
    for overlap in range(min(len(existing), len(incoming)), 0, -1):
        if existing[-overlap:] == incoming[:overlap]:
            return existing + incoming[overlap:]
    return existing + incoming


def collect_scrolled_table(read, move, settle, log, max_scrolls=500, on_progress=None):
    """Rewind to the start, then gather overlapping slices to the scrollbar end."""
    snapshot = read()
    if on_progress:
        on_progress(dict(snapshot))
    for direction in (-1, 1):
        unchanged = 0
        edge_confirmations = 0
        rows = []
        header = []
        for index in range(max_scrolls + 1):
            if direction == 1:
                page = snapshot['rows']
                if snapshot.get('header') and page:
                    if not header:
                        header = page[:1]
                    page = page[1:]
                rows = merge_table_rows(rows, page)
                if on_progress:
                    on_progress({**snapshot, 'rows': header + rows, 'header': bool(header), 'scope': 'partial_scrolled'})
                log(f"[table_scroll] 아래로 수집 {index}회, 누적 {len(rows)}행")
            edge = 'top' if direction < 0 else 'bottom'
            state = snapshot.get('scroll', {})
            if state.get(edge) is True:
                # Scrollbar geometry can reach the end before virtual rows are
                # replaced. Re-send downward scrolls and collect settled slices
                # until the bottom and row contents agree repeatedly.
                if direction < 0 or state.get('kind') == 'none' or edge_confirmations >= 3:
                    break
                previous = snapshot
                move(direction)
                snapshot = settle(previous)
                stable_edge = (snapshot.get('scroll', {}).get(edge) is True and
                               snapshot.get('rows') == previous.get('rows') and
                               snapshot.get('scroll', {}).get('position') == state.get('position'))
                edge_confirmations = edge_confirmations + 1 if stable_edge else 0
                log(f"[table_scroll] 마지막 행 확인 {edge_confirmations}/3")
                if index == max_scrolls:
                    raise ValueError("표 마지막 행 검증 한도를 초과했습니다. 부분 결과를 완료로 저장하지 않습니다.")
                continue
            edge_confirmations = 0
            if unchanged >= 3:
                if state.get(edge) is False:
                    raise ValueError(f"표 스크롤이 {edge}에 도달하기 전에 멈췄습니다. 부분 결과를 완료로 저장하지 않습니다.")
                log(f"[table_scroll] {edge}: 3회 연속 변화 없음으로 경계 확인")
                break
            if index == max_scrolls:
                raise ValueError(f"표 스크롤 {max_scrolls}회 한도를 초과했습니다. 부분 결과를 완료로 저장하지 않습니다.")
            previous = snapshot
            move(direction)
            snapshot = settle(previous)
            changed = (snapshot.get('rows') != previous.get('rows') or
                       snapshot.get('scroll', {}).get('position') != state.get('position'))
            unchanged = 0 if changed else unchanged + 1
        # The final rewind snapshot is the first downward page.
    return {**snapshot, 'rows': header + rows, 'header': bool(header), 'scope': 'scrolled'}


def table_dataset(result, name):
    rows = result.get("rows", [])
    if not rows or not any(any(str(value).strip() for value in row) for row in rows):
        raise ValueError("추출 영역에서 표 텍스트를 찾지 못했습니다. XPath를 확인하세요.")
    width = max(map(len, rows))
    rows = [[str(value) for value in row] + [""] * (width - len(row)) for row in rows]
    columns = rows.pop(0) if result.get("header") else [f"열 {i + 1}" for i in range(width)]
    if not rows:
        raise ValueError("추출한 표에 제목 이외의 데이터가 없습니다.")
    return Dataset(name=name, columns=columns, rows=rows)


class TableWorkbook:
    """One run owns one file, checkpointed atomically after every extracted table."""

    def __init__(self, output_dir, name):
        self.output_dir = Path(output_dir)
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:80] or "table"
        self.path = self.output_dir / f"{stem}_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}.xlsx"
        self.datasets = []
        self.batch_sheet_indices = {}

    def add(self, result, name):
        dataset = table_dataset(result, name)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        updated = [*self.datasets, dataset]
        export_excel(updated, self.path)
        self.datasets = updated
        return self.path, dataset.columns, dataset.rows

    def add_branch(self, result, name, table_key, branch_name):
        dataset = table_dataset(result, name)
        index = self.batch_sheet_indices.get(table_key)

        def identities(columns):
            counts = {}
            result = []
            for column in columns:
                label = ' '.join(column.split())
                counts[label] = counts.get(label, 0) + 1
                result.append((label, counts[label]))
            return result

        incoming_keys = identities(dataset.columns)
        columns = list(dataset.columns)
        old_rows = []
        if index is not None:
            previous = self.datasets[index]
            columns = list(previous.columns[1:])
            keys = identities(columns)
            for key, label in zip(incoming_keys, dataset.columns):
                if key not in keys:
                    keys.append(key)
                    columns.append(label)
            old_rows = [row + [''] * (len(columns) + 1 - len(row)) for row in previous.rows]
        keys = identities(columns)
        positions = {key: position for position, key in enumerate(keys)}
        rows = []
        for row in dataset.rows:
            aligned = [''] * len(columns)
            for key, value in zip(incoming_keys, row):
                aligned[positions[key]] = value
            rows.append([str(branch_name), *aligned])
        combined = Dataset(name=self.datasets[index].name if index is not None else name,
                           columns=['지점명', *columns], rows=old_rows + rows)
        updated = list(self.datasets)
        if index is None:
            index = len(updated)
            updated.append(combined)
        else:
            updated[index] = combined
        self.output_dir.mkdir(parents=True, exist_ok=True)
        export_excel(updated, self.path)
        self.datasets = updated
        self.batch_sheet_indices[table_key] = index
        return self.path, combined.columns, rows



def save_extracted_table(result, output_dir, name):
    return TableWorkbook(output_dir, name).add(result, name)


def table_wheel_events(snapshot, direction):
    """Leave several rows of overlap; rewind may use a larger burst."""
    if direction < 0:
        return 8
    count = len(snapshot.get('rows', [])) - int(bool(snapshot.get('header')))
    return max(1, min(6, (count - 3) // 4))


def normalize_table_headers(result):
    """Flatten leading header bands while retaining every data row and column."""
    count = int(result.get('header_rows', int(bool(result.get('header')))))
    rows = result.get('rows', [])
    if count <= 1:
        return result
    headers = rows[:count]
    width = max((len(row) for row in headers), default=0)
    columns = []
    for index in range(width):
        labels = []
        for row in headers:
            value = str(row[index]).strip() if index < len(row) else ''
            if value and value not in labels:
                labels.append(value)
        columns.append(' / '.join(labels))
    return {**result, 'header_rows': 1, 'header': True, 'rows': [columns] + rows[count:]}
