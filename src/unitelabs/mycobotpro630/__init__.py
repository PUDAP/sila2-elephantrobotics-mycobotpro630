"""SiLA 2 connector for the myCobot Pro 630 arm."""

import asyncio
import collections.abc
from importlib.metadata import version

from unitelabs.cdk import Connector
from unitelabs.cdk.features.core.lock_controller import LockController

from .config import Mycobotpro630Config
from .features.arm_controller import ArmController
from .features.gripper_controller import GripperController
from .features.simulation_controller import SimulationController
from .io.protocol import ArmProtocol

__version__ = version("unitelabs-mycobotpro630")


async def create_app(config: Mycobotpro630Config) -> collections.abc.AsyncGenerator[Connector]:
    """Create the connector application."""
    app = Connector(config)
    protocol = ArmProtocol(
        robot_ip=config.robot_ip,
        robot_port=config.robot_port,
        default_speed=config.default_speed,
        scan_x=config.scan_x,
        scan_y=config.scan_y,
        scan_z=config.scan_z,
        scan_rx=config.scan_rx,
        scan_ry=config.scan_ry,
        scan_rz=config.scan_rz,
        x_min=config.x_min,
        x_max=config.x_max,
        y_min=config.y_min,
        y_max=config.y_max,
        z_min=config.z_min,
        z_max=config.z_max,
    )
    simulation = SimulationController(protocol, simulation_mode=config.simulation_mode)

    try:
        if not config.simulation_mode:
            await simulation.start_real_mode()

        app.register(LockController())
        app.register(simulation)
        app.register(ArmController(protocol))
        app.register(GripperController(protocol))
        yield app
    finally:
        await asyncio.to_thread(protocol.close)
