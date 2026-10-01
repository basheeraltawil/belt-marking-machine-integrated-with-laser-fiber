"""Feed scale (steps/mm), position resolution and the calibration correction.

    steps/mm      s = (200 * u) / (pi * D * i)      u = micro-steps, D = roller diameter,
                                                    i = gear ratio (1 = direct drive)
    resolution    r = 1 / s  [mm per step]
    calibration   s_new = s_old * L_commanded / L_measured
    error         e(L) = L * (dD / D)               diameter error -> length error

Run:  python3 analysis/feed_calibration.py
"""

import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

from _paths import savefig  # noqa: E402

FULL_STEPS = 200          # 1.8 deg NEMA 23
LEGACY_STEPS_PER_MM = 69.0


def steps_per_mm(microsteps: int, roller_d_mm: float, gear: float = 1.0) -> float:
    return FULL_STEPS * microsteps / (math.pi * roller_d_mm * gear)


def roller_for(steps_mm: float, microsteps: int, gear: float = 1.0) -> float:
    """Roller diameter that gives `steps_mm` with a micro-step setting."""
    return FULL_STEPS * microsteps / (math.pi * steps_mm * gear)


def corrected(s_old: float, commanded_mm: float, measured_mm: float) -> float:
    return s_old * commanded_mm / measured_mm


def main():
    print('Which hardware matches the legacy 69 steps/mm? (direct drive)')
    print(f'{"micro-steps":>12} {"roller D [mm]":>14} {"resolution [mm]":>16}')
    for u in (1, 2, 4, 8, 16, 32, 64):
        print(f'{u:>12} {roller_for(LEGACY_STEPS_PER_MM, u):>14.1f} '
              f'{1 / LEGACY_STEPS_PER_MM:>16.4f}')
    print('-> plausible: 1/32 with a ~29.5 mm roller, or 1/64 with ~59 mm. '
          'Check the DM542 DIP switches and measure the roller (ASSUMPTIONS A-01, A-05).')

    s_new = corrected(69.0, 200.0, 197.0)
    print(f'\nCalibration example: 200 mm commanded, 197 mm measured -> '
          f'{s_new:.3f} steps/mm ({(s_new / 69 - 1) * 100:+.2f} %)')

    # length error over one label for roller diameter tolerances
    fig, ax = plt.subplots(figsize=(6, 3.5))
    lengths = range(10, 501, 10)
    for tol in (0.05, 0.1, 0.2):          # mm on a 29.5 mm roller
        ax.plot(lengths, [L * tol / 29.5 for L in lengths], label=f'ΔD = {tol} mm')
    ax.axhline(1 / 69.0, ls='--', c='grey', label='1 step (0.0145 mm)')
    ax.set_xlabel('feed length L [mm]')
    ax.set_ylabel('length error [mm]')
    ax.set_title('Uncalibrated error e = L·ΔD/D (D = 29.5 mm)')
    ax.legend()
    print('figure:', savefig(fig, 'feed_error.png'))


if __name__ == '__main__':
    main()
