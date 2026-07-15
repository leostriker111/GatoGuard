import json
import os
import queue
import sys
import threading
import time
import tkinter as tk

import keyboard
import pystray
from PIL import Image, ImageDraw

import deteccion
import hooks
import winutils

if getattr(sys, "frozen", False):          # corriendo como .exe (PyInstaller)
    BUNDLE = sys._MEIPASS                   # datos de solo lectura (diccionarios)
    DATA = os.path.join(os.environ.get("APPDATA", "."), "GatoGuard")
else:
    BUNDLE = DATA = os.path.dirname(os.path.abspath(__file__))
os.makedirs(DATA, exist_ok=True)
CFG_PATH = os.path.join(DATA, "config.json")

DICCIONARIOS = {"es": "es_50k.txt", "en": "en_50k.txt"}  # idiomas con diccionario
IDIOMAS_NOMBRE = {"es": "Español", "en": "Inglés", "ja": "Japonés (romaji, heurística)"}

DEFAULTS = {
    "rafaga": True,
    "simultaneas": True,
    "tecla_pegada": True,
    "prediccion": True,
    "sin_campo": False,          # apagado por defecto: era lo que botaba de mas
    "ignorar_pantalla_completa": True,
    "reset_teclado": True,
    "mostrar_hint": True,
    "held_threshold": 3,
    "burst_keys": 5,
    "burst_window": 0.45,
    "hold_ms": 1300,
    "cooldown": 1.0,
    "languages": [],             # [] = autodetectar del teclado
    "apps_ignoradas": [],        # exes donde NO vigilar (ej. juego.exe)
    "hotkey_unlock": "ctrl+alt+u",
    "hotkey_pause": "ctrl+alt+g",
    "hotkey_mouse": "ctrl+alt+m",
}

ETIQUETAS = {
    "rafaga": "Detectar ráfaga de teclas sin sentido",
    "simultaneas": "Detectar varias teclas mantenidas a la vez",
    "tecla_pegada": "Detectar una tecla pegada mucho tiempo",
    "prediccion": "Predicción de texto (no botar al escribir rápido)",
    "sin_campo": "Ser más agresivo si no hay campo de texto",
    "ignorar_pantalla_completa": "Relajar detección en apps de pantalla completa (juegos)",
    "reset_teclado": "Resetear teclado al estado default al desbloquear",
    "mostrar_hint": "Mostrar el aviso del mouse en la esquina",
}
SLIDERS = {
    "held_threshold": ("Teclas simultáneas para disparar", 2, 6, 1),
    "burst_keys": ("Teclas en ráfaga para disparar", 3, 12, 1),
    "burst_window": ("Ventana de la ráfaga (seg)", 0.2, 1.0, 0.05),
    "hold_ms": ("Tiempo de tecla pegada (ms)", 500, 3000, 100),
    "cooldown": ("Gracia tras desbloquear (seg)", 0.5, 3.0, 0.5),
}


def load_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(CFG_PATH):
        try:
            cfg.update(json.load(open(CFG_PATH, encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_cfg(cfg):
    json.dump(cfg, open(CFG_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def idiomas_activos(cfg):
    langs = cfg["languages"] or winutils.idiomas_teclado()
    return [l for l in langs if l in DICCIONARIOS]


URL_DIC = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/{l}/{l}_50k.txt"


def ruta_diccionario(l):
    for base in (BUNDLE, DATA):
        p = os.path.join(base, DICCIONARIOS[l])
        if os.path.exists(p):
            return p
    dest = os.path.join(DATA, DICCIONARIOS[l])
    try:
        import urllib.request
        urllib.request.urlretrieve(URL_DIC.format(l=l), dest)
        return dest
    except Exception:
        return None


def cargar_lexico(cfg):
    paths = [p for l in idiomas_activos(cfg) if (p := ruta_diccionario(l))]
    return deteccion.Lexico.cargar(paths)


cfg = load_cfg()
detector = deteccion.Detector(cfg, cargar_lexico(cfg))

cmd_queue = queue.Queue()
locked = False
paused = False
resume_after = 0.0
key_blocker = None
mouse_blocker = None
mouse_frozen = False
settings = None
icon = None
_front = (0.0, ("", False))


def app_al_frente():
    """(exe, pantalla_completa) con cache corto para no consultar cada tecla."""
    global _front
    ahora = time.time()
    if ahora - _front[0] > 0.4:
        _front = (ahora, winutils.app_frontal())
    return _front[1]


# ---------------- teclado ----------------
def monitor(e):
    if paused or locked or e.time < resume_after:
        return
    exe, full = app_al_frente()
    if exe in cfg["apps_ignoradas"]:
        return
    campo = winutils.hay_campo_texto() if cfg["sin_campo"] else True
    juego = full and cfg["ignorar_pantalla_completa"]
    motivo = detector.feed(e.name or "", e.scan_code, e.event_type, e.time, campo, juego)
    if motivo:
        cmd_queue.put(("LOCK", motivo))


def entrar_lock(motivo):
    global locked, key_blocker
    locked = True
    # hook crudo: bloquea TODO (incluye F11, Win+Ctrl+D, etc.) menos la combo
    key_blocker = hooks.KeyBlocker(cfg["hotkey_unlock"],
                                   lambda: cmd_queue.put(("UNLOCK", None)))
    key_blocker.start()
    motivo_var.set("Motivo: " + motivo)
    salida_var.set("Clic en cualquier parte  ·  o  " + cfg["hotkey_unlock"].upper())
    overlay.deiconify()
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.lift()
    overlay.focus_force()


def unlock(_=None):
    global locked, key_blocker, resume_after
    if not locked:
        return
    if key_blocker:
        key_blocker.stop()
        key_blocker = None
    detector.reset_estado()
    if cfg["reset_teclado"]:
        winutils.reset_teclado()
    resume_after = time.time() + cfg["cooldown"]
    locked = False
    overlay.withdraw()


def toggle_pause(*_):
    global paused
    paused = not paused
    if paused:
        detector.reset_estado()


def toggle_mouse(*_):
    global mouse_blocker, mouse_frozen
    if mouse_frozen:
        if mouse_blocker:
            mouse_blocker.stop()
            mouse_blocker = None
        mouse_frozen = False
    else:
        mouse_blocker = hooks.MouseBlocker()
        mouse_blocker.start()
        mouse_frozen = True
    actualizar_hint()


def registrar_hotkeys():
    keyboard.add_hotkey(cfg["hotkey_pause"], lambda: cmd_queue.put(("PAUSE", None)))
    keyboard.add_hotkey(cfg["hotkey_mouse"], lambda: cmd_queue.put(("MOUSE", None)))


# ---------------- bandeja ----------------
def icono_img():
    ico = os.path.join(BUNDLE, "gatoguard.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGBA", (64, 64), (16, 16, 20, 255))
    d = ImageDraw.Draw(img)
    d.polygon([(14, 30), (22, 12), (30, 30)], fill=(58, 122, 254, 255))
    d.polygon([(34, 30), (42, 12), (50, 30)], fill=(58, 122, 254, 255))
    d.ellipse([12, 24, 52, 56], fill=(58, 122, 254, 255))
    d.ellipse([22, 36, 28, 42], fill=(16, 16, 20, 255))
    d.ellipse([36, 36, 42, 42], fill=(16, 16, 20, 255))
    return img


def tray_thread():
    global icon
    menu = pystray.Menu(
        pystray.MenuItem("Configuración", lambda i, x: cmd_queue.put(("SETTINGS", None))),
        pystray.MenuItem("Pausado", lambda i, x: cmd_queue.put(("PAUSE", None)),
                         checked=lambda i: paused),
        pystray.MenuItem("Resetear teclado ahora", lambda i, x: cmd_queue.put(("RESET", None))),
        pystray.MenuItem("Salir", lambda i, x: cmd_queue.put(("QUIT", None))),
    )
    icon = pystray.Icon("GatoGuard", icono_img(), "GatoGuard", menu)
    icon.run()


# ---------------- config GUI ----------------
def build_settings():
    win = tk.Toplevel(root)
    win.title("GatoGuard - Configuración")
    win.configure(bg="#1a1a20", padx=18, pady=16)
    win.protocol("WM_DELETE_WINDOW", win.withdraw)
    win.resizable(False, False)
    win.vars = {}
    L = dict(bg="#1a1a20", fg="#ffffff")

    tk.Label(win, text="Activaciones", font=("Segoe UI", 12, "bold"), **L).pack(anchor="w")
    for key, txt in ETIQUETAS.items():
        v = tk.BooleanVar(value=cfg[key])
        win.vars[key] = v
        tk.Checkbutton(win, text=txt, variable=v, bg="#1a1a20", fg="#dddde3",
                       selectcolor="#2a2a33", activebackground="#1a1a20",
                       activeforeground="#ffffff", anchor="w",
                       font=("Segoe UI", 10)).pack(anchor="w", fill="x")

    tk.Label(win, text="Idiomas (predicción)", font=("Segoe UI", 12, "bold"),
             **L).pack(anchor="w", pady=(12, 2))
    win.langs = {}
    detectados = winutils.idiomas_teclado()
    activos = cfg["languages"] or detectados
    for code in dict.fromkeys(detectados + list(DICCIONARIOS)):
        nombre = IDIOMAS_NOMBRE.get(code, code)
        v = tk.BooleanVar(value=code in activos)
        win.langs[code] = v
        estado = "" if code in DICCIONARIOS else "  (sin diccionario)"
        tk.Checkbutton(win, text=nombre + estado, variable=v,
                       state="normal" if code in DICCIONARIOS else "disabled",
                       bg="#1a1a20", fg="#dddde3", selectcolor="#2a2a33",
                       activebackground="#1a1a20", anchor="w",
                       font=("Segoe UI", 10)).pack(anchor="w", fill="x")

    tk.Label(win, text="Atajos", font=("Segoe UI", 12, "bold"),
             **L).pack(anchor="w", pady=(12, 2))
    for key, txt in [("hotkey_unlock", "Desbloquear"), ("hotkey_pause", "Pausar/Reanudar"),
                     ("hotkey_mouse", "Congelar mouse")]:
        row = tk.Frame(win, bg="#1a1a20")
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=txt + ":", width=16, anchor="w", bg="#1a1a20",
                 fg="#9a9aa6", font=("Segoe UI", 9)).pack(side="left")
        v = tk.StringVar(value=cfg[key])
        win.vars[key] = v
        tk.Entry(row, textvariable=v, width=18, bg="#2a2a33", fg="#ffffff",
                 insertbackground="#ffffff", relief="flat").pack(side="left")

    row = tk.Frame(win, bg="#1a1a20")
    row.pack(anchor="w", fill="x", pady=(6, 0))
    tk.Label(row, text="Apps ignoradas:", width=16, anchor="w", bg="#1a1a20",
             fg="#9a9aa6", font=("Segoe UI", 9)).pack(side="left")
    win.apps_var = tk.StringVar(value=", ".join(cfg["apps_ignoradas"]))
    tk.Entry(row, textvariable=win.apps_var, width=28, bg="#2a2a33", fg="#ffffff",
             insertbackground="#ffffff", relief="flat").pack(side="left")
    tk.Label(win, text="(exe separados por coma, ej. juego.exe)", bg="#1a1a20",
             fg="#5a5a66", font=("Segoe UI", 8)).pack(anchor="w")

    tk.Label(win, text="Sensibilidad", font=("Segoe UI", 12, "bold"),
             **L).pack(anchor="w", pady=(12, 2))
    for key, (txt, lo, hi, res) in SLIDERS.items():
        tk.Label(win, text=txt, bg="#1a1a20", fg="#9a9aa6",
                 font=("Segoe UI", 9)).pack(anchor="w")
        v = tk.DoubleVar(value=cfg[key])
        win.vars[key] = v
        tk.Scale(win, from_=lo, to=hi, resolution=res, orient="horizontal",
                 variable=v, bg="#1a1a20", fg="#ffffff", troughcolor="#2a2a33",
                 highlightthickness=0, length=340).pack(anchor="w")

    def aplicar():
        for key, v in win.vars.items():
            val = v.get()
            cfg[key] = int(val) if key in ("held_threshold", "burst_keys", "hold_ms") else val
        cfg["languages"] = [c for c, v in win.langs.items() if v.get()]
        cfg["apps_ignoradas"] = [a.strip().lower() for a in win.apps_var.get().split(",") if a.strip()]
        save_cfg(cfg)
        detector.lx = cargar_lexico(cfg)
        keyboard.remove_all_hotkeys()
        registrar_hotkeys()
        actualizar_hint()
        win.withdraw()

    tk.Button(win, text="Guardar", font=("Segoe UI", 11, "bold"), bg="#3a7afe",
              fg="#ffffff", relief="flat", padx=24, pady=8, cursor="hand2",
              command=aplicar).pack(pady=(14, 0))
    return win


def mostrar_settings():
    global settings
    if settings is None:
        settings = build_settings()
    else:
        for key, v in settings.vars.items():
            v.set(cfg[key])
    settings.deiconify()
    settings.lift()
    settings.focus_force()


# ---------------- loop principal ----------------
def poll():
    try:
        while True:
            cmd, arg = cmd_queue.get_nowait()
            if cmd == "LOCK" and not locked and not paused:
                entrar_lock(arg)
            elif cmd == "UNLOCK":
                unlock()
            elif cmd == "PAUSE":
                toggle_pause()
            elif cmd == "MOUSE":
                toggle_mouse()
            elif cmd == "SETTINGS":
                mostrar_settings()
            elif cmd == "RESET":
                winutils.reset_teclado()
            elif cmd == "QUIT":
                if icon:
                    icon.stop()
                root.destroy()
                return
    except queue.Empty:
        pass
    if not locked and not paused:
        m = detector.check_hold(time.time())
        if m:
            entrar_lock(m)
    root.after(30, poll)


root = tk.Tk()
root.withdraw()
motivo_var = tk.StringVar(value="")
salida_var = tk.StringVar(value="")
hint_var = tk.StringVar(value="")


def _click_through(win):
    import ctypes
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
    cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, cur | WS_EX_LAYERED | WS_EX_TRANSPARENT)


hint = tk.Toplevel(root)
hint.overrideredirect(True)
hint.attributes("-topmost", True)
hint.attributes("-alpha", 0.80)
hint.configure(bg="#101014")
hint_lbl = tk.Label(hint, textvariable=hint_var, bg="#101014", fg="#9a9aa6",
                    font=("Segoe UI", 9), padx=10, pady=4)
hint_lbl.pack()
hint.withdraw()


def actualizar_hint():
    if not cfg["mostrar_hint"]:
        hint.withdraw()
        return
    combo = cfg["hotkey_mouse"].upper()
    if mouse_frozen:
        hint_var.set("🖱 MOUSE CONGELADO · " + combo)
        hint_lbl.config(fg="#ff6b6b")
    else:
        hint_var.set("🖱 " + combo + " congela el mouse")
        hint_lbl.config(fg="#6a6a76")
    hint.update_idletasks()
    w, h = hint.winfo_reqwidth(), hint.winfo_reqheight()
    x = root.winfo_screenwidth() - w - 14
    y = root.winfo_screenheight() - h - 48
    hint.geometry(f"+{x}+{y}")
    hint.deiconify()
    hint.lift()
    _click_through(hint)

overlay = tk.Toplevel(root)
overlay.withdraw()
overlay.configure(bg="#101014")
overlay.protocol("WM_DELETE_WINDOW", lambda: None)
overlay.bind("<Button-1>", unlock)

_f = tk.Frame(overlay, bg="#101014")
_f.place(relx=0.5, rely=0.5, anchor="center")
tk.Label(_f, text="\U0001F408", font=("Segoe UI Emoji", 90),
         bg="#101014", fg="#ffffff").pack(pady=(0, 10))
tk.Label(_f, text="Gato detectado sobre el teclado", font=("Segoe UI", 28, "bold"),
         bg="#101014", fg="#ffffff").pack()
tk.Label(_f, textvariable=motivo_var, font=("Segoe UI", 13),
         bg="#101014", fg="#3a7afe").pack(pady=(4, 0))
tk.Label(_f, textvariable=salida_var, font=("Segoe UI", 15),
         bg="#101014", fg="#9a9aa6").pack(pady=(10, 24))
tk.Button(_f, text="Desbloquear", font=("Segoe UI", 16, "bold"), bg="#3a7afe",
          fg="#ffffff", activebackground="#2f66d6", activeforeground="#ffffff",
          relief="flat", padx=30, pady=12, cursor="hand2", command=unlock).pack()


def main():
    global resume_after
    winutils.reset_teclado()
    keyboard.hook(monitor)
    registrar_hotkeys()
    resume_after = time.time() + 1.0
    threading.Thread(target=tray_thread, daemon=True).start()
    actualizar_hint()
    root.after(30, poll)
    root.mainloop()


if __name__ == "__main__":
    main()
