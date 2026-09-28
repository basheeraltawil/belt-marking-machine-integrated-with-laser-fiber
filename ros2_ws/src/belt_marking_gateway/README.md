# belt_marking_gateway

Optional connectivity for dashboards, MES and SCADA. It is not needed to run the machine.

| Node | Protocol | Direction | Content |
|---|---|---|---|
| `mqtt_gateway` | MQTT (paho) | publish only | `<prefix>/<id>/state` (retained JSON: state, job, counters, OEE, alarms), `/alarm`, `/event`, `/online` (LWT) |
| `opcua_gateway` | OPC UA (asyncua) | read + optional `StartJob` | variables for state/counters/OEE/alarms; `StartJob(recipe, job_id, quantity)` only with `allow_job_start:=true`, through the normal RunJob action |

```bash
sudo apt install python3-paho-mqtt && pip install asyncua
ros2 run belt_marking_gateway mqtt_gateway --ros-args -p host:=broker.local -p machine_id:=line3
BELT_MQTT_USER=... BELT_MQTT_PASSWORD=... ros2 run belt_marking_gateway mqtt_gateway
ros2 run belt_marking_gateway opcua_gateway --ros-args -p allow_job_start:=true
```

Security: credentials only from environment variables. For OPC UA in production, set
`certificate`/`private_key` (Basic256Sha256 Sign&Encrypt) and restrict port 4840. A remote
job start is off by default; the operator's touchscreen stays the primary interface.
