#!/usr/bin/env python3
"""
Vinted AI — Cockpit
===================
A small cross-platform (macOS / Windows / Linux) desktop control panel that ties
the whole project together so you never touch a terminal:

  • Start / Stop the web backend (the phone swipe app)
  • A QR code + URL, always visible — scan it to open the app on your phone
  • Scrape (with a settings bubble) / Retrain / Update, streaming REAL output
  • An integrated live terminal: boot scan, real job logs, idle heartbeat
  • Keeps the computer awake while the server is up or a job is running

Run it with the project's virtualenv Python:
    python launcher.py
(or double-click the platform launcher: "Vinted AI.command" / ".bat" / ".sh")
"""
import binascii
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

import qrcode
from PIL import ImageTk

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PORT = 8000
SYSTEM = platform.system()               # 'Darwin' | 'Windows' | 'Linux'
CONFIG_FILE = os.path.join(ROOT, "scraper_config.txt")
PREFS_FILE = os.path.join(ROOT, ".launcher_prefs.json")
PASSWORD_HASH_FILE = os.path.join(ROOT, "webapp", "password.hash")
DB_FILE = os.path.join(ROOT, "webapp", "vinted_clothes.db")
REQS = os.path.join(ROOT, "requirements.txt")

PIPELINES = {
    "scrape": ("Scrape new items", [
        ("Scraping Vinted",      [PY, os.path.join(ROOT, "vinted_scraper.py")]),
        ("Importing to DB",      [PY, os.path.join(ROOT, "db_creator.py")]),
        ("Computing embeddings", [PY, os.path.join(ROOT, "compute_embeddings.py")]),
    ]),
    "retrain": ("Retrain model", [
        ("Training MLP",  [PY, os.path.join(ROOT, "train_mlp.py")]),
        ("Scoring items", [PY, os.path.join(ROOT, "score_with_mlp.py")]),
    ]),
    "update": ("Update app", [
        ("Fetching latest",      ["git", "fetch", "origin"]),
        ("Resetting to remote",  ["git", "reset", "--hard", "@{u}"]),
        ("Updating dependencies", [PY, "-m", "pip", "install", "-r", REQS, "-q"]),
    ]),
}


# ── config + prefs ─────────────────────────────────────────────────────────────

def read_config():
    polish, max_pages, urls = False, 20, []
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                m = re.match(r"filter_polish\s*=\s*(\w+)", s)
                if m:
                    polish = m.group(1).lower() == "yes"; continue
                m = re.match(r"max_pages\s*=\s*(\d+)", s)
                if m:
                    max_pages = int(m.group(1)); continue
                if re.match(r"https?://", s):
                    urls.append(s)
    except FileNotFoundError:
        pass
    return polish, max_pages, urls


def write_config(polish, max_pages, urls):
    try:
        lines = open(CONFIG_FILE, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        lines = []
    out = []
    for line in lines:
        s = line.strip()
        if re.match(r"\s*filter_polish\s*=", line):
            out.append(f"filter_polish = {'yes' if polish else 'no'}")
        elif re.match(r"\s*max_pages\s*=", line):
            out.append(f"max_pages = {max_pages}")
        elif re.match(r"https?://", s):
            continue                       # drop old URLs; re-appended at end
        else:
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    out.append("")
    for u in urls:
        u = u.strip()
        if u:
            out.append(u)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def load_prefs():
    try:
        return json.load(open(PREFS_FILE))
    except Exception:
        return {}


def save_prefs(d):
    try:
        json.dump(d, open(PREFS_FILE, "w"))
    except Exception:
        pass


# ── helpers ─────────────────────────────────────────────────────────────────────

def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def make_qr_photo(url: str):
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color="#0b0b0e", back_color="#f5f2ea").convert("RGB").resize((150, 150))
    return ImageTk.PhotoImage(img)


def _hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(key).decode()


def _age(mtime) -> str:
    secs = max(0, time.time() - mtime)
    if secs < 3600:
        return f"{int(secs//60)}m"
    if secs < 86400:
        return f"{int(secs//3600)}h"
    return f"{int(secs//86400)}d"


def _git(args, timeout=6):
    try:
        return subprocess.run(["git", "-C", ROOT] + args, capture_output=True,
                              text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def _db_counts():
    try:
        import sqlite3
        con = sqlite3.connect(DB_FILE)
        n = con.execute("select count(*) from items").fetchone()[0]
        try:
            r = con.execute("select count(*) from ratings").fetchone()[0]
        except Exception:
            r = 0
        con.close()
        return n, r
    except Exception:
        return None, None


class KeepAwake:
    def __init__(self):
        self._proc = None; self._win_engaged = False

    def engage(self):
        if SYSTEM == "Windows":
            if not self._win_engaged:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
                self._win_engaged = True
            return
        if self._proc and self._proc.poll() is None:
            return
        if SYSTEM == "Darwin":
            self._proc = subprocess.Popen(["caffeinate", "-dimsu"])
        elif SYSTEM == "Linux" and shutil.which("systemd-inhibit"):
            self._proc = subprocess.Popen([
                "systemd-inhibit", "--what=sleep:idle",
                "--why=Vinted AI cockpit", "--mode=block", "sleep", "infinity"])

    def release(self):
        if SYSTEM == "Windows":
            if self._win_engaged:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                self._win_engaged = False
            return
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None


class ServerProcess:
    def __init__(self):
        self.proc = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running():
            return
        creation = 0
        if SYSTEM == "Windows":
            creation = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        self.proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "backend:app", "--host", "0.0.0.0", "--port", str(PORT)],
            cwd=os.path.join(ROOT, "webapp"),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=creation)

    def stop(self):
        if self.running():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None


class JobRunner:
    """Runs a list of (label, argv) steps in a worker thread, streaming output."""
    def __init__(self, on_line, on_done):
        self.on_line = on_line
        self.on_done = on_done
        self.running = False
        self._q = queue.Queue()

    def start(self, steps):
        if self.running:
            return False
        self.running = True
        threading.Thread(target=self._run, args=(steps,), daemon=True).start()
        return True

    def _run(self, steps):
        ok = True
        env = dict(os.environ, PYTHONUNBUFFERED="1", TERM="dumb", NO_COLOR="1")
        for label, argv in steps:
            self._q.put((f"$ {label.lower()}…", "cmd"))
            try:
                proc = subprocess.Popen(
                    argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=env)
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self._q.put((line, classify(line)))
                proc.wait()
            except Exception as e:
                self._q.put((f"✗ {e}", "red")); ok = False; break
            if proc.returncode != 0:
                self._q.put((f"✗ {label} failed (exit {proc.returncode})", "red")); ok = False; break
            self._q.put((f"✓ {label} done", "ok"))
        self._q.put(("__DONE__", ok))

    def drain(self):
        try:
            while True:
                item = self._q.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self.running = False
                    self.on_done(item[1])
                else:
                    self.on_line(*item)
        except queue.Empty:
            pass


def classify(t: str) -> str:
    s = t.strip(); low = s.lower()
    if s.startswith("$"):
        return "cmd"
    if "✓" in s or any(k in low for k in ("done", "saved", "success", "finished", "ok")):
        return "ok"
    if "✗" in s or any(k in low for k in ("error", "fail", "traceback", "fatal")):
        return "red"
    if any(k in low for k in ("warn", "skip", "retry")):
        return "amber"
    if s[:1] in ("→", "»", "▶", "="):
        return "cyan"
    return "dim"


# ── palette / fonts ────────────────────────────────────────────────────────────

C = {
    "bg":       "#0a0a0d",
    "panel":    "#121219",
    "surface":  "#1a1a23",
    "hover":    "#22222e",
    "border":   "#26262f",
    "text":     "#f5f2ea",
    "dim":      "#a6a299",
    "faint":    "#6b675f",
    "accent":   "#e6bd76",
    "accent_d": "#cfa356",
    "on_accent": "#1a1206",
    "ok":       "#4ade80",
    "bad":      "#f87171",
    "green":    "#6bff9e",
    "tg_dim":   "#4f9b6d",
    "tg_amber": "#ffce6a",
    "tg_red":   "#ff7a7a",
    "tg_cyan":  "#7fd6ff",
    "tg_white": "#eaffea",
}
TAGS = {"ok": "green", "white": "tg_white", "dim": "tg_dim", "cyan": "tg_cyan",
        "amber": "tg_amber", "red": "tg_red", "cmd": "tg_white"}


def pick_font(families, candidates, fallback):
    avail = {f.lower() for f in families}
    for c in candidates:
        if c.lower() in avail:
            return c
    return fallback


# ── UI ───────────────────────────────────────────────────────────────────────

class Cockpit(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vinted AI — Cockpit")
        self.configure(bg=C["bg"])
        self.geometry("1100x780")
        self.minsize(960, 700)

        fams = set(tkfont.families())
        self.f_serif = pick_font(fams, ["Fraunces", "Georgia", "Noto Serif", "DejaVu Serif"], "Times")
        self.f_ui = pick_font(fams, ["Hanken Grotesk", "Helvetica Neue", "Segoe UI", "DejaVu Sans"], "Helvetica")
        self.f_mono = pick_font(fams, ["JetBrains Mono", "Menlo", "DejaVu Sans Mono", "Consolas"], "Courier")

        self.server = ServerProcess()
        self.keep_awake = KeepAwake()
        self.job = JobRunner(self._log, self._job_done)
        self.url = f"http://{local_ip()}:{PORT}"
        self.prefs = load_prefs()

        self._evt_q = queue.Queue()
        self._cursor_on = True

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._tick)
        self.after(0, self._blink)
        threading.Thread(target=self._boot_scan, daemon=True).start()
        self.after(9000, self._heartbeat)

    # -- layout --
    def _build(self):
        self.columnconfigure(0, weight=0, minsize=360)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("V.Horizontal.TProgressbar", troughcolor=C["surface"],
                        background=C["accent"], bordercolor=C["surface"],
                        lightcolor=C["accent"], darkcolor=C["accent"], thickness=4)

        # ── SIDEBAR ──────────────────────────────────────────────────
        side = tk.Frame(self, bg=C["panel"], highlightbackground=C["border"], highlightthickness=1)
        side.grid(row=0, column=0, sticky="nsew")
        pad = tk.Frame(side, bg=C["panel"])
        pad.pack(fill="both", expand=True, padx=22, pady=22)

        tk.Label(pad, text="· vinted intelligence ·", bg=C["panel"], fg=C["faint"],
                 font=(self.f_mono, 8)).pack(anchor="w")
        wm = tk.Frame(pad, bg=C["panel"]); wm.pack(anchor="w", pady=(1, 18))
        tk.Label(wm, text="Vinted", bg=C["panel"], fg=C["text"],
                 font=(self.f_serif, 26, "bold")).pack(side="left")
        tk.Label(wm, text=" AI", bg=C["panel"], fg=C["accent"],
                 font=(self.f_serif, 26, "bold italic")).pack(side="left")

        # status + QR
        self.status = tk.Label(pad, text="●  server stopped", bg=C["panel"], fg=C["bad"],
                               font=(self.f_ui, 12, "bold"))
        self.status.pack(anchor="w", pady=(0, 10))
        qr_wrap = tk.Frame(pad, bg="#f5f2ea")
        qr_wrap.pack(anchor="w")
        self.qr_img = make_qr_photo(self.url)
        tk.Label(qr_wrap, image=self.qr_img, bg="#f5f2ea", bd=0).pack(padx=9, pady=9)
        tk.Label(pad, text=self.url, bg=C["panel"], fg=C["text"],
                 font=(self.f_mono, 10)).pack(anchor="w", pady=(8, 0))
        tk.Label(pad, text="scan to open the swipe app on your phone", bg=C["panel"],
                 fg=C["faint"], font=(self.f_ui, 9)).pack(anchor="w", pady=(1, 12))

        self.server_btn, self.server_lbl = self._solid(
            pad, "Start server", self._toggle_server, C["accent"], C["on_accent"])
        self.server_btn.pack(fill="x", pady=(0, 18))

        self._divider(pad)
        tk.Label(pad, text="ACTIONS", bg=C["panel"], fg=C["faint"],
                 font=(self.f_mono, 9, "bold")).pack(anchor="w", pady=(14, 8))

        self.scrape_row = self._action(pad, "⬇", "Scrape new items", "fetch fresh listings",
                                       self._scrape_clicked, C["tg_cyan"],
                                       gear=self._open_scrape_settings)
        self.retrain_row = self._action(pad, "✦", "Retrain model", "learn from your swipes",
                                        lambda: self._run("retrain"), C["accent"])
        self.update_row = self._action(pad, "↻", "Update app", "git reset + dependencies",
                                       self._confirm_update, C["green"])

        self.progress = ttk.Progressbar(pad, mode="indeterminate", style="V.Horizontal.TProgressbar")
        self.spacer = tk.Frame(pad, bg=C["panel"]); self.spacer.pack(fill="both", expand=True)
        self.footer = tk.Label(pad, text="cockpit", bg=C["panel"], fg=C["faint"],
                               font=(self.f_mono, 8), justify="left")
        self.footer.pack(anchor="w")

        # ── MAIN — integrated terminal ───────────────────────────────
        main = tk.Frame(self, bg=C["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(2, weight=1); main.columnconfigure(0, weight=1)
        head = tk.Frame(main, bg=C["bg"]); head.grid(row=0, column=0, sticky="ew", padx=30, pady=(24, 0))
        tk.Label(head, text="●  SYSTEM · LIVE", bg=C["bg"], fg=C["accent"],
                 font=(self.f_mono, 9, "bold")).pack(anchor="w")
        tk.Label(main, text="Always learning your taste.", bg=C["bg"], fg=C["text"],
                 font=(self.f_serif, 22, "italic")).grid(row=1, column=0, sticky="w", padx=30, pady=(2, 14))

        self.term = tk.Text(main, bg=C["bg"], fg=C["green"], relief="flat", bd=0,
                            font=(self.f_mono, 11), wrap="word", state="disabled",
                            padx=30, pady=4, highlightthickness=0,
                            insertbackground=C["green"], spacing1=2)
        self.term.grid(row=2, column=0, sticky="nsew")
        for tag, key in TAGS.items():
            self.term.tag_configure(tag, foreground=C[key])
        self.term.tag_configure("cur", foreground=C["green"])
        # read-only but selectable
        self.term.bind("<Key>", lambda e: "break")
        self.term.config(state="normal")
        self.term.insert("end", "▮", "cur")
        self.term.config(state="disabled")
        self.logbox = self.term

    # -- widget factories --
    def _divider(self, parent):
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

    def _solid(self, parent, text, cmd, color, fg):
        f = tk.Frame(parent, bg=color, cursor="hand2")
        lbl = tk.Label(f, text=text, bg=color, fg=fg, font=(self.f_ui, 12, "bold"), pady=12)
        lbl.pack(fill="x")
        for w in (f, lbl):
            w.bind("<Button-1>", lambda e: cmd())
        f._base = color
        f.bind("<Enter>", lambda e: self._tint(f, lbl, C["accent_d"] if color == C["accent"] else color))
        f.bind("<Leave>", lambda e: self._tint(f, lbl, f._base))
        return f, lbl

    def _tint(self, frame, lbl, color):
        frame.config(bg=color); lbl.config(bg=color)

    def _action(self, parent, icon, title, subtitle, cmd, color, gear=None):
        row = tk.Frame(parent, bg=C["surface"], highlightbackground=C["border"],
                       highlightthickness=1, cursor="hand2")
        row.pack(fill="x", pady=4)
        accent = tk.Frame(row, bg=color, width=3); accent.pack(side="left", fill="y")
        ico = tk.Label(row, text=icon, bg=C["surface"], fg=color, font=(self.f_ui, 14, "bold"))
        ico.pack(side="left", padx=(13, 11), pady=11)
        txt = tk.Frame(row, bg=C["surface"]); txt.pack(side="left", fill="x", expand=True, pady=9)
        t1 = tk.Label(txt, text=title, bg=C["surface"], fg=C["text"], font=(self.f_ui, 12, "bold"), anchor="w")
        t1.pack(anchor="w")
        t2 = tk.Label(txt, text=subtitle, bg=C["surface"], fg=C["faint"], font=(self.f_ui, 9), anchor="w")
        t2.pack(anchor="w")

        members = [row, ico, txt, t1, t2]
        gear_lbl = None
        if gear:
            gear_lbl = tk.Label(row, text="⚙", bg=C["surface"], fg=C["dim"],
                                font=(self.f_ui, 13), cursor="hand2")
            gear_lbl.pack(side="right", padx=14)
            gear_lbl.bind("<Button-1>", lambda e: (gear(), "break")[1])
            members.append(gear_lbl)   # tinted on hover but not the main click target

        def enter(_):
            for w in members:
                w.config(bg=C["hover"])
        def leave(_):
            for w in members:
                w.config(bg=C["surface"])
        click_targets = [row, ico, txt, t1, t2]
        for w in click_targets:
            w.bind("<Enter>", enter); w.bind("<Leave>", leave)
            w.bind("<Button-1>", lambda e: cmd())
        if gear_lbl:
            gear_lbl.bind("<Enter>", enter); gear_lbl.bind("<Leave>", leave)
        row._disabled = False
        row._members = members
        return row

    def _set_actions_enabled(self, enabled):
        for row in (self.scrape_row, self.retrain_row, self.update_row):
            row.config(cursor="hand2" if enabled else "watch")

    # -- terminal --
    def emit(self, text, tag="dim"):
        """Thread-safe: queue a line for the terminal."""
        self._evt_q.put((text, tag))

    def _term_push(self, text, tag):
        self.term.config(state="normal")
        r = self.term.tag_ranges("cur")
        if r:
            self.term.delete(r[0], r[1])
        self.term.insert("end", (text or " ") + "\n", tag)
        # cap history
        try:
            n = int(self.term.index("end-1c").split(".")[0])
            if n > 600:
                self.term.delete("1.0", f"{n-500}.0")
        except Exception:
            pass
        self.term.insert("end", "▮" if self._cursor_on else " ", "cur")
        self.term.see("end")
        self.term.config(state="disabled")

    def _blink(self):
        self._cursor_on = not self._cursor_on
        r = self.term.tag_ranges("cur")
        if r:
            self.term.config(state="normal")
            self.term.tag_config("cur", foreground=C["green"] if self._cursor_on else C["bg"])
            self.term.config(state="disabled")
        self.after(560, self._blink)

    def _boot_scan(self):
        self.emit("$ vinted-ai cockpit · boot", "cmd")
        self.emit(f"→ python {platform.python_version()} · {SYSTEM.lower()} · venv ok", "dim")
        mp = os.path.join(ROOT, "style_mlp.pt")
        if os.path.exists(mp):
            self.emit(f"✓ model       style_mlp.pt · {os.path.getsize(mp)/1e6:.1f}MB · {_age(os.path.getmtime(mp))} old", "ok")
        else:
            self.emit("✗ model       style_mlp.pt missing — retrain needed", "red")
        n, r = _db_counts()
        if n is not None:
            self.emit(f"✓ data        {n} items · {r} ratings", "ok")
        else:
            self.emit("→ data        no database yet — run a scrape", "amber")
        try:
            import numpy as np
            ep = os.path.join(ROOT, "embeddings.npz")
            if os.path.exists(ep):
                z = np.load(ep)
                arr = z[z.files[0]]
                self.emit(f"✓ embeddings  {arr.shape[0]} vectors · {z.files[0]}", "ok")
        except Exception:
            pass
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "?"
        h = _git(["rev-parse", "--short", "HEAD"]) or "?"
        dirty = " (dirty)" if _git(["status", "--porcelain"]) else " (clean)"
        self.emit(f"→ git         {branch}@{h}{dirty}", "cyan")
        self.emit("● server stopped", "dim")
        self.emit("→ ready · idle", "dim")
        # sidebar footer (scheduled on UI thread via the event queue)
        self._evt_q.put(("__FOOTER__", f"{branch}@{h} · {SYSTEM.lower()}"))

    def _heartbeat(self):
        if not self.job.running:
            n, _ = _db_counts()
            up = "server up" if self.server.running() else "server down"
            items = f"{n} items" if n is not None else "no db"
            self.emit(f"{time.strftime('%H:%M:%S')} · heartbeat · {up} · {items}", "dim")
        self.after(30000, self._heartbeat)

    # -- actions --
    def _toggle_server(self):
        if self.server.running():
            self.server.stop()
            self.emit("● server stopped", "amber")
        else:
            if not self._ensure_password():
                return
            self.server.start()
            self.emit(f"✓ server up · {self.url}", "ok")
        self._refresh_state()

    def _scrape_clicked(self):
        if self.job.running:
            return
        if self.prefs.get("ask_before_scrape", True):
            self._open_scrape_settings(then_run=True)
        else:
            self._run("scrape")

    def _confirm_update(self):
        if self.job.running:
            return
        self.emit("→ updating: git reset --hard to origin + pip install", "cyan")
        self._run("update")

    def _open_scrape_settings(self, then_run=False):
        polish, max_pages, urls = read_config()
        dlg = tk.Toplevel(self)
        dlg.title("Scrape settings")
        dlg.configure(bg=C["panel"])
        dlg.transient(self); dlg.grab_set(); dlg.resizable(False, False)

        tk.Label(dlg, text="Scrape settings", bg=C["panel"], fg=C["text"],
                 font=(self.f_serif, 17, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(dlg, text="What to fetch on the next scrape.", bg=C["panel"], fg=C["dim"],
                 font=(self.f_ui, 10)).pack(anchor="w", padx=24, pady=(0, 14))

        tk.Label(dlg, text="SEARCH URLS  ·  one per line, optional  # label",
                 bg=C["panel"], fg=C["faint"], font=(self.f_mono, 8, "bold")).pack(anchor="w", padx=24)
        urlbox = tk.Text(dlg, width=64, height=8, bg=C["bg"], fg=C["text"], relief="flat",
                         insertbackground=C["accent"], font=(self.f_mono, 10),
                         highlightbackground=C["border"], highlightthickness=1, padx=10, pady=8)
        urlbox.pack(padx=24, pady=(4, 14))
        urlbox.insert("1.0", "\n".join(urls))

        rowf = tk.Frame(dlg, bg=C["panel"]); rowf.pack(fill="x", padx=24)
        tk.Label(rowf, text="Max pages per URL", bg=C["panel"], fg=C["text"],
                 font=(self.f_ui, 11)).pack(side="left")
        pages_var = tk.StringVar(value=str(max_pages))
        tk.Entry(rowf, textvariable=pages_var, width=5, bg=C["bg"], fg=C["text"],
                 relief="flat", justify="center", insertbackground=C["accent"],
                 font=(self.f_mono, 11), highlightbackground=C["border"],
                 highlightthickness=1).pack(side="left", padx=10, ipady=4)

        polish_var = tk.BooleanVar(value=polish)
        ask_var = tk.BooleanVar(value=not self.prefs.get("ask_before_scrape", True))

        def chk(parent, var, text):
            return tk.Checkbutton(parent, text=text, variable=var, bg=C["panel"],
                                  fg=C["text"], selectcolor=C["bg"], activebackground=C["panel"],
                                  activeforeground=C["text"], font=(self.f_ui, 10),
                                  anchor="w", highlightthickness=0, bd=0)
        chk(dlg, polish_var, "Skip items from Polish sellers").pack(anchor="w", padx=22, pady=(14, 2))
        chk(dlg, ask_var, "Don't ask again — just scrape next time").pack(anchor="w", padx=22, pady=(0, 4))

        btns = tk.Frame(dlg, bg=C["panel"]); btns.pack(fill="x", padx=24, pady=(16, 20))

        def save(run):
            try:
                mp = max(1, int(pages_var.get()))
            except ValueError:
                mp = max_pages
            new_urls = [l for l in urlbox.get("1.0", "end").splitlines() if l.strip()]
            write_config(polish_var.get(), mp, new_urls)
            self.prefs["ask_before_scrape"] = not ask_var.get()
            save_prefs(self.prefs)
            self.emit(f"✓ config saved · {len(new_urls)} urls · {mp} pages · polish {'on' if polish_var.get() else 'off'}", "ok")
            dlg.destroy()
            if run:
                self._run("scrape")

        cancel, cl = self._solid(btns, "Cancel", dlg.destroy, C["surface"], C["text"])
        cancel.pack(side="left", expand=True, fill="x", padx=(0, 6))
        primary, pl = self._solid(btns, "Save & Scrape" if then_run else "Save",
                                  lambda: save(then_run), C["accent"], C["on_accent"])
        primary.pack(side="left", expand=True, fill="x", padx=(6, 0))
        dlg.update_idletasks()
        dlg.geometry(f"+{self.winfo_rootx()+120}+{self.winfo_rooty()+80}")

    def _ensure_password(self) -> bool:
        if os.path.exists(PASSWORD_HASH_FILE):
            return True
        pw = self._prompt_new_password()
        if not pw:
            return False
        os.makedirs(os.path.dirname(PASSWORD_HASH_FILE), exist_ok=True)
        with open(PASSWORD_HASH_FILE, "w") as f:
            f.write(_hash_password(pw))
        self.emit("🔑 password set · webapp/password.hash", "ok")
        return True

    def _prompt_new_password(self):
        dlg = tk.Toplevel(self)
        dlg.title("Set a password")
        dlg.configure(bg=C["panel"]); dlg.transient(self); dlg.grab_set(); dlg.resizable(False, False)
        tk.Label(dlg, text="First-time setup", bg=C["panel"], fg=C["text"],
                 font=(self.f_serif, 16, "bold")).pack(padx=28, pady=(22, 4))
        tk.Label(dlg, text="Choose a password for the phone app.\nThere is no recovery — remember it.",
                 bg=C["panel"], fg=C["dim"], font=(self.f_ui, 10), justify="center").pack(padx=28, pady=(0, 14))
        result = {"pw": None}
        e1 = tk.Entry(dlg, show="•", bg=C["bg"], fg=C["text"], relief="flat",
                      insertbackground=C["accent"], width=26, font=(self.f_ui, 12),
                      highlightbackground=C["border"], highlightthickness=1)
        e1.pack(padx=28, pady=3, ipady=6)
        e2 = tk.Entry(dlg, show="•", bg=C["bg"], fg=C["text"], relief="flat",
                      insertbackground=C["accent"], width=26, font=(self.f_ui, 12),
                      highlightbackground=C["border"], highlightthickness=1)
        e2.pack(padx=28, pady=3, ipady=6)
        tk.Label(dlg, text="confirm password", bg=C["panel"], fg=C["faint"], font=(self.f_ui, 8)).pack()
        err = tk.Label(dlg, text="", bg=C["panel"], fg=C["bad"], font=(self.f_ui, 9)); err.pack(pady=(4, 0))

        def ok(*_):
            p1, p2 = e1.get(), e2.get()
            if len(p1) < 4:
                err.config(text="At least 4 characters."); return
            if p1 != p2:
                err.config(text="Passwords don't match."); return
            result["pw"] = p1; dlg.destroy()

        btns = tk.Frame(dlg, bg=C["panel"]); btns.pack(pady=(16, 22))
        c, _ = self._solid(btns, "Cancel", dlg.destroy, C["surface"], C["text"]); c.pack(side="left", padx=6, ipadx=10)
        o, _ = self._solid(btns, "Set password", ok, C["accent"], C["on_accent"]); o.pack(side="left", padx=6, ipadx=10)
        e1.bind("<Return>", lambda e: e2.focus_set()); e2.bind("<Return>", ok); e1.focus_set()
        self.wait_window(dlg)
        return result["pw"]

    def _run(self, key):
        if self.job.running:
            return
        label, steps = PIPELINES[key]
        self.emit(f"=== {label} ===", "cyan")
        if self.job.start(steps):
            self.progress.pack(before=self.spacer, fill="x", pady=(12, 0))
            self.progress.start(12)
            self._refresh_state()

    def _job_done(self, ok):
        self.progress.stop()
        self.progress.pack_forget()
        self.emit("✓ done." if ok else "✗ finished with errors — see log above.", "ok" if ok else "red")
        self._refresh_state()

    # -- state / loop --
    def _refresh_state(self):
        up = self.server.running(); busy = self.job.running
        self.status.config(text="●  server running" if up else "●  server stopped",
                           fg=C["ok"] if up else C["bad"])
        self.server_lbl.config(text="Stop server" if up else "Start server")
        new = C["bad"] if up else C["accent"]
        self.server_btn._base = new
        self._tint(self.server_btn, self.server_lbl, new)
        self.server_lbl.config(fg="#fff" if up else C["on_accent"])
        self._set_actions_enabled(not busy)
        if up or busy:
            self.keep_awake.engage()
        else:
            self.keep_awake.release()

    def _tick(self):
        self.job.drain()
        try:
            while True:
                text, tag = self._evt_q.get_nowait()
                if text == "__FOOTER__":
                    self.footer.config(text=tag)
                else:
                    self._term_push(text, tag)
        except queue.Empty:
            pass
        up = self.server.running()
        want = "Stop server" if up else "Start server"
        if self.server_lbl.cget("text") != want:
            self._refresh_state()
        self.after(150, self._tick)

    def _log(self, text, tag="dim"):
        self._term_push(text, tag)

    def _on_close(self):
        self.server.stop(); self.keep_awake.release(); self.destroy()


def main():
    Cockpit().mainloop()


if __name__ == "__main__":
    main()
