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


# Step 1: Move to a known Z above the table
arm.safe_move([200.0, 0.0, 200.0, 180.0, 0.0, 0.0], speed=800)
print(f"Camera positioned at Z = {arm.get_coords()[2]:.1f}")

# Step 2: Capture a calibration image
from IPython.display import display, Image as IPImage

cal_image_path = arm.capture_image()
display(IPImage(filename=cal_image_path))

# Step 3: Measure a known object in the image
KNOWN_MM = 50.0
MEASURED_PIXELS = 188.0

mm_per_pixel = KNOWN_MM / MEASURED_PIXELS
print(f"mm_per_pixel_at_cal_z = {mm_per_pixel:.4f}")

# Update the calibration
arm._calibration.mm_per_pixel_at_cal_z = mm_per_pixel
arm._calibration.cal_z = arm.get_coords()[2]
print(f"Calibration: {arm._calibration}")

from IPython.display import display, Image as IPImage

image_path = arm.capture_image()
print(f"Image: {image_path}")
display(IPImage(filename=image_path))

import os
import re
import json
import base64
import requests
import cv2

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
VLM_MODEL = "openai/gpt-4.1-mini"


def call_vlm_json(prompt, image_path, *, model=VLM_MODEL, timeout=60):
    """Send image + prompt to a VLM via OpenRouter, return parsed JSON."""
    assert OPENROUTER_API_KEY, "Set OPENROUTER_API_KEY in your environment"

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      headers=headers, json=payload, timeout=timeout)
    data = r.json()
    if "choices" not in data:
        raise RuntimeError(f"VLM request failed: {json.dumps(data, indent=2)}")

    text = data["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError(f"No JSON in VLM response: {text}")
    return json.loads(match.group(0))


def detect_objects(object_name, image_path, *, model=VLM_MODEL):
    """Detect all instances of object_name, return bboxes + nearest-to-center selection."""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    icx, icy = w // 2, h // 2

    prompt = (
        "You are a precision vision detector for robotic manipulation.\n\n"
        f"Target object:\n{object_name}\n\n"
        "Find ALL visible instances. Return ONLY valid JSON:\n\n"
        '{\n  "objects": [{"bbox":[x1,y1,x2,y2]}]\n}\n\n'
        "Rules:\n"
        "- Tight bounding boxes, integer coordinates inside image bounds.\n"
        "- Do NOT merge multiple objects into one box.\n"
        '- If none found: {"objects":[]}\n'
        f"\nImage: {w}x{h} pixels."
    )

    result = call_vlm_json(prompt, image_path, model=model)
    candidates = result.get("objects", [])
    if not candidates:
        raise RuntimeError(f"No objects detected for: {object_name}")

    best, best_dist = None, float("inf")
    for obj in candidates:
        if "bbox" not in obj or len(obj["bbox"]) != 4:
            continue
        x1, y1, x2, y2 = obj["bbox"]
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        d = (cx - icx) ** 2 + (cy - icy) ** 2
        if d < best_dist:
            best_dist = d
            best = {"bbox": [int(x1), int(y1), int(x2), int(y2)], "cx": cx, "cy": cy}

    if best is None:
        raise RuntimeError("No valid bounding boxes in VLM response")

    return {
        "objects": candidates,
        "selected": best,
        "image_size": [w, h],
        "image_center_px": [icx, icy],
        "image_path": image_path,
    }


def draw_detections(detection, save_path="detection_debug.jpg"):
    """Draw bounding boxes on the image and return the path."""
    img = cv2.imread(detection["image_path"])
    icx, icy = detection["image_center_px"]

    for obj in detection["objects"]:
        if "bbox" not in obj or len(obj["bbox"]) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in obj["bbox"]]
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 255), 2)

    sel = detection["selected"]
    cv2.rectangle(img, (sel["bbox"][0], sel["bbox"][1]), (sel["bbox"][2], sel["bbox"][3]), (0, 255, 0), 3)
    cv2.circle(img, (sel["cx"], sel["cy"]), 6, (0, 0, 255), -1)
    cv2.drawMarker(img, (icx, icy), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)

    cv2.imwrite(save_path, img)
    return save_path


print("VLM helpers loaded.")

from IPython.display import display, Image as IPImage

image_path = arm.capture_image()

detection = detect_objects("blue vial cap", image_path)

print(f"Found {len(detection['objects'])} object(s)")
print(f"Selected center: ({detection['selected']['cx']}, {detection['selected']['cy']})")

debug_path = draw_detections(detection)
display(IPImage(filename=debug_path))

Z_TOUCH = 160.0

sel = detection["selected"]
icx, icy = detection["image_center_px"]

delta_x, delta_y, mm_px = arm.pixel_to_robot_offset(
    sel["cx"], sel["cy"], icx, icy, z_touch=Z_TOUCH
)

print(f"Pixel offset from center: dx_px={sel['cx'] - icx}, dy_px={sel['cy'] - icy}")
print(f"Robot move:  dx={delta_x:.2f} mm,  dy={delta_y:.2f} mm")
print(f"Scale:       {mm_px:.4f} mm/pixel")

Z_TOUCH = 160.0

# 1. Capture
image_path = arm.capture_image()

# 2. Detect
detection = detect_objects("blue vial cap", image_path)
sel = detection["selected"]
icx, icy = detection["image_center_px"]
print(f"Detected at pixel ({sel['cx']}, {sel['cy']})")

# 3. Convert pixel → robot mm
dx, dy, mm_px = arm.pixel_to_robot_offset(sel["cx"], sel["cy"], icx, icy, Z_TOUCH)
print(f"Move delta: X={dx:.2f} mm, Y={dy:.2f} mm  ({mm_px:.4f} mm/px)")

# 4. Move
arm.move_relative(dx=dx, dy=dy, speed=800)
print(f"Now at: {arm.get_coords()}")

Z_TOUCH = 160.0
PLACE_POSITION = [300.0, 150.0, 160.0, 180.0, 0.0, 0.0]

# Detect and move above the object
image_path = arm.capture_image()
detection = detect_objects("blue vial cap", image_path)
sel = detection["selected"]
icx, icy = detection["image_center_px"]
dx, dy, _ = arm.pixel_to_robot_offset(sel["cx"], sel["cy"], icx, icy, Z_TOUCH)
arm.move_relative(dx=dx, dy=dy, speed=800)

# Pick (descend to z_touch, grab, lift)
current = arm.get_pose()
arm.pick_from(current._replace(z=Z_TOUCH), speed=600)
print("Object picked")

# Place
arm.place_to(PLACE_POSITION, speed=600)
print("Object placed")

image_path = arm.capture_image()

result = call_vlm_json(
    'Describe all objects on the table. Return JSON: {"objects": [{"name": "...", "bbox": [x1,y1,x2,y2]}]}',
    image_path,
)

print(json.dumps(result, indent=2))

SCAN_POSITION  = [200.0, 0.0, 250.0, 180.0, 0.0, 0.0]
PLACE_POSITION = [300.0, 150.0, 160.0, 180.0, 0.0, 0.0]
Z_TOUCH = 160.0

# 1. Move to scanning position
arm.safe_move(SCAN_POSITION, speed=800)
print(f"At scan position: {arm.get_coords()}")

# 2. Capture and detect
image_path = arm.capture_image()
detection = detect_objects("blue vial cap", image_path)
print(f"Found {len(detection['objects'])} object(s)")

# 3. Compute robot offset and move above the object
sel = detection["selected"]
icx, icy = detection["image_center_px"]
dx, dy, _ = arm.pixel_to_robot_offset(sel["cx"], sel["cy"], icx, icy, Z_TOUCH)
arm.move_relative(dx=dx, dy=dy, speed=800)
print(f"Above object: {arm.get_coords()}")

# 4. Pick
current = arm.get_pose()
arm.pick_from(current._replace(z=Z_TOUCH), speed=600)
print("Object picked")

# 5. Place
arm.place_to(PLACE_POSITION, speed=600)
print("Object placed")

# 6. Home
arm.home(speed=800)
print("Done!")

arm.home(speed=800)
arm.disconnect()
print(f"Connected: {arm.connected}")

with Elephant(ip=ROBOT_IP, port=ROBOT_PORT, camera=camera, calibration=calibration) as arm:
    print(arm.get_coords())
    img = arm.capture_image()
    print(f"Captured: {img}")
    arm.home()
