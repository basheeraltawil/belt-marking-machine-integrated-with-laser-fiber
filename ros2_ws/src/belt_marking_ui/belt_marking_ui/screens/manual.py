"""Manual operation and calibration screens (technician)."""

import os

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSpinBox, QVBoxLayout, QWidget)
import yaml

from ..i18n import tr
from ..widgets import big_button, NumField

MODE_AUTO, MODE_MANUAL, MODE_MAINT = 0, 1, 2
JOG_CHUNK_MM = 5.0
CALIB_FILE = os.path.expanduser('~/.belt_marking/calibration.yaml')


def set_mode(ctx, mode):
    if not ctx.require('technician'):
        return
    req = ctx.bridge.request('set_mode')
    req.mode, req.user = mode, ctx.user()
    ctx.bridge.call('set_mode', req, lambda r: ctx.message(r.message if r else 'offline',
                                                           r is None or not r.accepted))


class ManualScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        modes = QHBoxLayout()
        for mode, key in ((MODE_AUTO, 'mode.AUTO'), (MODE_MANUAL, 'mode.MANUAL'),
                          (MODE_MAINT, 'mode.MAINTENANCE')):
            b = QPushButton(tr(key))
            b.clicked.connect(lambda _=False, m=mode: set_mode(ctx, m))
            modes.addWidget(b)
        self.mode_label = QLabel('')
        modes.addWidget(self.mode_label)
        lay.addLayout(modes)

        grid = QGridLayout()
        self.jog_minus = big_button('◀◀ ' + tr('manual.jog'))
        self.jog_plus = big_button(tr('manual.jog') + ' ▶▶')
        grid.addWidget(self.jog_minus, 0, 0)
        grid.addWidget(self.jog_plus, 0, 1)
        self._jog_dir = 0
        self._jog_timer = QTimer(self)
        self._jog_timer.timeout.connect(self._jog_chunk)
        for b, d in ((self.jog_minus, -1), (self.jog_plus, 1)):
            b.pressed.connect(lambda d=d: self._jog_start(d))
            b.released.connect(self._jog_stop)
        self.feed = NumField(tr('manual.feed'), 60.0, -ctx.cfg.machine.jog_max_mm,
                             ctx.cfg.machine.jog_max_mm, 2)
        feed_btn = big_button(tr('manual.feed') + ' ▶')
        feed_btn.clicked.connect(lambda: self._jog(self.feed.value()))
        grid.addWidget(self.feed, 1, 0)
        grid.addWidget(feed_btn, 1, 1)
        cut = big_button(tr('manual.cut'), 'stop')
        cut.clicked.connect(self._cut)
        grid.addWidget(cut, 2, 0)
        laser_row = QHBoxLayout()
        self.station = QSpinBox()
        self.station.setRange(0, max(0, ctx.cfg.laser.num_stations - 1))
        self.station.setMinimumHeight(48)
        laser = big_button(tr('manual.laser'), 'hold')
        laser.clicked.connect(self._laser)
        laser_row.addWidget(self.station)
        laser_row.addWidget(laser, 1)
        grid.addLayout(laser_row, 2, 1)
        self.zair = big_button(tr('manual.zair'), checkable=True)
        self.zair.toggled.connect(lambda on: self._output('zair', on))
        home = big_button(tr('manual.home'))
        home.clicked.connect(self._home)
        grid.addWidget(self.zair, 3, 0)
        grid.addWidget(home, 3, 1)
        lay.addLayout(grid)
        self.result = QLabel('')
        self.result.setProperty('role', 'small')
        lay.addWidget(self.result)

    def on_state(self, st):
        if st is not None:
            self.mode_label.setText(f'{tr("lbl.mode")}: {tr("mode." + st.mode_name)}  '
                                    f'{st.state_name}  {st.belt_position_mm:.2f} mm')

    def _ok_mode(self) -> bool:
        st = self.ctx.state
        if st is None or (st.mode_name not in ('MANUAL', 'MAINTENANCE')
                          and st.state_name != 'HELD'):
            self.ctx.message(tr('msg.need_manual'), True)
            return False
        return self.ctx.require('technician')

    def _report(self, res):
        if res is None:
            self.result.setText('offline')
            return
        text = res.message
        for attr in ('extend_time_s', 'retract_time_s', 'busy_time_s'):
            if getattr(res, attr, 0):
                text += f'   {attr}: {getattr(res, attr):.3f}'
        self.result.setText(text)

    def _jog(self, distance):
        if not self._ok_mode():
            return
        req = self.ctx.bridge.request('jog')
        req.distance_mm, req.speed_mm_s = float(distance), 0.0
        self.ctx.bridge.call('jog', req, self._report)

    def _jog_start(self, direction):
        if not self._ok_mode():
            return
        self._jog_dir = direction
        self._jog_chunk()
        self._jog_timer.start(int(JOG_CHUNK_MM / self.ctx.cfg.machine.jog_speed_mm_s * 900))

    def _jog_chunk(self):
        if self._jog_dir:
            req = self.ctx.bridge.request('jog')
            req.distance_mm, req.speed_mm_s = self._jog_dir * JOG_CHUNK_MM, 0.0
            self.ctx.bridge.call('jog', req, None)

    def _jog_stop(self):
        self._jog_dir = 0
        self._jog_timer.stop()

    def _cut(self):
        if self._ok_mode():
            self.ctx.bridge.call('cut_now', self.ctx.bridge.request('cut_now'), self._report)

    def _laser(self):
        if not self._ok_mode():
            return
        req = self.ctx.bridge.request('trigger_laser')
        req.station, req.wait_done = self.station.value(), True
        self.ctx.bridge.call('trigger_laser', req, self._report)

    def _output(self, name, on):
        if not self.ctx.require('technician'):
            return
        req = self.ctx.bridge.request('set_output')
        req.output, req.state = name, bool(on)
        self.ctx.bridge.call('set_output', req, self._report)

    def _home(self):
        if self._ok_mode():
            self.ctx.bridge.call('home', self.ctx.bridge.request('home'), self._report)


IO_ROWS = [('estop_ok', 'E-stop OK'), ('safety_relay_ok', 'Safety relay'),
           ('door_closed', 'Laser door closed'), ('air_pressure_ok', 'Air pressure'),
           ('belt_present', 'Belt (fork sensor)'), ('knife_retracted', 'Knife retracted'),
           ('knife_extended', 'Knife extended'), ('knife_start', 'Knife start sensor'),
           ('driver_fault', 'Driver fault (ALM)'), ('stepper_enabled', 'Stepper enabled')]


class CalibrationScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        box = QGroupBox('steps/mm wizard')
        g = QGridLayout(box)
        self.nominal = NumField('nominal feed [mm]', 200.0, 10.0, 500.0, 1)
        self.measured = NumField('measured [mm]', 200.0, 1.0, 600.0, 2)
        self.current = NumField('current steps/mm', 69.0, 1.0, 2000.0, 4)
        run = QPushButton('1. feed nominal')
        run.clicked.connect(self._feed)
        calc = QPushButton('2. compute + save')
        calc.clicked.connect(self._compute)
        g.addWidget(QLabel('current'), 0, 0)
        g.addWidget(self.current, 0, 1)
        g.addWidget(QLabel('nominal'), 1, 0)
        g.addWidget(self.nominal, 1, 1)
        g.addWidget(run, 2, 0, 1, 2)
        g.addWidget(QLabel('measured'), 3, 0)
        g.addWidget(self.measured, 3, 1)
        g.addWidget(calc, 4, 0, 1, 2)
        left.addWidget(box)
        tests = QGroupBox('tests')
        t = QVBoxLayout(tests)
        knife = QPushButton('knife timing test (1 cycle)')
        knife.clicked.connect(lambda: self._call('cut_now'))
        laser = QPushButton('laser test (station 0, wait done)')
        laser.clicked.connect(self._laser)
        blade = QPushButton('reset blade counter (new blade)')
        blade.clicked.connect(lambda: self._call('reset_blade'))
        for b in (knife, laser, blade):
            t.addWidget(b)
        left.addWidget(tests)
        self.result = QLabel('')
        self.result.setWordWrap(True)
        left.addWidget(self.result)
        lay.addLayout(left, 1)
        io_box = QGroupBox('sensor check (live)')
        self.io_grid = QGridLayout(io_box)
        self.io_labels = {}
        for i, (key, text) in enumerate(IO_ROWS):
            self.io_grid.addWidget(QLabel(text), i, 0)
            lamp = QLabel('●')
            self.io_grid.addWidget(lamp, i, 1)
            self.io_labels[key] = lamp
        self.laser_lamp = QLabel('')
        self.io_grid.addWidget(QLabel('Laser busy'), len(IO_ROWS), 0)
        self.io_grid.addWidget(self.laser_lamp, len(IO_ROWS), 1)
        lay.addWidget(io_box, 1)

    def on_io(self, io):
        for key, lamp in self.io_labels.items():
            on = bool(getattr(io, key, False))
            bad = (key == 'driver_fault' and on) or (key != 'driver_fault' and not on
                                                     and key not in ('knife_extended',
                                                                     'knife_start'))
            color = '#ff7b72' if bad else '#3fb950' if on else '#6e7681'
            lamp.setStyleSheet(f'color: {color}; font-size: 22px')
        self.laser_lamp.setText(' '.join('●' if b else '○' for b in io.laser_busy))

    def _call(self, name):
        if not self.ctx.require('technician'):
            return
        self.ctx.bridge.call(name, self.ctx.bridge.request(name),
                             lambda r: self.result.setText(self._fmt(r)))

    def _laser(self):
        if not self.ctx.require('technician'):
            return
        req = self.ctx.bridge.request('trigger_laser')
        req.station, req.wait_done = 0, True
        self.ctx.bridge.call('trigger_laser', req, lambda r: self.result.setText(self._fmt(r)))

    @staticmethod
    def _fmt(r):
        if r is None:
            return 'offline'
        parts = [getattr(r, 'message', '')]
        for attr in ('extend_time_s', 'retract_time_s', 'busy_time_s'):
            if getattr(r, attr, 0):
                parts.append(f'{attr} = {getattr(r, attr):.3f}')
        return '   '.join(parts)

    def _feed(self):
        if not self.ctx.require('technician'):
            return
        req = self.ctx.bridge.request('jog')
        req.distance_mm, req.speed_mm_s = self.nominal.value(), 0.0
        self.ctx.bridge.call('jog', req, lambda r: self.result.setText(
            self._fmt(r) + '  → mark start/end on the belt and measure'))

    def _compute(self):
        if not self.ctx.require('technician'):
            return
        new = compute_steps_per_mm(self.current.value(), self.nominal.value(),
                                   self.measured.value())
        save_calibration({'hardware': {'steps_per_mm': round(new, 4)}})
        self.ctx.db.audit(self.ctx.user(), 'calibration_steps_per_mm',
                          {'old': self.current.value(), 'new': new,
                           'nominal': self.nominal.value(), 'measured': self.measured.value()})
        for name in ('hw_params', 'sim_params'):
            self.ctx.bridge.call(name, self.ctx.bridge.param_request('steps_per_mm', new), None)
        self.current.set_value(new)
        self.result.setText(f'steps/mm = {new:.4f} saved to {CALIB_FILE} '
                            '(applied live if supported, else after restart)')


def compute_steps_per_mm(current: float, nominal_mm: float, measured_mm: float) -> float:
    """If the belt moved `measured` for a commanded `nominal`, scale the steps/mm."""
    if measured_mm <= 0:
        raise ValueError('measured length must be > 0')
    return current * nominal_mm / measured_mm


def save_calibration(update: dict, path: str = CALIB_FILE) -> None:
    data = {}
    if os.path.exists(path):
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
    for section, values in update.items():
        data.setdefault(section, {}).update(values)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        yaml.safe_dump(data, fh, sort_keys=True)
