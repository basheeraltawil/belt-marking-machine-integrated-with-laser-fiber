"""ROS message -> plain dict/JSON mapping shared by the MQTT and OPC UA gateways."""

import json

STATE_FIELDS = ('state_name', 'mode_name', 'use_sim', 'job_id', 'recipe', 'phase', 'marks_done',
                'marks_total', 'pieces_cut', 'rejects', 'progress', 'job_elapsed_s',
                'belt_position_mm', 'belt_speed_mm_s', 'belt_width_mm', 'total_marks',
                'total_pieces', 'knife_cycles', 'laser_triggers', 'belt_meters', 'uptime_s',
                'oee_availability', 'oee_performance', 'oee_quality', 'oee', 'light_red',
                'light_yellow', 'light_green')
EVENT_NAMES = {0: 'MARK', 1: 'CUT', 2: 'REJECT', 3: 'PIECE_OUT', 4: 'JOB_START', 5: 'JOB_END'}


def _stamp(t) -> float:
    return round(t.sec + t.nanosec * 1e-9, 3) if t is not None else 0.0


def alarm_to_dict(a) -> dict:
    return {'code': a.code_text, 'severity': int(a.severity), 'text': a.text,
            'active': bool(a.active), 'acknowledged': bool(a.acknowledged),
            'time': _stamp(getattr(a, 'stamp', None))}


def state_to_dict(st, machine_id: str = 'belt-marker-1') -> dict:
    d = {'machine_id': machine_id, 'time': _stamp(getattr(st, 'stamp', None))}
    for f in STATE_FIELDS:
        v = getattr(st, f)
        d[f] = round(v, 4) if isinstance(v, float) else v
    d['alarms'] = [alarm_to_dict(a) for a in st.active_alarms]
    return d


def event_to_dict(ev) -> dict:
    return {'type': EVENT_NAMES.get(ev.type, str(ev.type)), 'job_id': ev.job_id,
            'label': int(ev.label_index), 'station': int(ev.station),
            'belt_coord_mm': round(ev.belt_coord_mm, 3), 'length_mm': round(ev.length_mm, 3),
            'detail': ev.detail, 'time': _stamp(getattr(ev, 'stamp', None))}


def to_json(d: dict) -> str:
    return json.dumps(d, separators=(',', ':'), sort_keys=True)
