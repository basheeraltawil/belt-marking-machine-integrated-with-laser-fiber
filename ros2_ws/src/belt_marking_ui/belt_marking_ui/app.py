"""Operator UI main window (800x480 touchscreen, kiosk capable).

    ros2 run belt_marking_ui operator_ui                  # normal (ROS)
    ros2 run belt_marking_ui operator_ui --ros-args -p kiosk:=true
    ros2 run belt_marking_ui operator_ui --demo           # no ROS, fake data (UI design)
"""

import os
import sys
import time

from belt_marking_control.core.db import ProductionDb
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from .context import Context, load_control_config
from .i18n import set_language, tr
from .screens.alarms_logs import AlarmsScreen, LogsScreen
from .screens.job import JobScreen, RecipesScreen
from .screens.manual import CalibrationScreen, ManualScreen
from .screens.production import ProductionScreen
from .screens.settings import SettingsScreen
from .widgets import Keypad, STYLE

SCREENS = [('production', 'nav.production', ProductionScreen),
           ('job', 'nav.job', JobScreen),
           ('recipes', 'nav.recipes', RecipesScreen),
           ('manual', 'nav.manual', ManualScreen),
           ('calibration', 'nav.calibration', CalibrationScreen),
           ('alarms', 'nav.alarms', AlarmsScreen),
           ('logs', 'nav.logs', LogsScreen),
           ('settings', 'nav.settings', SettingsScreen)]


class MainWindow(QMainWindow):

    def __init__(self, ctx: Context, kiosk: bool = False):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.setWindowTitle('Belt Marking Machine')
        self.setStyleSheet(STYLE)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        # status bar
        bar = QHBoxLayout()
        self.lbl_state = QLabel('OFFLINE')
        self.lbl_state.setProperty('role', 'title')
        self.lbl_alarm = QPushButton('')
        self.lbl_alarm.setMinimumWidth(40)
        self.lbl_alarm.setFlat(True)
        self.lbl_alarm.clicked.connect(lambda: self.show_screen('alarms'))
        self.btn_user = QPushButton(tr('btn.login'))
        self.btn_user.clicked.connect(self._user_clicked)
        self.lbl_clock = QLabel('')
        bar.addWidget(self.lbl_state)
        bar.addWidget(self.lbl_alarm, 1)
        bar.addWidget(self.btn_user)
        bar.addWidget(self.lbl_clock)
        root.addLayout(bar)
        body = QHBoxLayout()
        nav = QVBoxLayout()
        nav.setSpacing(3)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        self.stack = QStackedWidget()
        self.screens = {}
        self.areas = {}
        for i, (key, text_key, cls) in enumerate(SCREENS):
            b = QPushButton(tr(text_key))
            b.setProperty('role', 'nav')
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.show_screen(k))
            self.nav_group.addButton(b, i)
            self.nav_buttons[key] = b
            nav.addWidget(b)
            screen = cls(ctx)
            self.screens[key] = screen
            area = QScrollArea()          # keeps every screen usable at 800x480
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setWidget(screen)
            self.areas[key] = area
            self.stack.addWidget(area)
        nav.addStretch(1)
        body.addLayout(nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.toast = QLabel('')
        self.toast.setProperty('role', 'small')
        root.addWidget(self.toast)
        self.show_screen('production')

        b = ctx.bridge
        b.state.connect(self._on_state)
        b.io.connect(self._on_io)
        b.job_done.connect(self._on_job_done)
        self._last_state_t = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)
        if kiosk:
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.showFullScreen()
            QApplication.setOverrideCursor(Qt.BlankCursor)
        else:
            self.resize(800, 480)

    # ----------------------------------------------------------------- nav
    def show_screen(self, key: str):
        self.stack.setCurrentWidget(self.areas[key])
        self.nav_buttons[key].setChecked(True)
        self.ctx.session.touch()

    def retranslate(self):
        for key, text_key, _ in SCREENS:
            self.nav_buttons[key].setText(tr(text_key))
        self._update_user()

    def message(self, text: str, error: bool = False):
        self.toast.setText(text)
        self.toast.setStyleSheet('color: #ff7b72' if error else 'color: #9aa4ad')

    # ----------------------------------------------------------------- login
    def login_dialog(self, role: str = 'operator') -> bool:
        pad = Keypad(f'PIN ({role})', secret=True, decimals=0, parent=self)
        if pad.exec_() != QDialog.Accepted:
            return False
        ok = self.ctx.session.login(pad.value())
        if not ok:
            self.message('wrong PIN', True)
        self._update_user()
        return ok

    def _user_clicked(self):
        if self.ctx.session.user:
            self.ctx.session.logout()
            self._update_user()
        else:
            self.login_dialog()

    def _update_user(self):
        s = self.ctx.session
        self.btn_user.setText(f'{s.user} [{s.role}]  ⏏' if s.user else tr('btn.login'))

    # ----------------------------------------------------------------- data
    def _on_state(self, st):
        self.ctx.state = st
        self._last_state_t = time.monotonic()
        self.lbl_state.setText(f'{st.state_name} · {tr("mode." + st.mode_name)}'
                               + ('  [SIM]' if st.use_sim else ''))
        color = '#f85149' if st.light_red else '#d29922' if st.light_yellow else \
            '#3fb950' if st.light_green else '#e8eaed'
        self.lbl_state.setStyleSheet(f'color: {color}')
        if st.active_alarms:
            a = st.active_alarms[0]
            more = f' (+{len(st.active_alarms) - 1})' if len(st.active_alarms) > 1 else ''
            self.lbl_alarm.setText(f'⚠ {a.code_text} {a.text}{more}')
            self.lbl_alarm.setStyleSheet('color: #ff7b72; text-align: left')
        else:
            self.lbl_alarm.setText('')
        for s in self.screens.values():
            if hasattr(s, 'on_state'):
                s.on_state(st)

    def _on_io(self, io):
        self.ctx.io = io
        cal = self.screens['calibration']
        if cal.isVisible():
            cal.on_io(io)

    def _on_job_done(self, result):
        if result is None:
            self.message('job not accepted (state/mode?)', True)
        else:
            self.message(f'job finished: {result.message}  marks {result.marks_done}, '
                         f'pieces {result.pieces_cut}, rejects {result.rejects}',
                         not result.success)

    def _tick(self):
        self.lbl_clock.setText(time.strftime('%H:%M:%S'))
        if self.ctx.session.expired():
            self.ctx.session.logout()
            self._update_user()
            self.message('auto logout')
        if self._last_state_t and time.monotonic() - self._last_state_t > 3.0:
            self.lbl_state.setText('OFFLINE')
            self.lbl_state.setStyleSheet('color: #f85149')
            self.screens['production'].on_state(None)
            self._last_state_t = 0.0

    def closeEvent(self, ev):
        if self.ctx.window is self and QMessageBox.question(
                self, 'exit', 'Close the operator UI?') != QMessageBox.Yes:
            ev.ignore()
            return
        ev.accept()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    demo = '--demo' in argv
    app = QApplication([a for a in argv if a != '--demo'])
    kiosk, use_sim, lang = False, True, 'en'
    db_path = '~/.belt_marking/belt_marking.db'
    config_path = ''
    if demo:
        from .ros_client import FakeBridge
        bridge = FakeBridge()
    else:
        from .ros_client import RosBridge
        bridge = RosBridge(args=argv)
        n = bridge.node
        for name, default in (('kiosk', False), ('use_sim', False), ('language', 'en'),
                              ('db_path', db_path), ('config_path', '')):
            n.declare_parameter(name, default)
        kiosk = n.get_parameter('kiosk').value
        use_sim = n.get_parameter('use_sim').value
        lang = n.get_parameter('language').value
        db_path = n.get_parameter('db_path').value
        config_path = n.get_parameter('config_path').value
    if not config_path:
        try:
            from ament_index_python.packages import get_package_share_directory
            config_path = os.path.join(get_package_share_directory('belt_marking_bringup'),
                                       'config', 'machine.yaml')
        except Exception:  # noqa: BLE001 - bringup optional
            config_path = ''
    set_language(lang)
    ctx = Context(bridge, ProductionDb(db_path), load_control_config(config_path), use_sim,
                  config_path)
    win = MainWindow(ctx, kiosk=kiosk)
    win.show()
    rc = app.exec_()
    bridge.shutdown()
    return rc


if __name__ == '__main__':
    sys.exit(main())
