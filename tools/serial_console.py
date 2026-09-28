#!/usr/bin/env python3
"""Interactive serial test console for the Arduino firmware (I/O check at commissioning).

    python3 tools/serial_console.py /dev/belt_arduino
    python3 tools/serial_console.py --virtual        # against the virtual firmware

Commands:  info | status | enable 0|1 | move <mm> [speed] | jog <+1|-1> <ms> | stop [quick]
           out <name> 0|1 | pulse <name> <ms> | zero | reset | watch | help | quit
Outputs:   knife_extend knife_retract zair dc_motor laser_0..3 light_red light_yellow
           light_green buzzer
A heartbeat is sent automatically every 100 ms while the console runs.
"""

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src',
                                'belt_marking_hardware'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src',
                                'belt_marking_laser'))

from belt_marking_hardware.firmware_client import (FirmwareClient, pipe_pair,  # noqa: E402
                                                   SerialTransport, VirtualFirmware)


def print_status(cl):
    s = cl.snapshot()
    ins = [n for n in ('estop_ok', 'door_closed', 'safety_relay_ok', 'air_pressure_ok',
                       'belt_present', 'knife_extended', 'knife_retracted', 'knife_start',
                       'driver_fault', 'home_sensor') if getattr(s, n)]
    outs = [n for n, v in s.outputs.items() if v]
    print(f'link={s.link_ok} pos={s.position_mm:.2f} mm ({s.position_steps} steps) '
          f'v={s.velocity_mm_s:.1f} moving={s.moving} id={s.motion_id} '
          f'enabled={s.stepper_enabled} faults=0x{s.fault_flags:02x}')
    print(f'  inputs ON : {" ".join(ins)}  laser_busy={s.laser_busy}')
    print(f'  outputs ON: {" ".join(outs)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default='/dev/belt_arduino')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--steps-per-mm', type=float, default=69.0)
    ap.add_argument('--virtual', action='store_true', help='use the virtual firmware')
    args = ap.parse_args()
    fw = None
    if args.virtual:
        host, dev = pipe_pair()
        fw = VirtualFirmware(dev)
        cl = FirmwareClient(host, args.steps_per_mm)
    else:
        cl = FirmwareClient(SerialTransport(args.port, args.baud), args.steps_per_mm)
    stop = threading.Event()

    def beat():                      # keeps the firmware watchdog satisfied
        while not stop.wait(0.1):
            cl.heartbeat()
    threading.Thread(target=beat, daemon=True).start()
    cl.on_event = lambda n, d: print(f'\n[firmware event] {n} {d}')
    print(cl.get_info(), cl.info)
    try:
        while True:
            try:
                line = input('fw> ').split()
            except EOFError:
                break
            if not line:
                continue
            c, a = line[0], line[1:]
            if c in ('quit', 'exit'):
                break
            elif c == 'help':
                print(__doc__)
            elif c == 'info':
                print(cl.get_info(), cl.info)
            elif c == 'status':
                print_status(cl)
            elif c == 'watch':
                try:
                    while True:
                        print_status(cl)
                        time.sleep(0.5)
                except KeyboardInterrupt:
                    pass
            elif c == 'enable':
                print(cl.cmd_enable(a and a[0] == '1'))
            elif c == 'move':
                print(cl.cmd_move_rel(float(a[0]), float(a[1]) if len(a) > 1 else 0.0))
            elif c == 'jog':
                print(cl.cmd_jog(int(a[0]), 10.0, int(a[1])))
            elif c == 'stop':
                print(cl.cmd_stop(bool(a and a[0] == 'quick')))
            elif c == 'out':
                print(cl.cmd_set_output(a[0], a[1] == '1'))
            elif c == 'pulse':
                print(cl.cmd_pulse_output(a[0], int(a[1])))
            elif c == 'zero':
                print(cl.cmd_zero())
            elif c == 'reset':
                print(cl.cmd_reset_faults())
            else:
                print('unknown command, try help')
    finally:
        stop.set()
        cl.close()
        if fw:
            fw.close()


if __name__ == '__main__':
    main()
