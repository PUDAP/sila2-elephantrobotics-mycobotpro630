"""
Hardware failures for the myCobot Pro 630 arm.

These exceptions carry the driver message. They do not import SiLA.
"""


class RobotConnectFailed(Exception):
    """The arm socket did not connect."""


class InvalidCoordinate(Exception):
    """A Cartesian coordinate is outside the arm's allowed range."""


class InvalidSpeed(Exception):
    """The speed is not an integer from 1 to 3000."""


class MoveTimedOut(Exception):
    """The arm did not reach the target before the settle deadline."""
