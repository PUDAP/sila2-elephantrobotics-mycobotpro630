# Auto-generated from elephant_basics.ipynb
ROBOT_IP   = "<robot-ip>"
ROBOT_PORT = 5001
PI_IP      = "<camera-host>"


#Connect
from elephant_driver import Elephant, CameraConfig, CameraCalibration

camera = CameraConfig(
    pi_ip=PI_IP,
    username="pi",
    password="elephant",
    remote_capture_cmd="python3 capture_frame.py",
    remote_image_path="/home/pi/frame.jpg",
    local_image_dir=".",
)

calibration = CameraCalibration(
    cal_z=200.0,
    table_z=130.0,
    mm_per_pixel_at_cal_z=0.266,
    camera_to_tcp_x=-71.0,
    camera_to_tcp_y=0.0,
    rotate_image_180=True,
)

arm = Elephant(
    ip=ROBOT_IP,
    port=ROBOT_PORT,
    camera=camera,
    calibration=calibration,
)

print(f"Connected: {arm.connected}")
print(f"Power on:  {arm.is_power_on()}")


# Power on the robot after emergency stop or power_off.
import time 
result = arm.power_on()

if result == 1:
    print("Power-on successful")
    time.sleep(8.0)
    print(f"Power on: {arm.is_power_on()}")
else:
    print("Power-on failed")

# Power off command.
power_off_result = arm.power_off()
if power_off_result == 1:
    print("1: power-off completed")
else:
    print("0: power-off failed")
print(f"Power on: {arm.is_power_on()}")



#Read current position
angles = arm.get_angles()
print(f"Joint angles (deg): {angles}")

coords = arm.get_coords()
print(f"Cartesian coords:   {coords}")

pose = arm.get_pose()
print(f"Pose6D:             {pose}")


#Init the robot
arm.scan_coord(speed=800)
print("Init position reached")
print(f"Angles: {arm.get_angles()}")
print(f"Coords: {arm.get_coords()}")


#Move to a known position(Absolute move)
arm.move([-354.894, 0, 300, -179.588, -2.512, 113.315], speed=800)
print(f"Moved to: {arm.get_coords()}")
# Also works with a dict
arm.move({"x": -300.0, "y": 0.0, "z": 350.0, "rx": 180.0, "ry": 0.0, "rz": 0.0}, speed=800)
print(f"Moved to: {arm.get_coords()}")


#Relative move
arm.move_relative(dz=-50.0)
print(f"After +50mm X: {arm.get_coords()}")


#Gripper control
arm.open_gripper()
print("Gripper opened")
time.sleep(1.0)

arm.close_gripper()
print("Gripper closed")
time.sleep(1.0)


#Pick and place
arm.pick_from([250.0, -100.0, 150.0, 180.0, 0.0, 0.0], speed=600, lift_mm=60.0)
print("Object picked")

arm.place_to([250.0, 100.0, 150.0, 180.0, 0.0, 0.0], speed=600, lift_mm=60.0)
print("Object placed")


#Joint-space motion
arm.send_angles([0, -20, 0, 0, 20, 0], speed=600)
print(f"Angles: {arm.get_angles()}")


#Error handling and reset
print(f"Error:        {arm.get_error()}")
print(f"Robot status: {arm.get_robot_status()}")

if arm.get_error():
    print("Resetting...")
    arm.reset()
    print(f"Error after reset: {arm.get_error()}")


#LED control
arm.set_color(0, 255, 0)   # green
time.sleep(1.0)
arm.set_color(0, 0, 255)   # blue
time.sleep(1.0)
arm.set_color(255, 0, 0)   # red

