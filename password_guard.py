# -*- coding: utf-8 -*-
"""Определение «фокус стоит в поле пароля/авторизации» — такие поля
исправлению не подлежат ни при каких настройках.

Защищаем содержимое пароля: движок не должен стирать и перепечатывать
(и тем более переключать раскладку) то, что пользователь печатает в
скрытом поле, — иначе пароль уходит в приложение «не той» раскладкой
или показывается на экране.

Два уровня проверки (вызываются ТОЛЬКО в момент предполагаемого
исправления, не на каждой клавише — проверка небыстрая):

1. UI Automation: IUIAutomation::GetFocusedElement -> CurrentIsPassword.
   Покрывает браузеры (Chromium, Gecko), Electron, WPF, WinUI — весь
   современный UI. Нужен пакет comtypes (чистый python); если его нет
   или UIA недоступен — переходим к уровню 2.
2. Нативные edit-контролы: фокус чужого потока читаем через
   GetGUIThreadInfo (hwndFocus), затем стиль ES_PASSWORD у класса
   edit-семейства. Микросекунды, без COM и без AttachThreadInput —
   тот вплетает очереди ввода и при отсоединении переносит фокус
   (исправления улетали в чужое окно).

Любая ошибка -> False (исправление разрешено): guard не имеет права
ломать основную функцию программы.
"""

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.oledll.ole32

CLSID_CUIAutomation = "{ff48dba4-60ef-4201-aa87-54103eef594e}"

ES_PASSWORD = 0x0020
GWL_STYLE = -16

# классы edit-семейства: стиль ES_PASSWORD осмыслен только у них
# (у кнопок и прочих бит 0x20 занят другими флагами)
EDIT_CLASSES = {
    "edit", "tedit", "richedit", "richedit20a", "richedit20w",
    "richedit50w", "ttntedit", "tntedit.unicodeclass",
}


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


kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetFocus.restype = wintypes.HWND
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND

_uia = None
_uia_failed = False
_uia_lock = threading.Lock()


def _focused_hwnd():
    """HWND контрола в фокусе ввода, включая фокус чужого потока.

    GetGUIThreadInfo только читает состояние потока переднего окна
    (hwndFocus) и НЕ трогает очереди ввода. Раньше здесь был
    AttachThreadInput + GetFocus: вплетение очереди нашего потока в
    очередь окна при отсоединении переносило фокус ввода в другое окно —
    из-за этого исправление печаталось не туда и фокус «уходил к мыши».
    """
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    tid_fg = user32.GetWindowThreadProcessId(hwnd, None)
    if not tid_fg:
        return None
    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid_fg, ctypes.byref(gti)):
        return None
    return gti.hwndFocus or gti.hwndActive or None


def _native_is_password():
    """Уровень 2: edit-контрол со стилем ES_PASSWORD."""
    try:
        hfocus = _focused_hwnd()
        if not hfocus:
            return False
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hfocus, buf, 64)
        if buf.value.lower() not in EDIT_CLASSES:
            return False
        style = user32.GetWindowLongW(hfocus, GWL_STYLE)
        return bool(style & ES_PASSWORD)
    except Exception:
        return False


def _uia_is_password():
    """Уровень 1: UI Automation IsPassword у сфокусированного элемента."""
    global _uia, _uia_failed
    if _uia_failed:
        return False
    with _uia_lock:
        try:
            if _uia is None:
                import comtypes.client
                mod = comtypes.client.GetModule("UIAutomationCore.dll")
                _uia = comtypes.client.CreateObject(
                    CLSID_CUIAutomation, interface=mod.IUIAutomation
                )
            el = _uia.GetFocusedElement()
            if el is None:
                return False
            return bool(el.CurrentIsPassword)
        except Exception:
            # comtypes нет, tlb не разобрался, UIA недоступен и т. д. —
            # больше не пытаемся, работает нативный уровень
            _uia_failed = True
            return False


def focused_is_password():
    """True, если фокус ввода стоит в поле пароля (не исправлять)."""
    return _uia_is_password() or _native_is_password()
