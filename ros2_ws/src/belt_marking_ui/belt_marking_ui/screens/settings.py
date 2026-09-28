"""Settings: language, users (admin), audit trail, simulation fault injection."""

from belt_marking_control.core.db import ROLES
from PyQt5.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                             QLabel, QListWidget, QPushButton, QTableWidget, QVBoxLayout,
                             QWidget)

from .alarms_logs import fill_table
from ..i18n import language, set_language
from ..widgets import big_button, Keypad

FAULTS = ['laser_no_response', 'laser_late', 'laser_weak_mark', 'knife_stuck_extend',
          'knife_stuck_retract', 'belt_runout', 'belt_slip', 'estop', 'door_open', 'low_air',
          'driver_fault', 'link_loss']
FAULT_VALUES = {'laser_late': 30.0, 'belt_runout': 30.0, 'belt_slip': 0.05}


class SettingsScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        lang = QGroupBox('language')
        ll = QHBoxLayout(lang)
        self.lang = QComboBox()
        self.lang.addItems(['en', 'tr'])
        self.lang.setCurrentText(language())
        self.lang.currentTextChanged.connect(self._language)
        ll.addWidget(self.lang)
        left.addWidget(lang)
        users = QGroupBox('users (admin)')
        ul = QVBoxLayout(users)
        self.users = QListWidget()
        ul.addWidget(self.users)
        row = QHBoxLayout()
        add = QPushButton('+ user')
        add.clicked.connect(self._add_user)
        rm = QPushButton('− user')
        rm.clicked.connect(self._remove_user)
        audit = QPushButton('audit trail')
        audit.clicked.connect(self._audit)
        for b in (add, rm, audit):
            row.addWidget(b)
        ul.addLayout(row)
        left.addWidget(users, 1)
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        self.audit_table = QTableWidget()
        self.audit_table.hide()
        right.addWidget(self.audit_table, 1)
        if ctx.use_sim:
            sim = QGroupBox('simulation: fault injection (technician)')
            g = QGridLayout(sim)
            for i, fault in enumerate(FAULTS):
                b = QPushButton(fault)
                b.setCheckable(True)
                b.toggled.connect(lambda on, f=fault: self._fault(f, on))
                g.addWidget(b, i // 2, i % 2)
            clear = big_button('clear all faults')
            clear.clicked.connect(lambda: self._fault('clear_all', True))
            g.addWidget(clear, len(FAULTS) // 2 + 1, 0, 1, 2)
            self.fault_box = sim
            right.addWidget(sim)
        info = QLabel(f'config: {ctx.config_path or "(defaults)"}\nDB: {ctx.db.path}')
        info.setProperty('role', 'small')
        info.setWordWrap(True)
        right.addWidget(info)
        lay.addLayout(right, 1)

    def showEvent(self, ev):
        self._load_users()
        super().showEvent(ev)

    def _language(self, lang):
        set_language(lang)
        self.ctx.message('language: ' + lang + ' (screens rebuild on restart)')
        if self.ctx.window is not None:
            self.ctx.window.retranslate()

    def _load_users(self):
        self.users.clear()
        for u in self.ctx.db.list_users():
            self.users.addItem(f'{u["name"]}  [{u["role"]}]')

    def _add_user(self):
        if not self.ctx.require('admin'):
            return
        name, ok = QInputDialog.getText(self, 'user', 'name')
        if not ok or not name.strip():
            return
        role, ok = QInputDialog.getItem(self, 'role', 'role', list(ROLES), 0, False)
        if not ok:
            return
        pad = Keypad('PIN (4-8 digits)', secret=True, decimals=0, parent=self)
        if not pad.exec_():
            return
        try:
            self.ctx.db.add_user(name.strip(), role, pad.value())
        except ValueError as exc:
            self.ctx.message(str(exc), True)
            return
        self.ctx.db.audit(self.ctx.user(), 'user_add', {'name': name, 'role': role})
        self._load_users()

    def _remove_user(self):
        item = self.users.currentItem()
        if item is None or not self.ctx.require('admin'):
            return
        name = item.text().split('  [')[0]
        if name == self.ctx.user():
            self.ctx.message('cannot remove the logged-in user', True)
            return
        self.ctx.db.delete_user(name)
        self.ctx.db.audit(self.ctx.user(), 'user_delete', name)
        self._load_users()

    def _audit(self):
        if not self.ctx.require('admin'):
            return
        rows = self.ctx.db.audit_trail(300)
        fill_table(self.audit_table, ['time', 'user', 'action', 'detail'],
                   [(r['ts'][:19], r['user'], r['action'], r['detail'][:120]) for r in rows])
        self.audit_table.show()

    def _fault(self, fault, on):
        if not self.ctx.require('technician'):
            return
        req = self.ctx.bridge.request('inject_fault')
        req.fault, req.enable = fault, bool(on)
        req.value, req.station = FAULT_VALUES.get(fault, 0.0), 0
        self.ctx.bridge.call('inject_fault', req, lambda r: self.ctx.message(
            r.message if r else 'sim/inject_fault not available', r is None))
        if fault == 'clear_all':
            for b in self.fault_box.findChildren(QPushButton):
                if b.isCheckable():
                    b.blockSignals(True)
                    b.setChecked(False)
                    b.blockSignals(False)
