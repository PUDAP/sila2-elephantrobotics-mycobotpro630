"""SiLA face of the electric gripper on the myCobot Pro 630."""

import asyncio

from unitelabs.cdk import sila

from ...io.errors import RobotConnectFailed
from ...io.protocol import ArmProtocol


class GripperController(sila.Feature):
    """Initialize, open, and close the electric gripper."""

    def __init__(self, protocol: ArmProtocol) -> None:
        super().__init__(
            originator="co.puda",
            category="gripper",
        )
        self.protocol = protocol

    @sila.ObservableCommand(name="Initialize", mode=sila.ExecutionMode.SINGLE, errors=[RobotConnectFailed])
    async def initialize_gripper(self, *, status: sila.Status) -> None:
        """
        Initialize the electric gripper.

        Run this once after the arm powers on, before Open or Close.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        await asyncio.to_thread(self.protocol.init_gripper)
        status.update(progress=1.0)

    @sila.ObservableCommand(name="Open", mode=sila.ExecutionMode.SINGLE, errors=[RobotConnectFailed])
    async def open_gripper(self, *, status: sila.Status) -> None:
        """
        Open the electric gripper.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        await asyncio.to_thread(self.protocol.open_gripper)
        status.update(progress=1.0)

    @sila.ObservableCommand(name="Close", mode=sila.ExecutionMode.SINGLE, errors=[RobotConnectFailed])
    async def close_gripper(self, *, status: sila.Status) -> None:
        """
        Close the electric gripper.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        await asyncio.to_thread(self.protocol.close_gripper)
        status.update(progress=1.0)
