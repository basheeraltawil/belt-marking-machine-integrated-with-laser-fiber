"""Offscreen UI tests with the ROS-free FakeBridge (skipped if PyQt5 is unusable)."""

import os
from types import SimpleNamespace

import pytest  # noqa: I100

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PyQt5.QtWidgets import QApplication
except Exception as exc:  # noqa: BLE001 - broken PyQt5 installs raise RuntimeError
    pytest.skip(f'PyQt5 not usable: {exc}', allow_module_level=True)

from belt_marking_control.core.config import ControlConfig  # noqa: E402, I100
from belt_marking_control.core.db import ProductionDb  # noqa: E402, I100
from belt_marking_ui.app import MainWindow  # noqa: E402, I100
from belt_marking_ui.context import Context  # noqa: E402, I100
from belt_marking_ui.ros_client import FakeBridge  # noqa: E402, I100
from belt_marking_ui.screens.manual import (  # noqa: E402, I100
    compute_steps_per_mm, save_calibration)

APP = QApplication.instance() or QApplication([])


def state(**kw):
    base = {'state_name': 'IDLE', 'mode_name': 'SIMULATION', 'use_sim': True, 'job_id': 'J',
            'recipe': 'r', 'phase': '', 'marks_done': 3, 'marks_total': 10, 'pieces_cut': 3,
            'rejects': 0, 'progress': 0.3, 'job_elapsed_s': 12.0, 'belt_position_mm': 180.0,
            'belt_speed_mm_s': 0.0, 'belt_width_mm': 25.0, 'total_marks': 100,
            'total_pieces': 90, 'knife_cycles': 95, 'laser_triggers': 100, 'belt_meters': 6.0,
            'uptime_s': 100.0, 'oee_availability': 0.9, 'oee_performance': 0.95,
            'oee_quality': 1.0, 'oee': 0.855, 'light_red': False, 'light_yellow': True,
            'light_green': False, 'buzzer': False, 'active_alarms': []}
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def win(tmp_path):
    db = ProductionDb(str(tmp_path / 'ui.db'))
    ctx = Context(FakeBridge(), db, ControlConfig(), use_sim=True)
    ctx.session.login('9999')                       # admin
    w = MainWindow(ctx)
    w.resize(800, 480)
    w.show()
    yield w
    w.ctx.window = None
    w.close()


def test_all_screens_render_at_800x480(win):
    win.ctx.bridge.state.emit(state())
    APP.processEvents()
    for key in win.screens:
        win.show_screen(key)
        APP.processEvents()
        assert win.stack.currentWidget() is win.areas[key]
    hint = win.minimumSizeHint()
    assert hint.width() <= 800 and hint.height() <= 480, hint
    assert 'IDLE' in win.lbl_state.text()
    prod = win.screens['production']
    assert prod.b_start.isEnabled() and not prod.b_resume.isEnabled()


def test_buttons_follow_state(win):
    win.ctx.bridge.state.emit(state(state_name='HELD', active_alarms=[SimpleNamespace(
        code=401, code_text='E-401', text='No belt', severity=2, active=True,
        acknowledged=False)]))
    APP.processEvents()
    prod = win.screens['production']
    assert prod.b_resume.isEnabled() and not prod.b_start.isEnabled()
    assert 'E-401' in win.lbl_alarm.text()


def test_job_validation_uses_controller_rules(win):
    job = win.screens['job']
    assert job.errors() == []
    job.fields['pitch_mm'].set_value(1.0)
    job._set('pitch_mm', 1.0)
    assert any('pitch' in e for e in job.errors())


def test_reset_command_sent(win):
    win.ctx.bridge.state.emit(state(state_name='STOPPED'))
    APP.processEvents()
    win.screens['production'].b_reset.click()
    names = [n for n, _ in win.ctx.bridge.calls]
    assert 'command' in names


def test_csv_export(win, tmp_path):
    out = win.screens['logs'].export(str(tmp_path))
    assert sorted(os.listdir(out)) == ['alarm_history.csv', 'audit.csv', 'jobs.csv',
                                       'production_log.csv']


def test_steps_per_mm_math(tmp_path):
    assert compute_steps_per_mm(69.0, 200.0, 197.0) == pytest.approx(70.0507, abs=1e-3)
    path = str(tmp_path / 'cal.yaml')
    save_calibration({'hardware': {'steps_per_mm': 70.05}}, path)
    save_calibration({'machine': {'knife_offset_mm': 55.5}}, path)
    import yaml
    data = yaml.safe_load(open(path))
    assert data == {'hardware': {'steps_per_mm': 70.05}, 'machine': {'knife_offset_mm': 55.5}}
