"""SiLA face of the myCobot Pro 630 arm."""

import asyncio
import dataclasses
import typing

from unitelabs.cdk import sila

from ...io.errors import InvalidCoordinate, MoveTimedOut, RobotConnectFailed
from ...io.protocol import ArmProtocol
from ...io.units import DEGREE, MILLIMETER


@dataclasses.dataclass
class Pose(sila.CustomDataType):
    """
    Cartesian pose of the tool.

    Attributes:
      X: Position along X.
      Y: Position along Y.
      Z: Position along Z.
      Rx: Rotation about X.
      Ry: Rotation about Y.
      Rz: Rotation about Z.
    """

    x: typing.Annotated[float, MILLIMETER]
    y: typing.Annotated[float, MILLIMETER]
    z: typing.Annotated[float, MILLIMETER]
    rx: typing.Annotated[float, DEGREE]
    ry: typing.Annotated[float, DEGREE]
    rz: typing.Annotated[float, DEGREE]


@dataclasses.dataclass
class Angles(sila.CustomDataType):
    """
    Six joint angles.

    Attributes:
      Joint1: Angle of joint 1.
      Joint2: Angle of joint 2.
      Joint3: Angle of joint 3.
      Joint4: Angle of joint 4.
      Joint5: Angle of joint 5.
      Joint6: Angle of joint 6.
    """

    joint_1: typing.Annotated[float, DEGREE]
    joint_2: typing.Annotated[float, DEGREE]
    joint_3: typing.Annotated[float, DEGREE]
    joint_4: typing.Annotated[float, DEGREE]
    joint_5: typing.Annotated[float, DEGREE]
    joint_6: typing.Annotated[float, DEGREE]


class ArmController(sila.Feature):
    """Move the tool center point and read the Cartesian pose."""

    def __init__(self, protocol: ArmProtocol) -> None:
        super().__init__(
            originator="co.puda",
            category="motion",
        )
        self.protocol = protocol

    @sila.UnobservableProperty(errors=[RobotConnectFailed])
    async def get_pose(self) -> Pose:
        """
        Read the Cartesian pose. A prior scan is not required.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        pose = await asyncio.to_thread(self.protocol.get_pose)
        return Pose(x=pose["x"], y=pose["y"], z=pose["z"], rx=pose["rx"], ry=pose["ry"], rz=pose["rz"])

    @sila.UnobservableProperty(errors=[RobotConnectFailed])
    async def get_angles(self) -> Angles:
        """
        Read the six joint angles.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        angles = await asyncio.to_thread(self.protocol.get_angles)
        return Angles(
            joint_1=angles[0],
            joint_2=angles[1],
            joint_3=angles[2],
            joint_4=angles[3],
            joint_5=angles[4],
            joint_6=angles[5],
        )

    @sila.ObservableCommand(
        mode=sila.ExecutionMode.SINGLE,
        errors=[InvalidCoordinate, MoveTimedOut, RobotConnectFailed],
    )
    async def move_absolute(self, pose: Pose, *, status: sila.Status) -> Pose:
        """
        Move to one absolute Cartesian pose.

        The target must stay inside the driver envelope and the configured workspace.
        Rx, Ry, and Rz must stay inside the driver rotation limits. The arm uses its configured default speed.

        Args:
          Pose: Absolute target pose.

        Returns:
          Pose: The Cartesian pose the arm reports after the move.

        Raises:
          InvalidCoordinate: A coordinate is outside the driver envelope or the configured workspace.
          MoveTimedOut: The arm did not reach the target before the settle deadline.
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        reported = await asyncio.to_thread(
            self.protocol.move_absolute,
            pose.x,
            pose.y,
            pose.z,
            pose.rx,
            pose.ry,
            pose.rz,
        )
        status.update(progress=1.0)
        return Pose(
            x=reported["x"],
            y=reported["y"],
            z=reported["z"],
            rx=reported["rx"],
            ry=reported["ry"],
            rz=reported["rz"],
        )

    @sila.ObservableCommand(
        mode=sila.ExecutionMode.SINGLE,
        errors=[InvalidCoordinate, MoveTimedOut, RobotConnectFailed],
    )
    async def move_relative(
        self,
        dx: typing.Annotated[float, MILLIMETER],
        dy: typing.Annotated[float, MILLIMETER],
        dz: typing.Annotated[float, MILLIMETER],
        drx: typing.Annotated[float, DEGREE],
        dry: typing.Annotated[float, DEGREE],
        drz: typing.Annotated[float, DEGREE],
        *,
        status: sila.Status,
    ) -> Pose:
        """
        Move by one Cartesian delta.

        The resulting pose must stay inside the driver envelope and the configured workspace.
        The arm uses its configured default speed.

        Args:
          Dx: Displacement along X.
          Dy: Displacement along Y.
          Dz: Displacement along Z.
          Drx: Rotation change about X.
          Dry: Rotation change about Y.
          Drz: Rotation change about Z.

        Returns:
          Pose: The Cartesian pose the arm reports after the move.

        Raises:
          InvalidCoordinate: The resulting pose is outside the driver envelope or the configured workspace.
          MoveTimedOut: The arm did not reach the target before the settle deadline.
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        reported = await asyncio.to_thread(self.protocol.move_relative, dx, dy, dz, drx, dry, drz)
        status.update(progress=1.0)
        return Pose(
            x=reported["x"],
            y=reported["y"],
            z=reported["z"],
            rx=reported["rx"],
            ry=reported["ry"],
            rz=reported["rz"],
        )

    @sila.ObservableCommand(
        mode=sila.ExecutionMode.SINGLE,
        errors=[InvalidCoordinate, MoveTimedOut, RobotConnectFailed],
    )
    async def scan(self, *, status: sila.Status) -> Pose:
        """
        Move to the configured scan pose.

        This is a Cartesian move to a known pose. It does not drive the joints into limit
        switches, and startup does not call it. Someone needs to be at the arm.

        Returns:
          Pose: The Cartesian pose the arm reports after the scan.

        Raises:
          InvalidCoordinate: The scan pose is outside the driver envelope or the configured workspace.
          MoveTimedOut: The arm did not reach the scan pose before the settle deadline.
          RobotConnectFailed: The arm socket is not connected.
        """
        status.update(progress=0.0)
        reported = await asyncio.to_thread(self.protocol.scan)
        status.update(progress=1.0)
        return Pose(
            x=reported["x"],
            y=reported["y"],
            z=reported["z"],
            rx=reported["rx"],
            ry=reported["ry"],
            rz=reported["rz"],
        )

    @sila.UnobservableCommand(errors=[RobotConnectFailed])
    async def stop(self) -> None:
        """
        Stop motion in progress.

        This is best-effort while a move command is already running.

        Raises:
          RobotConnectFailed: The arm socket is not connected.
        """
        await asyncio.to_thread(self.protocol.stop)
