"""Combined Pi/CAM2 raw and YOLO viewer for Elephant edge services."""

from __future__ import annotations

import argparse
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from flask import Flask, Response

from .camera import CameraConfig, capture_pi_image, start_pi_camera_stream_server
from .cv import DEFAULT_STREAM_URL, capture_snapshot
from .elephant import (
    DEFAULT_COMBINED_VIEWER_HOST,
    DEFAULT_COMBINED_VIEWER_PORT,
    DEFAULT_COMBINED_VIEWER_URL,
)


PI_CAMERA_RAW_STREAM_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/pi_camera"
PI_CAMERA_YOLO_STREAM_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/pi_camera_yolo"
PI_CAMERA_RAW_SNAPSHOT_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/snapshot/pi_camera"
PI_CAMERA_YOLO_SNAPSHOT_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/snapshot/pi_camera_yolo"

CAM2_RAW_STREAM_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/cam2"
CAM2_YOLO_STREAM_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/cam2_yolo"
CAM2_RAW_SNAPSHOT_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/snapshot/cam2"
CAM2_YOLO_SNAPSHOT_URL = f"{DEFAULT_COMBINED_VIEWER_URL}/snapshot/cam2_yolo"


@dataclass(frozen=True)
class StreamUrls:
    combined_viewer: str = DEFAULT_COMBINED_VIEWER_URL
    pi_raw_stream: str = PI_CAMERA_RAW_STREAM_URL
    pi_yolo_stream: str = PI_CAMERA_YOLO_STREAM_URL
    pi_raw_snapshot: str = PI_CAMERA_RAW_SNAPSHOT_URL
    pi_yolo_snapshot: str = PI_CAMERA_YOLO_SNAPSHOT_URL
    cam2_raw_stream: str = CAM2_RAW_STREAM_URL
    cam2_yolo_stream: str = CAM2_YOLO_STREAM_URL
    cam2_raw_snapshot: str = CAM2_RAW_SNAPSHOT_URL
    cam2_yolo_snapshot: str = CAM2_YOLO_SNAPSHOT_URL


@dataclass
class ViewerConfig:
    pi_ip: str
    pi_username: str = "pi"
    pi_password: str = "elephant"
    pi_local_image_dir: str = "."
    pi_rotate_180: bool = True
    cam2_stream_url: str = DEFAULT_STREAM_URL
    yolo_model_path: str | None = None
    yolo_conf: float = 0.25
    yolo_iou: float = 0.45
    yolo_imgsz: int = 640
    pi_poll_s: float = 0.03
    cam2_poll_s: float = 0.12
    start_pi_stream: bool = True
    pi_stream_port: int = 5000

    def pi_camera_config(self) -> CameraConfig:
        return CameraConfig(
            pi_ip=self.pi_ip,
            username=self.pi_username,
            password=self.pi_password,
            remote_stream_port=self.pi_stream_port,
            local_image_dir=self.pi_local_image_dir,
            local_raw_filename="pi_camera_raw.jpg",
            local_optimized_filename="pi_camera_optimized.jpg",
        )


class FrameSource:
    def __init__(self, name: str, capture_fn: Callable[[], str | None], poll_s: float) -> None:
        self.name = name
        self.capture_fn = capture_fn
        self.poll_s = float(poll_s)
        self.frame = None
        self.last_error = ""
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                image_path = self.capture_fn()
                if image_path:
                    frame = cv2.imread(str(image_path))
                    if frame is not None:
                        with self._lock:
                            self.frame = frame
                            self.last_error = ""
            except Exception as exc:
                with self._lock:
                    self.last_error = str(exc)
            time.sleep(self.poll_s)

    def get_frame(self):
        with self._lock:
            if self.frame is None:
                return None
            return self.frame.copy()


class CvStreamSource:
    """Reads frames from a persistent OpenCV livestream connection."""

    def __init__(self, name: str, url: str, poll_s: float, *, timeout_ms: int = 5_000) -> None:
        self.name = name
        self.url = url
        self.poll_s = float(poll_s)
        self.timeout_ms = int(timeout_ms)
        self.frame = None
        self.last_error = ""
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open_capture(self):
        if self.url.startswith("rtsp://"):
            timeout_us = max(1, self.timeout_ms) * 1_000
            os.environ.setdefault(
                "OPENCV_FFMPEG_CAPTURE_OPTIONS",
                f"rtsp_transport;tcp|stimeout;{timeout_us}",
            )

        cap = cv2.VideoCapture()
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.timeout_ms)
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.timeout_ms)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.open(self.url)
        return cap

    def _loop(self) -> None:
        cap = None
        while True:
            try:
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    cap = self._open_capture()
                    if not cap.isOpened():
                        raise RuntimeError(f"Could not open {self.url}")

                ok, frame = cap.read()
                if not ok or frame is None:
                    raise RuntimeError(f"Could not read frame from {self.url}")

                with self._lock:
                    self.frame = frame.copy()
                    self.last_error = ""
            except Exception as exc:
                with self._lock:
                    self.last_error = str(exc)
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.5)
            time.sleep(self.poll_s)

    def get_frame(self):
        with self._lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def save_snapshot(self, output_path: str | Path) -> bool:
        frame = self.get_frame()
        if frame is not None:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            return bool(cv2.imwrite(str(output), frame))
        return capture_snapshot(self.url, output_path)


class PiCameraStreamSource:
    """Reads live Pi camera frames from the Pi-hosted stream, with SSH snapshot fallback."""

    def __init__(self, camera: CameraConfig, *, rotate: bool, poll_s: float, start_stream: bool) -> None:
        self.camera = camera
        self.rotate = bool(rotate)
        self.poll_s = float(poll_s)
        self.start_stream = bool(start_stream)
        self.frame = None
        self.last_error = ""
        self._stream_start_attempted = False
        self._lock = threading.Lock()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _ensure_stream_started(self) -> None:
        if self._stream_start_attempted or not self.start_stream:
            return
        self._stream_start_attempted = True
        try:
            start_pi_camera_stream_server(self.camera, rotate=self.rotate, force_restart=True)
        except Exception as exc:
            with self._lock:
                self.last_error = f"Pi stream startup failed: {exc}"

    def _read_stream_snapshot(self):
        with urllib.request.urlopen(self.camera.stream_snapshot_url, timeout=2.0) as response:
            data = response.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def _read_ssh_snapshot(self):
        image_path = capture_pi_image(self.camera, rotate=self.rotate)
        return cv2.imread(str(image_path))

    def _loop(self) -> None:
        while True:
            self._ensure_stream_started()
            try:
                frame = self._read_stream_snapshot()
                if frame is None:
                    raise RuntimeError("Pi stream snapshot returned no decodable frame")
                with self._lock:
                    self.frame = frame
                    self.last_error = ""
            except Exception as stream_exc:
                try:
                    frame = self._read_ssh_snapshot()
                    if frame is not None:
                        with self._lock:
                            self.frame = frame
                            self.last_error = f"Using SSH snapshot fallback: {stream_exc}"
                    else:
                        raise RuntimeError("SSH snapshot returned no frame")
                except Exception as fallback_exc:
                    with self._lock:
                        self.last_error = f"Pi stream failed: {stream_exc}; fallback failed: {fallback_exc}"
                    time.sleep(0.5)
            time.sleep(self.poll_s)

    def get_frame(self):
        with self._lock:
            if self.frame is None:
                return None
            return self.frame.copy()


class YoloOverlay:
    def __init__(self, model_path: str | None, *, conf: float, iou: float, imgsz: int) -> None:
        self.model_path = model_path
        self.conf = float(conf)
        self.iou = float(iou)
        self.imgsz = int(imgsz)
        self._model = None

    def _load(self):
        if self.model_path is None:
            return None
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
        return self._model

    def draw(self, frame):
        model = self._load()
        if model is None:
            return frame
        result = model.predict(
            frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            verbose=False,
        )[0]
        return result.plot()


def _encode_jpeg(frame, quality: int = 85) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return None
    return buf.tobytes()


def _mjpeg(source: FrameSource, overlay: YoloOverlay | None = None):
    while True:
        frame = source.get_frame()
        if frame is None:
            frame = 255 * cv2.UMat(360, 640, cv2.CV_8UC3).get()
            cv2.putText(
                frame,
                f"Waiting for {source.name}",
                (24, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
        elif overlay is not None:
            frame = overlay.draw(frame)

        jpeg = _encode_jpeg(frame)
        if jpeg is not None:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        time.sleep(0.03)


def create_app(config: ViewerConfig) -> Flask:
    app = Flask(__name__)
    workdir = Path(config.pi_local_image_dir)
    workdir.mkdir(parents=True, exist_ok=True)

    pi_config = config.pi_camera_config()
    pi_source = PiCameraStreamSource(
        pi_config,
        rotate=config.pi_rotate_180,
        poll_s=config.pi_poll_s,
        start_stream=config.start_pi_stream,
    )
    cam2_source = CvStreamSource("CAM2 CV livestream", config.cam2_stream_url, config.cam2_poll_s)
    yolo = YoloOverlay(
        config.yolo_model_path,
        conf=config.yolo_conf,
        iou=config.yolo_iou,
        imgsz=config.yolo_imgsz,
    )

    @app.route("/")
    def index():
        return f"""
        <html>
        <head><title>Elephant Combined Viewer</title></head>
        <body style="background:#111;color:white;font-family:Arial,sans-serif;">
            <h1>Elephant Combined Viewer</h1>
            <p>CAM2 source: <code>{config.cam2_stream_url}</code></p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                <section><h2>Pi Camera Raw</h2><img src="/pi_camera" width="100%"></section>
                <section><h2>Pi Camera YOLO</h2><img src="/pi_camera_yolo" width="100%"></section>
                <section><h2>CAM2 Raw</h2><img src="/cam2" width="100%"></section>
                <section><h2>CAM2 YOLO</h2><img src="/cam2_yolo" width="100%"></section>
            </div>
        </body>
        </html>
        """

    @app.route("/pi_camera")
    def pi_camera():
        return Response(_mjpeg(pi_source), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/pi_camera_yolo")
    def pi_camera_yolo():
        return Response(_mjpeg(pi_source, yolo), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/cam2")
    def cam2():
        return Response(_mjpeg(cam2_source), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/cam2_yolo")
    def cam2_yolo():
        return Response(_mjpeg(cam2_source, yolo), mimetype="multipart/x-mixed-replace; boundary=frame")

    def snapshot_response(source: FrameSource, overlay: YoloOverlay | None = None):
        frame = source.get_frame()
        if frame is None:
            return "No frame available", 503
        if overlay is not None:
            frame = overlay.draw(frame)
        jpeg = _encode_jpeg(frame, quality=95)
        if jpeg is None:
            return "Could not encode frame", 500
        return Response(jpeg, mimetype="image/jpeg")

    @app.route("/snapshot/pi_camera")
    def snapshot_pi_camera():
        return snapshot_response(pi_source)

    @app.route("/snapshot/pi_camera_yolo")
    def snapshot_pi_camera_yolo():
        return snapshot_response(pi_source, yolo)

    @app.route("/snapshot/cam2")
    def snapshot_cam2():
        return snapshot_response(cam2_source)

    @app.route("/snapshot/cam2_yolo")
    def snapshot_cam2_yolo():
        return snapshot_response(cam2_source, yolo)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Elephant combined raw/YOLO camera viewer.")
    parser.add_argument("--pi-ip", required=True)
    parser.add_argument("--pi-username", default="pi")
    parser.add_argument("--pi-password", default="elephant")
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--cam2-stream-url", default=DEFAULT_STREAM_URL)
    parser.add_argument("--yolo-model-path")
    parser.add_argument("--pi-rotate-180", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--start-pi-stream", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pi-stream-port", type=int, default=5000)
    parser.add_argument("--host", default=DEFAULT_COMBINED_VIEWER_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_COMBINED_VIEWER_PORT)
    args = parser.parse_args()

    config = ViewerConfig(
        pi_ip=args.pi_ip,
        pi_username=args.pi_username,
        pi_password=args.pi_password,
        pi_local_image_dir=args.workdir,
        pi_rotate_180=args.pi_rotate_180,
        cam2_stream_url=args.cam2_stream_url,
        yolo_model_path=args.yolo_model_path,
        start_pi_stream=args.start_pi_stream,
        pi_stream_port=args.pi_stream_port,
    )
    app = create_app(config)
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
