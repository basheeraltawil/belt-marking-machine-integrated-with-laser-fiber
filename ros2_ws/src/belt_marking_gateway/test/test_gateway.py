import json
from types import SimpleNamespace

from belt_marking_gateway.payloads import event_to_dict, state_to_dict, to_json
from belt_marking_gateway.payloads import STATE_FIELDS
import pytest

T = SimpleNamespace(sec=100, nanosec=500000000)


def fake_state():
    d = {f: 0 for f in STATE_FIELDS}
    d.update(state_name='EXECUTE', mode_name='AUTO', job_id='J1', recipe='r', phase='FEED',
             use_sim=True, oee=0.87654321, light_green=True, light_red=False,
             light_yellow=False)
    d['active_alarms'] = [SimpleNamespace(code_text='W-601', severity=1, text='reject',
                                          active=False, acknowledged=False, stamp=T)]
    d['stamp'] = T
    return SimpleNamespace(**d)


def test_state_payload():
    d = state_to_dict(fake_state(), 'line3')
    assert d['machine_id'] == 'line3' and d['state_name'] == 'EXECUTE'
    assert d['oee'] == 0.8765 and d['time'] == 100.5
    assert d['alarms'][0]['code'] == 'W-601'
    assert json.loads(to_json(d)) == d


def test_event_payload():
    ev = SimpleNamespace(type=1, job_id='J1', label_index=4, station=0, belt_coord_mm=290.0,
                         length_mm=60.0, detail='', stamp=T)
    assert event_to_dict(ev)['type'] == 'CUT'


def test_mqtt_gateway_with_fake_client():
    rclpy = pytest.importorskip('rclpy')
    from belt_marking_gateway.mqtt_node import MqttGateway

    class FakeClient:

        def __init__(self):
            self.msgs = []

        def publish(self, topic, payload, qos=0, retain=False):
            self.msgs.append((topic, payload, retain))

    client = FakeClient()
    rclpy.init()
    try:
        node = MqttGateway(client_factory=lambda h, p, t: client)
        node._on_state(fake_state())
        node._on_state(fake_state())                  # unchanged -> not published again
        assert [m[0] for m in client.msgs] == ['factory/belt_marking/belt-marker-1/state']
        assert client.msgs[0][2] is True              # retained
        node.destroy_node()
    finally:
        rclpy.shutdown()
