#!/usr/bin/env python3
"""BSS Android macro: gathers, converts, runs scheduled tasks. Sends taps over ADB."""
import argparse, json, os, re, select, subprocess, sys, time, io, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "bss_data.json")
PKG = "com.roblox.client"
SERIAL = os.environ.get("ANDROID_SERIAL", "")
DRY = False
PATTERN = [(0, -1), (1, 0), (0, 1), (0, 1), (-1, 0), (0, -1)]  # zigzag around the joystick


# ---------- adb ----------
def adb(*args, binary=False):
    cmd = ["adb"] + (["-s", SERIAL] if SERIAL else []) + list(args)
    if DRY:
        print("[dry]", " ".join(cmd[1:]))
        return b"" if binary else ""
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    return r.stdout if binary else r.stdout.decode(errors="ignore")

def tap(x, y): adb("shell", "input", "tap", str(int(x)), str(int(y)))
def swipe(x0, y0, x1, y1, ms):
    adb("shell", "input", "swipe", *[str(int(v)) for v in (x0, y0, x1, y1)], str(max(int(ms), 50)))

def say(msg):
    print(">>", msg)
    try: subprocess.Popen(["termux-toast", msg], stderr=subprocess.DEVNULL)
    except OSError: pass

def shot():
    from PIL import Image
    if DRY: return Image.new("RGB", (100, 100))
    return Image.open(io.BytesIO(adb("exec-out", "screencap", "-p", binary=True))).convert("RGB")


# ---------- data ----------
def load():
    d = {"routes": {}, "plan": [], "tasks": [], "webhook": "", "joy": None, "bar": None,
         "honey": None, "reset": [], "tool": None, "max_gather": 300, "step_ms": 1200,
         "join": "roblox://placeId=1537690962"}
    if os.path.exists(DATA): d.update(json.load(open(DATA)))
    return d

def save(d): json.dump(d, open(DATA, "w"), indent=1)

def notify(d, msg):
    print("[note]", msg)
    if d["webhook"] and not DRY:
        try:
            req = urllib.request.Request(d["webhook"], json.dumps({"content": msg}).encode(),
                                         {"Content-Type": "application/json", "User-Agent": "bss"})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e: print("discord failed:", e)


# ---------- learning from your taps ----------
def touch_info():
    if DRY: return 1080, 2400, 1, 1079, 2399
    wm = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size"))
    W, H = int(wm[1]), int(wm[2])
    rot = re.search(r"SurfaceOrientation:\s*(\d)", adb("shell", "dumpsys input"))
    p = adb("shell", "getevent", "-pl")
    mx = re.search(r"ABS_MT_POSITION_X\s*:.*?max (\d+)", p)
    my = re.search(r"ABS_MT_POSITION_Y\s*:.*?max (\d+)", p)
    if not (mx and my): sys.exit("Could not read touch range from getevent.")
    return min(W, H), max(W, H), int(rot[1]) if rot else 0, int(mx[1]), int(my[1])

def capture(n=None, idle=None):
    """Record strokes you make on the phone. Stops after n strokes, or after idle seconds of quiet."""
    if DRY: return [{"x0": 100, "y0": 900, "x1": 100, "y1": 700, "ms": 800, "gap": 0}] * (n or 1)
    Wn, Hn, rot, mx, my = touch_info()
    def conv(rx, ry):
        x, y = rx / mx * Wn, ry / my * Hn
        return [(x, y), (y, Wn - x), (Wn - x, Hn - y), (Hn - y, x)][rot]
    p = subprocess.Popen(["adb"] + (["-s", SERIAL] if SERIAL else []) + ["shell", "getevent", "-lt"],
                         stdout=subprocess.PIPE, bufsize=0)
    st = {"x": None, "y": None, "cur": None, "last_end": None, "wall": time.time()}
    strokes, buf = [], b""
    def handle(line):
        m = re.match(r"\[\s*([\d.]+)\]\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)", line)
        if not m: return
        t, code, val = float(m[1]), m[3], m[4]
        if code == "ABS_MT_POSITION_X": st["x"] = int(val, 16)
        elif code == "ABS_MT_POSITION_Y": st["y"] = int(val, 16)
        elif code == "ABS_MT_TRACKING_ID":
            if val.lower() == "ffffffff":
                c = st["cur"]
                if c and c["pts"]:
                    (x0, y0), (x1, y1) = c["pts"][0], c["pts"][-1]
                    gap = int((c["t0"] - st["last_end"]) * 1000) if st["last_end"] else 0
                    strokes.append({"x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1),
                                    "ms": int((t - c["t0"]) * 1000), "gap": gap})
                    st["last_end"] = t
                st["cur"] = None; st["wall"] = time.time()
            else: st["cur"] = {"t0": t, "pts": []}
        elif code == "SYN_REPORT" and st["cur"] is not None and st["x"] is not None:
            st["cur"]["pts"].append(conv(st["x"], st["y"]))
    try:
        while not (n and len(strokes) >= n):
            r, _, _ = select.select([p.stdout], [], [], 0.5)
            if not r:
                if idle and strokes and st["cur"] is None and time.time() - st["wall"] >= idle: break
                continue
            chunk = os.read(p.stdout.fileno(), 4096)
            if not chunk: break
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for ln in lines: handle(ln.decode(errors="ignore"))
    except KeyboardInterrupt: pass
    finally: p.kill()
    return strokes

def connect():
    if "device" in adb("devices").split("List of devices attached")[-1] and not DRY:
        return
    if DRY: return
    print("Phone not connected. Turn on Developer options > Wireless debugging.")
    hp = input("Tap 'Pair device with pairing code'. Enter ip:port shown (or blank to skip): ").strip()
    if hp:
        code = input("Pairing code: ").strip()
        subprocess.run(["adb", "pair", hp], input=code.encode())
    hp = input("Now enter the ip:port on the main Wireless debugging screen: ").strip()
    subprocess.run(["adb", "connect", hp])


# ---------- reading the screen ----------
def fill(img, d):
    (x0, x1, y), col = d["bar"]["x"], tuple(d["bar"]["color"]), None
    y = d["bar"]["y"]; hit = 0; N = 40
    for i in range(N):
        px = img.getpixel((int(x0 + (x1 - x0) * i / (N - 1)), y))
        if sum(abs(a - b) for a, b in zip(px, d["bar"]["color"])) < 90: hit += 1
    return hit / N

def sig(img):
    s = img.resize((32, 18)).convert("L")
    return list(s.getdata())

def diff(a, b): return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


# ---------- actions ----------
def replay(strokes):
    for s in strokes:
        time.sleep(min(s["gap"], 8000) / 1000)
        if abs(s["x1"] - s["x0"]) + abs(s["y1"] - s["y0"]) < 25 and s["ms"] < 300: tap(s["x0"], s["y0"])
        else: swipe(s["x0"], s["y0"], s["x1"], s["y1"], s["ms"])

def reverse_walk(strokes, d):
    jx, jy, r = d["joy"]
    out = []
    for s in reversed(strokes):
        if abs(s["x0"] - jx) + abs(s["y0"] - jy) > 1.6 * r: continue  # only joystick drags walk
        out.append({**s, "x1": 2 * s["x0"] - s["x1"], "y1": 2 * s["y0"] - s["y1"]})
    return out

def reset(d):
    for s in d["reset"]:
        time.sleep(min(s["gap"], 4000) / 1000); tap(s["x0"], s["y0"])
    time.sleep(6)

def gather(d):
    jx, jy, r = d["joy"]; end = time.time() + d["max_gather"]; i = 0; still = 0; prev = None
    while time.time() < end:
        dx, dy = PATTERN[i % len(PATTERN)]; i += 1
        swipe(jx, jy, jx + dx * r, jy + dy * r, d["step_ms"])
        if d["tool"]: tap(*d["tool"])
        if i % 3: continue
        if DRY:
            if i >= 6: return "full"
            continue
        img = shot()
        if fill(img, d) >= 0.95: return "full"
        s = sig(img)
        still = still + 1 if prev and diff(s, prev) < 1.5 else 0
        prev = s
        if still >= 4: return "stuck"
    return "timeout"

def convert(d):
    tap(*d["honey"])
    end = time.time() + 150
    while time.time() < end:
        time.sleep(5)
        if DRY or fill(shot(), d) < 0.05: return
    
def fg(): return PKG in adb("shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")

def ensure_game(d):
    if DRY or fg(): return False
    notify(d, "Roblox closed, rejoining")
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", d["join"])
    time.sleep(75)
    if not fg():
        adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1"); time.sleep(75)
    return True

def do_route(d, name, is_field):
    rt = d["routes"][name]["strokes"]
    replay(rt); time.sleep(1)
    result = gather(d) if is_field else "done"
    if result != "done": notify(d, f"{name}: gather ended ({result})")
    if result == "stuck": reset(d); return
    replay(reverse_walk(rt, d)); time.sleep(1)
    if is_field: convert(d)
    else: reset(d)


# ---------- commands ----------
def need(d, *keys):
    for k in keys:
        if not d[k]: sys.exit(f"Missing '{k}'. Run: python bss.py setup")

def cmd_setup(a):
    connect(); d = load()
    say("Open the game. Tap joystick CENTER, then its EDGE."); j = capture(2)
    r = int(((j[1]["x0"] - j[0]["x0"]) ** 2 + (j[1]["y0"] - j[0]["y0"]) ** 2) ** .5)
    d["joy"] = [j[0]["x0"], j[0]["y0"], max(r, 40)]
    say("Fill your backpack. Tap the bar's LEFT end, then RIGHT end."); b = capture(2)
    img = shot(); x0, x1 = b[0]["x0"], b[1]["x0"]; y = b[0]["y0"]
    d["bar"] = {"x": [x0, x1], "y": y, "color": list(img.getpixel((int(x0 + .9 * (x1 - x0)), y)))}
    say("Tap Make Honey."); d["honey"] = [(h := capture(1)[0])["x0"], h["y0"]]
    say("Tap where your tool swings (screen center is fine)."); t = capture(1)[0]; d["tool"] = [t["x0"], t["y0"]]
    say("Record your reset: menu, reset button, confirm. Then wait 5s.")
    d["reset"] = capture(idle=5); save(d); say("Setup saved. Next: python bss.py check")

def cmd_check(a):
    d = load(); need(d, "joy", "bar", "honey")
    print("game in foreground:", fg() if not DRY else "dry")
    print("backpack fill now: %.0f%%" % (100 * fill(shot(), d)))
    print("routes:", list(d["routes"]), "plan:", d["plan"], "tasks:", d["tasks"])

def cmd_record(a, kind):
    d = load(); need(d, "joy")
    say(f"Recording '{a.name}'. Start at your hive after a reset. Stop touching for 6s to finish.")
    s = capture(idle=6)
    d["routes"][a.name] = {"kind": kind, "strokes": s}
    if kind == "field" and a.name not in d["plan"]: d["plan"].append(a.name)
    save(d); print(f"saved {a.name}: {len(s)} strokes")

def cmd_plan(a): d = load(); d["plan"] = a.names; save(d)
def cmd_schedule(a):
    d = load(); d["tasks"] = [t for t in d["tasks"] if t["route"] != a.name] + [{"route": a.name, "every": a.minutes * 60}]; save(d)
def cmd_webhook(a): d = load(); d["webhook"] = a.url; save(d); notify(d, "BSS macro connected")

def cmd_run(a):
    d = load(); need(d, "joy", "bar", "honey", "plan")
    end = time.time() + a.minutes * 60; due = {}; loops = 0
    notify(d, f"Started, running {a.minutes} min"); reset(d)
    while time.time() < end:
        if ensure_game(d): reset(d)
        for t in d["tasks"]:
            if time.time() >= due.get(t["route"], 0) and t["route"] in d["routes"]:
                do_route(d, t["route"], False); due[t["route"]] = time.time() + t["every"]
                notify(d, f"Task done: {t['route']}")
        for f in d["plan"]:
            if time.time() >= end: break
            do_route(d, f, True)
        loops += 1; notify(d, f"Loop {loops} done")
    notify(d, "Finished")

def main():
    global DRY
    p = argparse.ArgumentParser(); p.add_argument("--dry", action="store_true")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup"); sp.add_parser("check")
    for k in ("add-field", "add-task"): sp.add_parser(k).add_argument("name")
    sp.add_parser("plan").add_argument("names", nargs="+")
    s = sp.add_parser("schedule"); s.add_argument("name"); s.add_argument("minutes", type=int)
    sp.add_parser("webhook").add_argument("url")
    r = sp.add_parser("run"); r.add_argument("--minutes", type=int, default=60)
    a = p.parse_args(); DRY = a.dry
    {"setup": cmd_setup, "check": cmd_check, "plan": cmd_plan, "schedule": cmd_schedule,
     "webhook": cmd_webhook, "run": cmd_run,
     "add-field": lambda a: cmd_record(a, "field"), "add-task": lambda a: cmd_record(a, "task")}[a.cmd](a)

if __name__ == "__main__":
    main()
