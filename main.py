# CRAY LDR MIDI DECK v0.3
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
    "midi_output": "",
    "forward_knobs": True,
    "mixer_nav_enabled": True,
    "mixer_nav_step": 10,
    "profile_processes": {},
    "knobs": {"14": {"label": "KNOB 1", "channel": 1}, "15": {"label": "KNOB 2", "channel": 1}, "16": {"label": "KNOB 3", "channel": 1}, "17": {"label": "KNOB 4", "channel": 1}},
    "profiles": {
        "GLOBAL": {},
        "FL Studio": {
            "38": {
                "label": "PRO-Q 3",
                "type": "macro",
                "value": "shortcut:f8\nwait:350\ntext:FabFilter Pro-Q 3\nwait:250\nshortcut:enter"
            },
            "42": {
                "label": "CLA-76",
                "type": "macro",
                "value": "shortcut:f8\nwait:350\ntext:CLA-76\nwait:250\nshortcut:enter"
            },
            "46": {
                "label": "REC + PLAY",
                "type": "macro",
                "value": "shortcut:r\nwait:300\nshortcut:space"
            }
        },
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

def deep_merge(base, incoming):
    result = json.loads(json.dumps(base))
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists(): save_config(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict): data = {}
    except Exception: data = {}
    merged = deep_merge(DEFAULT_CONFIG, data)
    merged.setdefault("profiles", {})
    merged.setdefault("knobs", {})
    merged.setdefault("mapping", {}).setdefault("pads", {})
    for p in ("GLOBAL", "FL Studio", "Cubase", "OBS", "Windows"):
        merged["profiles"].setdefault(p, {})
    for cc, default in DEFAULT_CONFIG["knobs"].items():
        merged["knobs"].setdefault(cc, dict(default, input_cc=int(cc), output_cc=int(cc), min_value=0, max_value=127, output_channel=1))
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
        # Actions: shortcut:ctrl+s | text:hello | open:path | url:https://... | wait:250
        for line in value.splitlines():
            if ":" not in line:
                continue
            sub, val = line.split(":", 1)
            sub, val = sub.strip().lower(), val.strip()
            if sub == "wait":
                time.sleep(max(0, min(10000, int(val))) / 1000)
            elif sub in ("shortcut", "text", "open", "url"):
                run_action({"type": sub, "value": val})

class MidiDeckApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME + "  |  v0.2")
        self.root.geometry("1040x720")
        self.root.minsize(900, 640)
        self.root.configure(bg="#111214")
        self.cfg = load_config()
        self.events = queue.Queue()
        self.midi_in = None
        self.midi_out = None
        self.midi_thread = None
        self.running = False
        self.current_profile = "Windows"
        self.last_pad_state = set()
        self.selected_pad = tk.StringVar(value="36")
        self.profile_var = tk.StringVar(value="GLOBAL")
        self.device_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value=self.cfg.get("midi_output", ""))
        self.forward_var = tk.BooleanVar(value=self.cfg.get("forward_knobs", True))
        self.mixer_nav_var = tk.BooleanVar(value=self.cfg.get("mixer_nav_enabled", True))
        self.last_knob_values = {}
        self.knob_nav_accumulator = 0
        self.knob_values = {cc: tk.IntVar(value=0) for cc in ("14", "15", "16", "17")}
        self.knob_learn_target = None
        self.knob_learn_vars = {}
        self.action_type = tk.StringVar(value="none")
        self.action_value = tk.StringVar(value="")
        self.pad_label = tk.StringVar(value="PAD 1")
        self.auto_var = tk.BooleanVar(value=self.cfg.get("auto_profile", True))
        self.startup_var = tk.BooleanVar(value=self.cfg.get("start_with_windows", False))
        self._style()
        self._build()
        self.refresh_devices()
        self.refresh_outputs()
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
        tk.Label(header, text="  MIDI DECK  /  0.2", bg="#111214", fg="#f1f1f1", font=("Segoe UI", 15, "bold")).pack(side="left")
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
        outrow = tk.Frame(dev, bg="#1b1d21"); outrow.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(outrow, text="Salida MIDI:", bg="#1b1d21", fg="#c4c6ca").pack(side="left", padx=(0, 8))
        self.output_combo = ttk.Combobox(outrow, textvariable=self.output_var, state="readonly", width=30)
        self.output_combo.pack(side="left", padx=(0, 8))
        ttk.Button(outrow, text="Actualizar", command=self.refresh_outputs).pack(side="left", padx=3)
        ttk.Button(outrow, text="Abrir salida", command=self.connect_output).pack(side="left", padx=3)
        ttk.Button(outrow, text="Cerrar", command=self.disconnect_output).pack(side="left", padx=3)
        ttk.Checkbutton(outrow, text="Enviar CC14–17", variable=self.forward_var, command=self.save_forward).pack(side="left", padx=8)
        ttk.Checkbutton(outrow, text="K1 Mixer FL", variable=self.mixer_nav_var, command=self.save_mixer_nav).pack(side="left", padx=6)
        ttk.Button(outrow, text="Configurar knobs", command=self.open_knob_editor).pack(side="left", padx=4)
        ttk.Button(outrow, text="Perfiles", command=self.open_profile_manager).pack(side="left", padx=4)

        prof = self.panel(top, "PERFIL ACTIVO")
        prof.pack(side="left", fill="x", expand=True, padx=(8, 0))
        pr = tk.Frame(prof, bg="#1b1d21"); pr.pack(fill="x", padx=12, pady=(0, 12))
        self.profile_label = tk.Label(pr, text="Windows", bg="#1b1d21", fg="#ffffff", font=("Segoe UI", 14, "bold"))
        self.profile_label.pack(side="left", padx=(0, 12))
        ttk.Checkbutton(pr, text="Detección automática", variable=self.auto_var, command=self.save_auto).pack(side="left")
        ttk.Checkbutton(pr, text="Iniciar con Windows", variable=self.startup_var, command=self.save_startup).pack(side="left", padx=10)

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
        tk.Label(left, text="Knobs: CC 14 · 15 · 16 · 17 (configurables)", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=5)
        self.knob_status = tk.Label(left, text="K1 0  |  K2 0  |  K3 0  |  K4 0", bg="#1b1d21", fg="#f2c400")
        self.knob_status.pack(anchor="w", padx=14, pady=3)
        tk.Label(left, text="Teclas: canal 16 · notas 48–72", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=3)
        tk.Label(left, text="CC1 modulación · CC64 sustain · Pitch Bend", bg="#1b1d21", fg="#c4c6ca").pack(anchor="w", padx=14, pady=3)
        tk.Label(left, text="Los controles no asignados no ejecutan acciones.", bg="#1b1d21", fg="#e0a33a", wraplength=330).pack(anchor="w", padx=14, pady=(8, 14))

        right = self.panel(body, "ASIGNACIÓN DE MACROS")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        form = tk.Frame(right, bg="#1b1d21"); form.pack(fill="x", padx=12, pady=8)
        tk.Label(form, text="Perfil de edición", bg="#1b1d21", fg="#c4c6ca").grid(row=0,column=0,sticky="w",pady=4)
        self.profile_combo = ttk.Combobox(form, textvariable=self.profile_var, values=sorted(self.cfg.get("profiles", {}).keys()), state="readonly", width=24)
        self.profile_combo.grid(row=0,column=1,sticky="ew",pady=4)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda e: self.load_editor())
        tk.Label(form, text="Pad", bg="#1b1d21", fg="#c4c6ca").grid(row=1,column=0,sticky="w",pady=4)
        self.pad_combo = ttk.Combobox(form, textvariable=self.selected_pad, values=["36","38","42","46"], state="readonly", width=24)
        self.pad_combo.grid(row=1,column=1,sticky="ew",pady=4)
        self.pad_combo.bind("<<ComboboxSelected>>", lambda e: self.load_editor())
        tk.Label(form, text="Nombre del botón", bg="#1b1d21", fg="#c4c6ca").grid(row=2,column=0,sticky="w",pady=4)
        self.label_entry = ttk.Entry(form, textvariable=self.pad_label, width=36)
        self.label_entry.grid(row=2,column=1,sticky="ew",pady=4)
        tk.Label(form, text="Acción", bg="#1b1d21", fg="#c4c6ca").grid(row=3,column=0,sticky="w",pady=4)
        types = ["none","shortcut","open","url","text","macro"]
        self.type_combo = ttk.Combobox(form, textvariable=self.action_type, values=types, state="readonly", width=24)
        self.type_combo.grid(row=3,column=1,sticky="ew",pady=4)
        tk.Label(form, text="Valor / contenido", bg="#1b1d21", fg="#c4c6ca").grid(row=4,column=0,sticky="w",pady=4)
        self.value_entry = ttk.Entry(form, textvariable=self.action_value, width=36)
        self.value_entry.grid(row=4,column=1,sticky="ew",pady=4)
        form.columnconfigure(1, weight=1)
        helptext = "shortcut: ctrl+shift+r | open: ruta .exe o carpeta | url: https://... | text: texto a escribir | macro: una acción por línea (tipo:valor)"
        tk.Label(right, text=helptext, bg="#1b1d21", fg="#92969e", wraplength=430, justify="left").pack(anchor="w", padx=14, pady=4)
        buttons = tk.Frame(right, bg="#1b1d21"); buttons.pack(fill="x", padx=12, pady=8)
        ttk.Button(buttons, text="Guardar asignación", style="Accent.TButton", command=self.save_assignment).pack(side="left", padx=(0,6))
        ttk.Button(buttons, text="Probar acción", command=self.test_action).pack(side="left")
        ttk.Button(buttons, text="Editor de macro", command=self.open_macro_editor).pack(side="left", padx=6)

        logp = self.panel(self.root, "MONITOR MIDI EN DIRECTO")
        logp.pack(fill="both", expand=False, padx=20, pady=(4,18))
        self.log = tk.Text(logp, height=8, bg="#101114", fg="#d9dce1", insertbackground="#f2c400",
                           relief="flat", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.load_editor()
        self.refresh_pad_buttons()


    def open_knob_editor(self):
        win = tk.Toplevel(self.root)
        win.title("Configuración de knobs MIDI")
        win.configure(bg="#17191d")
        tk.Label(win, text="ASIGNACIÓN DE LOS CUATRO KNOBS", bg="#17191d", fg="#f2c400",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=12)
        grid = tk.Frame(win, bg="#17191d"); grid.pack(padx=14, pady=4)
        headers = ("Control", "CC entrada", "Canal", "CC salida", "Canal salida", "Mín.", "Máx.")
        for col, title in enumerate(headers):
            tk.Label(grid, text=title, bg="#17191d", fg="#c4c6ca").grid(row=0, column=col, padx=4)
        variables = {}
        for row, cc in enumerate(("14", "15", "16", "17"), 1):
            cfg = self.cfg["knobs"].get(cc, {})
            vals = {"input_cc": str(cfg.get("input_cc", int(cc))), "channel": str(cfg.get("channel", 1)),
                    "output_cc": str(cfg.get("output_cc", int(cc))), "output_channel": str(cfg.get("output_channel", 1)),
                    "min_value": str(cfg.get("min_value", 0)), "max_value": str(cfg.get("max_value", 127))}
            variables[cc] = {k: tk.StringVar(value=v) for k, v in vals.items()}
            tk.Label(grid, text="KNOB " + str(row), bg="#17191d", fg="#f2c400").grid(row=row, column=0, padx=4)
            for col, key in enumerate(vals, 1):
                tk.Entry(grid, textvariable=variables[cc][key], width=8, bg="#25282e", fg="white",
                         insertbackground="white", relief="flat").grid(row=row, column=col, padx=4, pady=5)
            ttk.Button(grid, text="MIDI Learn", command=lambda target=cc: self.start_knob_learn(target)).grid(row=row, column=7, padx=5)
        self.knob_learn_vars = variables
        tk.Label(win, text="CC y valores: 0–127. Canales MIDI: 1–16. MIDI Learn: mueve el knob que quieras capturar.",
                 bg="#17191d", fg="#aeb2ba").pack(anchor="w", padx=14, pady=8)
        def save():
            try:
                updated = {}
                for cc, fields in variables.items():
                    item = {k: int(v.get()) for k, v in fields.items()}
                    for k in ("input_cc", "output_cc", "min_value", "max_value"):
                        if not 0 <= item[k] <= 127: raise ValueError(k + ": rango 0–127")
                    for k in ("channel", "output_channel"):
                        if not 1 <= item[k] <= 16: raise ValueError(k + ": rango 1–16")
                    if item["min_value"] > item["max_value"]: raise ValueError("Mínimo superior al máximo")
                    item["label"] = "KNOB " + cc
                    updated[cc] = item
                self.cfg["knobs"] = updated
                save_config(self.cfg)
                self.logline("Configuración de knobs guardada.")
                win.destroy()
            except Exception as e:
                messagebox.showerror(APP_NAME, "Valores no válidos: " + str(e), parent=win)
        ttk.Button(win, text="Guardar", command=save).pack(pady=12)

    def start_knob_learn(self, knob_key):
        self.knob_learn_target = knob_key
        self.logline("MIDI Learn activo para KNOB " + str(int(knob_key) - 13) + ". Mueve el control físico.")
        messagebox.showinfo(APP_NAME, "Mueve ahora el knob físico que quieres asignar. Se capturará su CC y canal.")

    def open_profile_manager(self):
        win = tk.Toplevel(self.root)
        win.title("Gestor de perfiles")
        win.configure(bg="#17191d")
        listing = tk.Listbox(win, width=34, height=9, bg="#25282e", fg="white", selectbackground="#a88900", relief="flat")
        listing.pack(padx=14, pady=12, fill="both", expand=True)
        def refresh():
            listing.delete(0, "end")
            for name in sorted(self.cfg.get("profiles", {})): listing.insert("end", name)
        name_var = tk.StringVar()
        exe_var = tk.StringVar()
        row = tk.Frame(win, bg="#17191d"); row.pack(fill="x", padx=14, pady=6)
        tk.Entry(row, textvariable=name_var, bg="#25282e", fg="white", insertbackground="white", relief="flat").pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=5)
        exe_row = tk.Frame(win, bg="#17191d"); exe_row.pack(fill="x", padx=14, pady=4)
        tk.Label(exe_row, text="Proceso .exe (opcional):", bg="#17191d", fg="#c4c6ca").pack(side="left", padx=(0, 6))
        tk.Entry(exe_row, textvariable=exe_var, bg="#25282e", fg="white", insertbackground="white", relief="flat").pack(side="left", fill="x", expand=True, ipady=5)
        def add():
            name = name_var.get().strip()
            if not name: return
            if name in self.cfg["profiles"]:
                messagebox.showwarning(APP_NAME, "El perfil ya existe.", parent=win); return
            self.cfg["profiles"][name] = {}
            executable = exe_var.get().strip().lower()
            if executable:
                if not executable.endswith(".exe"): executable += ".exe"
                self.cfg.setdefault("profile_processes", {})[name] = executable
            save_config(self.cfg); name_var.set(""); exe_var.set(""); refresh(); self.refresh_profile_choices()
        def remove():
            selected = listing.curselection()
            if not selected: return
            name = listing.get(selected[0])
            if name in ("GLOBAL", "FL Studio", "Cubase", "OBS", "Windows"):
                messagebox.showwarning(APP_NAME, "No se pueden borrar perfiles base.", parent=win); return
            if messagebox.askyesno(APP_NAME, "¿Eliminar " + name + "?", parent=win):
                del self.cfg["profiles"][name]
                self.cfg.get("profile_processes", {}).pop(name, None)
                save_config(self.cfg); refresh(); self.refresh_profile_choices()
        ttk.Button(row, text="Crear perfil", command=add).pack(side="left")
        ttk.Button(win, text="Eliminar seleccionado", command=remove).pack(pady=10)
        refresh()

    def refresh_profile_choices(self):
        names = sorted(self.cfg.get("profiles", {}).keys())
        self.profile_combo["values"] = names
        if self.profile_var.get() not in names: self.profile_var.set("GLOBAL")
        self.load_editor()

    def open_macro_editor(self):
        win = tk.Toplevel(self.root)
        win.title("Editor de macros")
        win.configure(bg="#17191d")
        tk.Label(win, text="UNA ACCIÓN POR LÍNEA", bg="#17191d", fg="#f2c400",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=10)
        editor = tk.Text(win, width=72, height=16, bg="#101114", fg="#eeeeee",
                         insertbackground="#f2c400", relief="flat")
        editor.pack(fill="both", expand=True, padx=12, pady=6)
        if self.action_type.get() == "macro": editor.insert("1.0", self.action_value.get())
        tk.Label(win, text="shortcut:ctrl+s | text:Hola | open:ruta | url:https://... | wait:500",
                 bg="#17191d", fg="#aeb2ba", wraplength=560).pack(anchor="w", padx=12, pady=6)
        def use_macro():
            self.action_type.set("macro")
            self.action_value.set(editor.get("1.0", "end-1c"))
            win.destroy()
        ttk.Button(win, text="Usar macro", command=use_macro).pack(pady=10)

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

    def refresh_outputs(self):
        try:
            import mido
            names = mido.get_output_names()
        except Exception as e:
            names = []
            self.logline("No se pudo enumerar salidas MIDI: " + str(e))
        self.output_combo["values"] = names
        if self.output_var.get() not in names:
            self.output_var.set(names[0] if names else "")
        self.logline("Salidas MIDI: " + (", ".join(names) if names else "ninguna"))

    def connect_output(self):
        self.disconnect_output()
        name = self.output_var.get()
        if not name:
            messagebox.showwarning(APP_NAME, "No hay salida MIDI. Crea un puerto virtual con loopMIDI y actualiza.")
            return
        try:
            import mido
            self.midi_out = mido.open_output(name)
            self.cfg["midi_output"] = name
            save_config(self.cfg)
            self.logline("Salida MIDI abierta: " + name)
        except Exception as e:
            messagebox.showerror(APP_NAME, "No se pudo abrir la salida MIDI:\n" + str(e))

    def disconnect_output(self):
        if self.midi_out:
            try:
                self.midi_out.close()
            except Exception as e:
                self.logline("Aviso al cerrar salida MIDI: " + str(e))
            self.midi_out = None
            self.logline("Salida MIDI cerrada.")

    def save_forward(self):
        self.cfg["forward_knobs"] = bool(self.forward_var.get())
        save_config(self.cfg)

    def save_mixer_nav(self):
        self.cfg["mixer_nav_enabled"] = bool(self.mixer_nav_var.get())
        self.last_knob_values.pop("14", None)
        self.knob_nav_accumulator = 0
        save_config(self.cfg)
        self.logline("Navegación K1 Mixer FL " + ("activada." if self.mixer_nav_var.get() else "desactivada."))

    def handle_mixer_navigation(self, knob_key, value):
        # Convierte el recorrido del potenciómetro CC14 en pasos discretos.
        # Umbral alto + histéresis para evitar que pequeñas variaciones recorran
        # varios Inserts. Nunca procesa saltos de sincronización al conectar.
        previous = self.last_knob_values.get(knob_key)
        self.last_knob_values[knob_key] = int(value)
        if knob_key != "14" or not self.mixer_nav_var.get() or previous is None:
            return

        delta = int(value) - int(previous)
        if abs(delta) > 24:
            self.knob_nav_accumulator = 0
            return
        if delta == 0:
            return
        if detect_profile(foreground_process()) != "FL Studio":
            self.knob_nav_accumulator = 0
            return

        # Al invertir el giro, descarta el residuo anterior para que no
        # provoque un paso inesperado en la dirección contraria.
        direction = 1 if delta > 0 else -1
        previous_direction = getattr(self, "_knob_nav_direction", 0)
        if previous_direction and direction != previous_direction:
            self.knob_nav_accumulator = 0
        self._knob_nav_direction = direction
        self.knob_nav_accumulator += delta

        threshold = max(8, min(24, int(self.cfg.get("mixer_nav_step", 10))))
        if abs(self.knob_nav_accumulator) >= threshold:
            try:
                import pyautogui
                pyautogui.press("right" if self.knob_nav_accumulator > 0 else "left")
                self.knob_nav_accumulator -= direction * threshold
            except Exception as e:
                self.logline("Error navegación Mixer FL: " + str(e))
                self.knob_nav_accumulator = 0

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
        self.last_pad_state.clear()
        if self.midi_in:
            try:
                self.midi_in.close()
            except Exception as e:
                self.logline("Aviso al cerrar MIDI: " + str(e))
            self.midi_in = None
        self.status.config(text="● DESCONECTADO", fg="#e0a33a")
        self.logline("Dispositivo desconectado.")

    def midi_callback(self, msg):
        # Este callback corre en el hilo MIDI: solo transfiere el evento.
        # Tkinter, el estado de pads y las acciones se procesan en el hilo UI.
        try:
            self.events.put(("midi", msg.copy()))
        except Exception as e:
            self.events.put(("log", "Error MIDI callback: " + str(e)))

    def handle_midi_message(self, msg):
        try:
            typ = msg.type
            ch = getattr(msg, "channel", -1) + 1
            if typ in ("note_on", "note_off"):
                note = msg.note
                is_on = typ == "note_on" and msg.velocity > 0
                self.logline(f"{typ.upper()} ch{ch} note={note} vel={msg.velocity}")
                if ch == 1 and note in (36, 38, 42, 46):
                    if is_on and note not in self.last_pad_state:
                        self.last_pad_state.add(note)
                        profile = self.current_profile if self.current_profile != "Windows" else "GLOBAL"
                        self.execute_pad(str(note), profile)
                    elif not is_on:
                        self.last_pad_state.discard(note)
            elif typ == "control_change":
                self.logline(f"CC ch{ch} cc={msg.control} value={msg.value}")
                if self.knob_learn_target:
                    target = self.knob_learn_target
                    self.knob_learn_target = None
                    self.cfg.setdefault("knobs", {}).setdefault(target, {})["input_cc"] = int(msg.control)
                    self.cfg["knobs"][target]["channel"] = int(ch)
                    if target in self.knob_learn_vars:
                        self.knob_learn_vars[target]["input_cc"].set(str(msg.control))
                        self.knob_learn_vars[target]["channel"].set(str(ch))
                    save_config(self.cfg)
                    self.logline("MIDI Learn: KNOB " + str(int(target) - 13) +
                                  " = CC" + str(msg.control) + " canal " + str(ch))
                for key, knob in self.cfg.get("knobs", {}).items():
                    if msg.control != int(knob.get("input_cc", key)) or ch != int(knob.get("channel", 1)):
                        continue
                    self.knob_values[key].set(msg.value)
                    self.handle_mixer_navigation(key, msg.value)
                    self.knob_status.config(text="  |  ".join("K" + str(i + 1) + " " +
                        str(self.knob_values[k].get()) for i, k in enumerate(("14", "15", "16", "17"))))
                    if self.forward_var.get() and self.midi_out and not (key == "14" and self.mixer_nav_var.get()):
                        try:
                            low, high = int(knob.get("min_value", 0)), int(knob.get("max_value", 127))
                            scaled = round(low + (msg.value / 127) * (high - low))
                            outgoing = msg.copy(channel=int(knob.get("output_channel", 1)) - 1,
                                                control=int(knob.get("output_cc", key)), value=scaled)
                            self.midi_out.send(outgoing)
                        except Exception as e:
                            self.logline("Error enviando CC del knob " + key + ": " + str(e))
                    break
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
            # Las acciones pueden tardar (macros, apertura de apps); no bloquear Tk.
            def worker():
                try:
                    run_action(action)
                    self.events.put(("log", f"Acción lanzada: {profile} / PAD note {note}"))
                except Exception as e:
                    self.events.put(("log", "ERROR acción: " + str(e)))
            threading.Thread(target=worker, daemon=True).start()

    def update_profile(self):
        if self.auto_var.get():
            proc = foreground_process()
            p = detect_profile(proc)
            for custom_name, executable in self.cfg.get("profile_processes", {}).items():
                if executable and executable.lower() == proc.lower():
                    p = custom_name
                    break
            if p != self.current_profile:
                self.current_profile = p
                self.profile_label.config(text=p)
                self.refresh_pad_buttons()
                self.logline(f"Perfil activo: {p} ({proc or 'sin proceso'})")
        self.root.after(500, self.update_profile)

    def refresh_pad_buttons(self):
        for i, note in enumerate(("36", "38", "42", "46")):
            action = self.cfg.get("profiles", {}).get(self.current_profile, {}).get(note)
            if not action:
                action = self.cfg.get("profiles", {}).get("GLOBAL", {}).get(note)
            if not action:
                action = self.cfg.get("mapping", {}).get("pads", {}).get(note, {})
            label = action.get("label") or ("PAD " + str(i + 1))
            self.pad_buttons[note].config(text=label + "\nNOTE " + note)

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
        default_label = "PAD " + str(["36","38","42","46"].index(note) + 1)
        self.pad_label.set(action.get("label") or self.cfg.get("mapping", {}).get("pads", {}).get(note, {}).get("label", default_label))
        self.action_type.set(action.get("type","none"))
        self.action_value.set(action.get("value",""))

    def save_assignment(self):
        profile, note = self.profile_var.get(), self.selected_pad.get()
        label = self.pad_label.get().strip() or ("PAD " + str(["36","38","42","46"].index(note)+1))
        action = {"label": label, "type": self.action_type.get(), "value": self.action_value.get()}
        self.cfg.setdefault("profiles", {}).setdefault(profile,{})[note] = action
        if profile == "GLOBAL":
            self.cfg.setdefault("mapping",{}).setdefault("pads",{})[note] = dict(action)
        save_config(self.cfg)
        self.refresh_pad_buttons()
        self.logline(f"Guardado: {profile} / PAD {note}")
        messagebox.showinfo(APP_NAME, "Asignación guardada.")

    def test_action(self):
        try:
            run_action({"type":self.action_type.get(),"value":self.action_value.get()})
            self.logline("Prueba de acción ejecutada.")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def save_startup(self):
        enabled = bool(self.startup_var.get())
        if os.name != "nt":
            messagebox.showwarning(APP_NAME, "El inicio automático solo está disponible en Windows.")
            self.startup_var.set(False)
            return
        try:
            import winreg
            key_path = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    if getattr(sys, "frozen", False):
                        command = '"' + sys.executable + '"'
                    else:
                        command = '"' + sys.executable + '" "' + str(Path(__file__).resolve()) + '"'
                    winreg.SetValueEx(key, "CrayLDRMidiDeck", 0, winreg.REG_SZ, command)
                else:
                    try: winreg.DeleteValue(key, "CrayLDRMidiDeck")
                    except FileNotFoundError: pass
            self.cfg["start_with_windows"] = enabled
            save_config(self.cfg)
            self.logline("Inicio con Windows " + ("activado." if enabled else "desactivado."))
        except Exception as e:
            self.startup_var.set(False)
            messagebox.showerror(APP_NAME, "No se pudo cambiar el inicio automático:\\n" + str(e))

    def save_auto(self):
        self.cfg["auto_profile"] = bool(self.auto_var.get())
        save_config(self.cfg)

    def process_queue(self):
        try:
            while True:
                kind, msg = self.events.get_nowait()
                if kind == "midi":
                    self.handle_midi_message(msg)
                    continue
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
        self.disconnect_output()
        self.root.destroy()

def main():
    root = tk.Tk()
    MidiDeckApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
