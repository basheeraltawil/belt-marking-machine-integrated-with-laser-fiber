"""Laser abstraction for the belt marking machine."""

from .dry_contact import DryContactLaser, LaserIoPort
from .interface import DoneMode, LaserConfig, LaserInterface, LaserPoll, LaserResult
from .sim_model import SimCo2Laser, SimLaserFaults

__all__ = [
    'DoneMode', 'DryContactLaser', 'LaserConfig', 'LaserInterface', 'LaserIoPort',
    'LaserPoll', 'LaserResult', 'SimCo2Laser', 'SimLaserFaults',
]
