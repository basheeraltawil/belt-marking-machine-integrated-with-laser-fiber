"""OPC UA server for MES / SCADA (asyncua).

Address space (namespace ``urn:belt-marking-machine``):

    Objects/BeltMarkingMachine
        State, Mode, JobId, Recipe, MarksDone, MarksTotal, PiecesCut, Rejects, Progress,
        BeltPositionMm, TotalMarks, TotalPieces, KnifeCycles, BeltMeters,
        OeeAvailability, OeePerformance, OeeQuality, Oee, ActiveAlarms (string[])
        StartJob(recipe: String, job_id: String, quantity: UInt32) -> String
            only when the parameter ``allow_job_start`` is true (default false). The job
            goes through the normal RunJob action: same validation and state rules as the
            touchscreen; the machine must be IDLE/COMPLETE in AUTO mode.

Security: the default endpoint has no security for commissioning. For production set
``certificate``/``private_key`` to enable Basic256Sha256 Sign&Encrypt and firewall port
4840. Requires ``asyncua`` (``pip install asyncua``).
"""

import asyncio
import threading

from belt_marking_interfaces.action import RunJob
from belt_marking_interfaces.msg import MachineState
from belt_marking_interfaces.srv import LoadRecipe
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from .payloads import state_to_dict

VARIABLES = {  # OPC UA name: state dict key
    'State': 'state_name', 'Mode': 'mode_name', 'JobId': 'job_id', 'Recipe': 'recipe',
    'MarksDone': 'marks_done', 'MarksTotal': 'marks_total', 'PiecesCut': 'pieces_cut',
    'Rejects': 'rejects', 'Progress': 'progress', 'BeltPositionMm': 'belt_position_mm',
    'TotalMarks': 'total_marks', 'TotalPieces': 'total_pieces', 'KnifeCycles': 'knife_cycles',
    'BeltMeters': 'belt_meters', 'OeeAvailability': 'oee_availability',
    'OeePerformance': 'oee_performance', 'OeeQuality': 'oee_quality', 'Oee': 'oee',
}


class OpcUaGateway(Node):

    def __init__(self):
        super().__init__('opcua_gateway')
        p = self.declare_parameter
        p('endpoint', 'opc.tcp://0.0.0.0:4840/belt_marking/')
        p('allow_job_start', False)
        p('certificate', '')
        p('private_key', '')
        self.allow_start = self.get_parameter('allow_job_start').value
        self.state = None
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(MachineState, 'machine/state', self._on_state, latched)
        self.load_cli = self.create_client(LoadRecipe, 'recipes/load')
        self.action = ActionClient(self, RunJob, 'machine/run_job')
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        threading.Thread(target=self._run_server, daemon=True).start()

    def _on_state(self, msg):
        self.state = msg
        if self.ready.is_set():
            asyncio.run_coroutine_threadsafe(self._update(state_to_dict(msg)), self.loop)

    # ------------------------------------------------------------- server thread
    def _run_server(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._serve())

    async def _serve(self):
        from asyncua import Server, ua  # noqa: PLC0415 - optional dependency
        from asyncua.common.methods import uamethod  # noqa: PLC0415
        server = Server()
        await server.init()
        server.set_endpoint(self.get_parameter('endpoint').value)
        server.set_server_name('Belt Marking Machine')
        cert, key = (self.get_parameter('certificate').value,
                     self.get_parameter('private_key').value)
        if cert and key:
            await server.load_certificate(cert)
            await server.load_private_key(key)
            server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        else:
            self.get_logger().warn('OPC UA without security (commissioning only)')
        ns = await server.register_namespace('urn:belt-marking-machine')
        obj = await server.nodes.objects.add_object(ns, 'BeltMarkingMachine')
        self.vars = {}
        for name, key in VARIABLES.items():
            init = '' if key in ('state_name', 'mode_name', 'job_id', 'recipe') else 0.0
            self.vars[key] = await obj.add_variable(ns, name, init)
        self.alarms_var = await obj.add_variable(ns, 'ActiveAlarms', [''],
                                                 ua.VariantType.String)
        if self.allow_start:
            node = self

            @uamethod
            def start_job(parent, recipe, job_id, quantity):
                return node.start_job(recipe, job_id, int(quantity))
            await obj.add_method(ns, 'StartJob', start_job,
                                 [ua.VariantType.String, ua.VariantType.String,
                                  ua.VariantType.UInt32], [ua.VariantType.String])
        async with server:
            self.ready.set()
            self.get_logger().info(f'OPC UA server on {self.get_parameter("endpoint").value}'
                                   f' (StartJob {"enabled" if self.allow_start else "off"})')
            while rclpy.ok():
                await asyncio.sleep(1.0)

    async def _update(self, d):
        for key, var in self.vars.items():
            v = d[key]
            await var.write_value(float(v) if isinstance(v, (int, float)) and
                                  not isinstance(v, bool) else str(v))
        await self.alarms_var.write_value([f'{a["code"]} {a["text"]}' for a in d['alarms']]
                                          or [''])

    # ------------------------------------------------------------- job start
    def start_job(self, recipe: str, job_id: str, quantity: int) -> str:
        if not self.load_cli.wait_for_service(timeout_sec=2.0):
            return 'error: recipes service not available'
        req = LoadRecipe.Request(name=recipe)
        res = self._wait(self.load_cli.call_async(req), 5.0)
        if res is None or not res.found:
            return f'error: recipe {recipe!r} not found'
        spec = res.spec
        spec.job_id, spec.quantity = job_id, quantity
        if not self.action.wait_for_server(timeout_sec=2.0):
            return 'error: RunJob not available'
        handle = self._wait(self.action.send_goal_async(RunJob.Goal(spec=spec,
                                                                    user='opcua')), 5.0)
        if handle is None or not handle.accepted:
            return 'rejected: machine not IDLE/COMPLETE in AUTO mode'
        self.get_logger().info(f'job {job_id} started via OPC UA (recipe {recipe})')
        return 'accepted'

    @staticmethod
    def _wait(fut, timeout):
        ev = threading.Event()
        fut.add_done_callback(lambda _f: ev.set())
        return fut.result() if ev.wait(timeout) else None


def main(args=None):
    rclpy.init(args=args)
    try:
        import asyncua  # noqa: F401,PLC0415
    except ImportError:
        print('asyncua not installed: pip install asyncua')
        rclpy.try_shutdown()
        return
    node = OpcUaGateway()
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
