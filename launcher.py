#!/usr/bin/env python3
"""
Vinted AI — Cockpit
===================
A small cross-platform (macOS / Windows / Linux) desktop control panel that ties
the whole project together so you never touch a terminal:

  • Start / Stop the web backend (the phone swipe app)
  • A QR code + URL, always visible — scan it to open the app on your phone
  • One-tap pipeline buttons (Scrape new items, Retrain model) with a progress bar
  • Keeps the computer awake while the server is up or a job is running

Run it with the project's virtualenv Python:
    python launcher.py
(or double-click the platform launcher: "Vinted AI.command" / ".bat" / ".sh")
"""
import binascii
import hashlib
import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser

import tkinter as tk
from tkinter import ttk

import qrcode
from PIL import ImageTk

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable                      # the venv python running this cockpit
PORT = 8000
SYSTEM = platform.system()               # 'Darwin' | 'Windows' | 'Linux'
CONFIG_FILE = os.path.join(ROOT, "scraper_config.txt")
PASSWORD_HASH_FILE = os.path.join(ROOT, "webapp", "password.hash")

# Pipeline steps run as plain subprocesses (no auth, independent of the server).
PIPELINES = {
    "scrape": ("Scrape new items", [
        ("Scraping Vinted",     [PY, os.path.join(ROOT, "vinted_scraper.py")]),
        ("Importing to DB",     [PY, os.path.join(ROOT, "db_creator.py")]),
        ("Computing embeddings", [PY, os.path.join(ROOT, "compute_embeddings.py")]),
    ]),
    "retrain": ("Retrain model", [
        ("Training MLP",  [PY, os.path.join(ROOT, "train_mlp.py")]),
        ("Scoring items", [PY, os.path.join(ROOT, "score_with_mlp.py")]),
    ]),
}


# ── helpers ─────────────────────────────────────────────────────────────────────

def local_ip() -> str:
    """Best-effort LAN IP (the address your phone connects to)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def make_qr_photo(url: str):
    """Return a Tk PhotoImage of a QR code for `url` (requires an existing Tk root)."""
    img = qrcode.make(url).convert("RGB").resize((220, 220))
    return ImageTk.PhotoImage(img)


def _hash_password(password: str) -> str:
    """Salted PBKDF2 hash, byte-for-byte compatible with webapp/backend.py."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(key).decode()


class KeepAwake:
    """Prevent the computer from sleeping while engaged. No-op if unsupported.

    Note: this only *prevents* sleep — it cannot run jobs once the machine is
    already asleep. Engage while the server is up or a job is running.
    """
    def __init__(self):
        self._proc = None
        self._win_engaged = False

    def engage(self):
        if SYSTEM == "Windows":
            if not self._win_engaged:
                import ctypes
                ES_CONTINUOUS = 0x80000000
                ES_SYSTEM_REQUIRED = 0x00000001
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                self._win_engaged = True
            return
        if self._proc and self._proc.poll() is None:
            return
        if SYSTEM == "Darwin":
            self._proc = subprocess.Popen(["caffeinate", "-dimsu"])
        elif SYSTEM == "Linux" and shutil.which("systemd-inhibit"):
            self._proc = subprocess.Popen([
                "systemd-inhibit", "--what=sleep:idle",
                "--why=Vinted AI cockpit", "--mode=block",
                "sleep", "infinity",
            ])

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
    """Wraps the uvicorn backend subprocess."""
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
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation,
        )

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
        self.on_line = on_line          # called (thread-safe via queue) per output line
        self.on_done = on_done          # called with True/False when finished
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
        for label, argv in steps:
            self._q.put(f"▶ {label}…")
            try:
                proc = subprocess.Popen(
                    argv, cwd=ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                )
                for line in proc.stdout:
                    self._q.put(line.rstrip())
                proc.wait()
            except Exception as e:
                self._q.put(f"error: {e}")
                ok = False
                break
            if proc.returncode != 0:
                self._q.put(f"✗ {label} failed (exit {proc.returncode})")
                ok = False
                break
            self._q.put(f"✓ {label} done")
        self._q.put(("__DONE__", ok))

    def drain(self):
        """Call from the UI thread to flush queued lines; triggers callbacks."""
        try:
            while True:
                item = self._q.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self.running = False
                    self.on_done(item[1])
                else:
                    self.on_line(item)
        except queue.Empty:
            pass


# ── UI ───────────────────────────────────────────────────────────────────────

C = {
    "bg": "#0f1117", "card": "#171a23", "text": "#e8e8f0", "dim": "#8a8aa0",
    "accent": "#7c6cf8", "ok": "#22c55e", "bad": "#ef4444",
}


class Cockpit(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vinted AI — Cockpit")
        self.configure(bg=C["bg"])
        self.geometry("440x640")
        self.minsize(420, 600)

        self.server = ServerProcess()
        self.keep_awake = KeepAwake()
        self.job = JobRunner(self._log, self._job_done)
        self.url = f"http://{local_ip()}:{PORT}"

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._tick)

    # -- layout --
    def _build(self):
        tk.Label(self, text="VINTED AI", bg=C["bg"], fg=C["text"],
                 font=("Helvetica", 20, "bold")).pack(pady=(18, 2))
        tk.Label(self, text="cockpit", bg=C["bg"], fg=C["dim"],
                 font=("Helvetica", 11)).pack()

        # Server + QR card
        card = tk.Frame(self, bg=C["card"])
        card.pack(fill="x", padx=18, pady=(16, 10))
        self.status = tk.Label(card, text="● server stopped", bg=C["card"], fg=C["bad"],
                               font=("Helvetica", 12, "bold"))
        self.status.pack(pady=(14, 8))
        self.qr_img = make_qr_photo(self.url)
        self.qr_label = tk.Label(card, image=self.qr_img, bg=C["card"])
        self.qr_label.pack()
        tk.Label(card, text=self.url, bg=C["card"], fg=C["dim"],
                 font=("Helvetica", 11)).pack(pady=(6, 2))
        tk.Label(card, text="Scan with your phone to open the swipe app",
                 bg=C["card"], fg=C["dim"], font=("Helvetica", 9)).pack(pady=(0, 8))
        self.server_btn = tk.Button(card, text="Start server", command=self._toggle_server,
                                    bg=C["accent"], fg="white", relief="flat",
                                    font=("Helvetica", 12, "bold"), pady=8)
        self.server_btn.pack(fill="x", padx=14, pady=(0, 14))

        # Pipeline card
        card2 = tk.Frame(self, bg=C["card"])
        card2.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        tk.Label(card2, text="PIPELINE", bg=C["card"], fg=C["dim"],
                 font=("Helvetica", 9, "bold")).pack(anchor="w", padx=14, pady=(12, 6))

        self.scrape_btn = tk.Button(card2, text="⬇  Scrape new items",
                                    command=lambda: self._run("scrape"),
                                    bg="#222633", fg=C["text"], relief="flat",
                                    font=("Helvetica", 12), pady=8, anchor="w")
        self.scrape_btn.pack(fill="x", padx=14, pady=3)
        self.retrain_btn = tk.Button(card2, text="🧠  Retrain model",
                                     command=lambda: self._run("retrain"),
                                     bg="#222633", fg=C["text"], relief="flat",
                                     font=("Helvetica", 12), pady=8, anchor="w")
        self.retrain_btn.pack(fill="x", padx=14, pady=3)
        self.edit_btn = tk.Button(card2, text="✎  Edit search URLs",
                                  command=self._edit_urls,
                                  bg="#222633", fg=C["text"], relief="flat",
                                  font=("Helvetica", 12), pady=8, anchor="w")
        self.edit_btn.pack(fill="x", padx=14, pady=3)

        self.progress = ttk.Progressbar(card2, mode="indeterminate")
        self.progress.pack(fill="x", padx=14, pady=(10, 6))

        self.logbox = tk.Text(card2, height=8, bg="#0b0d12", fg=C["dim"], relief="flat",
                              font=("Menlo", 9), wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    # -- actions --
    def _toggle_server(self):
        if self.server.running():
            self.server.stop()
        else:
            if not self._ensure_password():
                return            # first-run setup cancelled — don't start
            self.server.start()
        self._refresh_state()

    def _ensure_password(self) -> bool:
        """Make sure webapp/password.hash exists; prompt to create it on first run."""
        if os.path.exists(PASSWORD_HASH_FILE):
            return True
        pw = self._prompt_new_password()
        if not pw:
            return False
        os.makedirs(os.path.dirname(PASSWORD_HASH_FILE), exist_ok=True)
        with open(PASSWORD_HASH_FILE, "w") as f:
            f.write(_hash_password(pw))
        self._log("🔑 Password set — saved to webapp/password.hash")
        return True

    def _prompt_new_password(self):
        """Modal first-run dialog. Returns the chosen password, or None if cancelled."""
        dlg = tk.Toplevel(self)
        dlg.title("Set a password")
        dlg.configure(bg=C["card"])
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.grab_set()
        result = {"pw": None}

        tk.Label(dlg, text="First-time setup", bg=C["card"], fg=C["text"],
                 font=("Helvetica", 14, "bold")).pack(padx=24, pady=(20, 4))
        tk.Label(dlg, text="Choose a password for the phone app.\n"
                           "There is no recovery — remember it.",
                 bg=C["card"], fg=C["dim"], font=("Helvetica", 10),
                 justify="center").pack(padx=24, pady=(0, 12))

        e1 = tk.Entry(dlg, show="•", bg="#0b0d12", fg=C["text"], relief="flat",
                      insertbackground=C["text"], width=26, font=("Helvetica", 12))
        e1.pack(padx=24, pady=3, ipady=5)
        e2 = tk.Entry(dlg, show="•", bg="#0b0d12", fg=C["text"], relief="flat",
                      insertbackground=C["text"], width=26, font=("Helvetica", 12))
        e2.pack(padx=24, pady=3, ipady=5)
        e2_hint = tk.Label(dlg, text="confirm password", bg=C["card"], fg=C["dim"],
                           font=("Helvetica", 8))
        e2_hint.pack()
        err = tk.Label(dlg, text="", bg=C["card"], fg=C["bad"], font=("Helvetica", 9))
        err.pack(pady=(4, 0))

        def ok(*_):
            p1, p2 = e1.get(), e2.get()
            if len(p1) < 4:
                err.config(text="At least 4 characters."); return
            if p1 != p2:
                err.config(text="Passwords don't match."); return
            result["pw"] = p1
            dlg.destroy()

        def cancel():
            dlg.destroy()

        btns = tk.Frame(dlg, bg=C["card"])
        btns.pack(pady=(14, 20))
        tk.Button(btns, text="Cancel", command=cancel, bg="#222633", fg=C["text"],
                  relief="flat", font=("Helvetica", 11), padx=14, pady=6).pack(side="left", padx=6)
        tk.Button(btns, text="Set password", command=ok, bg=C["accent"], fg="white",
                  relief="flat", font=("Helvetica", 11, "bold"), padx=14, pady=6).pack(side="left", padx=6)

        e1.bind("<Return>", lambda e: e2.focus_set())
        e2.bind("<Return>", ok)
        e1.focus_set()
        self.wait_window(dlg)
        return result["pw"]

    def _run(self, key):
        if self.job.running:
            return
        label, steps = PIPELINES[key]
        self._log(f"\n=== {label} ===")
        if self.job.start(steps):
            self.progress.start(12)
            self._refresh_state()

    def _edit_urls(self):
        # If the server is up, the phone-friendly config page is nicer; else open the file.
        if self.server.running():
            webbrowser.open(f"{self.url}/config")
        else:
            _open_in_editor(CONFIG_FILE)

    def _job_done(self, ok):
        self.progress.stop()
        self._log("✅ Done." if ok else "⚠️ Finished with errors — see log.")
        self._refresh_state()

    # -- state / loop --
    def _refresh_state(self):
        up = self.server.running()
        busy = self.job.running
        self.status.config(text="● server running" if up else "● server stopped",
                           fg=C["ok"] if up else C["bad"])
        self.server_btn.config(text="Stop server" if up else "Start server")
        for b in (self.scrape_btn, self.retrain_btn):
            b.config(state="disabled" if busy else "normal")
        # Keep the machine awake whenever something is active.
        if up or busy:
            self.keep_awake.engage()
        else:
            self.keep_awake.release()

    def _tick(self):
        self.job.drain()
        # Catch the server dying on its own (e.g. needs first-time password setup).
        self._sync_server_button()
        self.after(150, self._tick)

    def _sync_server_button(self):
        up = self.server.running()
        want = "Stop server" if up else "Start server"
        if self.server_btn.cget("text") != want:
            self._refresh_state()

    def _log(self, line):
        self.logbox.config(state="normal")
        self.logbox.insert("end", line + "\n")
        self.logbox.see("end")
        # cap to ~400 lines
        if int(self.logbox.index("end-1c").split(".")[0]) > 400:
            self.logbox.delete("1.0", "100.0")
        self.logbox.config(state="disabled")

    def _on_close(self):
        self.server.stop()
        self.keep_awake.release()
        self.destroy()


def _open_in_editor(path: str):
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", path])
    elif SYSTEM == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def main():
    Cockpit().mainloop()


if __name__ == "__main__":
    main()
