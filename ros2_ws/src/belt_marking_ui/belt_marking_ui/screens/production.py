"""Production screen: start / hold / resume / stop / reset / clear, progress, counters."""

from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                             QVBoxLayout, QWidget)

from ..i18n import tr
from ..widgets import big_button, LightTower, Tile

# MachineCommand codes
RESET, HOLD, UNHOLD, STOP, ABORT, CLEAR = range(6)
LASER_ALARMS = {201, 203}


class ProductionScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        head = QHBoxLayout()
        self.title = QLabel('–')
        self.title.setProperty('role', 'title')
        head.addWidget(self.title, 1)
        self.tower = LightTower()
        head.addWidget(self.tower)
        left.addLayout(head)
        grid = QGridLayout()
        self.t_state = Tile(tr('lbl.state'))
        self.t_marks = Tile(tr('lbl.marks'))
        self.t_remaining = Tile(tr('lbl.remaining'))
        self.t_pieces = Tile(tr('lbl.pieces'))
        self.t_rejects = Tile(tr('lbl.rejects'))
        self.t_phase = Tile(tr('lbl.phase'))
        for i, t in enumerate([self.t_state, self.t_marks, self.t_remaining, self.t_pieces,
                               self.t_rejects, self.t_phase]):
            grid.addWidget(t, i // 3, i % 3)
        left.addLayout(grid)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        left.addWidget(self.progress)
        self.info = QLabel('')
        self.info.setProperty('role', 'small')
        left.addWidget(self.info)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        self.b_start = big_button(tr('btn.start'), 'start')
        self.b_hold = big_button(tr('btn.hold'), 'hold')
        self.b_resume = big_button(tr('btn.resume'), 'start')
        self.b_stop = big_button(tr('btn.stop'), 'stop')
        self.b_reset = big_button(tr('btn.reset'))
        self.b_clear = big_button(tr('btn.clear'))
        for b in (self.b_start, self.b_hold, self.b_resume, self.b_stop, self.b_reset,
                  self.b_clear):
            right.addWidget(b)
        root.addLayout(right, 1)
        self.b_start.clicked.connect(self._start)
        self.b_hold.clicked.connect(lambda: self._cmd(HOLD))
        self.b_resume.clicked.connect(self._resume)
        self.b_stop.clicked.connect(self._stop)
        self.b_reset.clicked.connect(lambda: self._cmd(RESET))
        self.b_clear.clicked.connect(lambda: self._cmd(CLEAR))
        self.on_state(None)

    # ---------------------------------------------------------------- actions
    def _cmd(self, command: int, option: str = ''):
        if not self.ctx.require('operator'):
            return
        req = self.ctx.bridge.request('command')
        req.command, req.option, req.user = command, option, self.ctx.user()
        self.ctx.bridge.call('command', req, self._on_reply)

    def _on_reply(self, res):
        if res is None:
            self.ctx.message('control node not reachable', True)
        elif not res.accepted:
            self.ctx.message(res.message, True)

    def _start(self):
        if not self.ctx.require('operator'):
            return
        self.ctx.window.show_screen('job')
        self.ctx.window.screens['job'].request_start()

    def _stop(self):
        if not self.ctx.require('operator'):
            return
        self.ctx.bridge.cancel_job()
        self._cmd(STOP)

    def _resume(self):
        st = self.ctx.state
        option = ''
        if st is not None and any(a.code in LASER_ALARMS for a in st.active_alarms):
            box = QMessageBox(self)
            box.setText(tr('msg.resume_laser'))
            retry = box.addButton(tr('btn.retry'), QMessageBox.AcceptRole)
            box.addButton(tr('btn.reject'), QMessageBox.RejectRole)
            box.exec_()
            option = 'retry' if box.clickedButton() is retry else 'reject'
        self._cmd(UNHOLD, option)

    # ---------------------------------------------------------------- updates
    def on_state(self, st):
        name = st.state_name if st else 'OFFLINE'
        self.title.setText(f'{st.job_id or "—"}   {st.recipe}' if st else 'control node offline')
        self.t_state.set_text(name)
        if st is None:
            for b in (self.b_start, self.b_hold, self.b_resume, self.b_stop, self.b_reset,
                      self.b_clear):
                b.setEnabled(False)
            return
        self.t_marks.set_text(f'{st.marks_done} / {st.marks_total}')
        self.t_remaining.set_text(max(0, st.marks_total - st.marks_done))
        self.t_pieces.set_text(st.pieces_cut)
        self.t_rejects.set_text(st.rejects)
        self.t_phase.set_text(st.phase or '–')
        self.progress.setValue(int(st.progress * 1000))
        self.progress.setFormat(f'{st.progress * 100:.0f} %')
        self.tower.set_lights(st.light_red, st.light_yellow, st.light_green)
        self.info.setText(f'{tr("lbl.mode")}: {tr("mode." + st.mode_name)}   '
                          f'{tr("lbl.belt_pos")}: {st.belt_position_mm:.1f} mm   '
                          f'OEE {st.oee * 100:.1f} %   '
                          f'{st.job_elapsed_s:.0f} s')
        s = name
        auto = st.mode_name in ('AUTO', 'SIMULATION')
        self.b_start.setEnabled(auto and s in ('IDLE', 'COMPLETE'))
        self.b_hold.setEnabled(s in ('EXECUTE', 'STARTING', 'UNHOLDING'))
        self.b_resume.setEnabled(s == 'HELD')
        self.b_stop.setEnabled(s not in ('STOPPED', 'STOPPING', 'ABORTED', 'ABORTING',
                                         'CLEARING'))
        self.b_reset.setEnabled(s in ('STOPPED', 'COMPLETE'))
        self.b_clear.setEnabled(s == 'ABORTED')
