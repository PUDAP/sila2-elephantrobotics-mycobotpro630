import pytest
from unitelabs.cdk.features.core.simulation_controller import StartRealModeFailed

from unitelabs.mycobotpro630.features.simulation_controller import SimulationController
from unitelabs.mycobotpro630.io.protocol import ArmProtocol


def _protocol() -> ArmProtocol:
    return ArmProtocol(
        robot_ip="<robot-ip>",
        robot_port=5001,
        default_speed=800,
        scan_x=-250.0,
        scan_y=280.0,
        scan_z=330.0,
        scan_rx=-179.99,
        scan_ry=0.0,
        scan_rz=111.0,
    )


@pytest.mark.asyncio
async def test_start_real_mode_refused_socket_stays_in_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = _protocol()

    def factory(**_kwargs: object) -> None:
        message = "connection refused"
        raise ConnectionError(message)

    monkeypatch.setattr("unitelabs.mycobotpro630.io.protocol.Elephant", factory)
    controller = SimulationController(protocol, simulation_mode=True)

    with pytest.raises(StartRealModeFailed, match="connection refused"):
        await controller.start_real_mode()

    assert await controller.simulation_mode() is True
    assert protocol.simulated is True
    assert protocol.get_pose() == {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0}
