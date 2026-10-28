"""Tests for RTSP snapshot capture."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from elephant_driver.cv.function.function import DEFAULT_STREAM_URL, HLS_URL, RTSP_URL, capture_snapshot
from elephant_driver.cv.function.function import _capture_url_for


class TestCaptureSnapshot(unittest.TestCase):
    @patch("elephant_driver.cv.function.function.socket.create_connection")
    @patch("elephant_driver.cv.function.function.cv2.imwrite")
    @patch("elephant_driver.cv.function.function.cv2.VideoCapture")
    def test_successful_capture(
        self,
        mock_video_capture: MagicMock,
        mock_imwrite: MagicMock,
        mock_create_connection: MagicMock,
    ) -> None:
        mock_create_connection.return_value.__enter__.return_value = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, MagicMock())
        mock_imwrite.return_value = True
        mock_video_capture.return_value = mock_cap

        result = capture_snapshot(RTSP_URL, "snapshot.jpg")

        self.assertTrue(result)
        mock_video_capture.assert_called_once_with()
        mock_cap.open.assert_called_once_with(RTSP_URL)
        mock_imwrite.assert_called_once()
        mock_cap.release.assert_called_once()

    @patch("elephant_driver.cv.function.function.socket.create_connection")
    @patch("elephant_driver.cv.function.function.cv2.VideoCapture")
    def test_stream_not_opened(
        self,
        mock_video_capture: MagicMock,
        mock_create_connection: MagicMock,
    ) -> None:
        mock_create_connection.return_value.__enter__.return_value = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_video_capture.return_value = mock_cap

        result = capture_snapshot(RTSP_URL)

        self.assertFalse(result)
        mock_cap.open.assert_called_once_with(RTSP_URL)
        mock_cap.read.assert_not_called()
        mock_cap.release.assert_called_once()

    @patch("elephant_driver.cv.function.function.socket.create_connection")
    @patch("elephant_driver.cv.function.function.cv2.imwrite")
    @patch("elephant_driver.cv.function.function.cv2.VideoCapture")
    def test_frame_read_failure(
        self,
        mock_video_capture: MagicMock,
        mock_imwrite: MagicMock,
        mock_create_connection: MagicMock,
    ) -> None:
        mock_create_connection.return_value.__enter__.return_value = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_video_capture.return_value = mock_cap

        result = capture_snapshot(RTSP_URL)

        self.assertFalse(result)
        mock_imwrite.assert_not_called()
        mock_cap.release.assert_called_once()

    @patch("elephant_driver.cv.function.function.socket.create_connection")
    @patch("elephant_driver.cv.function.function.cv2.imwrite")
    @patch("elephant_driver.cv.function.function.cv2.VideoCapture")
    def test_custom_output_name(
        self,
        mock_video_capture: MagicMock,
        mock_imwrite: MagicMock,
        mock_create_connection: MagicMock,
    ) -> None:
        mock_create_connection.return_value.__enter__.return_value = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, MagicMock())
        mock_imwrite.return_value = True
        mock_video_capture.return_value = mock_cap

        result = capture_snapshot(RTSP_URL, "custom_output.jpg")

        self.assertTrue(result)
        args, _ = mock_imwrite.call_args
        self.assertEqual(args[0], "custom_output.jpg")

    @patch("elephant_driver.cv.function.function.cv2.VideoCapture")
    def test_unreachable_rtsp_endpoint_fails_before_opencv(
        self,
        mock_video_capture: MagicMock,
    ) -> None:
        result = capture_snapshot("rtsp://127.0.0.1:1/livestream", timeout_ms=100)

        self.assertFalse(result)
        mock_video_capture.assert_not_called()

    def test_webrtc_viewer_url_maps_to_hls_capture_url(self) -> None:
        result = _capture_url_for("http://<camera-host>:8889/livestream/")

        self.assertEqual(result, "http://<camera-host>:8888/livestream/index.m3u8")

    def test_default_stream_url_is_rtsp_url(self) -> None:
        self.assertEqual(DEFAULT_STREAM_URL, RTSP_URL)

    def test_hls_url_remains_available_for_explicit_capture(self) -> None:
        self.assertEqual(HLS_URL, "http://<camera-host>:8888/livestream/index.m3u8")


if __name__ == "__main__":
    unittest.main()
