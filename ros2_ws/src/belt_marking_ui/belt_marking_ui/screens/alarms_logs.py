"""Alarms (active + history) and Logs / Statistics (jobs, OEE, CSV export to USB)."""

import datetime
import glob
import os

from belt_marking_control.core.alarms import CATALOG
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..i18n import tr
from ..widgets import big_button, Tile

SEV_COLORS = {0: '#6e7681', 1: '#d29922', 2: '#f85149', 3: '#ff0000'}


def fill_table(table: QTableWidget, headers, rows):
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem('' if value is None else str(value)))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)


class AlarmsScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        self.active = QTableWidget()
        self.active.setSelectionBehavior(QTableWidget.SelectRows)
        self.history = QTableWidget()
        tabs.addTab(self.active, 'active')
        tabs.addTab(self.history, 'history')
        tabs.currentChanged.connect(lambda i: self._load_history() if i == 1 else None)
        lay.addWidget(tabs, 1)
        self.remedy = QLabel('')
        self.remedy.setWordWrap(True)
        lay.addWidget(self.remedy)
        row = QHBoxLayout()
        ack = big_button(tr('btn.ack'))
        ack.clicked.connect(self._ack_selected)
        ack_all = big_button(tr('btn.ack_all'))
        ack_all.clicked.connect(lambda: self._ack(0))
        row.addWidget(ack)
        row.addWidget(ack_all)
        lay.addLayout(row)
        self.active.itemSelectionChanged.connect(self._show_remedy)
        self._codes = []

    def on_state(self, st):
        alarms = list(st.active_alarms) if st else []
        codes = [(a.code, a.active, a.acknowledged) for a in alarms]
        if codes == self._codes:
            return
        self._codes = codes
        fill_table(self.active, ['code', 'text', 'active', 'ack'],
                   [(a.code_text, a.text, 'yes' if a.active else 'no',
                     'yes' if a.acknowledged else '') for a in alarms])
        for r, a in enumerate(alarms):
            for c in range(4):
                self.active.item(r, c).setForeground(QColor(SEV_COLORS.get(a.severity)))

    def _show_remedy(self):
        rows = self.active.selectionModel().selectedRows()
        if rows:
            code = self._codes[rows[0].row()][0]
            d = CATALOG.get(code)
            self.remedy.setText(f'{d.code_text}: {d.remedy}' if d else '')

    def _ack_selected(self):
        rows = self.active.selectionModel().selectedRows()
        if rows:
            self._ack(self._codes[rows[0].row()][0])

    def _ack(self, code):
        if not self.ctx.require('operator'):
            return
        req = self.ctx.bridge.request('ack')
        req.code, req.user = code, self.ctx.user()
        self.ctx.bridge.call('ack', req, None)

    def _load_history(self):
        rows = self.ctx.db.alarm_history(300)
        fill_table(self.history, ['time', 'code', 'event', 'text', 'detail', 'user'],
                   [(r['ts'][:19], r['code_text'], r['event'], r['text'], r['detail'],
                     r['user']) for r in rows])


def usb_mounts():
    """Candidate USB stick mount points (Ubuntu auto-mount), else a local folder."""
    user = os.environ.get('USER', '')
    mounts = sorted(glob.glob(f'/media/{user}/*')) + sorted(glob.glob('/media/usb*'))
    return [m for m in mounts if os.path.isdir(m) and os.access(m, os.W_OK)]


class LogsScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        tiles = QHBoxLayout()
        self.t_oee = Tile('OEE')
        self.t_a = Tile('availability')
        self.t_p = Tile('performance')
        self.t_q = Tile('quality')
        self.t_total = Tile('total marks / pieces')
        self.t_belt = Tile('belt [m] / knife cycles')
        for t in (self.t_oee, self.t_a, self.t_p, self.t_q, self.t_total, self.t_belt):
            tiles.addWidget(t)
        lay.addLayout(tiles)
        self.jobs = QTableWidget()
        lay.addWidget(self.jobs, 1)
        row = QHBoxLayout()
        refresh = big_button('⟳')
        refresh.clicked.connect(self.refresh)
        export = big_button(tr('btn.export'))
        export.clicked.connect(self.export)
        row.addWidget(refresh)
        row.addWidget(export, 2)
        lay.addLayout(row)

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

    def on_state(self, st):
        if st is None:
            return
        self.t_oee.set_text(f'{st.oee * 100:.1f} %')
        self.t_a.set_text(f'{st.oee_availability * 100:.1f} %')
        self.t_p.set_text(f'{st.oee_performance * 100:.1f} %')
        self.t_q.set_text(f'{st.oee_quality * 100:.1f} %')
        self.t_total.set_text(f'{st.total_marks} / {st.total_pieces}')
        self.t_belt.set_text(f'{st.belt_meters:.1f} / {st.knife_cycles}')

    def refresh(self):
        rows = self.ctx.db.jobs(200)
        fill_table(self.jobs, ['job', 'recipe', 'started', 'state', 'marks', 'pieces',
                               'rejects', 'duration s', 'user'],
                   [(r['job_id'], r['recipe'], (r['started'] or '')[:19], r['final_state'],
                     r['marks'], r['pieces'], r['rejects'], f'{r["duration_s"] or 0:.0f}',
                     r['user']) for r in rows])

    def export(self, target_dir: str = ''):
        if not self.ctx.require('operator'):
            return None
        mounts = usb_mounts()
        base = target_dir or (mounts[0] if mounts else
                              os.path.expanduser('~/.belt_marking/exports'))
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        out = os.path.join(base, f'belt_marking_{stamp}')
        os.makedirs(out, exist_ok=True)
        n = 0
        for table in ('jobs', 'production_log', 'alarm_history', 'audit'):
            self.ctx.db.export_csv(table, os.path.join(out, f'{table}.csv'))
            n += 1
        self.ctx.db.audit(self.ctx.user(), 'export_csv', out)
        self.ctx.message(tr('msg.exported', n=n, path=out))
        return out
