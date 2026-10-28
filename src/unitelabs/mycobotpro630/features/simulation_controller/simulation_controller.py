"""Switch the arm between the in-memory double and the robot socket."""

import asyncio

from typing_extensions import override
from unitelabs.cdk.features.core.simulation_controller import SimulationControllerBase, StartRealModeFailed

from ...io.errors import RobotConnectFailed
from ...io.protocol import ArmProtocol


class SimulationController(SimulationControllerBase):
    """Control whether the arm protocol uses the robot socket or the in-memory arm."""

    def __init__(self, protocol: ArmProtocol, *, simulation_mode: bool = True) -> None:
        super().__init__()
        self.protocol = protocol
        self._simulation_mode = True
        if simulation_mode:
            self.protocol.use_simulation()

    @override
    async def simulation_mode(self) -> bool:
        """Whether or not the SiLA Server is in Simulation Mode."""
        return self._simulation_mode

    @override
    async def start_real_mode(self) -> None:
        """
        Set the SiLA Server to run in real mode.

        In real-mode all following commands are executed with real-world
        interactions, like serial port/CAN communication, motor actions etc.

        If the server is in Simulation Mode it can be interrupted at any time. A re-initialization of
        the hardware might be required. The Real Mode can be stopped by issuing the 'Start Simulation Mode' command.

        Raises:
          StartRealModeFailed: If the server cannot change to Real Mode.
        """
        if not self._simulation_mode:
            return

        try:
            await asyncio.to_thread(self.protocol.connect)
        except RobotConnectFailed as error:
            message = str(error)
            raise StartRealModeFailed(message) from error
        self._simulation_mode = False

    @override
    async def start_simulation_mode(self) -> None:
        """
        Set the SiLA Server to run in Simulation Mode, i.e. all following commands are executed in simulation mode.

        The Simulation Mode can only be entered, if all hardware operations have been safely terminated
        or are in a controlled, safe state.

        The simulation mode can be stopped by issuing the 'Start Real Mode' command.
        """
        if self._simulation_mode:
            return

        await asyncio.to_thread(self.protocol.use_simulation)
        self._simulation_mode = True
