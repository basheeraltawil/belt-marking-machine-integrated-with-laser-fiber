import os
import random

from belt_marking_control.core.job import CutMode
from belt_marking_vision.anomaly import DriftDetector
from belt_marking_vision.assistant import DocsAssistant
from belt_marking_vision.inspector import MarkInspector, render_label
from belt_marking_vision.nl_job import parse_job_text
from belt_marking_vision.vision_qa_node import mark_center_x
import pytest

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs')


@pytest.mark.parametrize('kw,ok,reason', [
    ({}, True, ''), ({'weak': True}, False, 'low_contrast'),
    ({'missing': True}, False, 'no_mark'), ({'offset_px': 60}, False, 'offset')])
def test_inspector(kw, ok, reason):
    r = MarkInspector(use_tesseract=False).inspect(render_label(**kw))
    assert (r.ok, r.reason) == (ok, reason)


@pytest.mark.parametrize('text', ['A-1', 'AI1-0', 'AI1-1', 'AI1-11', 'ORDER-2026-000123'])
def test_short_and_long_texts_are_found(text):
    assert MarkInspector(use_tesseract=False).inspect(render_label(text)).ok


def test_inspector_text_check_with_injected_ocr():
    ins = MarkInspector(ocr=lambda img: 'BELT-2O26', use_tesseract=False)
    assert ins.inspect(render_label(), expected_text='BELT-2026').ok      # O vs 0 tolerated
    ins = MarkInspector(ocr=lambda img: 'XXXX', use_tesseract=False)
    assert ins.inspect(render_label(), expected_text='BELT-2026').reason == 'text_mismatch'


def test_mark_passes_camera_geometry():
    # label marked at belt coordinate 120 mm, 20 mm long; camera at 32 mm
    assert mark_center_x(feed_mm=142.0, belt_coord_mm=120.0, mark_len_mm=20.0) == 32.0


def test_drift_detector():
    rng = random.Random(0)
    base = [0.30 + rng.gauss(0, 0.01) for _ in range(150)]
    det = DriftDetector(baseline_n=100, window=30)
    assert not det.evaluate('knife_extend', base).drift
    slow = base + [0.40 + rng.gauss(0, 0.01) for _ in range(40)]
    res = det.evaluate('knife_extend', slow)
    assert res.drift and res.rel_change > 0.2 and 'slower' in res.message()
    assert det.evaluate('laser', base[:50]) is None                    # not enough data


def test_multivariate_detector_names_the_signal():
    from belt_marking_vision.anomaly import MultivariateDetector
    rng = random.Random(1)

    def series(knife):
        return {k: [v + rng.gauss(0, 0.005) for _ in range(300)]
                for k, v in (('knife_extend', knife), ('knife_retract', 0.3), ('laser', 2.0),
                             ('feed', 1.0))}
    det = MultivariateDetector().fit(series(0.3))
    assert det.anomalous_fraction(series(0.3)) < 0.1
    assert det.anomalous_fraction(series(0.36)) > 0.9               # +20 % knife time
    assert set().union(*det.evaluate(series(0.36))) == {'knife_extend'}


@pytest.mark.parametrize('text,qty,pitch,mode,n', [
    ('200 pieces of 30 mm belt, cut each', 200, 30.0, CutMode.EVERY, 1),
    ('50 marks every 60 mm, no cut', 50, 60.0, CutMode.NONE, 1),
    ('job A-77: 120 labels 40mm long, sets of 5', 120, 40.0, CutMode.EVERY_N, 5),
    ('order X12 30 adet 80 mm parti sonu', 30, 80.0, CutMode.END, 1),
])
def test_nl_job(text, qty, pitch, mode, n):
    job, notes = parse_job_text(text)
    assert (job.quantity, job.pitch_mm, job.cut_mode, job.cut_every_n) == (qty, pitch, mode, n)
    assert any('confirm' in x for x in notes)


def test_nl_job_width_not_taken_as_pitch():
    job, _ = parse_job_text('width 20 mm, 10 labels of 45 mm')
    assert (job.belt_width_mm, job.pitch_mm) == (20.0, 45.0)


def test_assistant_alarm_and_retrieval():
    a = DocsAssistant(DOCS)
    res = a.answer('what does E-401 mean?')
    assert 'fork sensor' in res['answer'] and 'RESUME' in res['answer']
    res = a.answer('how is the relay wired to the laser foot pedal?')
    assert any('ELECTRICAL' in s for s in res['sources'])
    assert not res['generated']                  # no LLM configured in tests
