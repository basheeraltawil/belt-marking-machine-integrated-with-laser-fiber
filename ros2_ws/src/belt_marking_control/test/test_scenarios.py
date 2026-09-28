"""All industrial scenarios (docs/SCENARIOS.md) against the plant model, headless."""

import os

from belt_marking_control.scenarios import run_scenario, SCENARIOS
import pytest

SOAK_HOURS = float(os.environ.get('SOAK_HOURS', '2'))


@pytest.mark.parametrize('number', sorted(SCENARIOS))
def test_scenario(number):
    kwargs = {'hours': SOAK_HOURS} if number == 12 else {}
    r = run_scenario(number, **kwargs)
    failed = [d for d, ok in r.checks if not ok]
    assert r.checks, 'scenario made no checks'
    assert not failed, f'scenario {number} ({r.name}) failed: {failed}'
