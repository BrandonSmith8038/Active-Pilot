"""Run ActivePilot locally (outside Docker) against throwaway data, and drive it.

  python .claude/skills/run-activepilot/driver.py smoke   # stage, launch, check API + page, screenshot, stop
  python .claude/skills/run-activepilot/driver.py serve   # stage, launch, keep running until Ctrl-C

Stdlib only. Never touches /data or a real ntfy topic: app.py is copied to a work
dir and its hardcoded /data path is rewritten to <workdir>/data.
"""
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request

UNIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]

def log(*a): print("[driver]", *a, flush=True)

def runtime_files():
    # The Dockerfile COPY line is the list of files the container ships; mirror it exactly
    m = re.search(r"^COPY\s+(.+?)\s+\./\s*$", open(os.path.join(UNIT, "Dockerfile")).read(), re.M)
    return m.group(1).split()

def stage(work, fresh):
    app_dir, data_dir = os.path.join(work, "app"), os.path.join(work, "data")
    if fresh: shutil.rmtree(data_dir, ignore_errors=True)
    os.makedirs(app_dir, exist_ok=True); os.makedirs(data_dir, exist_ok=True)
    for f in runtime_files(): shutil.copy2(os.path.join(UNIT, f), app_dir)
    src = open(os.path.join(app_dir, "app.py"), encoding="utf-8").read()
    d = data_dir.replace("\\", "/")
    src, n = re.subn(r'"/data(/data\.json)?"', lambda m: repr(d + (m.group(1) or "")), src)
    if n != 2: sys.exit(f"[driver] expected 2 '/data' paths in app.py, patched {n}; update stage() in driver.py")
    open(os.path.join(app_dir, "app.py"), "w", encoding="utf-8").write(src)
    deps = os.path.join(work, "deps")
    if subprocess.run([sys.executable, "-c", "import tzdata"], env={**os.environ, "PYTHONPATH": deps},
                      capture_output=True).returncode:
        log("installing tzdata into", deps)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "--target", deps, "tzdata"], check=True)
    return app_dir, data_dir, deps

def launch(app_dir, deps, port, tz):
    env = {**os.environ, "PYTHONPATH": deps, "HTTP_PORT": str(port), "TZ": tz,
           "NTFY_TOPIC": "", "PYTHONUNBUFFERED": "1"}
    out = open(os.path.join(app_dir, "server.log"), "w")
    p = subprocess.Popen([sys.executable, "app.py"], cwd=app_dir, env=env, stdout=out, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(40):
        if p.poll() is not None:
            sys.exit("[driver] server exited:\n" + open(os.path.join(app_dir, "server.log")).read())
        try: urllib.request.urlopen(base + "/api/state", timeout=1); return p, base
        except (urllib.error.URLError, ConnectionError): time.sleep(0.25)
    p.kill(); sys.exit(f"[driver] server never answered on {base} (port in use?)")

def req(base, path, body=None):
    r = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                               method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp: return resp.status, resp.headers.get("Content-Type"), resp.read()
    except urllib.error.HTTPError as e: return e.code, e.headers.get("Content-Type"), e.read()

def screenshot(url, path):
    exe = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not exe: log("no Chrome/Edge found; skipping screenshot"); return None
    prof = tempfile.mkdtemp(prefix="ap-chrome-")  # own profile so it can't collide with the user's open browser
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        "--no-first-run", "--window-size=1280,1100", "--virtual-time-budget=5000",
                        f"--screenshot={path}", url], capture_output=True, timeout=90)
    finally: shutil.rmtree(prof, ignore_errors=True)
    return path if os.path.exists(path) else None

def js_check(app_dir):
    node = shutil.which("node")
    if not node: log("node not found; skipping JS syntax check"); return True
    html = open(os.path.join(app_dir, "dashboard.html"), encoding="utf-8").read()
    js = os.path.join(app_dir, "page.js")
    open(js, "w", encoding="utf-8").write("\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)))
    r = subprocess.run([node, "--check", js], capture_output=True, text=True)
    if r.returncode: print(r.stderr)
    return r.returncode == 0

def smoke(base, app_dir, work):
    fails = []
    def check(name, ok, detail=""):
        log(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
        if not ok: fails.append(name)
    code, ctype, body = req(base, "/")
    check("dashboard page", code == 200 and b"<title>ActivePilot" in body, f"{code} {len(body)}B")
    for f, t in (("logo.png", "image/png"), ("icon.png", "image/png"), ("favicon.ico", "image/x-icon")):
        code, ctype, _ = req(base, "/" + f); check(f"static {f}", code == 200 and ctype == t, f"{code} {ctype}")
    code, ctype, _ = req(base, "/icon.png?x=1")
    check("query string falls back to dashboard", ctype.startswith("text/html"), ctype)
    s = json.loads(req(base, "/api/state")[2])
    check("fresh state", [a["id"] for a in s["airlines"]] == ["ups", "swa", "fdx"]
          and all(a["status"] == "none" for a in s["airlines"]) and s["ntfy"] is False, f"today={s['today']}")
    # Known-good fixture from CLAUDE.md: SWA flights Oct 27 + Oct 30 2026 -> site showed Jan 25 2027
    for d in ("2026-10-27", "2026-10-30"): req(base, "/api/log", {"id": "swa", "date": d})
    swa = next(a for a in json.loads(req(base, "/api/state")[2])["airlines"] if a["id"] == "swa")
    check("SWA strict rolling deadline", swa["deadline"] == "2027-01-25", f"{swa['deadline']} status={swa['status']}")
    tomorrow = (dt.date.fromisoformat(s["today"]) + dt.timedelta(days=1)).isoformat()
    code, _, body = req(base, "/api/log", {"id": "swa", "date": tomorrow})
    check("future date rejected", code == 400, body.decode())
    req(base, "/api/delete", {"id": "swa", "date": "2026-10-27"})
    swa = next(a for a in json.loads(req(base, "/api/state")[2])["airlines"] if a["id"] == "swa")
    check("delete flight", swa["history"] == ["2026-10-30"], str(swa["history"]))
    req(base, "/api/log", {"id": "swa", "date": "2026-10-27"})  # restore so the screenshot shows a dated card
    check("page JS syntax", js_check(app_dir))
    shot = screenshot(base + "/", os.path.join(work, "dashboard.png"))
    log("screenshot:", shot or "none")
    return fails

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["smoke", "serve"])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--tz", default="America/Phoenix")
    ap.add_argument("--workdir", default=os.path.join(tempfile.gettempdir(), "activepilot-run"))
    ap.add_argument("--keep-data", action="store_true", help="serve: reuse data from the last run instead of wiping it")
    a = ap.parse_args()
    work = os.path.abspath(a.workdir)
    app_dir, data_dir, deps = stage(work, fresh=(a.cmd == "smoke" or not a.keep_data))
    p, base = launch(app_dir, deps, a.port, a.tz)
    log(f"running at {base}  (data: {data_dir}, log: {os.path.join(app_dir, 'server.log')})")
    try:
        if a.cmd == "smoke":
            fails = smoke(base, app_dir, work)
            log("ALL PASSED" if not fails else f"{len(fails)} FAILED: {', '.join(fails)}")
            return 1 if fails else 0
        log("Ctrl-C to stop"); p.wait()
    except KeyboardInterrupt: pass
    finally:
        p.terminate(); p.wait(timeout=10)
        tail = open(os.path.join(app_dir, "server.log")).read().strip()
        if tail: log("server output:\n" + tail)

if __name__ == "__main__":
    sys.exit(main())
