from unitelabs.cdk import sila

from unitelabs.mycobotpro630.features.gripper_controller import GripperController
from unitelabs.mycobotpro630.io.protocol import ArmProtocol


def test_gripper_feature_identity() -> None:
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
    feature = GripperController(protocol)
    feature.attach()

    assert feature.originator == "co.puda"
    assert feature.category == "gripper"
    assert feature.fully_qualified_identifier == "co.puda/gripper/GripperController/v1"
    assert feature.commands["Initialize"].execution_mode == sila.ExecutionMode.SINGLE
    assert feature.commands["Open"].execution_mode == sila.ExecutionMode.SINGLE
    assert feature.commands["Close"].execution_mode == sila.ExecutionMode.SINGLE
