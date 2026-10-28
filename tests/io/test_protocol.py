import pytest

from unitelabs.mycobotpro630.io.errors import InvalidCoordinate, InvalidSpeed, RobotConnectFailed
from unitelabs.mycobotpro630.io.protocol import ArmProtocol
from unitelabs.mycobotpro630.io.simulation import SimulatedArm


def make_protocol(*, default_speed: int = 800, scan_z: float = 330.0, **workspace: float) -> ArmProtocol:
    return ArmProtocol(
        robot_ip="<robot-ip>",
        robot_port=5001,
        default_speed=default_speed,
        scan_x=-250.0,
        scan_y=280.0,
        scan_z=scan_z,
        scan_rx=-179.99,
        scan_ry=0.0,
        scan_rz=111.0,
        **workspace,
    )


class RecordingArm:
    """Stand-in that records constructor arguments and later calls."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls: list[str] = []

    def disconnect(self) -> None:
        self.calls.append("disconnect")

    def scan(self, *, speed: int | None = None) -> None:
        del speed
        self.calls.append("scan")

    def reset(self) -> None:
        self.calls.append("reset")

    def move(self, coords: object, *, speed: int | None = None) -> None:
        del coords, speed
        self.calls.append("move")


def test_simulation_starts_at_the_origin_and_does_not_open_a_socket() -> None:
    protocol = make_protocol()

    protocol.use_simulation()

    assert protocol.simulated is True
    assert protocol.get_pose() == {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}
    assert protocol.get_angles() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert isinstance(protocol._arm, SimulatedArm)
    assert "scan" not in protocol._arm.calls


def test_simulated_moves_scan_and_gripper() -> None:
    protocol = make_protocol()
    protocol.use_simulation()

    moved = protocol.move_absolute(-400, 100, 300, -179.99, 0, 111)
    shifted = protocol.move_relative(-10, 20, -5, 0, 0, 1)

    assert moved == {"x": -400.0, "y": 100.0, "z": 300.0, "rx": -179.99, "ry": 0.0, "rz": 111.0}
    assert shifted == {"x": -410.0, "y": 120.0, "z": 295.0, "rx": -179.99, "ry": 0.0, "rz": 112.0}
    with pytest.raises(InvalidCoordinate, match="allowed range"):
        protocol.move_absolute(631, 0, 300, 0, 0, 0)

    scanned = protocol.scan()
    assert scanned == {"x": -250.0, "y": 280.0, "z": 330.0, "rx": -179.99, "ry": 0.0, "rz": 111.0}

    protocol.stop()
    protocol.init_gripper()
    protocol.open_gripper()
    protocol.close_gripper()
    arm = protocol._arm
    assert isinstance(arm, SimulatedArm)
    assert arm.stopped is True
    assert arm.gripper == "closed"


def test_workspace_rejects_a_pose_inside_the_driver_range() -> None:
    protocol = make_protocol(x_min=-400, x_max=-100)
    protocol.use_simulation()

    with pytest.raises(InvalidCoordinate, match="configured workspace"):
        protocol.move_absolute(-50, 200, 300, -179.99, 0, 111)

    assert protocol.get_pose()["x"] == 0.0

    protocol.move_absolute(-200, 200, 300, -179.99, 0, 111)
    with pytest.raises(InvalidCoordinate, match="configured workspace"):
        protocol.move_relative(200, 0, 0, 0, 0, 0)

    assert protocol.get_pose()["x"] == -200.0


def test_workspace_bounds_must_sit_inside_the_driver_range() -> None:
    with pytest.raises(InvalidCoordinate, match="x_min"):
        make_protocol(x_min=-100, x_max=-500)
    with pytest.raises(InvalidCoordinate, match="driver range"):
        make_protocol(x_min=-700, x_max=-100)


def test_invalid_speed_and_scan_pose_raise_before_connect() -> None:
    with pytest.raises(InvalidSpeed, match="1-3000"):
        make_protocol(default_speed=0)
    with pytest.raises(InvalidCoordinate, match="outside"):
        make_protocol(scan_z=9000)


def test_connect_does_not_scan_or_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = make_protocol()
    protocol.use_simulation()
    holder: dict[str, RecordingArm] = {}

    def factory(**kwargs: object) -> RecordingArm:
        arm = RecordingArm(**kwargs)
        holder["arm"] = arm
        return arm

    monkeypatch.setattr("unitelabs.mycobotpro630.io.protocol.Elephant", factory)

    protocol.connect()

    arm = holder["arm"]
    assert arm.calls == []
    assert arm.kwargs["ip"] == "<robot-ip>"
    assert arm.kwargs["port"] == 5001
    assert arm.kwargs["camera"] is None
    assert arm.kwargs["stream_url"] is None
    assert arm.kwargs["combined_viewer_url"] is None
    assert protocol.simulated is False


def test_connect_failure_stays_on_the_simulated_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = make_protocol()
    protocol.use_simulation()

    def factory(**_kwargs: object) -> None:
        message = "connection refused"
        raise ConnectionError(message)

    monkeypatch.setattr("unitelabs.mycobotpro630.io.protocol.Elephant", factory)

    with pytest.raises(RobotConnectFailed, match="connection refused"):
        protocol.connect()

    assert protocol.simulated is True
    assert protocol.get_pose()["x"] == 0.0
