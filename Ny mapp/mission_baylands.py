#!/usr/bin/env python3

import asyncio
import logging

from mavsdk import System
from mavsdk.mission import MissionItem, MissionPlan

# Enable INFO level logging by default so that INFO messages are shown
logging.basicConfig(level=logging.INFO)


async def run():
    drone = System()
    
    await drone.connect(system_address="udpin://0.0.0.0:14540")

    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("-- Connected to drone!")
            break

    print_mission_progress_task = asyncio.ensure_future(print_mission_progress(drone))

    running_tasks = [print_mission_progress_task]
    termination_task = asyncio.ensure_future(observe_is_in_air(drone, running_tasks))
    await drone.param.set_param_int("NAV_RCL_ACT", 1)
    await drone.param.set_param_int("NAV_DLL_ACT",1)
    await drone.param.set_param_int("COM_OBL_RC_ACT",1)

    await drone.param.set_param_float("COM_OF_LOSS_T", 10.0)
    await drone.param.set_param_int("COM_DL_LOSS_T", 60)

    

    mission_items = []
    mission_items.append(
        MissionItem(
            37.412253,
        -121.996753,
        30,
        5,
        False,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_items.append(
        MissionItem(
            37.412353,
        -121.996853,
        30,
        2,
        True,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_items.append(
        MissionItem(
            37.412470,
        -121.996953,
        30,
        5,
            True,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_items.append(
        MissionItem(
           37.412570,
        -121.996553,
        30,
        2,
            True,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_items.append(
        MissionItem(
           37.412340,
        -121.996653,
        30,
        5,
            True,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_items.append(
        MissionItem(
           37.412253,
        -121.996753,
        30,
        5,
            False,
            float("nan"),
            float("nan"),
            MissionItem.CameraAction.NONE,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            MissionItem.VehicleAction.NONE,
        )
    )
    mission_plan = MissionPlan(mission_items)

    await drone.mission.set_return_to_launch_after_mission(True)

    print("-- Uploading mission")
    await drone.mission.upload_mission(mission_plan)

    print("Waiting for drone to have a global position estimate...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("-- Global position estimate OK")
            break

    print("-- Arming")
    await drone.action.arm()

    print("-- Starting mission")
    await drone.mission.start_mission()

    await termination_task


async def print_mission_progress(drone):
    async for mission_progress in drone.mission.mission_progress():
        print(f"Mission progress: {mission_progress.current}/{mission_progress.total}")


async def observe_is_in_air(drone, running_tasks):
    """Monitors whether the drone is flying or not and
    returns after landing"""

    was_in_air = False

    async for is_in_air in drone.telemetry.in_air():
        if is_in_air:
            was_in_air = is_in_air

        if was_in_air and not is_in_air:
            for task in running_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await asyncio.get_event_loop().shutdown_asyncgens()

            return


if __name__ == "__main__":
    # Run the asyncio loop
    asyncio.run(run())
