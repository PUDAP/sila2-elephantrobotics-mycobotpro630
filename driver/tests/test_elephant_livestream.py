"""Tests for Elephant livestream integration."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from elephant_driver import Elephant
from elephant_driver.cv import DEFAULT_STREAM_URL


class TestElephantLivestream(unittest.TestCase):
    def _make_elephant(self, **kwargs: object) -> Elephant:
        patcher = patch("elephant_driver.elephant.ElephantRobot")
        self.addCleanup(patcher.stop)
        mock_robot = patcher.start()
        mock_client = MagicMock()
        mock_client.start_client.return_value = True
        mock_client.state_check.return_value = True
        mock_robot.return_value = mock_client
        return Elephant(ip="127.0.0.1", **kwargs)

    @patch("elephant_driver.elephant.capture_snapshot")
    def test_capture_stream_image_uses_constructor_stream_url(
        self,
        mock_capture_snapshot: MagicMock,
    ) -> None:
        output_path = Path("captures") / "stream.jpg"
        mock_capture_snapshot.return_value = True

        arm = self._make_elephant(stream_url="rtsp://camera.local:8554/livestream")
        result = arm.capture_stream_image(output_path)

        self.assertEqual(result, str(output_path))
        mock_capture_snapshot.assert_called_once_with(
            "rtsp://camera.local:8554/livestream",
            output_path,
        )

    @patch("elephant_driver.elephant.capture_snapshot")
    def test_capture_stream_image_defaults_to_livestream_url(
        self,
        mock_capture_snapshot: MagicMock,
    ) -> None:
        mock_capture_snapshot.return_value = True

        arm = self._make_elephant()
        arm.capture_stream_image()

        mock_capture_snapshot.assert_called_once_with(DEFAULT_STREAM_URL, Path("snapshot.jpg"))

    @patch("elephant_driver.elephant.capture_snapshot")
    def test_capture_stream_image_raises_on_failure(
        self,
        mock_capture_snapshot: MagicMock,
    ) -> None:
        mock_capture_snapshot.return_value = False

        arm = self._make_elephant(stream_url="rtsp://camera.local:8554/livestream")

        with self.assertRaisesRegex(RuntimeError, "Stream capture failed"):
            arm.capture_stream_image()


if __name__ == "__main__":
    unittest.main()
