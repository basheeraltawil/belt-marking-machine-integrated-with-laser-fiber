"""Make the ROS-free Python packages of ros2_ws importable without building ROS."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIGURES = os.path.join(ROOT, 'analysis', 'figures')
for pkg in ('belt_marking_laser', 'belt_marking_hardware', 'belt_marking_control',
            'belt_marking_vision'):
    path = os.path.join(ROOT, 'ros2_ws', 'src', pkg)
    if path not in sys.path:
        sys.path.insert(0, path)
os.makedirs(FIGURES, exist_ok=True)


def savefig(fig, name: str) -> str:
    path = os.path.join(FIGURES, name)
    fig.savefig(path, dpi=110, bbox_inches='tight')
    return path
