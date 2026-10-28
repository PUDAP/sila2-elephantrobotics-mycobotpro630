"""
myCobot Pro 630 arm protocol.

This module imports ``elephant-driver`` and does not import SiLA. Motion stays
in ``Elephant``. Connecting opens the robot socket. It does not call ``scan``
or ``reset``.
"""

import threading
import typing

from elephant_driver.elephant import COORD_RANGE, Elephant, Pose6D

from .errors import InvalidCoordinate, InvalidSpeed, MoveTimedOut, RobotConnectFailed
from .simulation import SimulatedArm, validate_coords

T = typing.TypeVar("T")


def _pose_dict(pose: Pose6D) -> dict[str, float]:
    return {
        "x": float(pose.x),
        "y": float(pose.y),
        "z": float(pose.z),
        "rx": float(pose.rx),
        "ry": float(pose.ry),
        "rz": float(pose.rz),
    }


class ArmProtocol:
    """One Pro630 arm, simulated or on its TCP socket."""

    def __init__(
        self,
        *,
        robot_ip: str,
        robot_port: int,
        default_speed: int,
        scan_x: float,
        scan_y: float,
        scan_z: float,
        scan_rx: float,
        scan_ry: float,
        scan_rz: float,
        x_min: float = -630.0,
        x_max: float = 630.0,
        y_min: float = -630.0,
        y_max: float = 630.0,
        z_min: float = -425.0,
        z_max: float = 835.0,
    ) -> None:
        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self.default_speed = default_speed
        self._scan = Pose6D(x=scan_x, y=scan_y, z=scan_z, rx=scan_rx, ry=scan_ry, rz=scan_rz)
        self._workspace = {
            "x": (x_min, x_max),
            "y": (y_min, y_max),
            "z": (z_min, z_max),
        }
        self._arm: Elephant | SimulatedArm | None = None
        self._simulated = True
        self._lock = threading.Lock()
        self._validate_speed(default_speed)
        self._validate_workspace_bounds()
        self._validate_scan(self._scan)

    @property
    def simulated(self) -> bool:
        """Whether the current arm is the in-memory double."""
        return self._simulated

    def use_simulation(self) -> None:
        """Serve poses from memory and leave the robot socket closed."""
        with self._lock:
            previous = self._arm
            self._arm = None
            self._simulated = True
            if previous is not None:
                self._release(previous)
            self._arm = SimulatedArm(self._scan)

    def connect(self) -> None:
        """Open the robot socket and do not scan or reset."""
        with self._lock:
            self._validate_speed(self.default_speed)
            try:
                arm = Elephant(
                    ip=self.robot_ip,
                    port=self.robot_port,
                    scan_coords=self._scan.as_list(),
                    default_speed=self.default_speed,
                    camera=None,
                    stream_url=None,
                    combined_viewer_url=None,
                )
            except OSError as error:
                message = f"Could not connect to the arm at {self.robot_ip}:{self.robot_port}: {error}"
                raise RobotConnectFailed(message) from error
            previous = self._arm
            self._arm = arm
            self._simulated = False
            if previous is not None:
                self._release(previous)

    def close(self) -> None:
        """Disconnect the current arm."""
        with self._lock:
            arm = self._arm
            self._arm = None
            self._simulated = True
            if arm is not None:
                self._release(arm)

    def get_pose(self) -> dict[str, float]:
        """Read the Cartesian pose in millimeters and degrees."""
        pose = self._invoke(lambda: self._arm_or_error().get_pose())
        return _pose_dict(pose)

    def get_angles(self) -> list[float]:
        """Read six joint angles in degrees."""
        raw = self._invoke(lambda: self._arm_or_error().get_angles())
        try:
            angles = [float(value) for value in raw]
        except (TypeError, ValueError) as error:
            message = f"The arm did not return six joint angles: {raw!r}"
            raise ValueError(message) from error
        if len(angles) != 6:
            message = f"The arm did not return six joint angles: {raw!r}"
            raise ValueError(message)
        return angles

    def move_absolute(self, x: float, y: float, z: float, rx: float, ry: float, rz: float) -> dict[str, float]:
        """Move to one absolute Cartesian pose. Speed stays at the configured default."""
        pose = Pose6D(x=x, y=y, z=z, rx=rx, ry=ry, rz=rz)
        self._check_translation(pose)

        def action() -> Pose6D:
            return self._arm_or_error().move(pose.as_list(), speed=self.default_speed)

        return _pose_dict(self._invoke(action))

    def move_relative(
        self,
        dx: float,
        dy: float,
        dz: float,
        drx: float,
        dry: float,
        drz: float,
    ) -> dict[str, float]:
        """Move by one Cartesian delta. Speed stays at the configured default."""
        current = self.get_pose()
        target = Pose6D(
            x=current["x"] + dx,
            y=current["y"] + dy,
            z=current["z"] + dz,
            rx=current["rx"] + drx,
            ry=current["ry"] + dry,
            rz=current["rz"] + drz,
        )
        self._check_translation(target)

        def action() -> Pose6D:
            return self._arm_or_error().move_relative(dx, dy, dz, drx, dry, drz, speed=self.default_speed)

        return _pose_dict(self._invoke(action))

    def scan(self) -> dict[str, float]:
        """Move to the configured scan pose and return the pose the arm reports."""
        return _pose_dict(self._invoke(self._scan_and_read))

    def stop(self) -> None:
        """Stop motion in progress without waiting for the current move to finish."""
        self._invoke(lambda: self._arm_or_error().stop(), locked=False)

    def init_gripper(self) -> None:
        """Initialize the electric gripper."""
        self._invoke(lambda: self._arm_or_error().init_gripper())

    def open_gripper(self) -> None:
        """Open the electric gripper."""
        self._invoke(lambda: self._arm_or_error().open_gripper())

    def close_gripper(self) -> None:
        """Close the electric gripper."""
        self._invoke(lambda: self._arm_or_error().close_gripper())

    def _scan_and_read(self) -> Pose6D:
        """Scan, then read the pose."""
        arm = self._arm_or_error()
        arm.scan(speed=self.default_speed)
        return arm.get_pose()

    def _invoke(self, action: typing.Callable[[], T], *, locked: bool = True) -> T:
        if locked:
            with self._lock:
                return self._run(action)
        return self._run(action)

    def _run(self, action: typing.Callable[[], T]) -> T:
        try:
            return action()
        except TimeoutError as error:
            message = str(error)
            raise MoveTimedOut(message) from error
        except ValueError as error:
            self._raise_value(error)
        except OSError as error:
            message = str(error)
            raise RobotConnectFailed(message) from error

    def _arm_or_error(self) -> Elephant | SimulatedArm:
        if self._arm is None:
            message = "The arm is not connected."
            raise RobotConnectFailed(message)
        return self._arm

    def _release(self, arm: Elephant | SimulatedArm) -> None:
        try:
            arm.disconnect()
        except OSError:
            return

    def _validate_workspace_bounds(self) -> None:
        for name, (low, high) in self._workspace.items():
            if low > high:
                message = f"Workspace {name}_min={low} is above {name}_max={high}"
                raise InvalidCoordinate(message)
            driver_low, driver_high = COORD_RANGE[name]
            if low < driver_low or high > driver_high:
                message = (
                    f"Workspace {name} [{low}, {high}] extends outside the driver range [{driver_low}, {driver_high}]"
                )
                raise InvalidCoordinate(message)

    def _validate_workspace(self, pose: Pose6D) -> None:
        for name, (low, high) in self._workspace.items():
            value = float(getattr(pose, name))
            if not low <= value <= high:
                message = f"Coordinate {name}={value:.2f} is outside the configured workspace [{low}, {high}]"
                raise ValueError(message)

    def _check_translation(self, pose: Pose6D) -> None:
        """Reject an XYZ target outside the driver envelope or the configured workspace."""
        for name in ("x", "y", "z"):
            value = float(getattr(pose, name))
            driver_low, driver_high = COORD_RANGE[name]
            if not driver_low <= value <= driver_high:
                message = f"Coordinate {name}={value:.2f} is outside the allowed range [{driver_low}, {driver_high}]"
                raise InvalidCoordinate(message)
            low, high = self._workspace[name]
            if not low <= value <= high:
                message = f"Coordinate {name}={value:.2f} is outside the configured workspace [{low}, {high}]"
                raise InvalidCoordinate(message)

    def _check_pose(self, pose: Pose6D) -> None:
        try:
            validate_coords(pose)
            self._validate_workspace(pose)
        except ValueError as error:
            self._raise_value(error)

    def _validate_scan(self, pose: Pose6D) -> None:
        self._check_pose(pose)

    @staticmethod
    def _validate_speed(speed: int) -> None:
        if isinstance(speed, bool) or not isinstance(speed, int) or not 1 <= speed <= 3000:
            message = f"speed must be 1-3000, got {speed!r}"
            raise InvalidSpeed(message)

    def _raise_value(self, error: ValueError) -> typing.NoReturn:
        text = str(error)
        if "speed" in text:
            raise InvalidSpeed(text) from error
        raise InvalidCoordinate(text) from error
