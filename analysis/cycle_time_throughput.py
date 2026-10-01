"""Cycle time per label, throughput, and a check of the model against the simulation.

Per label (one laser station, cut every piece, knife offset not a multiple of the pitch,
so there are two stops per label: mark stop + cut stop):

    T = t_move(p - k) + t_move(k) + t_settle + t_laser + t_post + t_knife
    k = (x_c - lead) mod p          (distance mark stop -> cut stop)
    t_knife = t_extend + t_dwell + t_retract
    throughput = 3600 / T  [labels/h]

t_move is the trapezoidal move time (motion_profile.py). The planner (planner.py) uses
exactly this model for the OEE "ideal cycle time".

Run:  python3 analysis/cycle_time_throughput.py      (~10 s, runs short simulations)
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from _paths import savefig  # noqa: E402
from belt_marking_control.core import ControlConfig, CutMode, Job, plan_job, State  # noqa
from belt_marking_control.core.sim_harness import Harness  # noqa: E402


def simulated_cycle(job: Job, laser_s: float) -> float:
    h = Harness(dt=0.01)
    h.set_laser_time(laser_s)
    h.start(job)
    assert h.wait_state(State.COMPLETE, 3600)
    run = h.ctrl.last_run
    return (run.t_end - run.t_start) / job.quantity


def main():
    cfg = ControlConfig()
    print(f'{"pitch":>6} {"laser":>6} {"cut":>6} {"model [s]":>10} {"sim [s]":>8} '
          f'{"diff":>6} {"labels/h":>9}')
    for pitch, laser, cut in [(30, 0.5, CutMode.EVERY), (60, 0.5, CutMode.EVERY),
                              (60, 2.0, CutMode.EVERY), (60, 2.0, CutMode.NONE),
                              (120, 3.0, CutMode.EVERY_N)]:
        job = Job(job_id='A', quantity=20, pitch_mm=pitch,
                  mark_length_mm=min(pitch * 0.5, 40.0), lead_mm=pitch * 0.2,
                  cut_mode=cut, cut_every_n=5, laser_time_s=laser,
                  settle_s=0.05, feed_speed_mm_s=30.0)
        model = plan_job(job, cfg).ideal_cycle_s
        sim = simulated_cycle(job, laser)
        print(f'{pitch:>6} {laser:>6} {cut.name:>6} {model:>10.3f} {sim:>8.3f} '
              f'{(sim / model - 1) * 100:>5.1f}% {3600 / sim:>9.0f}')
    print('-> the simulation is a few % slower than the ideal model (control tick, laser '
          'start latency, done-signal polling). That gap is the OEE "performance" loss.')

    # throughput map from the model
    pitches = np.arange(20, 201, 10)
    lasers = np.arange(0.5, 6.01, 0.5)
    tput = np.array([[3600 / plan_job(Job(job_id='A', quantity=10, pitch_mm=float(p),
                                          mark_length_mm=min(p * 0.5, 40.0),
                                          lead_mm=p * 0.2,
                                          laser_time_s=float(t), settle_s=0.05,
                                          feed_speed_mm_s=30.0), cfg).ideal_cycle_s
                      for p in pitches] for t in lasers])
    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.contourf(pitches, lasers, tput, levels=15, cmap='viridis')
    fig.colorbar(im, label='labels / hour')
    ax.set_xlabel('pitch [mm]')
    ax.set_ylabel('laser marking time [s]')
    ax.set_title('Throughput, cut every piece, 30 mm/s')
    print('figure:', savefig(fig, 'throughput_map.png'))
    print('-> the laser time dominates: halving it helps more than doubling the feed speed.')


if __name__ == '__main__':
    main()
