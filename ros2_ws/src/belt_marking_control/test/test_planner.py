from belt_marking_control.core import ControlConfig, CutMode, Job, plan_job, Station, validate
from belt_marking_control.core.planner import cut_labels, move_time
import pytest


def job(**kw):
    base = {'job_id': 'T', 'quantity': 5, 'pitch_mm': 60.0, 'mark_length_mm': 40.0,
            'lead_mm': 10.0, 'cut_mode': CutMode.EVERY, 'laser_time_s': 1.0}
    base.update(kw)
    return Job(**base)


def test_continuous_one_stop_per_label():
    plan = plan_job(job(cut_mode=CutMode.NONE, quantity=50), ControlConfig())
    assert len(plan.stops) == 50
    assert [s.feed_mm for s in plan.stops[:3]] == [0.0, 60.0, 120.0]
    assert all(s.cut is None for s in plan.stops)
    assert plan.total_cuts == 0


def test_cut_every_piece_positions():
    cfg = ControlConfig()
    plan = plan_job(job(quantity=3), cfg)
    cuts = [s for s in plan.stops if s.cut]
    # cut after label k at (k+1)*60 - 10 + 56
    assert [c.feed_mm for c in cuts] == [106.0, 166.0, 226.0]
    assert [c.cut.belt_coord_mm for c in cuts] == [50.0, 110.0, 170.0]
    assert plan.total_cuts == 3


def test_merge_when_knife_offset_is_pitch_multiple():
    cfg = ControlConfig()
    cfg.machine.knife_offset_mm = 70.0          # 70 - lead 10 = 60 = pitch
    plan = plan_job(job(quantity=4), cfg)
    # fires at 0,60,120,180; cuts at 120,180,240,300 -> merged into 6 stops
    assert [s.feed_mm for s in plan.stops] == [0.0, 60.0, 120.0, 180.0, 240.0, 300.0]
    assert plan.stops[2].fires and plan.stops[2].cut.after_label == 0


def test_cut_every_n_and_end():
    j = job(quantity=12, cut_mode=CutMode.EVERY_N, cut_every_n=5)
    assert cut_labels(j) == [4, 9, 11]
    plan = plan_job(j, ControlConfig())
    assert [s.cut.labels_in_piece for s in plan.stops if s.cut] == [5, 5, 2]
    assert cut_labels(job(quantity=7, cut_mode=CutMode.END)) == [6]


def test_initial_trim():
    plan = plan_job(job(quantity=2, initial_trim_cut=True), ControlConfig())
    first_cut = next(s for s in plan.stops if s.cut)
    assert first_cut.cut.trim and first_cut.feed_mm == 46.0
    assert plan.total_cuts == 2


def test_two_stations_offsets_and_delays():
    cfg = ControlConfig()
    cfg.laser.num_stations = 2
    cfg.laser.station_offsets_mm = [0.0, 150.0]
    cfg.laser.station_delays_s = [0.0, 0.5]
    cfg.laser.station_enabled = [True, True]
    j = job(quantity=4, cut_mode=CutMode.NONE)
    plan = plan_job(j, cfg)
    fires = [(s.feed_mm, f.station, f.label) for s in plan.stops for f in s.fires]
    assert (150.0, 1, 0) in fires and (210.0, 1, 1) in fires
    assert sum(1 for f in fires if f[1] == 1) == 4
    assert plan.final_feed_mm == 3 * 60 + 150


def test_validation_limits_and_station_past_knife():
    cfg = ControlConfig()
    assert validate(job(), cfg) == []
    errs = validate(job(pitch_mm=1.0, belt_width_mm=500), cfg)
    assert any('pitch' in e for e in errs) and any('belt width' in e for e in errs)
    j = job(stations=[Station(True, 0.0, 0.0), Station(True, 100.0, 0.0)])
    cfg.laser.num_stations = 2
    cfg.laser.station_offsets_mm = [0.0, 100.0]
    cfg.laser.station_delays_s = [0.0, 0.0]
    cfg.laser.station_enabled = [True, True]
    assert any('past the cut line' in e for e in validate(j, cfg))
    j.cut_mode = CutMode.NONE
    assert validate(j, cfg) == []


def test_mark_must_fit_in_label():
    errs = validate(job(mark_length_mm=55, lead_mm=10), ControlConfig())
    assert any('mark length' in e or 'lead' in e for e in errs)


@pytest.mark.parametrize('d,v,a,expected', [(0, 10, 100, 0.0), (100, 10, 100, 10.1),
                                            (1, 10, 100, 0.2)])
def test_move_time(d, v, a, expected):
    assert move_time(d, v, a) == pytest.approx(expected, abs=1e-6)
