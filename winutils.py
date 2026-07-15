import ctypes
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process

user32 = ctypes.windll.user32


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


_PRI_LANG = {0x09: "en", 0x0A: "es", 0x0C: "fr", 0x07: "de", 0x10: "it",
             0x16: "pt", 0x11: "ja", 0x12: "ko", 0x04: "zh", 0x19: "ru"}


def idiomas_teclado():
    """Idiomas de teclado instalados por el usuario, ej. ['es','en','ja']."""
    try:
        n = user32.GetKeyboardLayoutList(0, None)
        arr = (ctypes.c_void_p * n)()
        user32.GetKeyboardLayoutList(n, arr)
        out = []
        for h in arr:
            pri = (h & 0xFFFF) & 0x3FF
            code = _PRI_LANG.get(pri)
            if code and code not in out:
                out.append(code)
        return out or ["en"]
    except Exception:
        return ["en"]


kernel32 = ctypes.windll.kernel32


def _exe_de_pid(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def _es_pantalla_completa(hwnd):
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        if r - l >= sw and b - t >= sh:
            if win32gui.GetClassName(hwnd) in ("Progman", "WorkerW"):
                return False  # es el escritorio, no una app
            return True
    except Exception:
        pass
    return False


def app_frontal():
    """(exe_en_minusculas, pantalla_completa) de la ventana activa."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return _exe_de_pid(pid), _es_pantalla_completa(hwnd)
    except Exception:
        return "", False


def hay_campo_texto():
    """True si la ventana activa tiene un caret (campo editable enfocado)."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return bool(info.hwndCaret)
    except Exception:
        pass
    return True  # ante la duda, asumimos que si (para no botar de mas)


class _ACCESS(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD)]


class STICKYKEYS(_ACCESS):
    pass


class FILTERKEYS(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD),
        ("iWaitMSec", wintypes.DWORD), ("iDelayMSec", wintypes.DWORD),
        ("iRepeatMSec", wintypes.DWORD), ("iBounceMSec", wintypes.DWORD),
    ]


def _apaga(struct_cls, get_action, set_action, on_flag):
    s = struct_cls()
    s.cbSize = ctypes.sizeof(s)
    if user32.SystemParametersInfoW(get_action, s.cbSize, ctypes.byref(s), 0):
        if s.dwFlags & on_flag:
            s.dwFlags &= ~on_flag
            user32.SystemParametersInfoW(set_action, s.cbSize, ctypes.byref(s), 2)


def reset_teclado():
    """Suelta modificadores atorados y apaga los modos raros que activa el gato."""
    # soltar cualquier modificador logico que quedo presionado
    for vk in (win32con.VK_LSHIFT, win32con.VK_RSHIFT, win32con.VK_LCONTROL,
               win32con.VK_RCONTROL, win32con.VK_LMENU, win32con.VK_RMENU,
               win32con.VK_LWIN, win32con.VK_RWIN, win32con.VK_SHIFT,
               win32con.VK_CONTROL, win32con.VK_MENU):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    # apagar CapsLock si quedo prendido
    if win32api.GetKeyState(win32con.VK_CAPITAL) & 1:
        win32api.keybd_event(win32con.VK_CAPITAL, 0, 0, 0)
        win32api.keybd_event(win32con.VK_CAPITAL, 0, win32con.KEYEVENTF_KEYUP, 0)

    # StickyKeys (0x003B get / 0x003B set = SPI_GETSTICKYKEYS/SETSTICKYKEYS)
    _apaga(STICKYKEYS, 0x003B, 0x003C, 0x00000001)   # SKF_STICKYKEYSON
    _apaga(FILTERKEYS, 0x0033, 0x0034, 0x00000001)   # FKF_FILTERKEYSON
    _apaga(STICKYKEYS, 0x0035, 0x0036, 0x00000001)   # TKF_TOGGLEKEYSON (mismo layout)
