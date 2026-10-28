from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import cv2

RTSP_URL = "rtsp://<camera-host>:8554/livestream"
HLS_URL = "http://<camera-host>:8888/livestream/index.m3u8"
WEBRTC_VIEWER_URL = "http://<camera-host>:8889/livestream/"
DEFAULT_STREAM_URL = RTSP_URL
# Backward-compatible name used by existing imports/tests.
DEFAULT_RTSP_URL = RTSP_URL


def capture_snapshot(
    url: str = DEFAULT_STREAM_URL,
    output_name: str | Path = "snapshot.jpg",
    *,
    timeout_ms: int = 5_000,
    preflight: bool = True,
) -> bool:
    """Capture one frame from the livestream into ``output_name``.

    OpenCV can read the MediaMTX HLS URL on port 8888 or the RTSP URL on
    port 8554. If the WebRTC viewer URL on port 8889 is passed, it is mapped
    to the corresponding HLS URL before capture. The default uses RTSP for
    lower latency, but callers can still pass ``HLS_URL`` explicitly.
    """
    url = _capture_url_for(url)
    if url.startswith("rtsp://"):
        if preflight and not _rtsp_endpoint_reachable(url, timeout_ms=timeout_ms):
            return False

        timeout_us = max(1, int(timeout_ms)) * 1_000
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            f"rtsp_transport;tcp|stimeout;{timeout_us}",
        )

    cap = cv2.VideoCapture()
    try:
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
        cap.open(url)

        if not cap.isOpened():
            return False

        ret, frame = cap.read()
        if not ret or frame is None:
            return False

        output = Path(output_name)
        output.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(output), frame))
    finally:
        cap.release()


def _capture_url_for(url: str) -> str:
    """Return an OpenCV-readable URL for known MediaMTX viewer URLs."""
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.port == 8889:
        path = parsed.path.rstrip("/")
        hls_path = f"{path}/index.m3u8"
        return urlunparse(
            (
                parsed.scheme,
                f"{parsed.hostname}:8888",
                hls_path,
                "",
                "",
                "",
            )
        )
    return url


def _rtsp_endpoint_reachable(url: str, *, timeout_ms: int) -> bool:
    parsed = urlparse(url)
    if parsed.hostname is None:
        return False

    timeout_s = max(0.001, int(timeout_ms) / 1_000)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 554), timeout=timeout_s):
            return True
    except OSError:
        return False
