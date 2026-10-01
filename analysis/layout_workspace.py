"""Conveyor layout (the machine's 1-D workspace): positions, planner stops, constraints.

Coordinates: x along the belt, 0 = mark origin of laser station 0. A belt point with
belt coordinate s is at x = F - s when the belt has been fed by F.

    station i marks label k at        F = k*p + x_i
    knife cuts after label k at       F = (k+1)*p - lead + x_c
    cut modes need every station before the cut line:   x_i <= x_c - lead
    mark must fit the label and the laser field:        lead + L_mark <= p,  L_mark <= W_field
    camera sees the mark centre at    F = s + x_cam - L_mark/2
    motion blur at speed v, exposure t_e:   b = v * t_e   ->   t_e <= b_max / v

Run:  python3 analysis/layout_workspace.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from _paths import savefig  # noqa: E402
from belt_marking_control.core import ControlConfig, CutMode, Job, plan_job  # noqa: E402

LAYOUT = {'fork sensor': -350, 'drive roller': -120, 'laser 0': 0, 'QA camera': 32,
          'knife': 56, 'ejector': 146}


def main():
    cfg = ControlConfig()
    job = Job(job_id='L', quantity=4, pitch_mm=60, mark_length_mm=40, lead_mm=10,
              cut_mode=CutMode.EVERY)
    plan = plan_job(job, cfg)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5),
                                   gridspec_kw={'height_ratios': [1, 1.4]})
    for name, x in LAYOUT.items():
        ax1.axvline(x, c='tab:red' if name in ('laser 0', 'knife') else 'grey', lw=1)
        ax1.text(x, 0.55, name, rotation=90, ha='right', va='bottom', fontsize=8)
    ax1.axvspan(-25, 25, color='orange', alpha=0.2, label='laser field 50 mm')
    ax1.set_xlim(-400, 180)
    ax1.set_yticks([])
    ax1.set_title('Machine layout along the belt [mm]')
    ax1.legend(loc='upper left', fontsize=8)

    for stop in plan.stops:
        y = 1 if stop.fires else 0
        ax2.plot(stop.feed_mm, y if not stop.cut else 0, 'o',
                 c='tab:orange' if stop.fires and not stop.cut else 'tab:blue')
        if stop.fires:
            ax2.annotate(f'mark L{stop.fires[0].label}', (stop.feed_mm, 1), fontsize=8,
                         textcoords='offset points', xytext=(0, 6), ha='center')
        if stop.cut:
            ax2.plot(stop.feed_mm, 0, 's', c='tab:blue')
            ax2.annotate(f'cut after L{stop.cut.after_label}', (stop.feed_mm, 0), fontsize=8,
                         textcoords='offset points', xytext=(0, -14), ha='center')
    ax2.set_yticks([0, 1], ['knife', 'laser'])
    ax2.set_ylim(-0.6, 1.6)
    ax2.set_xlabel('commanded feed F since job start [mm]')
    ax2.set_title('Planner stops: pitch 60, lead 10, knife 56 → two stops per label')
    fig.tight_layout()
    print('figure:', savefig(fig, 'layout_and_stops.png'))
    print('stops F [mm]:', [round(s.feed_mm, 1) for s in plan.stops])

    lead = job.lead_mm
    print(f'\ncut modes: stations allowed up to x_c - lead = {56 - lead:.0f} mm downstream')
    print('-> a second laser at 150 mm needs the knife beyond 150 + lead (multi_laser.yaml '
          'uses 230 mm).')
    for v in (15, 30, 58):
        print(f'camera exposure for <= 0.1 mm blur at {v} mm/s: '
              f'{0.1 / v * 1000:.1f} ms')

    # feasible (pitch, lead) for a 40 mm mark, cut every piece
    p = np.linspace(20, 120, 200)
    fig2, ax = plt.subplots(figsize=(6, 3.5))
    ax.fill_between(p, 0, np.clip(p - 40, 0, None), alpha=0.3, label='lead + 40 mm ≤ pitch')
    ax.set_xlabel('pitch [mm]')
    ax.set_ylabel('lead [mm]')
    ax.set_title('Valid lead for a 40 mm mark')
    ax.legend()
    savefig(fig2, 'lead_feasibility.png')


if __name__ == '__main__':
    main()
