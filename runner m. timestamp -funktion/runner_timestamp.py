
import threading
import subprocess
import sys
import time
from datetime import datetime
import signal
from typing import Tuple, TextIO
import atexit
import os
import csv





class timestamps:
    def __init__(self, startpoint): #skapar timestampobjekt
        self.events = []
        self.timestamp = []
        self.startpoint = startpoint
    
    def add_event(self, event, timestamp): 
        self.events.append(event)
        self.timestamp.append(timestamp)
    def get_reference_point(self):
        return self.startpoint
    
    def get_events(self):
        return self.events

    def get_timestamps(self):
        return self.timestamp
    



def write_csv(event, timestamp, file_path): #funktion för att skriva till csv, kollar först om filen finns och skriver header om den inte gör det, sedan skriver den event och timestamp
    write_header = not os.path.exists(file_path)

    with open(file_path, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['event', 'timestamp'])
        if write_header:
            writer.writeheader()
        writer.writerow({'event': event, 'timestamp': timestamp})

def clean_slate(): #dödar eventuella kvarvarande processer och rensar tempfiler, kollar även efter kvarvarande gz-processer och dödar dessa
        
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
            if command.startswith("ps aux"): #komplementfunktion till grep - kommando, kollar efter kvarvarande gz-processer och dödar dessa
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



#huvudprogrammet, startar alla processer och trådar, hanterar signaler och avbrott, och skriver eventloggen till csv när alla processer är klara
def start_program(cwd_qgroundcontrol: str, cwd_px4: str, cwd_mavsdk_mission: str, cwd_interrupt: str, mission_name: str, interrupt_mission_name: str, make_px4: str, file_path: str):
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RESET = "\033[0m"

    processes = []
    threads = []
    timestamps_holder = []
    fault_flag = threading.Event()
    print(f"{RED}clearing csv file...{RESET}") #kontrollerar csv-filen, om den finns så rensas den, annars skapas den när första eventet skrivs till csv
    if os.path.exists(file_path):
         open(file_path, 'w', newline='').close()

    def signal_handler(sig, frame): #felhanterare, fångar upp signaler som SIGINT och SIGTERM, och ser till att alla processer dödas innan programmet avslutas
        print(f"{RED}Received signal {sig}, cleaning up...{RESET}")
        kill_all(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler) #registrerar signalhanteraren för SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, signal_handler)#registrerar signalhanteraren för SIGTERM (avslutningssignal)

    atexit.register(lambda: kill_all(processes)) #registrerar en funktion som kommer att köras när programmet avslutas, oavsett hur det avslutas, för att se till att alla processer dödas


    

    def start_process(cmd: str, cwd: str, color: str, tag: str) -> Tuple[subprocess.Popen, TextIO]: 
        #kommandohanterare för att starta subprocesses, samma som att skriva in kommando i kommandotolken i wsl
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
        #funktion som dödar alla processer i listan, används både i signalhanteraren och i reader-funktionen när missionen är klar eller när ett fel upptäcks
        for p in processes:
            print(f"Checking process with PID {p.pid}...")
            if p and p.poll() is None:
                try:
                    print(f"Killing process with PID {p.pid}...")
                    p.kill()
                except Exception:
                    pass
    
    def interrupt_callback():
        #funktion som körs när interrupt-timern går ut, startar interrupt-missionen och interrupt-tråden, och loggar timestamp för när interruptet sker
        if not fault_flag.is_set():
            interrupt_mission(processes, threads)

        
    def interrupt_mission(processes, threads):
        #offboard control - funktionen som startar interrupt-missionen och interrupt-tråden, och loggar timestamp för när interruptet sker

        print(f"{RED}Launching Interrupting MAVSDK mission...{RESET}")
        interrupt_proc = start_process("python3 -u " + interrupt_mission_name, cwd_interrupt, RED, "INTERRUPT")
        processes.append(interrupt_proc[0])
        print(f"{RED}Implementing interrupt thread...{RESET}")
        threads.append(threading.Thread(target=reader, args=(interrupt_proc[0], RED, "INTERRUPT", processes, threads, timestamps_holder), daemon=True))
        print(f"{RED}starting thread...{RESET}")
        threads[-1].start()
        
        return interrupt_proc

    def reader(proc, color, tag, processes=None, threads=None, timestamps_holder=None):
        #funktionen som sköter output för varje process via threading, samt reagerar på specifik output för att markera event
        try:
            for line in proc.stdout:
                print(f"{color}[{tag}] {line.rstrip()}\033[0m")
                sys.stdout.flush()
                if tag == "MAVSDK" and "Mission progress: 1/6" in line:
                    print(f"{RED}Starting interrupt timer...{RESET}")
                    threading.Timer(30.0, interrupt_callback).start()
                    
                    delta = datetime.now() - timestamps_holder[0].get_reference_point()
                    timestamp_int = delta.total_seconds()
                    print(f"timestamp in secondsis: {timestamp_int}")
                    timestamps_holder[0].add_event("checkpoint", timestamp_int)
                    
                
                if tag == "INTERRUPT" and "Rotating" in line:
                    print(f"{RED}Starting interrupt timer...{RESET}")
                    
                    delta = datetime.now() - timestamps_holder[0].get_reference_point()
                    timestamp_int = delta.total_seconds()

                    print(f"timestamp in secondsis: {timestamp_int}")
                    timestamps_holder[0].add_event("interruption", timestamp_int)
                    
                    
                
                if tag == "MAVSDK" and "Timecheck" in line:
                    parts = line.split()
                    timestamp_str = " ".join(parts[-2:])
                    
                    reference_point = datetime.fromisoformat(timestamp_str)

                    print("timestamp",reference_point)
                    timestamps_holder.append(timestamps(reference_point))
                    
                
                if tag == "QGC" and "INFO  [logger] closed logfile, bytes written:" in line:
                    print("writing to csv")
                    for event, timestamp in zip(timestamps_holder[0].events, timestamps_holder[0].timestamp):
                        print(f"event: {event}, timestamp: {timestamp}")
                        write_csv(event, timestamp, file_path)
                    print(f"mission ended, killing all processes...")
                    kill_all(processes)
                    exit(0)
        except Exception as e:
            print(f"[{tag}] fault: {e}")
            fault_flag.set()
            kill_all(processes)



#####################################################################
#Huvuddelen av start_program-funktion
####################################################################




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
    #skapar threads-listan
    for proc, color, tag in [
        (processes[0], GREEN, "PX4"),
        (processes[1], YELLOW, "QGC"),
        (processes[2], CYAN, "MAVSDK"),
    ]:
        threads.append(threading.Thread(target=reader   , args=(proc, color, tag, processes, threads, timestamps_holder), daemon=True))
        print(f"Starting thread for {tag} output...")
        threads[-1].start()
    print("vid timer")

    while not fault_flag.is_set() and any(p.poll() is None for p in processes):
        time.sleep(0.2)
    if fault_flag.is_set():
        kill_all(processes)
        print("Fault detected, exiting.")
        sys.exit(1)

    for p in processes:
        p.wait()

    for t in threads: 
        t.join(timeout=0.1)
    #programmet färdigkört, skriver eventloggen till csv och avslutar
    print("all done")
    
    #for event, timestamp in zip(timestamps_holder[0].events, timestamps_holder[0].timestamp): #skriver eventloggen till csv när alla processer är klara
    #    print(f"writing to file:event: {event}, timestamp: {timestamp}")
    #    write_csv(event, timestamp,file_path)

    clean_slate() #rensar ev kvarvarande processer
    sys.exit(0) #avslutar program
    #clean_slate()
   


def main(cwd_qgroundcontrol: str, cwd_px4: str, cwd_mavsdk_mission: str, cwd_interrupt: str, mission_name: str, interrupt_mission_name: str, make_px4: str, file_path: str):
    clean_slate()
    start_program(cwd_qgroundcontrol, cwd_px4, cwd_mavsdk_mission, 
                  cwd_interrupt, mission_name, interrupt_mission_name, make_px4, file_path)

if __name__ == "__main__":
    cwd_qgroundcontrol = "/home/kmos123"
    cwd_px4 = "/home/kmos123/PX4-Autopilot"
    cwd_mavsdk_mission = "/home/kmos123/MAVSDK-Python/examples"
    mission_name = "mission_baylands.py"
    make_px4 = "make px4_sitl gz_x500_baylands"
    cwd_interrupt= "/home/kmos123/MAVSDK-Python/examples"
    interrupt_mission_name = "interrupted_mission.py"
    file_path = 'packets/event_log.csv'
    
    main(cwd_qgroundcontrol,cwd_px4,cwd_mavsdk_mission,cwd_interrupt,mission_name,interrupt_mission_name,make_px4,file_path)
