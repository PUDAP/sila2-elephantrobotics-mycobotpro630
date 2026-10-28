from elephant_driver import Elephant

arm = Elephant(ip="<robot-ip>", port=5001)
try:
    print(arm.get_coords())
except Exception as e:
    raise e