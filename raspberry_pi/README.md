# Raspberry Pi deployment

| File | Purpose |
|---|---|
| `setup_pi.sh` | one-shot, idempotent install: ROS 2 Humble (ros-base), workspace build in `/opt/belt_marking/ws`, service user `belt`, udev, systemd, logrotate, journald limit, backup tools, optional read-only root |
| `udev/99-belt-arduino.rules` | `/dev/belt_arduino` for genuine Mega (2341:0042/0010) and CH340 clones |
| `systemd/belt-marking-ros.service` | `real.launch.py ui:=false` with the site overlay `/etc/belt_marking/site.yaml`, restarts automatically |
| `systemd/belt-marking-ui.service` | touchscreen kiosk: **cage** (Wayland kiosk compositor) runs only the operator UI, full screen, on tty1 |
| `logrotate/belt-marking` | ROS logs: daily, 14 days, 20 MB max |
| `scripts/backup.sh` → `belt-backup` | online SQLite backup + calibration + site config → USB stick |
| `scripts/restore.sh` → `belt-restore` | restore such a backup |

## Choosing the Pi and the OS

| Board | OS | ROS | Status |
|---|---|---|---|
| **Raspberry Pi 4 (4 GB+)** | Ubuntu Server 22.04 arm64 | Humble (apt) | **recommended**, matches this repository |
| Raspberry Pi 5 | Ubuntu 24.04 | Jazzy (apt) | Ubuntu 22.04 has no Pi 5 kernel. The Python packages are source compatible with Jazzy but not tested here (`ros_gz` names differ, which only matters for the simulation) |
| Raspberry Pi 5 | Raspberry Pi OS (Bookworm) | Humble in Docker (`docker/Dockerfile` without Gazebo), UI natively or via X11 | works, more moving parts |

Display: official 7" touchscreen (800×480) or any HDMI/USB touch panel. The UI is designed for 800×480.

## Steps

```bash
git clone https://github.com/basheeraltawil/belt-marking-machine-integrated-with-laser-fiber.git
cd belt-marking-machine-integrated-with-laser-fiber
sudo ./raspberry_pi/setup_pi.sh            # add --overlayroot for a read-only system
sudo reboot
```

Check:

```bash
ls -l /dev/belt_arduino                     # udev link
systemctl status belt-marking-ros belt-marking-ui
journalctl -u belt-marking-ros -f
```

## Read-only root filesystem (optional)

An SD card that loses power during writes can corrupt. `--overlayroot` mounts `/` read-only
with a RAM overlay. Keep `/home` (DB, recipes, calibration, logs) on a separate writable
partition or a USB SSD. System changes: `sudo overlayroot-chroot`. Back up regularly with
`belt-backup`, at least weekly and after every recipe/calibration change.
