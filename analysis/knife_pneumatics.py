"""Knife cylinder: force, air consumption, timing budget.

    extend force    F_ext = p * pi*D^2/4
    retract force   F_ret = p * pi*(D^2 - d^2)/4          (rod side)
    free air / cycle  V = (A_ext + A_ret) * stroke * (p + p_atm) / p_atm
    air flow          Q = V * cycles_per_hour

The cylinder bore/rod/stroke of the installed knife are not documented (ASSUMPTIONS
A-20..A-26). The values below are EXAMPLES; replace them with the nameplate data.

Run:  python3 analysis/knife_pneumatics.py
"""

import math

P_ATM = 1.013  # bar

EXAMPLE = {'bore_mm': 16.0, 'rod_mm': 6.0, 'stroke_mm': 120.0, 'pressure_bar': 5.0}


def forces(bore_mm, rod_mm, pressure_bar):
    a_ext = math.pi * bore_mm ** 2 / 4            # mm^2
    a_ret = math.pi * (bore_mm ** 2 - rod_mm ** 2) / 4
    p = pressure_bar * 0.1                        # bar -> N/mm^2 (MPa)
    return p * a_ext, p * a_ret, a_ext, a_ret


def free_air_per_cycle_l(a_ext, a_ret, stroke_mm, pressure_bar):
    v_mm3 = (a_ext + a_ret) * stroke_mm * (pressure_bar + P_ATM) / P_ATM
    return v_mm3 / 1e6


def main():
    e = EXAMPLE
    f_ext, f_ret, a_ext, a_ret = forces(e['bore_mm'], e['rod_mm'], e['pressure_bar'])
    v = free_air_per_cycle_l(a_ext, a_ret, e['stroke_mm'], e['pressure_bar'])
    print(f'example cylinder Ø{e["bore_mm"]:.0f}/{e["rod_mm"]:.0f} mm, stroke '
          f'{e["stroke_mm"]:.0f} mm at {e["pressure_bar"]} bar')
    print(f'  extend force  {f_ext:6.0f} N   (theoretical, no friction)')
    print(f'  retract force {f_ret:6.0f} N')
    print(f'  free air      {v:6.2f} L per cut cycle')
    for cph in (300, 600, 1200):
        print(f'  {cph:5d} cuts/h -> {v * cph / 60:5.1f} L/min average air demand')
    print('\npressure needed for a required force F (bore 16 mm):')
    for f in (50, 80, 100):
        print(f'  {f:4d} N -> {f / (math.pi * 16 ** 2 / 4) * 10:.1f} bar')
    print('\ntiming budget per cut (controller):  extend <= 1.5 s timeout, dwell 0.1 s, '
          'retract <= 1.5 s; normal stroke 0.2-0.4 s (flow controls)')


if __name__ == '__main__':
    main()
