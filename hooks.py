"""Hooks de bajo nivel propios (WH_KEYBOARD_LL / WH_MOUSE_LL) y atajos globales
con RegisterHotKey. Todo crudo con ctypes: la libreria `keyboard` pierde su hook
tras suspender Windows y no lo recupera, ademas de no suprimir bien varias teclas.
Un solo hook persistente hace deteccion Y bloqueo."""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_HOTKEY = 0x0312
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 1, 2, 4, 8, 0x4000
VK_ESCAPE = 0x1B

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                              wintypes.WPARAM, wintypes.LPARAM)

# argtypes explicitos: sin esto ctypes trunca los handles de 64 bits
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                  wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


_ESPECIALES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x13: "pause",
    0x14: "caps lock", 0x1B: "esc", 0x20: "space", 0x21: "page up",
    0x22: "page down", 0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up",
    0x27: "right", 0x28: "down", 0x2C: "print screen", 0x2D: "insert",
    0x2E: "delete", 0x5D: "menu", 0x90: "num lock", 0x91: "scroll lock",
    0xA0: "shift", 0xA1: "shift", 0xA2: "ctrl", 0xA3: "ctrl",
    0xA4: "alt", 0xA5: "alt", 0x10: "shift", 0x11: "ctrl", 0x12: "alt",
    0x5B: "win", 0x5C: "win",
}

MODIFICADORES_VK = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


def vk_a_nombre(vk):
    """Nombre legible de la tecla, estilo 'a', '1', 'f5', 'space', 'ctrl'."""
    if vk in _ESPECIALES:
        return _ESPECIALES[vk]
    if 0x70 <= vk <= 0x87:            # F1..F24
        return "f%d" % (vk - 0x6F)
    if 0x30 <= vk <= 0x39:            # 0-9
        return chr(vk)
    if 0x41 <= vk <= 0x5A:            # A-Z
        return chr(vk).lower()
    if 0x60 <= vk <= 0x69:            # numpad 0-9
        return chr(vk - 0x30)
    if 0x6A <= vk <= 0x6F:            # numpad operadores
        return "num%d" % vk
    return "vk%d" % vk


def combo_a_mods_vk(combo):
    """'ctrl+alt+h' -> (MOD_CONTROL|MOD_ALT, ord('H')). None si no se entiende."""
    mods, vk = 0, None
    for parte in combo.lower().split("+"):
        p = parte.strip()
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "windows"):
            mods |= MOD_WIN
        elif len(p) == 1:
            vk = ord(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x6F + int(p[1:])
        elif p == "esc":
            vk = VK_ESCAPE
    return (mods, vk) if vk else (None, None)


class _LLHook:
    def __init__(self, tipo):
        self.tipo = tipo
        self.hook = None
        self.tid = None
        self._proc = None

    def _cb(self, nCode, wParam, lParam):
        raise NotImplementedError

    def start(self):
        listo = threading.Event()

        def run():
            self._proc = HOOKPROC(self._cb)
            self.hook = user32.SetWindowsHookExW(
                self.tipo, self._proc, kernel32.GetModuleHandleW(None), 0)
            self.tid = kernel32.GetCurrentThreadId()
            listo.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
            if self.hook:
                user32.UnhookWindowsHookEx(self.hook)
                self.hook = None

        threading.Thread(target=run, daemon=True).start()
        listo.wait(2)
        return bool(self.hook)

    def stop(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            self.tid = None

    def vivo(self):
        return bool(self.hook)


class KeyHook(_LLHook):
    """Hook unico y persistente: siempre escucha; bloquea cuando se le pide.

    on_key(nombre, vk, es_down, tiempo) se llama con cada evento.
    Devuelve True desde `bloquear_todo` para tragarse las teclas.
    """

    def __init__(self, on_key):
        super().__init__(WH_KEYBOARD_LL)
        self.on_key = on_key
        self.bloqueando = False

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0:
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            es_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            try:
                self.on_key(vk_a_nombre(info.vkCode), info.vkCode, es_down,
                            info.time / 1000.0)
            except Exception:
                pass
            if self.bloqueando:
                return 1  # se traga la tecla: nada llega a las apps
        return user32.CallNextHookEx(None, nCode, wParam, lParam)


class MouseBlocker(_LLHook):
    """Congela el mouse: bloquea movimiento y clics (el gato juega solo)."""

    def __init__(self):
        super().__init__(WH_MOUSE_LL)

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0:
            return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)


class Hotkeys:
    """Atajos globales con RegisterHotKey (mucho mas confiable que un hook)."""

    def __init__(self):
        self.tid = None
        self.acciones = {}
        self._pendientes = []

    def registrar(self, combo, accion):
        self._pendientes.append((combo, accion))

    def start(self):
        listo = threading.Event()

        def run():
            self.tid = kernel32.GetCurrentThreadId()
            for i, (combo, accion) in enumerate(self._pendientes, start=1):
                mods, vk = combo_a_mods_vk(combo)
                if vk and user32.RegisterHotKey(None, i, mods | MOD_NOREPEAT, vk):
                    self.acciones[i] = accion
            listo.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    accion = self.acciones.get(msg.wParam)
                    if accion:
                        try:
                            accion()
                        except Exception:
                            pass
            for i in self.acciones:
                user32.UnregisterHotKey(None, i)

        threading.Thread(target=run, daemon=True).start()
        listo.wait(2)
        return len(self.acciones)

    def stop(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            self.tid = None
