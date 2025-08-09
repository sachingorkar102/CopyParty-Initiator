import tkinter as tk
from datetime import datetime
from PIL import Image, ImageDraw
import subprocess
import pystray
import threading
# import sys
import os
import signal
import gspread
from google.oauth2.service_account import Credentials
import re


CLOUDFLARED: str = "cloudflared"
COPYPARTY: str = "copyparty"
CONFIG_PATH: str = ""
OUTPUT_PATH: str = ""


current_proc = {}
outputText1: tk.Entry
outputText2: tk.Entry
tray_icon = None

def get_output_dir():
    updatePaths()
    return os.path.join(os.getcwd(),OUTPUT_PATH)

def get_config_path():
    updatePaths()
    return os.path.join(os.getcwd(),CONFIG_PATH)

def get_output_file(name: str) -> str:
    output_path: str = get_output_dir()
    os.makedirs(output_path, exist_ok=True)
    return os.path.join(output_path, f"{name}.log")

def runCommand(cmd: list[str], name: str, output: tk.Entry) -> None:
    global current_proc
    if name in current_proc and current_proc[name] is not None:
        setOutputText(f"{name} is already running.", output)
        return

    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == 'nt' else 0
    out_path = get_output_file(name)

    with open(out_path, "w") as out:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags
        )

    current_proc[name] = proc
    setOutputText(f"Started '{name}' with PID {proc.pid}", output)


def stopCommand(name: str, output: tk.Entry) -> None:
    global current_proc
    proc = current_proc.get(name)

    if not proc:
        setOutputText(f"No running process found for '{name}'.", output)
        return

    try:
        proc.terminate()  # or proc.kill() for force
        setOutputText(f"Stopped '{name}' with PID {proc.pid}", output)
        current_proc[name] = None
    except Exception as e:
        setOutputText(f"Error stopping '{name}': {e}", output)


def closingEvents() -> None:
    for name in list(current_proc.keys()): 
        if(name == COPYPARTY):
            stopCommand(name,cpOutputText) 
        elif(name == CLOUDFLARED):
            stopCommand(name,cfOutputText) 
    if tray_icon is not None:
        tray_icon.stop()
    window.destroy()
        


def setOutputText(text: str,output: tk.Entry) -> None:
    
    output.config(state="normal")
    output.delete(0,tk.END)
    output.insert(0,text)
    output.config(state="readonly")      

def runCloudFlared() -> None:
    runCommand(["cloudflared","tunnel","--url","http://127.0.0.1:80"],CLOUDFLARED,cfOutputText)
    t = threading.Timer(interval=10, function=update_sheet)
    t.daemon = True
    t.start()
    

def runCopyParty() -> None:
    runCommand(["pyw", get_output_dir() + "copyparty-sfx.py", "-c", get_config_path() + "cpconfig.config"],COPYPARTY,cpOutputText)

def updatePaths():
    global OUTPUT_PATH
    global CONFIG_PATH
    with open("copyparty-initiator.txt", "r") as file:
        for line in file:
            if line.startswith("config_path:"):
                CONFIG_PATH = line.split("config_path:")[1].strip()
            elif line.startswith("output_path:"):
                OUTPUT_PATH = line.split("output_path:")[1].strip()    


def update_sheet():
    link: str = None
    timestamp: str = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
    with open(get_output_file(CLOUDFLARED),"r") as s:
        for line in s:
            match = re.search(r'https://[^\s]*\.trycloudflare\.com', line)
            if(match):
                link = match.group(0)
                break
    if(link==None):
        stopCommand(COPYPARTY,cpOutputText)
        stopCommand(CLOUDFLARED,cfOutputText)
        return
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = Credentials.from_service_account_file("credentials.json",scopes=scopes)
    client = gspread.authorize(creds)

    sheet_id = "1yZZlKgbljklhGtNFHdYTJsRRsDIUm9CJG7QPE8xmgp0"
    sheet = client.open_by_key(sheet_id).sheet1

    col_values = sheet.col_values(1)

    next_empty_row = len(col_values)+1
    sheet.update_cell(next_empty_row,1,timestamp)
    sheet.update_cell(next_empty_row,2,link)

def should_restart():
    false_path = get_config_path()+"should_restart_false.txt"
    true_path = get_config_path()+"should_restart_true.txt"
    file_path = os.path.join(true_path)
    file_is_true: bool = os.path.isfile(file_path)
    if(file_is_true or (current_proc.get(CLOUDFLARED)==None and current_proc.get(COPYPARTY)==None)):
        if(file_is_true):
            os.rename(true_path,false_path)
        stopCommand(COPYPARTY,cpOutputText)
        stopCommand(CLOUDFLARED,cfOutputText)    
        t_restart = threading.Timer(5, function=restart)
        t_restart.daemon = True
        t_restart.start()
    t_should_restart = threading.Timer(300, should_restart)
    t_should_restart.daemon = True
    t_should_restart.start()

def restart():
    runCopyParty()
    runCloudFlared()

def create_image():
    image = Image.new('RGB', (64, 64), color="gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image


def on_quit(icon, item):
    icon.stop()
    window.destroy()


def show_window(icon, item):
    icon.stop()
    window.after(0, window.deiconify)


def minimize_to_tray(event=None):
    window.withdraw()
    icon = pystray.Icon("name", create_image(), "CopyParty Initiator", menu=pystray.Menu(
        pystray.MenuItem("Show", show_window),
        pystray.MenuItem("Quit", on_quit)
    ))
    threading.Thread(target=icon.run, daemon=True).start()


updatePaths()
window = tk.Tk()


window.geometry("400x400")
window.resizable(False, False)
window.protocol("WM_DELETE_WINDOW",closingEvents)
window.bind("<Unmap>", lambda e: minimize_to_tray() if window.state() == "iconic" else None)
window.title("Copyparty Initiator")
cpOutputText = tk.Entry(window,state="readonly",width=50)
cpOutputText.pack(padx=5,pady=5)

cprunBtn = tk.Button(window,text="Run CopyParty",command=runCopyParty)
cprunBtn.pack(padx=10,pady=10)

cpstopBtn = tk.Button(window,text="Stop CopyParty",command=lambda: stopCommand(COPYPARTY,cpOutputText))
cpstopBtn.pack(padx=12,pady=12)

cfOutputText = tk.Entry(window,state="readonly",width=50)
cfOutputText.pack(padx=16,pady=16)


cfrunBtn = tk.Button(window,text="Run Cloudflared",command=runCloudFlared)
cfrunBtn.pack(padx=20,pady=20)

cfstopBtn = tk.Button(window,text="Stop Cloudflared",command=lambda: stopCommand(CLOUDFLARED,cfOutputText))
cfstopBtn.pack(padx=22,pady=22)

minimize_to_tray()
should_restart()

window.mainloop()


