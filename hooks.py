"""Hooks de bajo nivel (WH_KEYBOARD_LL / WH_MOUSE_LL) para bloquear TODO
de verdad: la libreria `keyboard` no suprime bien la tecla Windows ni varias
F-keys, asi que aqui se hace crudo con ctypes."""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105

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
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


def _vk_norm(vk):
    if vk in (0x11, 0xA2, 0xA3):
        return "ctrl"
    if vk in (0x12, 0xA4, 0xA5):
        return "alt"
    if vk in (0x10, 0xA0, 0xA1):
        return "shift"
    if vk in (0x5B, 0x5C):
        return "win"
    if 0x30 <= vk <= 0x5A:
        return chr(vk).lower()
    return str(vk)


class _LLHook:
    def __init__(self, tipo):
        self.tipo = tipo
        self.hook = None
        self.tid = None
        self._proc = None
        self.thread = None

    def _cb(self, nCode, wParam, lParam):
        raise NotImplementedError

    def start(self):
        def run():
            self._proc = HOOKPROC(self._cb)
            hmod = kernel32.GetModuleHandleW(None)
            self.hook = user32.SetWindowsHookExW(self.tipo, self._proc, hmod, 0)
            self.tid = kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
            if self.hook:
                user32.UnhookWindowsHookEx(self.hook)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
            self.tid = None


class KeyBlocker(_LLHook):
    """Bloquea absolutamente todas las teclas menos la combo de desbloqueo."""

    def __init__(self, combo, on_unlock):
        super().__init__(WH_KEYBOARD_LL)
        self.combo = {p.strip().lower() for p in combo.split("+")}
        self.on_unlock = on_unlock
        self.pressed = set()

    def start(self):
        self.pressed.clear()
        super().start()

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0:
            vk = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            name = _vk_norm(vk)
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self.pressed.add(name)
                # Esc = salida de emergencia, o la combo de desbloqueo
                if vk == 0x1B or (self.combo and self.combo.issubset(self.pressed)):
                    self.on_unlock()
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                self.pressed.discard(name)
            return 1  # bloquea la tecla
        return user32.CallNextHookEx(None, nCode, wParam, lParam)


class MouseBlocker(_LLHook):
    """Congela el mouse: bloquea movimiento y clics (el gato juega solo)."""

    def __init__(self):
        super().__init__(WH_MOUSE_LL)

    def _cb(self, nCode, wParam, lParam):
        if nCode == 0:
            return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
