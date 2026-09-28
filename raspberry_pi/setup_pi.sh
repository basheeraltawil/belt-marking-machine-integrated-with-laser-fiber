#!/bin/bash
# Raspberry Pi 4 (Ubuntu Server 22.04 arm64) setup: ROS 2 Humble + belt marking stack,
# udev rule, systemd services (ROS + kiosk UI), log rotation, optional read-only root.
#
#   sudo ./raspberry_pi/setup_pi.sh                 # from a checkout of this repository
#   sudo ./raspberry_pi/setup_pi.sh --overlayroot   # additionally enable a read-only root fs
#
# Idempotent: safe to run again after `git pull` to rebuild and reinstall.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX=/opt/belt_marking
USER_NAME=belt
OVERLAY=false
[[ "${1:-}" == "--overlayroot" ]] && OVERLAY=true

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
. /etc/os-release
if [[ "$VERSION_ID" != "22.04" ]]; then
  echo "WARNING: ROS 2 Humble binaries need Ubuntu 22.04 (found $VERSION_ID)."
  echo "Raspberry Pi 5: see raspberry_pi/README.md (Ubuntu 24.04 + Jazzy, or Docker)."
fi

echo "==> ROS 2 Humble apt repository"
apt-get update
apt-get install -y curl gnupg lsb-release software-properties-common
add-apt-repository -y universe
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  > /etc/apt/sources.list.d/ros2.list
apt-get update

echo "==> packages (no Gazebo on the Pi: the real machine does not need it)"
apt-get install -y ros-humble-ros-base ros-humble-xacro ros-humble-robot-state-publisher \
  ros-humble-launch-testing-ros python3-colcon-common-extensions python3-rosdep \
  python3-pyqt5 python3-serial python3-yaml python3-opencv \
  cage qtwayland5 fonts-dejavu sqlite3 logrotate
[[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]] || rosdep init
sudo -u "$SUDO_USER" rosdep update --rosdistro humble || true

echo "==> service user '$USER_NAME'"
id "$USER_NAME" >/dev/null 2>&1 || useradd -m -s /bin/bash -G dialout,video,input,render "$USER_NAME"
usermod -aG dialout,video,input "$USER_NAME"

echo "==> workspace -> $PREFIX/ws (only the packages needed on the machine)"
mkdir -p "$PREFIX/ws/src"
rsync -a --delete --exclude belt_marking_gazebo "$REPO/ros2_ws/src/" "$PREFIX/ws/src/"
chown -R "$USER_NAME:$USER_NAME" "$PREFIX"
sudo -u "$USER_NAME" bash -lc "source /opt/ros/humble/setup.bash && cd $PREFIX/ws && \
  colcon build --packages-skip belt_marking_gazebo --event-handlers console_cohesion+"

echo "==> site configuration /etc/belt_marking/site.yaml (overlay on machine.yaml)"
mkdir -p /etc/belt_marking
[[ -f /etc/belt_marking/site.yaml ]] || cat > /etc/belt_marking/site.yaml <<'YAML'
# Site-specific values measured at commissioning (see docs/IMPLEMENTATION_GUIDE.md).
# Example:
# machine: {knife_offset_mm: 55.4}
# laser: {done_mode: signal, pulse_ms: 200}
hardware: {port: /dev/belt_arduino}
YAML

echo "==> udev, systemd, logrotate"
install -m 644 "$REPO/raspberry_pi/udev/99-belt-arduino.rules" /etc/udev/rules.d/
udevadm control --reload-rules && udevadm trigger
UID_BELT=$(id -u "$USER_NAME")
install -m 644 "$REPO/raspberry_pi/systemd/belt-marking-ros.service" /etc/systemd/system/
sed "s|/run/user/1001|/run/user/$UID_BELT|" "$REPO/raspberry_pi/systemd/belt-marking-ui.service" \
  > /etc/systemd/system/belt-marking-ui.service
install -m 644 "$REPO/raspberry_pi/logrotate/belt-marking" /etc/logrotate.d/belt-marking
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=200M\n' > /etc/systemd/journald.conf.d/belt-marking.conf
install -m 755 "$REPO/raspberry_pi/scripts/backup.sh" /usr/local/bin/belt-backup
install -m 755 "$REPO/raspberry_pi/scripts/restore.sh" /usr/local/bin/belt-restore
systemctl daemon-reload
systemctl enable belt-marking-ros.service belt-marking-ui.service
systemctl set-default graphical.target

if $OVERLAY; then
  echo "==> read-only root (overlayroot). Data stays writable on /home (keep DB there)."
  apt-get install -y overlayroot
  sed -i 's|^overlayroot=.*|overlayroot="tmpfs:swap=1,recurse=0"|' /etc/overlayroot.conf
  echo "Reboot to activate. To change the system later: sudo overlayroot-chroot"
  echo "NOTE: /home must be a separate writable partition, otherwise the DB is lost at reboot."
fi

echo "==> done. Reboot, or: systemctl start belt-marking-ros belt-marking-ui"
echo "    default PINs 1111/2222/9999 - CHANGE THEM in Settings -> users (admin)."
