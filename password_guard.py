# -*- coding: utf-8 -*-
"""Защита полей пароля/авторизации и чтение «что реально лежит у каретки».

Поля пароля исправлению не подлежат ни при каких настройках: движок не
должен стирать и перепечатывать (и тем более переключать раскладку) то,
что пользователь печатает в скрытом поле, — иначе пароль уходит в
приложение «не той» раскладкой или показывается на экране.

Вторяя задача: перед заменой слова движок спрашивает, какой текст стоит
ПЕРЕД кареткой. Стереть нужно ровно то, что там лежит: слепого
«len(набранного слова) Backspace'ов» не хватает там, где приложение
печатает символы, которых движок не видел (автозакрытые скобки и
кавычки, автокоррект, автодополнение) — из-за этого начало слова
оставалось в старой раскладке, а зеркало печаталось рядом.

Два уровня проверки пароля (вызываются ТОЛЬКО в момент предполагаемого
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

ВСЕ функции живут в колбэке WH_KEYBOARD_LL, а UIA — межпроцессный COM.
Windows не ждёт колбэк дольше LowLevelHooksTimeout и просто снимает хук,
поэтому:
  * в консольные окна (cmd, conhost, PowerShell, Windows Terminal) UIA не
    спрашиваем вообще — поля пароля там нет, а UIA-обход UWP-терминала
    самый долгий (и TextPattern там всё равно не отдаётся);
  * состояние поля пароля помним для контрола фокуса;
  * текст у каретки перечитываем не чаще TEXT_TTL.
"""

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.oledll.ole32

CLSID_CUIAutomation = "{ff48dba4-60ef-4201-aa87-54103eef594e}"

ES_PASSWORD = 0x0020
GWL_STYLE = -16

# UIA: паттерн текста и константы для чтения «что стоит у каретки»
UIA_TextPatternId = 10009
UIA_Endpoint_Start = 0        # начало диапазона
TEXTUNIT_CHARACTER = 0        # единица «символ» для MoveEndpointByUnit

# классы edit-семейства: стиль ES_PASSWORD осмыслен только у них
# (у кнопок и прочих бит 0x20 занят другими флагами)
EDIT_CLASSES = {
    "edit", "tedit", "richedit", "richedit20a", "richedit20w",
    "richedit50w", "ttntedit", "tntedit.unicodeclass",
}

# Консольные окна (проверено на этой машине): conhost классического cmd и
# PowerShell — ConsoleWindowClass; Windows Terminal — Cascadia... и контрол
# ввода Windows.UI.Input.InputSite.WindowClass.
CONSOLE_WINDOW_CLASSES = {
    "consolewindowclass",
    "pseudoconsole",
    "cascadia_hosting_window_class",
    "cascadiaconhost",
    "cascadiaconhostcontent",
    "cascadiapane",
    "windows.ui.input.inputsite.windowclass",
    "vtterm",
}

# как часто перечитывать текст у каретки (сек)
TEXT_TTL = 0.35
# сколько записей хранить в кэше поля пароля
PW_CACHE_MAX = 64


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
_uia_mod = None
_uia_failed = False
_uia_lock = threading.Lock()
_pw_cache = {}
_text_cache = {}


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


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, buf, 64)
    return buf.value.lower()


def focused_window_classes():
    """(класс переднего окна, класс контрола в фокусе ввода), '' если нет."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""
        win_cls = _class_name(hwnd)
        focus_cls = ""
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        if tid:
            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
                focus_cls = _class_name(gti.hwndFocus)
        return win_cls, focus_cls
    except Exception:
        return "", ""


def is_console_window():
    """True, если фокус стоит в консольном/терминальном окне (cmd, conhost,
    PowerShell, Windows Terminal): там нет поля пароля и нет UIA-текста."""
    win_cls, focus_cls = focused_window_classes()
    return win_cls in CONSOLE_WINDOW_CLASSES or focus_cls in CONSOLE_WINDOW_CLASSES


def _uia_ready():
    """Инстанс UIA (один на процесс) ИЛИ None. Не бросает исключений."""
    global _uia, _uia_mod, _uia_failed
    if _uia_failed:
        return None
    with _uia_lock:
        try:
            if _uia is None:
                import comtypes.client
                _uia_mod = comtypes.client.GetModule("UIAutomationCore.dll")
                _uia = comtypes.client.CreateObject(
                    CLSID_CUIAutomation, interface=_uia_mod.IUIAutomation
                )
            return _uia
        except Exception:
            # comtypes нет, tlb не разобрался, UIA недоступен и т. д. —
            # больше не пытаемся, работает нативный уровень
            _uia_failed = True
            return None


def _native_is_password():
    """Уровень 2: edit-контрол со стилем ES_PASSWORD."""
    try:
        hfocus = _focused_hwnd()
        if not hfocus:
            return False
        if _class_name(hfocus) not in EDIT_CLASSES:
            return False
        style = user32.GetWindowLongW(hfocus, GWL_STYLE)
        return bool(style & ES_PASSWORD)
    except Exception:
        return False


def _uia_is_password():
    """Уровень 1: UI Automation IsPassword у сфокусированного элемента."""
    uia = _uia_ready()
    if uia is None:
        return False
    with _uia_lock:
        try:
            el = uia.GetFocusedElement()
            if el is None:
                return False
            return bool(el.CurrentIsPassword)
        except Exception:
            return False


def focused_is_password():
    """True, если фокус ввода стоит в поле пароля (не исправлять)."""
    # консоль: поля пароля там нет, а UIA-запрос из хука в терминале —
    # самый дорогой и самый рискованный (хук снимают по таймауту)
    if is_console_window():
        return False
    hfocus = _focused_hwnd()
    key = hfocus or user32.GetForegroundWindow()
    if key:
        cached = _pw_cache.get(key)
        if cached is not None:
            return cached
    result = _uia_is_password() or _native_is_password()
    if key:
        if len(_pw_cache) >= PW_CACHE_MAX:
            _pw_cache.clear()
        _pw_cache[key] = result
    return result


def focused_text_before_caret(n):
    """Текст перед кареткой (до n символов) ИЛИ None, если прочитать нельзя.

    Только чтение UIA (очереди ввода не трогает). В консольных окнах
    TextPattern нет -> вернёт None, и решение о стирании принимает движок.
    """
    if is_console_window():
        return None
    now = time.time()
    hfocus = _focused_hwnd()
    key = (hfocus, n)
    cached = _text_cache.get(key)
    if cached is not None and now - cached[0] < TEXT_TTL:
        return cached[1]
    text = None
    uia = _uia_ready()
    if uia is not None:
        with _uia_lock:
            try:
                el = uia.GetFocusedElement()
                if el is not None:
                    raw = el.GetCurrentPattern(UIA_TextPatternId)
                    if raw:
                        pat = raw.QueryInterface(_uia_mod.IUIAutomationTextPattern)
                        rng = pat.GetCaretRange()
                        if rng is not None:
                            # начало диапазона каретки на -n символов назад:
                            # MoveEndpointByUnit(Endpoint, Unit, Count), а НЕ
                            # MoveEndpoint — у него другой контракт
                            # (переставить конец в чужой диапазон)
                            rng.MoveEndpointByUnit(UIA_Endpoint_Start,
                                                   TEXTUNIT_CHARACTER, -n)
                            text = rng.GetText(-1)
            except Exception:
                text = None
    if len(_text_cache) >= PW_CACHE_MAX:
        _text_cache.clear()
    _text_cache[key] = (now, text)
    return text
