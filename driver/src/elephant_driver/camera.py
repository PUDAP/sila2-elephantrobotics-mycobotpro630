"""Pi camera capture and calibration helpers for the Elephant driver."""

from __future__ import annotations

import logging
import os
import time
import urllib.request
from dataclasses import dataclass

import cv2
import paramiko

logger = logging.getLogger(__name__)


@dataclass
class CameraCalibration:
    """Camera-to-robot calibration parameters.

    These values are determined during a one-time calibration procedure where
    a known-size target is placed on the table at *table_z* and the camera
    captures it from *cal_z*.
    """

    cal_z: float = 200.0
    table_z: float = 130.0
    mm_per_pixel_at_cal_z: float = 0.266
    camera_to_tcp_x: float = -71.0
    camera_to_tcp_y: float = 0.0
    rotate_image_180: bool = True

    @property
    def cal_distance(self) -> float:
        """Camera-to-plane distance during calibration."""
        return self.cal_z - self.table_z


@dataclass
class CameraConfig:
    """SSH connection and path settings for the on-robot Pi camera."""

    pi_ip: str = ""
    username: str = "pi"
    password: str = "elephant"
    remote_capture_cmd: str = "python3 capture_frame.py"
    remote_image_path: str = "/home/pi/frame.jpg"
    remote_stream_python: str = "/home/pi/.pyenv/shims/python3"
    remote_stream_port: int = 5000
    remote_stream_script_path: str = "/home/pi/robot_pi_server_auto.py"
    remote_stream_log_path: str = "/home/pi/robot_pi_server_auto.log"
    local_image_dir: str = "."
    local_raw_filename: str = "frame.jpg"
    local_optimized_filename: str = "optimized.jpg"

    @property
    def local_raw_path(self) -> str:
        return os.path.join(self.local_image_dir, self.local_raw_filename)

    @property
    def local_optimized_path(self) -> str:
        return os.path.join(self.local_image_dir, self.local_optimized_filename)

    @property
    def stream_url(self) -> str:
        return f"http://{self.pi_ip}:{self.remote_stream_port}/pi"

    @property
    def stream_snapshot_url(self) -> str:
        return f"http://{self.pi_ip}:{self.remote_stream_port}/snapshot/pi"


def url_ok(url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except Exception:
        return False


def wait_for_url(url: str, *, timeout_s: float = 20.0, poll_s: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if url_ok(url, timeout=2.0):
            return True
        time.sleep(poll_s)
    return False


def start_pi_camera_stream_server(
    camera: CameraConfig,
    *,
    rotate: bool = True,
    force_restart: bool = True,
    wait_timeout_s: float = 35.0,
) -> str:
    """Start the Pi-hosted camera Flask livestream server and return its URL."""
    robot_pi_code = r'''
import cv2
import logging
import threading
import time
from flask import Flask, Response

logging.getLogger("werkzeug").setLevel(logging.ERROR)

PORT = __PORT__
PI_CAMERA_INDEX = 0
ROTATE_180 = __ROTATE_180__

app = Flask(__name__)


class CameraStream:
    def __init__(self, index):
        self.index = index
        self.lock = threading.Lock()
        self.frame = None
        self.cap = self.open_cam()
        threading.Thread(target=self.update, daemon=True).start()

    def open_cam(self):
        cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open robot Pi camera at index {self.index}")
        return cap

    def update(self):
        while True:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                print("[PI CAMERA ERROR] reconnecting...", flush=True)
                try:
                    self.cap.release()
                except Exception:
                    pass
                time.sleep(1)
                self.cap = self.open_cam()
                continue

            if ROTATE_180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                label = "ROBOT PI CAMERA TOP ROTATED 180"
            else:
                label = "ROBOT PI CAMERA TOP"

            cv2.putText(
                frame,
                label,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            with self.lock:
                self.frame = frame.copy()
            time.sleep(0.03)

    def get_jpeg(self, quality=90):
        with self.lock:
            if self.frame is None:
                return None
            frame = self.frame.copy()

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return None
        return buf.tobytes()


pi_camera = None
while pi_camera is None:
    try:
        pi_camera = CameraStream(PI_CAMERA_INDEX)
    except Exception as exc:
        print(f"[PI CAMERA START ERROR] {exc}", flush=True)
        time.sleep(2)


def gen_stream():
    while True:
        jpeg = pi_camera.get_jpeg()
        if jpeg is None:
            time.sleep(0.1)
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"


@app.route("/")
def index():
    return """
    <html>
    <body style="background:black;color:white;text-align:center;font-family:Arial;">
        <h1>Robot Pi Camera Server Running</h1>
        <img src="/pi" width="640" style="border:3px solid white;">
        <p><a href="/pi" style="color:cyan;">Robot Pi Livestream</a></p>
        <p><a href="/snapshot/pi" style="color:cyan;">Robot Pi Snapshot</a></p>
    </body>
    </html>
    """


@app.route("/pi")
def pi_route():
    return Response(gen_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot/pi")
def snapshot_pi():
    jpeg = pi_camera.get_jpeg(quality=95)
    if jpeg is None:
        return "No Pi camera frame", 503
    return Response(jpeg, mimetype="image/jpeg")


if __name__ == "__main__":
    print(f"Robot Pi camera livestream running on port {PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
'''
    robot_pi_code = (
        robot_pi_code.replace("__PORT__", str(int(camera.remote_stream_port)))
        .replace("__ROTATE_180__", "True" if rotate else "False")
    )

    if not force_restart and url_ok(camera.stream_snapshot_url, timeout=2.0):
        return camera.stream_url

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(camera.pi_ip, username=camera.username, password=camera.password, timeout=15)
    try:
        sftp = ssh.open_sftp()
        try:
            with sftp.file(camera.remote_stream_script_path, "w") as remote_file:
                remote_file.write(robot_pi_code)
        finally:
            sftp.close()

        if force_restart:
            ssh.exec_command("pkill -f 'robot_.*server.*\\.py' || true")
            ssh.exec_command("pkill -f robot_pi_server_auto.py || true")
            ssh.exec_command("pkill -f logitech_stream.py || true")
            ssh.exec_command("pkill -f capture_frame.py || true")
            time.sleep(4.0)

        cmd = (
            f"nohup {camera.remote_stream_python} {camera.remote_stream_script_path} "
            f"> {camera.remote_stream_log_path} 2>&1 &"
        )
        ssh.exec_command(cmd)
    finally:
        ssh.close()

    if not wait_for_url(camera.stream_snapshot_url, timeout_s=wait_timeout_s):
        raise RuntimeError(
            "Pi camera livestream server did not become reachable at "
            f"{camera.stream_snapshot_url}. Check {camera.remote_stream_log_path} on the Pi."
        )
    return camera.stream_url


def capture_pi_image(camera: CameraConfig, *, rotate: bool = True) -> str:
    """SSH into the Pi, capture a frame, and return the local optimized path."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(camera.pi_ip, username=camera.username, password=camera.password)
    try:
        logger.info("Capturing image via SSH (%s)", camera.pi_ip)
        _stdin, stdout, stderr = ssh.exec_command(camera.remote_capture_cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode()
            raise RuntimeError(f"Remote capture failed (exit {exit_status}): {err}")

        os.makedirs(camera.local_image_dir, exist_ok=True)
        raw_path = camera.local_raw_path
        if os.path.exists(raw_path):
            os.remove(raw_path)

        ftp = ssh.open_sftp()
        try:
            ftp.get(camera.remote_image_path, raw_path)
        finally:
            ftp.close()
    finally:
        ssh.close()

    # Same 180° convention as faythebest2.py (cv2.rotate + ROTATE_180 on the Pi camera path).
    img = cv2.imread(raw_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Failed to read Pi camera JPEG: {raw_path}")
    if rotate:
        img = cv2.rotate(img, cv2.ROTATE_180)
    opt_path = camera.local_optimized_path
    if not cv2.imwrite(
        opt_path,
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), 95],
    ):
        raise RuntimeError(f"Failed to write optimized JPEG: {opt_path}")
    logger.info("Image saved: %s", opt_path)
    return opt_path


def calculate_pixel_to_robot_offset(
    *,
    calibration: CameraCalibration,
    cx: int,
    cy: int,
    image_center_x: int,
    image_center_y: int,
    z_cam: float,
    z_touch: float,
) -> tuple[float, float, float]:
    """Convert a pixel offset from image center to robot-frame XY mm deltas.

    Returns (delta_x_mm, delta_y_mm, mm_per_pixel).
    """
    camera_to_object = z_cam - z_touch
    if calibration.cal_distance <= 0:
        raise ValueError("cal_z must be > table_z")
    if camera_to_object <= 0:
        raise ValueError(f"Camera Z ({z_cam}) must be above touch Z ({z_touch})")

    scale_ratio = camera_to_object / calibration.cal_distance
    mm_per_pixel = calibration.mm_per_pixel_at_cal_z * scale_ratio

    dx_px = cx - image_center_x
    dy_px = cy - image_center_y

    delta_x_mm = -(dy_px) * mm_per_pixel + calibration.camera_to_tcp_x
    delta_y_mm = (dx_px) * mm_per_pixel + calibration.camera_to_tcp_y

    logger.debug(
        "pixel_to_robot: px(%d,%d) -> mm(%.2f, %.2f) @ %.4f mm/px",
        dx_px,
        dy_px,
        delta_x_mm,
        delta_y_mm,
        mm_per_pixel,
    )
    return delta_x_mm, delta_y_mm, mm_per_pixel
