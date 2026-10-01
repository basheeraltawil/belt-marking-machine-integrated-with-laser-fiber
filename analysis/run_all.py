"""Run every analysis script and regenerate analysis/figures/ (about 30 s)."""

import importlib
import time

SCRIPTS = ['feed_calibration', 'motion_profile', 'cycle_time_throughput', 'layout_workspace',
           'knife_pneumatics', 'oee_and_drift']

if __name__ == '__main__':
    for name in SCRIPTS:
        t0 = time.time()
        print(f'\n===== {name} =====')
        importlib.import_module(name).main()
        print(f'({time.time() - t0:.1f} s)')
