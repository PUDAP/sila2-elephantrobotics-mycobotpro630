import dataclasses
from importlib.metadata import version

from unitelabs.cdk import ConnectorBaseConfig, SiLAServerConfig

__version__ = version("unitelabs-mycobotpro630")


@dataclasses.dataclass
class Mycobotpro630Config(ConnectorBaseConfig):
    """Configuration for the myCobotPro630."""

    simulation_mode: bool = True
    """Start without opening the robot socket. The server answers from a simulated arm."""

    robot_ip: str = "<robot-ip>"
    """IPv4 address of the arm socket. Replace `<robot-ip>` in real mode. Connecting does not scan."""

    robot_port: int = 5001
    """TCP port of the arm's built-in socket server."""

    default_speed: int = 800
    """Motion speed from 1 to 3000. SiLA move commands use this value."""

    scan_x: float = -250.0
    """Scan pose X in millimeters."""

    scan_y: float = 280.0
    """Scan pose Y in millimeters."""

    scan_z: float = 330.0
    """Scan pose Z in millimeters."""

    scan_rx: float = -179.99
    """Scan pose Rx in degrees."""

    scan_ry: float = 0.0
    """Scan pose Ry in degrees."""

    scan_rz: float = 111.0
    """Scan pose Rz in degrees."""

    x_min: float = -500.0
    """Minimum allowed X in millimeters. The bench workspace used with this arm is -500 to -100."""

    x_max: float = -100.0
    """Maximum allowed X in millimeters. The bench workspace used with this arm is -500 to -100."""

    y_min: float = -250.0
    """Minimum allowed Y in millimeters. The bench workspace used with this arm is -250 to 400."""

    y_max: float = 400.0
    """Maximum allowed Y in millimeters. The bench workspace used with this arm is -250 to 400."""

    z_min: float = -425.0
    """Minimum allowed Z in millimeters. Past bench use did not tighten Z, so this stays at the driver envelope."""

    z_max: float = 835.0
    """Maximum allowed Z in millimeters. Past bench use did not tighten Z, so this stays at the driver envelope."""

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="myCobotPro630",
            type="Robot",
            description=(
                """
                A SiLA 2 connector for the myCobot Pro 630 arm, built with the UniteLabs CDK.
                """
            ),
            version=str(__version__),
            vendor_url="https://puda.co/",
            port=50053,
        )
    )
