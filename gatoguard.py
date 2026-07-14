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
    "ocultar_cursor": True,
    "reset_teclado": True,
    "held_threshold": 4,
    "burst_keys": 6,
    "burst_window": 0.45,
    "hold_ms": 1300,
    "cooldown": 1.0,
    "languages": [],             # [] = autodetectar del teclado
    "hotkey_unlock": "ctrl+alt+u",
    "hotkey_pause": "ctrl+alt+g",
}

ETIQUETAS = {
    "rafaga": "Detectar ráfaga de teclas sin sentido",
    "simultaneas": "Detectar varias teclas mantenidas a la vez",
    "tecla_pegada": "Detectar una tecla pegada mucho tiempo",
    "prediccion": "Predicción de texto (no botar al escribir rápido)",
    "sin_campo": "Ser más agresivo si no hay campo de texto",
    "ocultar_cursor": "Ocultar el cursor al bloquear",
    "reset_teclado": "Resetear teclado al estado default al desbloquear",
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
block_hook = None
combo_pressed = set()
settings = None
icon = None


def _norm(name):
    n = (name or "").lower()
    for m in ("ctrl", "alt", "shift", "win"):
        if m in n:
            return m
    return n


def _combo_ok(combo, pressed):
    partes = {_norm(p) for p in combo.split("+")}
    return partes.issubset(pressed)


# ---------------- teclado ----------------
def monitor(e):
    if paused or locked or e.time < resume_after:
        return
    campo = winutils.hay_campo_texto() if cfg["sin_campo"] else True
    motivo = detector.feed(e.name or "", e.scan_code, e.event_type, e.time, campo)
    if motivo:
        cmd_queue.put(("LOCK", motivo))


def _block(e):
    # bloquea TODO menos el atajo de desbloqueo, que se vigila aparte
    if e.event_type == "down":
        combo_pressed.add(_norm(e.name))
    else:
        combo_pressed.discard(_norm(e.name))
    if _combo_ok(cfg["hotkey_unlock"], combo_pressed):
        cmd_queue.put(("UNLOCK", None))
    return False


def entrar_lock(motivo):
    global locked, block_hook
    locked = True
    combo_pressed.clear()
    block_hook = keyboard.hook(_block, suppress=True)
    motivo_var.set("Motivo: " + motivo)
    salida_var.set("Clic en cualquier parte  ·  o  " + cfg["hotkey_unlock"].upper())
    overlay.config(cursor="none" if cfg["ocultar_cursor"] else "arrow")
    overlay.deiconify()
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.lift()
    overlay.focus_force()


def unlock(_=None):
    global locked, block_hook, resume_after
    if not locked:
        return
    if block_hook:
        keyboard.unhook(block_hook)
        block_hook = None
    combo_pressed.clear()
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


def registrar_hotkeys():
    keyboard.add_hotkey(cfg["hotkey_pause"], lambda: cmd_queue.put(("PAUSE", None)),
                        suppress=False)


# ---------------- bandeja ----------------
def icono_img():
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
    for key, txt in [("hotkey_unlock", "Desbloquear"), ("hotkey_pause", "Pausar/Reanudar")]:
        row = tk.Frame(win, bg="#1a1a20")
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=txt + ":", width=16, anchor="w", bg="#1a1a20",
                 fg="#9a9aa6", font=("Segoe UI", 9)).pack(side="left")
        v = tk.StringVar(value=cfg[key])
        win.vars[key] = v
        tk.Entry(row, textvariable=v, width=18, bg="#2a2a33", fg="#ffffff",
                 insertbackground="#ffffff", relief="flat").pack(side="left")

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
        save_cfg(cfg)
        detector.lx = cargar_lexico(cfg)
        keyboard.remove_all_hotkeys()
        registrar_hotkeys()
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
    root.after(30, poll)
    root.mainloop()


if __name__ == "__main__":
    main()
