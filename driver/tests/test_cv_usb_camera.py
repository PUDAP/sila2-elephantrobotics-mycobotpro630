"""Tests for USB camera capture helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import cv2

from elephant_driver.cv import UsbCamera1


class TestUsbCamera(unittest.TestCase):
    @patch("elephant_driver.cv.usb_camera.cv2.imwrite")
    @patch("elephant_driver.cv.usb_camera.cv2.VideoCapture")
    def test_usb_camera_capture(self, mock_video_capture: MagicMock, mock_imwrite: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, MagicMock())
        mock_imwrite.return_value = True
        mock_video_capture.return_value = mock_cap

        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "capture.jpg"
            camera = UsbCamera1(camera_index=2, camera_resolution=(640, 480), camera_name="top_camera")

            result = camera.capture_image(output_path)

        self.assertEqual(result, str(output_path))
        mock_video_capture.assert_called_once_with(2)
        mock_cap.set.assert_any_call(cv2.CAP_PROP_FRAME_WIDTH, 640)
        mock_cap.set.assert_any_call(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        mock_imwrite.assert_called_once()
        mock_cap.release.assert_called_once()

    @patch("elephant_driver.cv.usb_camera.cv2.VideoCapture")
    def test_usb_camera_open_failure(self, mock_video_capture: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_video_capture.return_value = mock_cap

        camera = UsbCamera1(camera_index=9, camera_name="missing_camera")

        with self.assertRaisesRegex(RuntimeError, "Could not open missing_camera"):
            camera.capture_image()

        mock_cap.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
