from unitelabs.cdk import sila

from unitelabs.mycobotpro630.features.arm_controller import ArmController
from unitelabs.mycobotpro630.io.protocol import ArmProtocol


def _protocol() -> ArmProtocol:
    protocol = ArmProtocol(
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
    protocol.use_simulation()
    return protocol


def test_feature_identity_and_single_execution() -> None:
    feature = ArmController(_protocol())
    feature.attach()

    assert feature.originator == "co.puda"
    assert feature.category == "motion"
    assert feature.fully_qualified_identifier == "co.puda/motion/ArmController/v1"
    assert feature.commands["MoveAbsolute"].execution_mode == sila.ExecutionMode.SINGLE
    assert feature.commands["MoveRelative"].execution_mode == sila.ExecutionMode.SINGLE
    assert feature.commands["Scan"].execution_mode == sila.ExecutionMode.SINGLE
    assert "Stop" in feature.commands
    assert "Pose" in feature.properties
    assert "Angles" in feature.properties
