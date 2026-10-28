"""Tests for Elephant USB camera integration."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from elephant_driver import CameraConfig, Elephant, UsbCamera1


class TestElephantUsbCamera(unittest.TestCase):
    def _make_elephant(self, **kwargs: object) -> Elephant:
        patcher = patch("elephant_driver.elephant.ElephantRobot")
        self.addCleanup(patcher.stop)
        mock_robot = patcher.start()
        mock_client = MagicMock()
        mock_client.start_client.return_value = True
        mock_client.state_check.return_value = True
        mock_robot.return_value = mock_client
        return Elephant(ip="127.0.0.1", **kwargs)

    def test_available_cameras_includes_usb_camera_name(self) -> None:
        usb_camera = UsbCamera1(camera_index=1, camera_name="top_camera")

        arm = self._make_elephant(usb_camera=usb_camera)

        self.assertEqual(arm.available_cameras(), ["top_camera"])

    def test_capture_usb_image_delegates_to_configured_usb_camera(self) -> None:
        usb_camera = MagicMock(spec=UsbCamera1)
        usb_camera.camera_name = "top_camera"
        usb_camera.capture_image.return_value = "usb.jpg"
        output_path = Path("captures") / "usb.jpg"

        arm = self._make_elephant(usb_camera=usb_camera)
        result = arm.capture_usb_image(output_path)

        self.assertEqual(result, "usb.jpg")
        usb_camera.capture_image.assert_called_once_with(output_path)

    def test_capture_image_defaults_to_usb_when_only_usb_is_configured(self) -> None:
        usb_camera = MagicMock(spec=UsbCamera1)
        usb_camera.camera_name = "top_camera"
        usb_camera.capture_image.return_value = "usb.jpg"

        arm = self._make_elephant(usb_camera=usb_camera)
        result = arm.capture_image()

        self.assertEqual(result, "usb.jpg")
        usb_camera.capture_image.assert_called_once_with(None)

    @patch("elephant_driver.elephant.capture_pi_image")
    def test_capture_image_keeps_pi_default_when_both_cameras_are_configured(
        self,
        mock_capture_pi_image: MagicMock,
    ) -> None:
        pi_camera = CameraConfig(pi_ip="192.0.2.10")
        usb_camera = UsbCamera1(camera_index=1, camera_name="top_camera")
        mock_capture_pi_image.return_value = "optimized.jpg"

        arm = self._make_elephant(camera=pi_camera, usb_camera=usb_camera)
        result = arm.capture_image()

        self.assertEqual(result, "optimized.jpg")
        self.assertEqual(arm.available_cameras(), ["pi", "top_camera"])
        mock_capture_pi_image.assert_called_once_with(pi_camera, rotate=True)


if __name__ == "__main__":
    unittest.main()
