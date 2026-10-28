# Elephant Driver

Python driver for the **Elephant Pro630 6-axis robot arm**. Connects directly to the robot's built-in socket server on port 5001 via `pymycobot.ElephantRobot` — no bridge process needed on the Pi.

## Installation

```bash
pip install -e driver
```

Requires Python 3.10. Key dependencies: `pymycobot==4.0.4`, `paramiko`, `Pillow`.

## Quick Start

```python
from elephant_driver import Elephant, CameraConfig, CameraCalibration

arm = Elephant(ip="<robot-ip>")

print(arm.get_coords())          # [x, y, z, rx, ry, rz]
arm.move([-250, 0, 350, -180, 0, 120], speed=800)
arm.scan()
arm.disconnect()
```

Context manager is also supported:

```python
with Elephant(ip="<robot-ip>") as arm:
    arm.move([200, 0, 300, 180, 0, 0])
```

## Coordinate System

All Cartesian coordinates follow `[x, y, z, rx, ry, rz]` order (millimetres and degrees).

| Axis | Range |
|------|-------|
| x    | -630 to 630 mm |
| y    | -630 to 630 mm |
| z    | -425 to 835 mm |
| rx   | -180 to 180 deg |
| ry   | -180 to 180 deg |
| rz   | -180 to 180 deg |

Speed ranges from 1 to 3000 (default 800).

---

## Data Classes

### `Pose6D`

Immutable dataclass representing a 6-axis Cartesian pose.

```python
from elephant_driver import Pose6D

pose = Pose6D(x=-250, y=0, z=350, rx=-180, ry=0, rz=120)
pose.as_list()          # [-250, 0, 350, -180, 0, 120]
pose._replace(z=400)    # new Pose6D with z=400, rest unchanged

# Build from list, dict, or another Pose6D
Pose6D.from_any([-250, 0, 350, -180, 0, 120])
Pose6D.from_any({"x": -250, "y": 0, "z": 350})   # rx/ry/rz default to 0
```

### `CameraConfig`

SSH connection settings for the on-robot Raspberry Pi camera.

```python
from elephant_driver import CameraConfig

camera = CameraConfig(
    pi_ip="<camera-host>",
    username="pi",
    password="elephant",
    remote_capture_cmd="python3 capture_frame.py",
    remote_image_path="/home/pi/frame.jpg",
    local_image_dir=".",
)
```

### `CameraCalibration`

Pixel-to-millimetre calibration parameters for the camera.

```python
from elephant_driver import CameraCalibration

cal = CameraCalibration(
    cal_z=200.0,            # robot Z when calibration image was taken
    table_z=130.0,          # Z height of the table surface
    mm_per_pixel_at_cal_z=0.266,
    camera_to_tcp_x=-71.0,  # fixed X offset from camera center to TCP
    camera_to_tcp_y=0.0,
    rotate_image_180=True,
)
```

---

## `Elephant` Class — Constructor

```python
Elephant(
    ip: str,                           # robot IP address
    port: int = 5001,                  # socket server port
    home_coords: list[float] = None,   # custom home Cartesian coords (6 values)
    safe_height: float = 300.0,        # Z height for collision-avoidant moves
    default_speed: int = 800,          # default motion speed (1–3000)
    camera: CameraConfig = None,       # optional camera config
    calibration: CameraCalibration = None,  # optional calibration
)
```

Connects automatically on construction. Retries up to 5 times with 3-second delays.

---

## `Elephant` Class — All Methods

### Connection

| Method | Description |
|--------|-------------|
| `disconnect()` | Close the TCP connection to the robot. |
| `reconnect()` | Disconnect and reconnect. |

```python
arm.disconnect()
arm.reconnect()
```

The class can also be used as a context manager (`with Elephant(...) as arm:`), which calls `disconnect()` on exit.

---

### Status & Diagnostics

| Method | Returns | Description |
|--------|---------|-------------|
| `connected` | `bool` | Property — whether the connection is active. |
| `is_power_on()` | `bool` | Whether the robot power is on. |
| `is_moving()` | `bool` | Whether the robot is currently executing a motion. |
| `get_error()` | `str` | Next queued error message, or `""` if none. |
| `clear_error()` | — | Clear all queued errors. |
| `get_robot_status()` | `str` | 64-bit robot state string. |

```python
print(arm.connected)        # True
print(arm.is_power_on())    # True
print(arm.is_moving())      # False
print(arm.get_error())      # ""
print(arm.get_robot_status())
arm.clear_error()
```

---

### Pose Queries

| Method | Returns | Description |
|--------|---------|-------------|
| `get_angles()` | `list[float]` | Current six joint angles in degrees. |
| `get_coords()` | `list[float]` | Current Cartesian coords `[x, y, z, rx, ry, rz]`. |
| `get_pose()` | `Pose6D` | Current Cartesian pose as a `Pose6D` object. |

```python
angles = arm.get_angles()   # [174.3, -83.6, 136.0, -151.4, -91.3, 151.0]
coords = arm.get_coords()   # [-301.6, -57.2, 224.3, -172.7, -5.5, 112.8]
pose   = arm.get_pose()     # Pose6D(x=-301.6, y=-57.2, z=224.3, ...)
```

---

### Speed

| Method | Description |
|--------|-------------|
| `set_default_speed(speed)` | Set the default speed for all subsequent moves (1–3000). |

```python
arm.set_default_speed(600)
```

---

### Low-Level Motion

These methods send a command and return immediately (non-blocking).

| Method | Description |
|--------|-------------|
| `send_angles(angles, speed=None)` | Move all joints to the given angles (degrees). |
| `send_coords(coords, speed=None)` | Move TCP to Cartesian coordinates. Accepts list, dict, or `Pose6D`. |
| `send_angle(joint_id, degree, speed=None)` | Move a single joint (0–5) to the given degree. |
| `send_coord(axis_id, value, speed=None)` | Move a single Cartesian axis (0=x, 1=y, 2=z, 3=rx, 4=ry, 5=rz). |
| `stop()` | Immediately stop all motion. |
| `wait_done()` | Block until the current motion command finishes. |

```python
arm.send_angles([0, -20, 0, 0, 20, 0], speed=600)
arm.wait_done()

arm.send_coords([-250, 0, 350, -180, 0, 120], speed=800)
arm.wait_done()

arm.send_coord(2, 400, speed=600)   # move Z to 400
arm.send_angle(0, 90, speed=500)    # move joint 0 to 90 deg

arm.stop()  # emergency stop
```

---

### High-Level Motion

These methods block until the motion is complete and return the actual `Pose6D` reached.

#### `move(coords, *, speed=None) -> Pose6D`

Move the TCP to an absolute Cartesian pose. Accepts a list, dict, or `Pose6D`.

```python
actual = arm.move([-250, 0, 350, -180, 0, 120], speed=800)
actual = arm.move({"x": -200, "y": 0, "z": 350, "rx": 180, "ry": 0, "rz": 0})
actual = arm.move(Pose6D(x=-200, y=0, z=350, rx=180, ry=0, rz=0))
```

#### `move_relative(dx=0, dy=0, dz=0, drx=0, dry=0, drz=0, *, speed=None) -> Pose6D`

Move the TCP relative to its current position.

```python
arm.move_relative(dx=-50)           # move 50mm in negative X
arm.move_relative(dz=100, speed=400)  # raise 100mm slowly
arm.move_relative(dx=30, dy=-20)    # diagonal move
```

#### `safe_move(coords, *, speed=None, speed_vertical=None, speed_lateral=None) -> Pose6D`

Collision-avoidant move via a three-step path:
1. Lift to safe height (default 300mm or whichever is highest).
2. Move laterally to target X/Y/rotation.
3. Descend to target Z.

```python
arm.safe_move([250, 150, 200, 180, 0, 0], speed=800)
arm.safe_move([250, 150, 200, 180, 0, 0], speed_vertical=400, speed_lateral=800)
```

#### `scan(*, speed=None)`

Move to the configured scan position.

```python
arm.scan()                   # move to configured scan coords
arm.scan(speed=600)
```

#### `pick_from(coords, *, speed=None, lift_mm=50) -> Pose6D`

Full pick sequence:
1. Safe-move above the target (target Z + `lift_mm`).
2. Open gripper.
3. Descend to target at 1/3 speed.
4. Close gripper.
5. Lift back up.

```python
arm.pick_from([250, -100, 150, 180, 0, 0], speed=600, lift_mm=60)
```

#### `place_to(coords, *, speed=None, lift_mm=50) -> Pose6D`

Full place sequence:
1. Safe-move above the target.
2. Descend to target at 1/3 speed.
3. Open gripper.
4. Lift back up.

```python
arm.place_to([250, 100, 150, 180, 0, 0], speed=600, lift_mm=60)
```

---

### Gripper

| Method | Description |
|--------|-------------|
| `open_gripper(speed=70)` | Open the adaptive gripper. |
| `close_gripper(speed=70)` | Close the adaptive gripper. |
| `set_gripper_value(value, speed=70)` | Set gripper opening (0 = fully closed, 100 = fully open). |
| `init_gripper()` | Initialize the electric gripper. |
| `release_gripper()` | De-energize the gripper servo. |

```python
arm.open_gripper()
arm.close_gripper()
arm.set_gripper_value(50, speed=50)   # half open
arm.init_gripper()
arm.release_gripper()
```

---

### Reset & Safety

| Method | Description |
|--------|-------------|
| `reset()` | Clear errors, restart the robot, and home. |
| `release_all_servos()` | Disable torque on all joints (arm becomes free-moving). |
| `focus_all_servos()` | Re-enable torque on all joints. |

```python
arm.reset()
arm.release_all_servos()   # manually guide the arm
arm.focus_all_servos()     # lock joints back in place
```

---

### LED

| Method | Description |
|--------|-------------|
| `set_color(r, g, b)` | Set the end-effector LED color (0–255 per channel). |

```python
arm.set_color(0, 255, 0)   # green
arm.set_color(255, 0, 0)   # red
arm.set_color(0, 0, 255)   # blue
```

---

### Camera

| Method | Description |
|--------|-------------|
| `capture_image(*, rotate=None)` | SSH to the Pi, capture a frame, and return the local image path. Rotates 180 deg by default per calibration. |
| `pixel_to_robot_offset(cx, cy, image_center_x, image_center_y, z_touch, *, z_cam=None)` | Convert a pixel coordinate to robot-frame XY mm deltas. Returns `(delta_x_mm, delta_y_mm, mm_per_pixel)`. |

Requires `camera=CameraConfig(...)` to be passed to the constructor.

```python
arm = Elephant(ip="<robot-ip>", camera=CameraConfig(pi_ip="<camera-host>"))

image_path = arm.capture_image()
# "optimized.jpg"

dx, dy, mm_px = arm.pixel_to_robot_offset(
    cx=320, cy=240,
    image_center_x=320, image_center_y=240,
    z_touch=160.0,
)
arm.move_relative(dx=dx, dy=dy)
```

**Height correction** is automatic — when the object is at a different height than the calibration surface, the pixel-to-mm scale adjusts:

```
actual_mm_per_pixel = mm_per_pixel_at_cal_z * (z_cam - z_touch) / (cal_z - table_z)
```

---

## Logging

Enable logging to see all commands and target-vs-actual comparisons:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Example output:

```
Moving to x=-250.00 y=0.00 z=350.00 rx=-180.00 ry=0.00 rz=120.00 @ speed=800
Target: [-250.0, 0.0, 350.0, -180.0, 0.0, 120.0]  Actual: [-249.8, 0.1, 349.9, ...]
```

---

## ROS

To run the ROS interface (Linux only):

```bash
source /opt/ros/humble/setup.bash
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/ros/humble/lib
uv run python tests/ros.py
```
