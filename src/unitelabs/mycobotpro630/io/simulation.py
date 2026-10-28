"""
Simulated Pro630 arm.

``Elephant`` connects from its constructor and has no controller argument, so
simulation is a separate in-memory arm. The SiLA feature still calls the same
protocol methods. Joint angles stay at zero: this double has no kinematic model.
"""

from elephant_driver.elephant import COORD_RANGE, Pose6D


def validate_coords(pose: Pose6D) -> None:
    """Raise ValueError when a pose is outside the driver's Cartesian range."""
    for name, (low, high) in COORD_RANGE.items():
        value = float(getattr(pose, name))
        if not low <= value <= high:
            message = f"Coordinate {name}={value:.2f} is outside the allowed range [{low}, {high}]"
            raise ValueError(message)


class SimulatedArm:
    """In-memory arm. Creating it does not open a socket."""

    def __init__(self, scan_coords: Pose6D) -> None:
        self.scan_coords = scan_coords
        self.pose = Pose6D(x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0)
        self.angles = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.calls: list[object] = []
        self.stopped = False
        self.gripper = "unknown"

    def disconnect(self) -> None:
        """Record a disconnect. There is no socket to close."""
        self.calls.append("disconnect")

    def get_pose(self) -> Pose6D:
        """Return the stored Cartesian pose."""
        self.calls.append("get_pose")
        return self.pose

    def get_angles(self) -> list[float]:
        """Return the stored joint angles in degrees."""
        self.calls.append("get_angles")
        return list(self.angles)

    def move(self, coords: list[float] | Pose6D | dict[str, float], *, speed: int | None = None) -> Pose6D:
        """Store one absolute pose when it is inside the arm's Cartesian range."""
        pose = Pose6D.from_any(coords)
        validate_coords(pose)
        self.pose = pose
        self.calls.append(("move", pose.as_list(), speed))
        return pose

    def move_relative(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        drx: float = 0.0,
        dry: float = 0.0,
        drz: float = 0.0,
        *,
        speed: int | None = None,
    ) -> Pose6D:
        """Add a delta to the stored pose and store the result when it is in range."""
        current = self.pose
        target = Pose6D(
            x=current.x + dx,
            y=current.y + dy,
            z=current.z + dz,
            rx=current.rx + drx,
            ry=current.ry + dry,
            rz=current.rz + drz,
        )
        return self.move(target, speed=speed)

    def scan(self, *, speed: int | None = None) -> None:
        """Move to the configured scan pose."""
        self.calls.append("scan")
        self.move(self.scan_coords.as_list(), speed=speed)

    def stop(self) -> None:
        """Record a stop. The stored pose does not change."""
        self.calls.append("stop")
        self.stopped = True

    def init_gripper(self) -> None:
        """Record electric-gripper initialization."""
        self.calls.append("init_gripper")
        self.gripper = "initialized"

    def open_gripper(self, *, settle_s: float | None = None) -> None:
        """Record an electric-gripper open."""
        self.calls.append(("open_gripper", settle_s))
        self.gripper = "open"

    def close_gripper(self, *, settle_s: float | None = None) -> None:
        """Record an electric-gripper close."""
        self.calls.append(("close_gripper", settle_s))
        self.gripper = "closed"
