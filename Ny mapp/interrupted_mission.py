#!/usr/bin/env python3

"""
This example shows how to use the manual controls plugin.

Note: Manual inputs are taken from a test set in this example to decrease
complexity. Manual inputs can be received from devices such as a joystick
using third-party python extensions.

Note: Taking off the drone is not necessary before enabling manual inputs.
It is acceptable to send positive throttle input to leave the ground.
Takeoff is used in this example to decrease complexity
"""

import asyncio
from mavsdk import System
from mavsdk.offboard import Attitude,VelocityBodyYawspeed,OffboardError

# Test set of manual inputs. Format: [roll, pitch, throttle, yaw]
manual_inputs = [
    [0, 0, 0.5, 0],  # no movement
    [-1, 0, 0.5, 0],  # minimum roll
    [1, 0, 0.5, 0],  # maximum roll
    [0, -1, 0.5, 0],  # minimum pitch
    [0, 1, 0.5, 0],  # maximum pitch
    [0, 0, 0.5, -1],  # minimum yaw
    [0, 0, 0.5, 1],  # maximum yaw
    [0, 0, 1, 0],  # max throttle
    [0, 0, 0, 0],  # minimum throttle
]

async def manual_controls():
    """Main function to connect to the drone and input manual controls"""
    # Connect to the Simulation
    drone = System()
    await drone.connect(system_address="udpout://127.0.0.1:14540")

    # This waits till a mavlink based drone is connected
    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("-- Connected to drone!")
            break
    print("---arming")
    await drone.action.arm()
    print("pausing mission...")
    await drone.mission.pause_mission()

    print("Setting initial setpoint...")
      # Send initial setpoint before starting offboard
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    #await asyncio.sleep(1)  # Wait for the setpoint to be received

    try:
        print("Starting Offboard mode...")
        await drone.offboard.start()
    except OffboardError as e:
        print(f"Offboard start failed: {e}")
        return

    count = 0
    
    while count < 5:
        count += 1
        print("Rotating 90 degrees left...")

        yaw_rate = -30.0  # degrees/sec
        duration = 3.0    # seconds (30°/s × 3 ≈ 90°)

        steps = int(duration / 0.05)

        for _ in range(steps):
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, 0.0, yaw_rate)
            )
            await asyncio.sleep(0.05)

        print("Stopping rotation...")
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )

    print("Stopping offboard...")
    await drone.offboard.stop()

    # Resume mission
    print("Resuming mission...")
    await drone.mission.start_mission()


if __name__ == "__main__":
    # Run the asyncio loop
    asyncio.run(manual_controls())
