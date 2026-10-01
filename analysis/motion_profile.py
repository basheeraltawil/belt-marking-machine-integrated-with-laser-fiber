"""Trapezoidal feed moves and the speed limit of the stepper drive.

    accelerate to v, cruise, decelerate (acceleration a, distance d):
      d >= v^2/a :  t = d/v + v/a                     (trapezoid)
      d <  v^2/a :  t = 2*sqrt(d/a),  v_peak = sqrt(a*d)   (triangle)
    step rate limit (AccelStepper on a 16 MHz AVR): f_max ~ 4000 steps/s
      v_max = f_max / s  = 4000 / 69 = 58 mm/s

Run:  python3 analysis/motion_profile.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from _paths import savefig  # noqa: E402
from belt_marking_control.core.planner import move_time  # noqa: E402  (same formula)

STEPS_PER_MM = 69.0
F_MAX = 4000.0
A = 100.0            # mm/s^2 (machine.yaml hardware.accel_mm_s2)


def velocity_profile(d: float, v: float, a: float, n: int = 300):
    t_total = move_time(d, v, a)
    t = np.linspace(0, t_total, n)
    v_peak = min(v, np.sqrt(a * d))
    t_acc = v_peak / a
    vel = np.minimum.reduce([a * t, np.full_like(t, v_peak), a * (t_total - t)])
    return t, np.clip(vel, 0, None), t_acc


def main():
    v_max = F_MAX / STEPS_PER_MM
    print(f'max feed speed from step rate: {v_max:.1f} mm/s')
    print(f'{"distance":>9} ' + ' '.join(f'{v:>8.0f}' for v in (15, 30, 45, 58)) +
          '   <- feed speed [mm/s], move time [s]')
    for d in (20, 40, 60, 106, 200):
        print(f'{d:>7} mm ' + ' '.join(f'{move_time(d, v, A):>8.2f}' for v in (15, 30, 45, 58)))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
    for v in (15, 30, 58):
        t, vel, _ = velocity_profile(60.0, v, A)
        ax1.plot(t, vel, label=f'v = {v} mm/s')
    ax1.set_title('60 mm feed (a = 100 mm/s²)')
    ax1.set_xlabel('t [s]')
    ax1.set_ylabel('v [mm/s]')
    ax1.legend()
    d = np.linspace(1, 300, 200)
    for v in (15, 30, 58):
        ax2.plot(d, [move_time(x, v, A) for x in d], label=f'v = {v} mm/s')
    ax2.set_title('move time vs distance')
    ax2.set_xlabel('d [mm]')
    ax2.set_ylabel('t [s]')
    ax2.legend()
    print('figure:', savefig(fig, 'motion_profile.png'))
    print('-> above ~30 mm/s short moves gain little: acceleration dominates.')


if __name__ == '__main__':
    main()
