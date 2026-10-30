import json, os, threading, time, calendar, datetime as dt, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

PORT = int(os.getenv("HTTP_PORT", "8100"))
TZ = ZoneInfo(os.getenv("TZ", "UTC"))
NTFY = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
TOPIC = os.getenv("NTFY_TOPIC", "").strip()
HOUR = int(os.getenv("NOTIFY_HOUR", "16"))
FILE = "/data/data.json"
lock = threading.Lock()

# Card accent colors live here (not in data.json) so changing them never needs a data reset
COLORS = {"ups": "#8c6a2b", "swa": "#3b4f8f", "fdx": "#5a3f8a"}

# Official rules (flights needed per rolling period, plus grace days before deactivation)
RULES = {"ups": (1, 30, "days", 0), "swa": (2, 90, "days", 7), "fdx": (1, 90, "days", 10)}

def seed(i, name, sub, color, n, p, u, g=0):
    return {"id": i, "name": name, "sub": sub, "color": color, "flights": n,
            "period": p, "unit": u, "grace": g, "history": [], "notified": ""}

state = {"warn_days": 5, "rules_v": 2, "airlines": [
    seed("ups", "UPS", "UPS Virtual Airlines", "#8c6a2b", 1, 30, "days"),
    seed("swa", "Southwest", "Southwest Virtual", "#3b4f8f", 2, 90, "days"),
    seed("fdx", "FedEx", "FedEx Virtual", "#5a3f8a", 1, 90, "days", 10),
]}

def today(): return dt.datetime.now(TZ).date()

def load():
    global state
    try:
        with open(FILE) as f: state = json.load(f)
    except Exception: save()

def migrate():
    # One-time update of saved data to the exact airline rules; flight history is kept
    if state.get("rules_v", 0) < 2:
        for a in state["airlines"]:
            if a["id"] in RULES: a["flights"], a["period"], a["unit"], a["grace"] = RULES[a["id"]]
        state["rules_v"] = 2; save()
    if state.get("rules_v", 0) < 3:
        # Southwest's site counts fixed 90-day periods; its current period ends Dec 1, 2026
        for a in state["airlines"]:
            if a["id"] == "swa": a["period_end"] = "2026-12-01"
        state["rules_v"] = 3; save()
    if state.get("rules_v") < 4:
        # Southwest SOP: 7-day warning status after missing the requirement
        for a in state["airlines"]:
            if a["id"] == "swa": a["grace"] = 7
        state["rules_v"] = 4; save()

def save():
    os.makedirs("/data", exist_ok=True)
    with open(FILE + ".tmp", "w") as f: json.dump(state, f, indent=1)
    os.replace(FILE + ".tmp", FILE)

def add_period(d, n, unit):
    if unit == "days": return d + dt.timedelta(days=n)
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def compute(a):
    h = sorted(a["history"], reverse=True)
    out = {k: a[k] for k in ("id", "name", "sub", "color", "flights", "period", "unit")}
    out["color"] = COLORS.get(a["id"], a.get("color", "#445"))
    out["history"] = h
    out["last"] = h[0] if h else None
    out["grace"] = a.get("grace", 0)
    out["period_end"] = a.get("period_end", "")
    cut = add_period(today(), -a["period"], a["unit"])
    out["in_window"] = sum(1 for x in h if dt.date.fromisoformat(x) > cut)
    out["grace_left"] = None
    pe = a.get("period_end") if a["unit"] == "days" else ""
    out["fixed"], out["done"] = bool(pe), False
    if pe:
        # Fixed back-to-back periods: current period is (end - period, end]; deadline is its end
        step = a["period"]
        end = dt.date.fromisoformat(pe)
        end += dt.timedelta(days=step * -((-(today() - end).days) // step))
        start = end - dt.timedelta(days=step)
        out["in_window"] = sum(1 for x in h if start < dt.date.fromisoformat(x) <= end)
        dl = end
        if out["in_window"] >= a["flights"]:
            dl = end + dt.timedelta(days=step); out["done"] = True
    elif not h:
        out.update(status="none", deadline=None, days_left=None); return out
    else:
        basis = dt.date.fromisoformat(h[min(a["flights"], len(h)) - 1])
        dl = add_period(basis, a["period"], a["unit"])
    left = (dl - today()).days
    out["deadline"], out["days_left"] = dl.isoformat(), left
    if left < 0: out["grace_left"] = out["grace"] + left
    out["status"] = "overdue" if left < 0 else "warning" if left <= state["warn_days"] else "ok"
    return out

def ntfy(title, msg, prio="default", tags="airplane"):
    if not TOPIC: return False
    req = urllib.request.Request(f"{NTFY}/{TOPIC}", data=msg.encode(), method="POST",
        headers={"Title": title, "Priority": prio, "Tags": tags})
    try:
        urllib.request.urlopen(req, timeout=10); return True
    except Exception as e:
        print("ntfy failed:", e); return False

def notify_loop():
    while True:
        try:
            now = dt.datetime.now(TZ)
            with lock:
                for a in state["airlines"]:
                    if now.hour < HOUR or a.get("notified") == now.date().isoformat(): continue
                    c = compute(a)
                    if c["status"] == "overdue":
                        n = -c["days_left"]
                        g = c["grace_left"]
                        extra = "" if not c["grace"] else f" Grace period: {g} day{'s' if g != 1 else ''} left." if g >= 0 else " Grace period has ended."
                        ntfy(f"{a['name']} is overdue", f"Overdue by {n} day{'s' if n != 1 else ''}. Last flight: {c['last']}.{extra}", "high", "rotating_light")
                    elif c["status"] == "warning":
                        l = c["days_left"]
                        when = "due TODAY" if l == 0 else f"due in {l} day{'s' if l != 1 else ''} ({c['deadline']})"
                        ntfy(f"{a['name']}: fly soon", f"Next flight {when}. Last flight: {c['last']}.", "high" if l == 0 else "default", "warning")
                    a["notified"] = now.date().isoformat()
                save()
        except Exception as e: print("notify loop error:", e)
        time.sleep(30)

STATIC = {"/logo.png": "image/png", "/icon.png": "image/png", "/favicon.ico": "image/x-icon"}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/state":
            with lock: self.send(200, {"today": today().isoformat(), "warn_days": state["warn_days"],
                                       "ntfy": bool(TOPIC), "airlines": [compute(a) for a in state["airlines"]]})
        elif self.path in STATIC:
            with open(os.path.join(os.path.dirname(__file__), self.path[1:]), "rb") as f:
                self.send(200, f.read(), STATIC[self.path])
        else:
            with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), "rb") as f:
                self.send(200, f.read(), "text/html; charset=utf-8")
    def do_POST(self):
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with lock:
                a = next((x for x in state["airlines"] if x["id"] == d.get("id")), None)
                p = self.path
                if p in ("/api/log", "/api/delete"):
                    day = dt.date.fromisoformat(d.get("date") or today().isoformat())
                    if p == "/api/log":
                        if day > today(): return self.send(400, {"error": "Date can't be in the future."})
                        a["history"].append(day.isoformat())
                    elif d["date"] in a["history"]: a["history"].remove(d["date"])
                elif p == "/api/settings":
                    a["flights"] = max(1, int(d["flights"])); a["period"] = max(1, int(d["period"]))
                    a["unit"] = d["unit"] if d["unit"] in ("days", "months") else "days"
                    a["grace"] = max(0, int(d.get("grace", 0)))
                    a["period_end"] = dt.date.fromisoformat(d["period_end"]).isoformat() if d.get("period_end") else ""
                elif p == "/api/warn": state["warn_days"] = max(0, min(60, int(d["days"])))
                elif p == "/api/test":
                    ok = ntfy("Test from ActivePilot", "Notifications are working.")
                    return self.send(200, {"sent": ok})
                save()
            self.send(200, {"ok": True})
        except Exception as e: self.send(400, {"error": str(e)})

if __name__ == "__main__":
    load(); migrate()
    threading.Thread(target=notify_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
