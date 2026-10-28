"""PUDA Driver for the Elephant Pro630 6-axis robot arm.

Uses ``pymycobot.ElephantRobot`` to talk directly to the robot's built-in
socket server on port 5001 — no bridge process needed on the Pi.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from pymycobot import ElephantRobot

from .camera import (
    CameraCalibration,
    CameraConfig,
    calculate_pixel_to_robot_offset,
    capture_pi_image,
)
from .cv.function.function import DEFAULT_STREAM_URL, capture_snapshot

logger = logging.getLogger(__name__)

DEFAULT_SCAN_COORDS = [-250.0, 280.0, 330.0, -179.99, 0.0, 111.0]
DEFAULT_SPEED = 800
DEFAULT_COMBINED_VIEWER_HOST = "127.0.0.1"
DEFAULT_COMBINED_VIEWER_PORT = 5000
DEFAULT_COMBINED_VIEWER_URL = (
    f"http://{DEFAULT_COMBINED_VIEWER_HOST}:{DEFAULT_COMBINED_VIEWER_PORT}"
)
# Seconds to wait after electric gripper open/close before the next motion.
DEFAULT_GRIPPER_SETTLE_S = 1.2
DEFAULT_MOVE_SETTLE_TIMEOUT_S = 180.0
DEFAULT_MOVE_POSITION_TOLERANCE_MM = 2.0
DEFAULT_MOVE_ROTATION_TOLERANCE_DEG = 2.0

COORD_RANGE = {
    "x": (-630.0, 630.0),
    "y": (-630.0, 630.0),
    "z": (-425.0, 835.0),
    "rx": (-180.0, 180.0),
    "ry": (-180.0, 180.0),
    "rz": (-180.0, 180.0),
}


@dataclass(frozen=True, slots=True)
class Pose6D:
    """Cartesian pose for a 6-axis arm: x, y, z, rx, ry, rz."""

    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.rx, self.ry, self.rz]

    def _replace(self, **kwargs: float) -> Pose6D:
        d = {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}
        d.update(kwargs)
        return Pose6D(**d)

    @classmethod
    def from_any(cls, value: Any) -> Pose6D:
        """Build from a list, dict, Pose6D, or positional floats."""
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                float(value["x"]),
                float(value["y"]),
                float(value["z"]),
                float(value.get("rx", 0.0)),
                float(value.get("ry", 0.0)),
                float(value.get("rz", 0.0)),
            )
        if isinstance(value, (list, tuple)) and len(value) == 6:
            return cls(*[float(v) for v in value])
        raise TypeError(f"Cannot convert {type(value).__name__} to Pose6D")


class Elephant:
    """PUDA wrapper around pymycobot's ElephantRobot for the Pro630 6-axis arm.

    Connects directly to the robot's built-in socket server (default port 5001)
    so no bridge process is required on the Pi.
    """

    def __init__(
        self,
        *,
        ip: str,
        port: int = 5001,
        scan_coords: Sequence[float] | None = None,
        default_speed: int = DEFAULT_SPEED,
        gripper_settle_s: float = DEFAULT_GRIPPER_SETTLE_S,
        camera: CameraConfig | None = None,
        stream_url: str | None = None,
        combined_viewer_url: str | None = DEFAULT_COMBINED_VIEWER_URL,
        calibration: CameraCalibration | None = None,
    ) -> None:
        self._ip = ip
        self._port = port
        self._default_speed = int(default_speed)
        self._gripper_settle_s = float(gripper_settle_s)
        self._scan_coords = list(scan_coords or DEFAULT_SCAN_COORDS)
        self._connected = False
        self._logger = logger.getChild(self.__class__.__name__)
        self._camera = camera
        self._stream_url = stream_url
        self._combined_viewer_url = combined_viewer_url
        self._calibration = calibration or CameraCalibration()

        self._client = ElephantRobot(ip, port)
        self._connect()

    # -- Context manager ---------------------------------------------------

    def __enter__(self) -> Elephant:
        if not self._connected:
            self._connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.disconnect()

    def startup(self) -> None:
        """Ensure the robot is connected and report the configured Pi camera."""
        if not self._connected:
            self._connect()
        self._logger.info("Driver ready with cameras=%s", self.available_cameras())

    # -- Connection --------------------------------------------------------

    def _connect(self, *, retry_delay: float = 3.0, max_retries: int = 5) -> None:
        for attempt in range(1, max_retries + 1):
            try:
                self._logger.info("Connecting to %s:%s (attempt %d)", self._ip, self._port, attempt)
                self._client = ElephantRobot(self._ip, self._port)
                if not self._client.start_client():
                    raise ConnectionError(
                        f"Robot socket connect returned False for {self._ip}:{self._port}"
                    )

                # Try to enable the robot if it isn't already.  Some firmware
                # builds have a broken start_robot(), so we treat enable
                # failures as non-fatal — the connection itself is still valid.
                try:
                    if not self._client.state_check():
                        self._client.start_robot()
                        time.sleep(2)
                        self._client._state_on()
                except Exception as e:
                    self._logger.warning("Robot enable step failed (non-fatal): %s", e)

                self._connected = True
                self._logger.info("Connected")
                return
            except Exception as e:
                self._logger.warning("Connection attempt %d failed: %s", attempt, e)
                if attempt < max_retries:
                    time.sleep(retry_delay)
        raise ConnectionError(
            f"Failed to connect to Elephant at {self._ip}:{self._port} after {max_retries} attempts"
        )

    def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._connected:
            try:
                self._client.stop_client()
            except Exception as e:
                self._logger.warning("Error during disconnect: %s", e)
            self._connected = False
            self._logger.info("Disconnected")

    def reconnect(self) -> None:
        """Disconnect then reconnect."""
        self.disconnect()
        self._connect()


    # -- Status / diagnostics ----------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def is_power_on(self) -> bool:
        return self._client.is_power_on()

    def is_moving(self) -> bool:
        return self._client.check_running()

    def get_error(self) -> str:
        """Return the next queued error message, or empty string if none."""
        return self._client.read_next_error()

    def clear_error(self) -> None:
        self._client.clear_all_errors()

    def get_robot_status(self) -> str:
        """Return the 64-bit robot state string."""
        return self._client.get_robot_state()

    # -- Pose queries ------------------------------------------------------
    
    def get_position(self) -> dict[str, Any]:
        """Return all position information as a dict.

        Refresh the TCP client before reading telemetry because long-lived
        ElephantRobot sockets can become stale on Windows and trigger
        WinError 10053.
        """
        if self._connected:
            self.disconnect()
        self._connect()

        return {
            "angles": self.get_angles(),
            "coords": self.get_coords(),
        }

    def get_angles(self) -> list[float]:
        """Return the current six joint angles in degrees."""
        angles = self._client.get_angles()
        self._logger.debug("Joint angles: %s", angles)
        return angles

    def get_coords(self) -> list[float]:
        """Return the current Cartesian coords [x, y, z, rx, ry, rz]."""
        coords = self._client.get_coords()
        self._logger.debug("Coords: %s", coords)
        return coords

    def get_pose(self) -> Pose6D:
        """Return the current Cartesian pose as a Pose6D."""
        c = self.get_coords()
        return Pose6D(*c)

    # -- Speed -------------------------------------------------------------

    def set_default_speed(self, speed: int) -> None:
        if not 1 <= speed <= 3000:
            raise ValueError("speed must be 1-3000")
        self._default_speed = speed

    # -- Low-level motion --------------------------------------------------

    def send_angles(self, angles: Sequence[float], speed: int | None = None) -> None:
        """Move all joints to the given angles (degrees)."""
        speed = speed or self._default_speed
        self._logger.debug("send_angles(%s, speed=%d)", angles, speed)
        self._client.write_angles(list(angles), speed)

    def send_coords(
        self,
        coords: Sequence[float] | Pose6D | dict[str, float],
        speed: int | None = None,
    ) -> None:
        """Move the TCP to the given Cartesian coordinates."""
        speed = speed or self._default_speed
        pose = Pose6D.from_any(coords)
        self._validate_coords(pose)
        coord_list = self._sanitize_zeros(pose.as_list())
        self._logger.debug("send_coords(%s, speed=%d)", coord_list, speed)
        self._logger.info(
            "Moving to x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f @ speed=%d",
            *coord_list, speed,
        )
        self._client.write_coords(coord_list, speed)

    def send_coord(self, axis_id: int, value: float, speed: int | None = None) -> None:
        """Move a single Cartesian axis (0-5 = x,y,z,rx,ry,rz)."""
        speed = speed or self._default_speed
        self._client.write_coord(axis_id, value, speed)

    def send_angle(self, joint_id: int, degree: float, speed: int | None = None) -> None:
        """Move a single joint (0-5) to the given degree."""
        speed = speed or self._default_speed
        self._client.write_angle(joint_id, degree, speed)

    def stop(self) -> None:
        """Immediately stop all motion."""
        self._client.task_stop()

    def wait_done(self) -> None:
        """Block until the robot finishes the current motion command."""
        self._client.command_wait_done()

    # -- High-level motion -------------------------------------------------

    def move(
        self,
        coords: Sequence[float] | Pose6D | dict[str, float],
        *,
        speed: int | None = None,
        normalize_rotation: bool = True,
        confirm_target: bool = True,
        settle_timeout_s: float = DEFAULT_MOVE_SETTLE_TIMEOUT_S,
        position_tolerance_mm: float = DEFAULT_MOVE_POSITION_TOLERANCE_MM,
        rotation_tolerance_deg: float = DEFAULT_MOVE_ROTATION_TOLERANCE_DEG,
    ) -> Pose6D:
        """Move the TCP to an absolute Cartesian pose and return the actual pose.

        When ``normalize_rotation`` is True (default), the target's ``rx/ry/rz``
        are shifted by +/-360 degrees (within the [-180, 180] limit) to the
        representation closest to the arm's current pose. This prevents the
        ``+/-180`` Euler-angle singularity from sending the wrist the long way
        round (e.g. current rx=+179.99 and target rx=-180 represent the same
        physical orientation, but commanded naively the IK may rotate the
        wrist ~360 degrees instead of ~0).

        By default this also confirms the reported Cartesian pose reaches the
        requested target before returning. The firmware can briefly report the
        motion command as complete while a long physical move is still settling,
        so a coordinate readback loop is safer than relying on idle status only.
        """
        pose = Pose6D.from_any(coords)
        if normalize_rotation:
            pose = self._normalize_rotation_to_current(pose)
        self.send_coords(pose, speed=speed)
        self._wait_until_done()
        if confirm_target:
            actual = self._wait_until_pose_reached(
                pose,
                timeout=settle_timeout_s,
                position_tolerance_mm=position_tolerance_mm,
                rotation_tolerance_deg=rotation_tolerance_deg,
            )
        else:
            actual = self.get_pose()
        self._logger.info("Target: %s  Actual: %s", pose.as_list(), actual.as_list())
        return actual

    def _normalize_rotation_to_current(self, target: Pose6D) -> Pose6D:
        """Return target with rx/ry/rz adjusted to the short-path representation.

        For each rotational axis, picks whichever of ``target``, ``target+360``,
        or ``target-360`` lies inside the valid [-180, 180] range *and* is
        closest to the current pose. Translational axes are untouched.
        """
        try:
            current = self.get_pose()
        except Exception:
            return target

        def _closest(t: float, c: float) -> float:
            candidates = [t, t + 360.0, t - 360.0]
            valid = [v for v in candidates if -180.0 <= v <= 180.0]
            if not valid:
                return t
            return min(valid, key=lambda v: abs(v - c))

        new_rx = _closest(target.rx, current.rx)
        new_ry = _closest(target.ry, current.ry)
        new_rz = _closest(target.rz, current.rz)
        if (new_rx, new_ry, new_rz) == (target.rx, target.ry, target.rz):
            return target
        self._logger.info(
            "Normalized rotation to avoid 360-deg flip: "
            "rx %.3f->%.3f, ry %.3f->%.3f, rz %.3f->%.3f (current rx=%.3f ry=%.3f rz=%.3f)",
            target.rx, new_rx, target.ry, new_ry, target.rz, new_rz,
            current.rx, current.ry, current.rz,
        )
        return target._replace(rx=new_rx, ry=new_ry, rz=new_rz)

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
        """Move the TCP relative to its current position."""
        current = self.get_pose()
        target = Pose6D(
            current.x + dx,
            current.y + dy,
            current.z + dz,
            current.rx + drx,
            current.ry + dry,
            current.rz + drz,
        )
        return self.move(target, speed=speed)

    def scan(self, *, speed: int | None = None) -> None:
        """Move the robot to its configured scan Cartesian position."""
        spd = speed or self._default_speed
        self._logger.info("Scanning at Cartesian coords: %s", self._scan_coords)
        self.move(self._scan_coords, speed=spd)

    # -- Gripper -----------------------------------------------------------
    #
    # The Pro630 can be fitted with two very different end-effectors:
    #   * "Adaptive" gripper -> controlled via set_gripper_state(0/1, speed)
    #   * "Electric"  gripper -> controlled via set_ele_gripper_open/close()
    #
    # init_gripper() below calls init_ele_gripper(), so this driver targets
    # the ELECTRIC gripper by default. Previous versions of this class mixed
    # the two APIs (init electric, open/close adaptive) which caused
    # `arm.open_gripper()` to silently do nothing. Keep these consistent.
    #
    # If you have the adaptive gripper, use `set_gripper_value()` or call
    # `self._client.set_gripper_state()` directly.

    def _gripper_settle(self, settle_s: float | None) -> None:
        time.sleep(self._gripper_settle_s if settle_s is None else settle_s)

    def open_gripper(self, *, settle_s: float | None = None) -> None:
        """Open the electric gripper."""
        self._logger.debug("Opening electric gripper")
        self._client.set_ele_gripper_open()
        self._gripper_settle(settle_s)

    def close_gripper(self, *, settle_s: float | None = None) -> None:
        """Close the electric gripper."""
        self._logger.debug("Closing electric gripper")
        self._client.set_ele_gripper_close()
        self._gripper_settle(settle_s)

    def set_gripper_value(self, value: int, speed: int = 70) -> None:
        """Set the adaptive gripper opening (0 = closed, 100 = open).

        Only meaningful for the adaptive gripper; ignored by the electric one.
        """
        self._client.set_gripper_value(value, speed)

    def init_gripper(self) -> None:
        """Initialize the electric gripper.

        Must be called once per power-cycle before `open_gripper()` /
        `close_gripper()` will respond.
        """
        self._logger.debug("Initializing electric gripper")
        self._client.init_ele_gripper()
        # The firmware needs a moment after init before it accepts
        # open/close commands; skipping this delay causes the first
        # open/close to no-op.
        time.sleep(0.6)

    def release_gripper(self) -> None:
        """Release (de-energize) the gripper servo."""
        self._client.set_gripper_enabled(0)

    # -- Reset / safety ----------------------------------------------------

    def reset(self) -> None:
        """Clear errors, restart the robot, and move to the scan position."""
        self._logger.info("Resetting robot")
        self.clear_error()
        time.sleep(0.5)
        self._client.start_robot()
        time.sleep(2.0)
        self._client._state_on()
        time.sleep(1.0)
        self.scan()
        self._logger.info("Reset complete")

    def release_all_servos(self) -> None:
        """Disable torque on all joints (arm becomes free-moving)."""
        self._client.set_free_move_mode(True)

    def focus_all_servos(self) -> None:
        """Re-enable torque on all joints."""
        self._client.set_free_move_mode(False)

    # -- LED ---------------------------------------------------------------

    def set_color(self, r: int, g: int, b: int) -> None:
        """Set the end-effector LED color."""
        self._client.set_end_color(r, g, b)

    # -- Camera ------------------------------------------------------------

    def available_cameras(self) -> list[str]:
        """Return identifiers for configured cameras (Pi SSH and/or livestream)."""
        names: list[str] = []
        if self._camera is not None:
            names.append("pi")
        if self._stream_url is not None:
            names.append("livestream")
        if self._combined_viewer_url is not None:
            names.append("combined_viewer")
        return names

    def combined_viewer_url(self) -> str | None:
        """Return the base URL for the combined raw/YOLO camera viewer."""
        return self._combined_viewer_url

    def camera_urls(self) -> dict[str, str]:
        """Return raw and YOLO viewer endpoints exposed by the combined viewer."""
        urls: dict[str, str] = {}
        if self._stream_url is not None:
            urls["cam2_source"] = self._stream_url
        if self._combined_viewer_url is None:
            return urls

        base = self._combined_viewer_url.rstrip("/")
        urls.update(
            {
                "combined_viewer": base,
                "pi_raw_stream": f"{base}/pi_camera",
                "pi_yolo_stream": f"{base}/pi_camera_yolo",
                "pi_raw_snapshot": f"{base}/snapshot/pi_camera",
                "pi_yolo_snapshot": f"{base}/snapshot/pi_camera_yolo",
                "cam2_raw_stream": f"{base}/cam2",
                "cam2_yolo_stream": f"{base}/cam2_yolo",
                "cam2_raw_snapshot": f"{base}/snapshot/cam2",
                "cam2_yolo_snapshot": f"{base}/snapshot/cam2_yolo",
            }
        )
        return urls

    def capture_image(self, *, rotate: bool | None = None) -> str:
        """Capture using the Pi camera when configured; otherwise the livestream."""
        if self._camera is not None:
            cam = self._require_camera()
            if rotate is None:
                rotate = self._calibration.rotate_image_180
            return capture_pi_image(cam, rotate=rotate)
        if self._stream_url is not None:
            return self.capture_stream_image()
        raise RuntimeError(
            "No camera configured. Pass camera=CameraConfig(...) and/or "
            "stream_url='rtsp://...:8554/livestream'."
        )

    def capture_stream_image(
        self,
        output_path: str | Path = "snapshot.jpg",
        *,
        stream_url: str | None = None,
    ) -> str:
        """Capture one frame from an RTSP or OpenCV URL and return the written path.

        Uses the ``stream_url`` argument, then the constructor ``stream_url=`` value,
        then ``DEFAULT_STREAM_URL`` from ``cv/function/function.py``.
        """
        url = stream_url if stream_url is not None else self._stream_url
        if url is None:
            url = DEFAULT_STREAM_URL
        out = Path(output_path)
        ok = capture_snapshot(url, out)
        if not ok:
            raise RuntimeError(f"Stream capture failed for {url!r} (open, read, or write)")
        return str(out)

    def pixel_to_robot_offset(
        self,
        cx: int,
        cy: int,
        image_center_x: int,
        image_center_y: int,
        z_touch: float,
        *,
        z_cam: float | None = None,
    ) -> tuple[float, float, float]:
        """Convert a pixel offset from image center to robot-frame XY mm deltas.

        Returns (delta_x_mm, delta_y_mm, mm_per_pixel).
        """
        if z_cam is None:
            z_cam = self.get_coords()[2]

        return calculate_pixel_to_robot_offset(
            calibration=self._calibration,
            cx=cx,
            cy=cy,
            image_center_x=image_center_x,
            image_center_y=image_center_y,
            z_cam=z_cam,
            z_touch=z_touch,
        )

    # -- Private helpers ---------------------------------------------------

    def _require_camera(self) -> CameraConfig:
        if self._camera is None:
            raise RuntimeError(
                "Camera not configured. Pass camera=CameraConfig(...) to the constructor."
            )
        return self._camera

    def _wait_until_done(
        self,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
        initial_delay: float = 0.4,
        stable_polls: int = 3,
    ) -> None:
        """Block until the robot finishes moving.

        Uses a polling loop instead of the upstream ``command_wait_done()``
        which has a broken ``except socket.timeout`` in pymycobot 4.0.4.

        There is a short window between ``write_coords`` being sent over TCP
        and the firmware actually starting the motion, during which
        ``check_running()`` still reports "not running". Polling immediately
        therefore races: if the first poll hits that window the method
        returns right away and the caller fires the next command while the
        arm has not yet moved. That causes stacked/cancelled commands and,
        at rx=+-180 singularities, wildly unexpected paths.

        Mitigation:
          * ``initial_delay`` gives the firmware time to kick off the motion
            before we ever poll.
          * ``stable_polls`` consecutive "not running" readings are required
            before we declare the motion complete; transient False readings
            (or exceptions) reset the counter.
        """
        time.sleep(initial_delay)
        deadline = time.monotonic() + timeout
        idle_polls = 0
        while time.monotonic() < deadline:
            try:
                running = self._client.check_running()
            except Exception:
                running = True  # unknown -> assume still moving
            if running:
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= stable_polls:
                    return
            time.sleep(poll_interval)
        self._logger.warning("_wait_until_done timed out after %.1fs", timeout)

    def _wait_until_pose_reached(
        self,
        target: Pose6D,
        *,
        timeout: float = DEFAULT_MOVE_SETTLE_TIMEOUT_S,
        poll_interval: float = 0.5,
        position_tolerance_mm: float = DEFAULT_MOVE_POSITION_TOLERANCE_MM,
        rotation_tolerance_deg: float = DEFAULT_MOVE_ROTATION_TOLERANCE_DEG,
        stable_polls: int = 2,
    ) -> Pose6D:
        """Poll coordinates until the robot reports it has reached ``target``."""
        deadline = time.monotonic() + timeout
        stable_count = 0
        last_pose: Pose6D | None = None
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                actual = self.get_pose()
                last_pose = actual
                last_error = None
            except Exception as exc:
                last_error = exc
                stable_count = 0
                time.sleep(poll_interval)
                continue

            if self._pose_within_tolerance(
                actual,
                target,
                position_tolerance_mm=position_tolerance_mm,
                rotation_tolerance_deg=rotation_tolerance_deg,
            ):
                stable_count += 1
                if stable_count >= stable_polls:
                    return actual
            else:
                stable_count = 0
            time.sleep(poll_interval)

        if last_pose is not None:
            raise TimeoutError(
                "Timed out waiting for Elephant to reach target pose. "
                f"target={target.as_list()} actual={last_pose.as_list()} "
                f"position_tolerance_mm={position_tolerance_mm} "
                f"rotation_tolerance_deg={rotation_tolerance_deg}"
            )
        raise TimeoutError(
            "Timed out waiting for Elephant target pose; no coordinate readback "
            f"was available. Last error: {last_error}"
        )

    @classmethod
    def _pose_within_tolerance(
        cls,
        actual: Pose6D,
        target: Pose6D,
        *,
        position_tolerance_mm: float,
        rotation_tolerance_deg: float,
    ) -> bool:
        return (
            abs(actual.x - target.x) <= position_tolerance_mm
            and abs(actual.y - target.y) <= position_tolerance_mm
            and abs(actual.z - target.z) <= position_tolerance_mm
            and cls._angle_delta_deg(actual.rx, target.rx) <= rotation_tolerance_deg
            and cls._angle_delta_deg(actual.ry, target.ry) <= rotation_tolerance_deg
            and cls._angle_delta_deg(actual.rz, target.rz) <= rotation_tolerance_deg
        )

    @staticmethod
    def _angle_delta_deg(first: float, second: float) -> float:
        """Return the shortest absolute angular distance in degrees."""
        return abs((first - second + 180.0) % 360.0 - 180.0)

    @staticmethod
    def _sanitize_zeros(coords: list[float], eps: float = 0.001) -> list[float]:
        """Replace exact 0.0 values with a tiny epsilon.

        The Pro630 firmware interprets 0.0 in ``set_coords`` as "skip this
        axis" rather than "move to 0".  Nudging to ±eps avoids this.
        """
        return [eps if v == 0.0 else v for v in coords]

    @staticmethod
    def _validate_coords(pose: Pose6D) -> None:
        for name, (lo, hi) in COORD_RANGE.items():
            val = getattr(pose, name)
            if not (lo <= val <= hi):
                raise ValueError(
                    f"Coordinate {name}={val:.2f} is outside the allowed range [{lo}, {hi}]"
                )
