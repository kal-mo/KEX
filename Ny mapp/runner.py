
import threading
import subprocess
import sys
import time
import signal
from typing import Tuple, TextIO
import atexit


def clean_slate(): 
        
    cmd = ["killall -9 px4 gz gz-sim ignition-gazebo gzserver gzclient make cmake QGroundControl",
    "rm -rf /tmp/px4*",
    "rm -rf /tmp/gz*",
    "unset GAZEBO_MASTER_URI",
    "ps aux | grep gz | grep -v grep"]
    #"rm -rf ~/.ignition",
    #"rm -rf ~/.gazebo",
    #"unset GAZEBO_MASTER_URI"]
    for command in cmd:
            print(f"executing command: {command}")
            proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line buffered
            universal_newlines=True
        )
            if command.startswith("ps aux"):
                first_line = proc.stdout.readline()
                if len(first_line) > 0:
                    process_id=[]
                    print("Error: Detected lingering processes:")
                    print(first_line, end="")
                    for line in proc.stdout:
                        print(line, end="")
                        process_id.append(line.split()[1])
                    process_id.append(first_line.split()[1])
                    print(process_id)
                    for pid in process_id:
                        print(f"Killing process with PID {pid}...")
                        subprocess.run(f"kill -9 {pid}", shell=True)
                        
                    input("Press Enter to continue....")
                        
            for line in proc.stdout:
                
                    
                print(f"{line.rstrip()}")
                sys.stdout.flush()
            
            proc.kill()


def start_program(cwd_qgroundcontrol: str, cwd_px4: str, cwd_mavsdk_mission: str, cwd_interrupt: str, mission_name: str, interrupt_mission_name: str, make_px4: str):
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RESET = "\033[0m"

    processes = []
    threads = []
    fault_flag = threading.Event()

    def signal_handler(sig, frame):
        print(f"{RED}Received signal {sig}, cleaning up...{RESET}")
        kill_all(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    atexit.register(lambda: kill_all(processes))


    

    def start_process(cmd: str, cwd: str, color: str, tag: str) -> Tuple[subprocess.Popen, TextIO]:
        proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line buffered
        universal_newlines=True
    )
        return proc, proc.stdout


    def kill_all(processes):
        for p in processes:
            print(f"Checking process with PID {p.pid}...")
            if p and p.poll() is None:
                try:
                    print(f"Killing process with PID {p.pid}...")
                    p.kill()
                except Exception:
                    pass
    
    def interrupt_callback():
        if not fault_flag.is_set():
            interrupt_mission(processes, threads)

        
    def interrupt_mission(processes, threads):

        print(f"{RED}Launching Interrupting MAVSDK mission...{RESET}")
        interrupt_proc = start_process("python3 -u " + interrupt_mission_name, cwd_interrupt, RED, "INTERRUPT")
        processes.append(interrupt_proc[0])
        print(f"{RED}Implementing interrupt thread...{RESET}")
        threads.append(threading.Thread(target=reader, args=(interrupt_proc[0], RED, "INTERRUPT"), daemon=True))
        print(f"{RED}starting thread...{RESET}")
        threads[-1].start()
        
        return interrupt_proc

    def reader(proc, color, tag, processes=None, threads=None):
        try:
            for line in proc.stdout:
                print(f"{color}[{tag}] {line.rstrip()}\033[0m")
                sys.stdout.flush()
                if tag == "MAVSDK" and "Mission progress: 1/6" in line:
                    print(f"{RED}Starting interrupt timer...{RESET}")
                    threading.Timer(30.0, interrupt_callback).start()
                
                if tag == "QGC" and "INFO  [logger] closed logfile, bytes written:" in line:
                    print(f"mission ended, killing all processes...")
                    kill_all(processes)
                    exit(0)
        except Exception as e:
            print(f"[{tag}] fault: {e}")
            fault_flag.set()
            kill_all(processes)


    #startar qgroundcontrol
    print(f"{YELLOW}Starting QGroundControl...{RESET}")
    qground = start_process("./QGroundControl-x86_64.AppImage", cwd_qgroundcontrol, YELLOW, "QGC")
    #startar px4
    print(f"{GREEN}Starting PX4 SITL + Gazebo...{RESET}")
    px4 = start_process(make_px4, cwd_px4, GREEN, "PX4")
    #inväntar att px4 ska starta klart innan mavsdk-mission startas
    go_ahead = False
    while not go_ahead:
        for line in px4[1]:  # px4[1] is the stdout of the px4 process
            print(line, end="")  # to your terminal
            if "Ready for takeoff!" in line:
                go_ahead = True
                break
            sys.stdout.flush()
    print(f"{CYAN}PX4 is ready, starting MAVSDK mission...{RESET}")

    #input=("press enter to proceed: ")
        
    print(f"{CYAN}Starting MAVSDK mission in 5 seconds...{RESET}")
    mission = start_process("python3 -u " + mission_name, cwd_mavsdk_mission, CYAN, "MAVSDK")
    processes.extend([qground[0], px4[0], mission[0]])
    #threads = [
    #    threading.Thread(target=reader, args=(qground[0], "\033[32m", "PX4"), daemon=True),
    #    threading.Thread(target=reader, args=(px4[0], "\033[33m", "QGC"), daemon=True),
    #    threading.Thread(target=reader, args=(mission[0], "\033[36m", "MAVSDK"), daemon=True),
    #    threading.Thread(target=reader, args=(interrupt_mission[0], "\033[31m", "INTERRUPT"), daemon=True)
    #]
    
    for proc, color, tag in [
        (processes[0], GREEN, "PX4"),
        (processes[1], YELLOW, "QGC"),
        (processes[2], CYAN, "MAVSDK"),
    ]:
        threads.append(threading.Thread(target=reader, args=(proc, color, tag, processes, threads), daemon=True))
        print(f"Starting thread for {tag} output...")
        threads[-1].start()
    print("vid timer")

    while not fault_flag.is_set() and any(p.poll() is None for p in processes):
        time.sleep(0.2)
    if fault_flag.is_set():
        kill_all(processes)
        print("Fault detected, exiting.")
        sys.exit(1)
    #timer = threading.Timer(60.0, lambda: interrupt_mission(processes, threads))
    #print(f"{RED}Timer started for interrupting mission after 60 seconds...{RESET}")
    #timer.start()

    for p in processes:
        p.wait()

    for t in threads: 
        t.join(timeout=0.1)
    #kill_all(processes)
    #atexit.register(lambda: kill_all(processes))
    print("all done")
    clean_slate()
    sys.exit(0)
    #clean_slate()
   


def main(cwd_qgroundcontrol: str, cwd_px4: str, cwd_mavsdk_mission: str, cwd_interrupt: str, mission_name: str, interrupt_mission_name: str, make_px4: str):
    clean_slate()
    start_program(cwd_qgroundcontrol, cwd_px4, cwd_mavsdk_mission, 
                  cwd_interrupt, mission_name, interrupt_mission_name,make_px4)

if __name__ == "__main__":
    cwd_qgroundcontrol = "/home/kmos123"
    cwd_px4 = "/home/kmos123/PX4-Autopilot"
    cwd_mavsdk_mission = "/home/kmos123/MAVSDK-Python/examples"
    mission_name = "mission_baylands.py"
    make_px4 = "make px4_sitl gz_x500_baylands"
    cwd_interrupt= "/home/kmos123/MAVSDK-Python/examples"
    interrupt_mission_name = "interrupted_mission.py"
    
    main(cwd_qgroundcontrol,cwd_px4,cwd_mavsdk_mission,cwd_interrupt,mission_name,interrupt_mission_name,make_px4)
