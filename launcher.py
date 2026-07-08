import os, sys, time, subprocess, signal

WATCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
WATCH_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_EXTS = (".py",)

def get_mtime():
    """Get latest mtime of any .py file in the project."""
    latest = 0
    for root, dirs, files in os.walk(WATCH_DIR):
        dirs[:] = [d for d in dirs if d not in ("data", "__pycache__", ".git", "templates")]
        for f in files:
            if f.endswith(WATCH_EXTS):
                try:
                    m = os.path.getmtime(os.path.join(root, f))
                    if m > latest:
                        latest = m
                except:
                    pass
    return latest

print(f"Watching {WATCH_DIR} for .py changes...")
print("Bot restarts automatically when any source file is modified.\n")

last_mtime = get_mtime()
proc = None

def stop():
    global proc
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            try: proc.kill()
            except: pass
        proc = None

def start():
    global proc
    stop()
    print(f"[{time.strftime('%H:%M:%S')}] Starting bot...")
    proc = subprocess.Popen([sys.executable, "bot.py"])

start()

try:
    while True:
        time.sleep(1)
        current = get_mtime()
        if current != last_mtime:
            last_mtime = current
            print(f"[{time.strftime('%H:%M:%S')}] bot.py changed, restarting...")
            start()
        # Also restart if process died
        if proc and proc.poll() is not None:
            print(f"[{time.strftime('%H:%M:%S')}] Bot process exited (code {proc.returncode}), restarting in 3s...")
            time.sleep(3)
            start()
except KeyboardInterrupt:
    print("\nShutting down...")
    stop()
