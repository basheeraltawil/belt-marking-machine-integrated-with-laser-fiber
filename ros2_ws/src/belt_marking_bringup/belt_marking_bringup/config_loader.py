"""Map config/machine.yaml (one file) onto the parameters of every node."""

import copy
import os
from typing import Dict, List, Optional

import yaml


def deep_merge(base: Dict, overlay: Dict) -> Dict:
    out = copy.deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str, overlays: Optional[List[str]] = None) -> Dict:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    for ov in overlays or []:
        if ov:
            with open(os.path.expanduser(ov)) as fh:
                cfg = deep_merge(cfg, yaml.safe_load(fh) or {})
    return cfg


def _flat(section: Dict, prefix: str) -> Dict:
    return {f'{prefix}.{k}': v for k, v in section.items()}


def station_offsets(cfg: Dict) -> List[float]:
    lz = cfg['laser']
    return [float(v) for v in lz['station_offsets_mm'][:int(lz['num_stations'])]]


def control_params(cfg: Dict, use_sim: bool) -> Dict:
    p = {}
    for sec in ('machine', 'laser', 'knife', 'zair'):
        p.update(_flat(cfg[sec], sec))
    p['tick_hz'] = float(cfg['control']['tick_hz'])
    p['db_path'] = cfg['control']['db_path']
    p['use_sim'] = use_sim
    p['accel_mm_s2'] = float(cfg['hardware']['accel_mm_s2'])
    p['steps_per_mm'] = float(cfg['hardware']['steps_per_mm'])
    p['laser.station_offsets_mm'] = [float(v) for v in p['laser.station_offsets_mm']]
    p['laser.station_delays_s'] = [float(v) for v in p['laser.station_delays_s']]
    return p


def sim_hardware_params(cfg: Dict) -> Dict:
    m, h, s = cfg['machine'], cfg['hardware'], cfg['sim']
    return {
        'steps_per_mm': float(h['steps_per_mm']),
        'default_speed_mm_s': float(m['feed_speed_default_mm_s']),
        'max_speed_mm_s': float(m['feed_speed_max_mm_s']),
        'accel_mm_s2': float(h['accel_mm_s2']),
        'station_offsets_mm': station_offsets(cfg),
        'knife_offset_mm': float(m['knife_offset_mm']),
        'fork_sensor_offset_mm': float(m['fork_sensor_offset_mm']),
        'knife_stroke_time_s': float(s['knife_stroke_time_s']),
        'laser_marking_time_s': float(s['laser_marking_time_s']),
        'watchdog_s': float(h['heartbeat_timeout_ms']) / 1000.0,
        'encoder_enabled': bool(m['encoder_enabled']),
        'physics_hz': float(s['physics_hz']),
    }


def serial_bridge_params(cfg: Dict) -> Dict:
    m, h = cfg['machine'], cfg['hardware']
    return {
        'port': h['port'], 'baud': int(h['baud']),
        'steps_per_mm': float(h['steps_per_mm']),
        'default_speed_mm_s': float(m['feed_speed_default_mm_s']),
        'max_speed_mm_s': float(m['feed_speed_max_mm_s']),
        'accel_mm_s2': float(h['accel_mm_s2']),
        'num_stations': int(cfg['laser']['num_stations']),
        'heartbeat_timeout_ms': int(h['heartbeat_timeout_ms']),
        'status_timeout_s': float(h['status_timeout_s']),
        'encoder_enabled': bool(m['encoder_enabled']),
    }


def xacro_args(cfg: Dict, gazebo: bool) -> str:
    g = cfg['geometry']
    offsets = ' '.join(f'{v / 1000.0:.4f}' for v in station_offsets(cfg))
    return (f' station_offsets:="{offsets}"'
            f' belt_width:={g["belt_width_mm"] / 1000.0:.4f}'
            f' knife_offset:={cfg["machine"]["knife_offset_mm"] / 1000.0:.4f}'
            f' camera_offset:={g["camera_offset_mm"] / 1000.0:.4f}'
            f' laser_field:={cfg["laser"]["field_length_mm"] / 1000.0:.4f}'
            f' gazebo:={"true" if gazebo else "false"}')
