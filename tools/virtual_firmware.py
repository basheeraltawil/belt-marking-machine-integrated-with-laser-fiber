#!/usr/bin/env python3
"""Run the virtual Arduino firmware on a pseudo-terminal: test serial_bridge_node without
hardware (the full real ROS path: bridge -> serial bytes -> protocol -> plant model).

    python3 tools/virtual_firmware.py              # prints e.g. /dev/pts/7
    ros2 launch belt_marking_bringup real.launch.py overlay:=<(echo "hardware: {port: /dev/pts/7}")
    # or: ros2 run belt_marking_hardware serial_bridge_node --ros-args -p port:=/dev/pts/7
"""

import os
import select
import sys
import time
import tty

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src',
                                'belt_marking_hardware'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src',
                                'belt_marking_laser'))

from belt_marking_hardware.fake_plant import PlantConfig  # noqa: E402
from belt_marking_hardware.firmware_client import VirtualFirmware  # noqa: E402


class PtyTransport:

    def __init__(self, fd):
        self.fd = fd
        os.set_blocking(fd, False)

    def write(self, data):
        # write the whole frame (a partial frame would be a CRC error on the host side);
        # give up after 50 ms if nobody reads the pty
        view, deadline = memoryview(data), time.monotonic() + 0.05
        while view and time.monotonic() < deadline:
            try:
                view = view[os.write(self.fd, view):]
            except BlockingIOError:
                select.select([], [self.fd], [], 0.005)
            except OSError:
                return

    def read(self, n=256):
        try:
            return os.read(self.fd, n)
        except (BlockingIOError, OSError):
            time.sleep(0.002)
            return b''

    def close(self):
        os.close(self.fd)


def main():
    master, slave = os.openpty()
    tty.setraw(slave)
    name = os.ttyname(slave)
    link = sys.argv[1] if len(sys.argv) > 1 else None
    if link:
        if os.path.islink(link):
            os.remove(link)
        os.symlink(name, link)
    print(f'virtual firmware on {name}' + (f' (symlink {link})' if link else ''), flush=True)
    fw = VirtualFirmware(PtyTransport(master), PlantConfig(laser_marking_time_s=2.0))
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        fw.close()


if __name__ == '__main__':
    main()
