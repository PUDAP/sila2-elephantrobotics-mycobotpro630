"""Call the simulated myCobotPro630 arm with the hackathon SiLA client.

Run this with the device-integration-hackathon-2026 environment, not the
connector virtual environment.
"""

import asyncio

from sila.client import Client, ClientConfig

ARM = "co.puda/motion/ArmController/v1"
GRIPPER = "co.puda/gripper/GripperController/v1"


async def finish(execution):
    """Wait for an observable command and return its responses."""
    try:
        while not execution.done:
            await asyncio.sleep(0.05)
        return await execution.get_responses()
    finally:
        execution.cancel()


async def main() -> None:
    """Read the pose, move, scan, and exercise the electric gripper."""
    client = Client(ClientConfig(hostname="<sila-host>", port=50053, tls=False))
    try:
        await asyncio.wait_for(client.open(sync=False), timeout=10)
        print("Connected to:", await client.get_server_name())
        print("Features:", await client.get_implemented_features())
        arm = await client.load_feature(ARM)
        gripper = await client.load_feature(GRIPPER)
        print("Arm properties:", list(arm.properties))
        print("Arm commands:", list(arm.commands))
        print("Gripper commands:", list(gripper.commands))
        print("Pose:", await arm.properties["Pose"].read())
        print(
            "MoveAbsolute:",
            await finish(
                await arm.commands["MoveAbsolute"].execute(
                    {"Pose": {"X": -400.0, "Y": 100.0, "Z": 300.0, "Rx": -179.99, "Ry": 0.0, "Rz": 111.0}}
                )
            ),
        )
        print(
            "MoveRelative:",
            await finish(
                await arm.commands["MoveRelative"].execute(
                    {"Dx": -10.0, "Dy": 20.0, "Dz": -5.0, "Drx": 0.0, "Dry": 0.0, "Drz": 1.0}
                )
            ),
        )
        print("Scan:", await finish(await arm.commands["Scan"].execute({})))
        print("Pose:", await arm.properties["Pose"].read())
        print("Initialize:", await finish(await gripper.commands["Initialize"].execute({})))
        print("Open:", await finish(await gripper.commands["Open"].execute({})))
        print("Close:", await finish(await gripper.commands["Close"].execute({})))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=60))
