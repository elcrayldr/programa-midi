# CRAY LDR MIDI DECK v0.1
# Windows 10/11 - Alesis V Mini - MIDI monitor + per-application pad actions
import os, sys, json, time, threading, subprocess, queue, ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "CRAY LDR MIDI DECK"
APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "CrayLDR" / "MidiDeck"
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_CONFIG = {
    "device_hint": "Alesis V Mini",
    "auto_profile": True,
    "start_with_windows": False,
    "profiles": {
        "GLOBAL": {},
        "FL Studio": {},
        "Cubase": {},
        "OBS": {},
        "Windows": {}
    },
    "mapping": {
        "pads": {
            "36": {"label": "PAD 1", "type": "none", "value": ""},
            "38": {"label": "PAD 2", "type": "none", "value": ""},
            "42": {"label": "PAD 3", "type": "none", "value": ""},
            "46": {"label": "PAD 4", "type": "none", "value": ""}
        }
    }
}

def load_config():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    merged.setdefault("profiles", {})
    for p in ("GLOBAL", "FL Studio", "Cubase", "OBS", "Windows"):
        merged["profiles"].setdefault(p, {})
    return merged

def save_config(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def foreground_process():
    if os.name != "nt":
        return ""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(handle)
        return Path(buf.value).name.lower() if ok else ""
    except Exception:
        return ""

def detect_profile(proc):
    if not proc:
        return "Windows"
    if "fl64" in proc or proc in ("fl.exe", "fl studio.exe"):
        return "FL Studio"
    if "cubase" in proc:
        return "Cubase"
    if proc in ("obs64.exe", "obs.exe"):
        return "OBS"
    return "Windows"

def parse_keys(value):
    return [x.strip() for x in value.split("+") if x.strip()]

def run_action(action):
    kind = action.get("type", "none")
    value = action.get("value", "").strip()
    if kind == "none" or not value:
        return
    if kind == "shortcut":
        import pyautogui
        keys = parse_keys(value)
        if keys:
            pyautogui.hotkey(*keys)
    elif kind == "text":
        import pyautogui
        pyautogui.write(value, interval=0.01)
    elif kind == "open":
        os.startfile(os.path.expandvars(os.path.expanduser(value)))
    elif kind == "url":
        import webbrowser
        webbrowser.open(value)
    elif kind == "macro":
        # One action per line: shortcut:ctrl+s | text:hello | open:C:\path
        for line in value.splitlines():
            if ":" not in line:
                continue
            sub, val = line.split(":", 1)
            run_action({"type": sub.strip(), "value": val.strip()})
            time.sleep(0.12)

class MidiDeckApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME + "  |  v0.1")
        self.root.geometry("1040x720")
        self.root.minsize(900, 640)
        self.root.configure(bg="#111214")
        self.cfg = load_config()
        self.events = queue.Queue()
        self.midi_in = None
        self.midi_thread = None
        self.running = False
        self.current_profile = "Windows"
        self.last_pad_state = set()
        self.selected_pad = tk.StringVar(value="36")
        self.profile_var = tk.StringVar(value="GLOBAL")
        self.device_var = tk.StringVar(value="")
        self.action_type = tk.StringVar(value="none")
        self.action_value = tk.StringVar(value="")
        self.auto_var = tk.BooleanVar(value=self.cfg.get("auto_profile", True))
        self._style()
        self._build()
        self.refresh_devices()
        self.root.after(100, self.process_queue)
        self.root.after(500, self.update_profile)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background="#111214", foreground="#eeeeee", fieldbackground="#202226")
        s.configure("TFrame", background="#111214")
        s.configure("TLabel", background="#111214", foreground="#eeeeee")
        s.configure("Muted.TLabel", background="#111214", foreground="#999da5")
        s.configure("TButton", background="#292c31", foreground="#f5f5f5", padding=8)
        s.map("TButton", background=[("active", "#3b3f46")])
        s.configure("Accent.TButton", background="#f2c400", foreground="#111214", padding=9, font=("Segoe UI", 9, "bold"))
        s.map("Accent.TButton", background=[("active", "#ffdb28")])
        s.configure("TEntry", fieldbackground="#202226", foreground="#ffffff")
        s.configure("TCombobox", fieldbackground="#202226", foreground="#ffffff")
        s.configure("Treeview", background="#1c1e22", fieldbackground="#1c1e22", foreground="#eeeeee", rowheight=24)
        s.configure("Treeview.Heading", background="#292c31", foreground="#f2c400")

    def panel(self, parent, title):
        f = tk.Frame(parent, bg="#1b1d21", highlightbackground="#34373d", highlightthickness=1)
        tk.Label(f, text=title, bg="#1b1d21", fg="#f2c400", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 7))
        return f

    def _build(self):
        header = tk.Frame(self.root, bg="#111214")
        header.pack(fill="x", padx=20, pady=(18, 12))
        tk.Label(header, text="CRAY LDR", bg="#111214", fg="#f2c400", font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(header, text="  MIDI DECK  /  0.1", bg="#111214", fg="#f1f1f1", font=("Segoe UI", 15, "bold")).pack(side="left")
        self.status = tk.Label(header, text="● DESCONECTADO", bg="#111214", fg="#e0a33a", font=("Segoe UI", 9, "bold"))
        self.status.pack(side="right")

        top = tk.Frame(self.root, bg="#111214")
        top.pack(fill="x", padx=20, pady=5)
        dev = self.panel(top, "DISPOSITIVO MIDI")
        dev.pack(side="left", fill="x", expand=True, padx=(0, 8))
        row = tk.Frame(dev, bg="#1b1d21"); row.pack(fill="x", padx=12, pady=(0, 12))
        self.device_combo = ttk.Combobox(row, textvariable=self.device_var, state="readonly", width=42)
        self.device_combo.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Actualizar", command=self.refresh_devices).pack(side="left", padx=3)
        ttk.Button(row, text="Conectar", style="Accent.TButton", command=self.connect).pack(side="left", padx=3)
        ttk.Button(row, text="Desconectar", command=self.disconnect).pack(side="left", padx=3)

        prof = self.panel(top, "PERFIL ACTIVO")
        prof.pack(side="left", fill="x", expand=True, padx=(8, 0))
        pr = tk.Frame(prof, bg="#1b1d21"); pr.pack(fill="x", padx=12, pady=(0, 12))
        self.profile_label = tk.Label(pr, text="Windows", bg="#1b1d21", fg="#ffffff", font=("Segoe UI", 14, "bold"))
        self.profile_label.pack(side="left", padx=(0, 12))
        ttk.Checkbutton(pr, text="Detección automática", variable=self.auto_var, command=self.save_auto).pack(side="left")

        body = tk.Frame(self.root, bg="#111214")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        left = self.panel(body, "CONTROLES DETECTADOS")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.pad_buttons = {}
        pads = tk.Frame(left, bg="#1b1d21"); pads.pack(fill="x", padx=12, pady=8)
        for i, note in enumerate(("36","38","42","46")):
            b = tk.Button(pads, text=f"PAD {i+1}\nNOTE {note}", bg="#292c31", fg="#f2c400",
                          activebackground="#f2c400", activeforeground="#111214", relief="flat",
                          font=("Segoe UI", 10, "bold"), height=3,
                          command=lambda n=note: self.select_pad(n))
            b.grid(row=i//2, column=i%2, sticky="nsew", padx=5, pady=5)
            self.pad_buttons[note] = b
        pads.columnconfigure(0, weight=1); pads.columnconfigure(1, weight=1)
        tk.Label(left, text="Knobs candidatos: CC 14 · 15 · 16 · 17", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=5)
        tk.Label(left, text="Teclas: canal 16 · notas 48–72", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=3)
        tk.Label(left, text="CC1 modulación · CC64 sustain · Pitch Bend", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=3)
        tk.Label(left, text="Los controles no asignados no ejecutan acciones.", bg="#1b1d21", fg="#e0a33a", wraplength=330).pack(anchor="w", padx=14, pady=(8, 14))

        right = self.panel(body, "ASIGNACIÓN DE MACROS")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        form = tk.Frame(right, bg="#1b1d21"); form.pack(fill="x", padx=12, pady=8)
        tk.Label(form, text="Perfil de edición", bg="#1b1d21", fg="#c4c6ca").grid(row=0,column=0,sticky="w",pady=4)
        self.profile_combo = ttk.Combobox(form, textvariable=self.profile_var, values=["GLOBAL","FL Studio","Cubase","OBS","Windows"], state="readonly", width=24)
        self.profile_combo.grid(row=0,column=1,sticky="ew",pady=4)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda e: self.load_editor())
        tk.Label(form, text="Pad", bg="#1b1d21", fg="#c4c6ca").grid(row=1,column=0,sticky="w",pady=4)
        self.pad_combo = ttk.Combobox(form, textvariable=self.selected_pad, values=["36","38","42","46"], state="readonly", width=24)
        self.pad_combo.grid(row=1,column=1,sticky="ew",pady=4)
        self.pad_combo.bind("<<ComboboxSelected>>", lambda e: self.load_editor())
        tk.Label(form, text="Acción", bg="#1b1d21", fg="#c4c6ca").grid(row=2,column=0,sticky="w",pady=4)
        types = ["none","shortcut","open","url","text","macro"]
        self.type_combo = ttk.Combobox(form, textvariable=self.action_type, values=types, state="readonly", width=24)
        self.type_combo.grid(row=2,column=1,sticky="ew",pady=4)
        tk.Label(form, text="Valor / contenido", bg="#1b1d21", fg="#c4c6ca").grid(row=3,column=0,sticky="w",pady=4)
        self.value_entry = ttk.Entry(form, textvariable=self.action_value, width=36)
        self.value_entry.grid(row=3,column=1,sticky="ew",pady=4)
        form.columnconfigure(1, weight=1)
        helptext = "shortcut: ctrl+shift+r | open: ruta .exe o carpeta | url: https://... | text: texto a escribir | macro: una acción por línea (tipo:valor)"
        tk.Label(right, text=helptext, bg="#1b1d21", fg="#92969e", wraplength=430, justify="left").pack(anchor="w", padx=14, pady=4)
        buttons = tk.Frame(right, bg="#1b1d21"); buttons.pack(fill="x", padx=12, pady=8)
        ttk.Button(buttons, text="Guardar asignación", style="Accent.TButton", command=self.save_assignment).pack(side="left", padx=(0,6))
        ttk.Button(buttons, text="Probar acción", command=self.test_action).pack(side="left")

        logp = self.panel(self.root, "MONITOR MIDI EN DIRECTO")
        logp.pack(fill="both", expand=False, padx=20, pady=(4,18))
        self.log = tk.Text(logp, height=8, bg="#101114", fg="#d9dce1", insertbackground="#f2c400",
                           relief="flat", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.load_editor()

    def logline(self, msg):
        self.events.put(("log", msg))

    def refresh_devices(self):
        try:
            import mido
            names = mido.get_input_names()
        except Exception as e:
            names = []
            self.logline("No se pudo enumerar MIDI: " + str(e))
        self.device_combo["values"] = names
        match = next((n for n in names if "v mini" in n.lower() or "alesis" in n.lower()), "")
        if match:
            self.device_var.set(match)
        elif names and not self.device_var.get():
            self.device_var.set(names[0])
        self.logline("Entradas MIDI: " + (", ".join(names) if names else "ninguna"))

    def connect(self):
        if self.running:
            return
        name = self.device_var.get()
        if not name:
            messagebox.showwarning(APP_NAME, "Selecciona una entrada MIDI.")
            return
        try:
            import mido
            self.midi_in = mido.open_input(name, callback=self.midi_callback)
            self.running = True
            self.status.config(text="● CONECTADO", fg="#78d69a")
            self.logline("Conectado: " + name)
        except Exception as e:
            messagebox.showerror(APP_NAME, "No se pudo abrir el dispositivo MIDI:\n" + str(e))

    def disconnect(self):
        self.running = False
        if self.midi_in:
            try: self.midi_in.close()
            except Exception: pass
            self.midi_in = None
        self.status.config(text="● DESCONECTADO", fg="#e0a33a")
        self.logline("Dispositivo desconectado.")

    def midi_callback(self, msg):
        try:
            typ = msg.type
            ch = getattr(msg, "channel", -1) + 1
            if typ in ("note_on", "note_off"):
                note = msg.note
                is_on = typ == "note_on" and msg.velocity > 0
                label = f"{typ.upper()} ch{ch} note={note} vel={msg.velocity}"
                self.logline(label)
                if ch == 1 and note in (36,38,42,46):
                    if is_on and note not in self.last_pad_state:
                        self.last_pad_state.add(note)
                        profile = self.current_profile if self.current_profile != "Windows" else "GLOBAL"
                        self.execute_pad(str(note), profile)
                    elif not is_on:
                        self.last_pad_state.discard(note)
            elif typ == "control_change":
                self.logline(f"CC ch{ch} cc={msg.control} value={msg.value}")
            elif typ == "pitchwheel":
                self.logline(f"PITCH ch{ch} value={msg.pitch}")
            else:
                self.logline(str(msg))
        except Exception as e:
            self.logline("Error MIDI: " + str(e))

    def execute_pad(self, note, profile):
        action = self.cfg.get("profiles", {}).get(profile, {}).get(note)
        if not action:
            action = self.cfg.get("profiles", {}).get("GLOBAL", {}).get(note)
        if not action:
            action = self.cfg.get("mapping", {}).get("pads", {}).get(note, {})
        if action and action.get("type") != "none":
            try:
                run_action(action)
                self.logline(f"MACRO ejecutada: {profile} / PAD note {note}")
            except Exception as e:
                self.logline("ERROR macro: " + str(e))

    def update_profile(self):
        if self.auto_var.get():
            proc = foreground_process()
            p = detect_profile(proc)
            if p != self.current_profile:
                self.current_profile = p
                self.profile_label.config(text=p)
                self.logline(f"Perfil activo: {p} ({proc or 'sin proceso'})")
        self.root.after(500, self.update_profile)

    def select_pad(self, note):
        self.selected_pad.set(note)
        self.load_editor()

    def load_editor(self):
        profile = self.profile_var.get()
        note = self.selected_pad.get()
        action = self.cfg.get("profiles", {}).get(profile, {}).get(note)
        if not action and profile == "GLOBAL":
            action = self.cfg.get("mapping", {}).get("pads", {}).get(note, {})
        action = action or {"type":"none","value":""}
        self.action_type.set(action.get("type","none"))
        self.action_value.set(action.get("value",""))

    def save_assignment(self):
        profile, note = self.profile_var.get(), self.selected_pad.get()
        action = {"type": self.action_type.get(), "value": self.action_value.get()}
        self.cfg.setdefault("profiles", {}).setdefault(profile,{})[note] = action
        if profile == "GLOBAL":
            self.cfg.setdefault("mapping",{}).setdefault("pads",{})[note] = {
                "label": "PAD " + str(["36","38","42","46"].index(note)+1), **action
            }
        save_config(self.cfg)
        self.logline(f"Guardado: {profile} / PAD {note}")
        messagebox.showinfo(APP_NAME, "Asignación guardada.")

    def test_action(self):
        try:
            run_action({"type":self.action_type.get(),"value":self.action_value.get()})
            self.logline("Prueba de acción ejecutada.")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def save_auto(self):
        self.cfg["auto_profile"] = bool(self.auto_var.get())
        save_config(self.cfg)

    def process_queue(self):
        try:
            while True:
                kind, msg = self.events.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", time.strftime("%H:%M:%S ") + msg + "\n")
                self.log.see("end")
                # Keep the monitor bounded
                lines = int(self.log.index("end-1c").split(".")[0])
                if lines > 300:
                    self.log.delete("1.0", "50.0")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def close(self):
        self.disconnect()
        self.root.destroy()

def main():
    root = tk.Tk()
    MidiDeckApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
