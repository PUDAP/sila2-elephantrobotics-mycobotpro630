"""Tests for Elephant motion completion behavior."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from elephant_driver import Elephant


class TestElephantMotion(unittest.TestCase):
    def _make_elephant(self) -> tuple[Elephant, MagicMock]:
        patcher = patch("elephant_driver.elephant.ElephantRobot")
        self.addCleanup(patcher.stop)
        mock_robot = patcher.start()
        mock_client = MagicMock()
        mock_client.start_client.return_value = True
        mock_client.state_check.return_value = True
        mock_client.check_running.return_value = False
        mock_robot.return_value = mock_client
        return Elephant(ip="127.0.0.1"), mock_client

    @patch("elephant_driver.elephant.time.sleep", return_value=None)
    def test_move_waits_for_coordinate_confirmation(self, _mock_sleep: MagicMock) -> None:
        arm, client = self._make_elephant()
        target = [-331.06, 296.51, 160.0, 179.99, 0.001, 111.0]
        client.get_coords.side_effect = [
            target,
            [-331.017, 296.486, 268.545, 179.964, 0.034, 111.0],
            [-331.063, 296.513, 185.749, 179.991, 0.0, 111.0],
            [-331.06, 296.51, 159.999, 179.99, 0.001, 111.0],
            [-331.06, 296.51, 160.0, 179.99, 0.001, 111.0],
        ]

        actual = arm.move(target, speed=100)

        self.assertAlmostEqual(actual.z, 160.0, places=3)
        self.assertGreaterEqual(client.get_coords.call_count, 5)
        client.write_coords.assert_called_once_with(target, 100)

    @patch("elephant_driver.elephant.time.sleep", return_value=None)
    @patch("elephant_driver.elephant.time.monotonic")
    def test_move_raises_when_target_pose_not_confirmed(
        self,
        mock_monotonic: MagicMock,
        _mock_sleep: MagicMock,
    ) -> None:
        arm, client = self._make_elephant()
        target = [-331.06, 296.51, 160.0, 179.99, 0.001, 111.0]
        client.get_coords.return_value = [-331.06, 296.51, 250.0, 179.99, 0.001, 111.0]
        mock_monotonic.side_effect = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 1.6]

        with self.assertRaisesRegex(TimeoutError, "Timed out waiting"):
            arm.move(target, speed=100, settle_timeout_s=1.0)


if __name__ == "__main__":
    unittest.main()
