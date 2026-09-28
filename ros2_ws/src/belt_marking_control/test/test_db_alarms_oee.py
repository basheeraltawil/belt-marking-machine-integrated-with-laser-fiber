import os

from belt_marking_control.core import CODES, CutMode, Job
from belt_marking_control.core.alarms import AlarmManager
from belt_marking_control.core.db import ProductionDb
from belt_marking_control.core.oee import OeeTracker


def test_recipes_roundtrip(tmp_path):
    db = ProductionDb(str(tmp_path / 'x.db'))
    j = Job(job_id='A', recipe='r1', cut_mode=CutMode.EVERY_N, cut_every_n=4, pitch_mm=33.3)
    assert db.save_recipe('r1', j.to_json(), 25.0, 'tech')
    assert not db.save_recipe('r1', j.to_json(), 25.0, 'tech', overwrite=False)
    back = Job.from_json(db.load_recipe('r1'))
    assert back == j
    assert [r['name'] for r in db.list_recipes()] == ['r1']
    assert db.delete_recipe('r1', 'admin')
    assert [a['action'] for a in db.audit_trail()][:2] == ['recipe_delete', 'recipe_save']


def test_users_pins(tmp_path):
    db = ProductionDb(str(tmp_path / 'x.db'))
    assert db.check_pin('9999')['role'] == 'admin'
    assert db.check_pin('0000') is None
    db.add_user('ali', 'technician', '4321')
    assert db.check_pin('4321') == {'name': 'ali', 'role': 'technician'}


def test_log_and_export(tmp_path):
    db = ProductionDb(str(tmp_path / 'x.db'))
    rid = db.job_started('J', 'r', '{}', 'op')
    db.log_event({'type': 'MARK', 'job_id': 'J', 'label': 0})
    db.job_ended(rid, 'COMPLETE', 1, 1, 0, 3.2)
    out = tmp_path / 'jobs.csv'
    assert db.export_csv('jobs', str(out)) == 1
    assert 'COMPLETE' in out.read_text()
    ro = ProductionDb(str(tmp_path / 'x.db'), read_only=True)
    assert ro.jobs()[0]['final_state'] == 'COMPLETE'
    assert os.path.exists(str(tmp_path / 'x.db'))


def test_alarm_manager_latching():
    events = []
    am = AlarmManager(on_change=lambda a, e: events.append((a.code, e)))
    am.condition(CODES['LOW_AIR'], True, 1.0)
    am.condition(CODES['LOW_AIR'], True, 1.1)            # no duplicate
    assert len(am.blocking()) == 1
    am.condition(CODES['LOW_AIR'], False, 2.0)
    assert not am.blocking() and CODES['LOW_AIR'] in am.alarms   # latched until ack
    assert am.ack(0, 'op') == 1
    assert not am.alarms
    assert [e for _, e in events] == ['raised', 'cleared', 'acknowledged']


def test_oee():
    o = OeeTracker()
    o.add_time('EXECUTE', 90, True)
    o.add_time('HELD', 10, True)
    o.add_time('IDLE', 1000, False)
    o.add_labels(80, 1.0)
    o.add_rejects(4)
    assert o.availability == 0.9
    assert abs(o.performance - 80 / 90) < 1e-9
    assert o.quality == 0.95
