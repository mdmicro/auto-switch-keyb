# -*- coding: utf-8 -*-
"""E2E-проверка замены слова на РЕАЛЬНОМ контроле ввода.

Своё окно с контролом (текст читаем WM_GETTEXT: UIA TextPattern в консоли и
в Notepad 11 не отдаёт текст), шлём клавиши SendInput, вызываем
fixer.replace_last_word так, как делает движок, и сравниваем текст на экране.

Два контрола:
  EDIT        — нативный edit (Notepad 11, Delphi TEdit): Ctrl+Backspace НЕ
                понимает (печатает \x7f), стираем только точным числом
                Backspace'ов -> режим 'count';
  RICHEDIT50W — RichEdit (Word-подобные, поля офис/мессенджеров): понимает
                Ctrl+Backspace -> режим 'word'.
Фокус проверяем перед КАЖДЫМ посылом: не наш фокус — клавиши не шлём.
"""
import ctypes
import time
from ctypes import wintypes

import fixer

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_CREATE, WM_DESTROY = 1, 2
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
EM_SETSEL, EM_REPLACESEL = 0x00B1, 0x00C2
WS_CHILD, WS_VISIBLE = 0x40000000, 0x10000000
WS_OVERLAPPEDWINDOW, WS_EX_TOPMOST = 0xCF0000, 0x00000008
ES_AUTOHSCROLL, SW_SHOW, SWP_SHOWWINDOW = 0x0080, 5, 0x0040
HWND_TOPMOST, PM_REMOVE, OCR_NORMAL, WHITE_BRUSH = -1, 1, 32512, 0

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, ctypes.c_uint,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hBackground", wintypes.HBRUSH),
        ("hMenu", wintypes.HMENU), ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


for _f, _r, _a in (
    ("DefWindowProcW", ctypes.c_long, (wintypes.HWND, ctypes.c_uint,
                                       wintypes.WPARAM, wintypes.LPARAM)),
    ("CreateWindowExW", wintypes.HWND, (wintypes.DWORD, wintypes.LPCWSTR,
                                        wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                        wintypes.HINSTANCE, wintypes.LPVOID)),
    ("SetWindowPos", wintypes.BOOL, (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     wintypes.UINT)),
    ("ShowWindow", wintypes.BOOL, (wintypes.HWND, ctypes.c_int)),
    ("SetForegroundWindow", wintypes.BOOL, (wintypes.HWND,)),
    ("SetFocus", wintypes.HWND, (wintypes.HWND,)),
    ("SendMessageW", ctypes.c_long, (wintypes.HWND, ctypes.c_uint,
                                     wintypes.WPARAM, ctypes.c_void_p)),
    ("PostMessageW", wintypes.BOOL, (wintypes.HWND, ctypes.c_uint,
                                     wintypes.WPARAM, wintypes.LPARAM)),
    ("PeekMessageW", wintypes.BOOL, (ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                     wintypes.UINT, wintypes.UINT, wintypes.UINT)),
    ("TranslateMessage", ctypes.c_int, (ctypes.POINTER(wintypes.MSG),)),
    ("DispatchMessageW", ctypes.c_long, (ctypes.POINTER(wintypes.MSG),)),
    ("LoadCursorW", ctypes.c_void_p, (wintypes.HINSTANCE, ctypes.c_void_p)),
    ("GetGUIThreadInfo", wintypes.BOOL, (wintypes.UINT,
                                         ctypes.POINTER(GUITHREADINFO))),
    ("GetForegroundWindow", wintypes.HWND, ()),
    ("GetWindowThreadProcessId", wintypes.UINT,
     (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))),
    ("RegisterClassW", wintypes.ATOM, (ctypes.POINTER(WNDCLASS),)),
):
    getattr(user32, _f).restype = _r
    getattr(user32, _f).argtypes = _a
gdi32.GetStockObject.restype = ctypes.c_void_p
gdi32.GetStockObject.argtypes = (ctypes.c_int,)
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.LoadLibraryW.restype = wintypes.HMODULE
kernel32.LoadLibraryW.argtypes = (wintypes.LPCWSTR,)
user32.GetClassInfoW.restype = wintypes.BOOL
user32.GetClassInfoW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR,
                                  ctypes.POINTER(WNDCLASS))

_keep = []                                  # callback/структуры живы весь тест
_windows = {}                               # hwnd -> (hwnd контрола, класс)
_current = [None]
_stop = [False]


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_CREATE:
        cls = _current[0]
        _windows[hwnd] = (user32.CreateWindowExW(
            0, cls, "", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
            10, 10, 640, 60, hwnd, None, None, None), cls)
        return 0
    if msg == WM_DESTROY:
        _stop[0] = True
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def pump(seconds):
    end = time.time() + seconds
    msg = wintypes.MSG()
    while time.time() < end and not _stop[0]:
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        else:
            time.sleep(0.01)


def open_window(cls, tag):
    """Окно с контролом класса cls, поднятое в передний план. -> (hwnd, edit)"""
    _current[0] = cls
    name = "ProbeWin" + cls.replace("W", "")
    cb = WNDPROC(_wndproc)
    wc = WNDCLASS()
    _keep.extend((cb, wc))
    wc.lpfnWndProc = cb
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.hCursor = user32.LoadCursorW(None, OCR_NORMAL)
    wc.hBackground = gdi32.GetStockObject(WHITE_BRUSH)
    wc.lpszClassName = name
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise ctypes.WinError()
    hwnd = user32.CreateWindowExW(WS_EX_TOPMOST, name, "probe " + tag,
                                  WS_OVERLAPPEDWINDOW, 60, 60, 740, 170,
                                  None, None, None, None)
    if not hwnd:
        raise ctypes.WinError()
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 60, 60, 740, 170, SWP_SHOWWINDOW)
    pump(0.6)
    edit = _windows[hwnd][0]
    if not edit:
        raise ctypes.WinError()
    user32.SetFocus(edit)
    user32.SetForegroundWindow(hwnd)
    pump(0.6)
    return hwnd, edit


def focus_is_ours(hwnd, edit):
    """Клавиши шлём ТОЛЬКО когда фокус реально у нашего контрола."""
    top = user32.GetForegroundWindow()
    if top != hwnd:
        return False
    tid = user32.GetWindowThreadProcessId(top, None)
    g = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    return bool(user32.GetGUIThreadInfo(tid, ctypes.byref(g))
                and g.hwndFocus == edit)


def get_text(edit):
    n = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(edit, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p))
    return buf.value


def clear(edit):
    user32.SendMessageW(edit, EM_SETSEL, 0, -1)
    empty = ctypes.create_unicode_buffer(1)
    user32.SendMessageW(edit, EM_REPLACESEL, 1, ctypes.cast(empty, ctypes.c_void_p))


def run_case(tag, typed, call, expected):
    hwnd, edit = _current_window[0]
    if not focus_is_ours(hwnd, edit):
        print("%-36s ПРОПУСК: фокус не у нашего окна (клавиши не шлём)" % tag)
        return False
    clear(edit)
    pump(0.2)
    fixer.send_text(typed)
    pump(0.8)
    before = get_text(edit)
    call()
    pump(1.2)
    after = get_text(edit)
    ok = after == expected
    print("%-36s before=%r after=%r  %s" %
          (tag, before, after, "OK" if ok else "FAIL (want %r)" % expected))
    return ok


_current_window = [None]


def richedit_available():
    """Класс RICHEDIT50W появляется только после загрузки MSFTEDIT.DLL."""
    h = kernel32.LoadLibraryW("MSFTEDIT.DLL")
    if not h:
        return False
    wc = WNDCLASS()
    return bool(user32.GetClassInfoW(None, "RICHEDIT50W", ctypes.byref(wc)))


def main():
    results = []

    # ---------------- нативный EDIT: режим 'count' ----------------
    _current_window[0] = open_window("EDIT", "edit")
    if not focus_is_ours(*_current_window[0]):
        print("нет доступа к фокусу — тест прерван (клавиши не шлются)")
        return 1

    # 1. РЕГРЕССИЯ багa: стереть ровно len(слова), хвост не трогать ->
    #    первый Backspace съедает пробел, слово стёрто с конца, осталась
    #    начальная буква старой раскладки: «pзкште»
    results.append(run_case(
        "edit  old bug: erase len(word)",
        "print ",
        lambda: fixer.replace_last_word("print", "зкште", None, None,
                                        "count", 5, ""),
        "pзкште"))

    # 2. Исправление: стереть «слово + хвост», хвост вернуть на место
    results.append(run_case(
        "edit  fix: erase word + tail",
        "print ",
        lambda: fixer.replace_last_word("print", "зкште", None, None,
                                        "count", 6, " "),
        "зкште "))

    # 3. Терминатор «съеден» хуком: на экране только слово, пробел печатает
    #    сама пачка
    results.append(run_case(
        "edit  eaten terminator",
        "print",
        lambda: fixer.replace_last_word("print", "зкште", 0x20, None,
                                        "count", 5, ""),
        "зкште "))

    # 4. Слово русской раскладки -> зеркало латиницей
    results.append(run_case(
        "edit  ru word -> latin mirror",
        "привет ",
        lambda: fixer.replace_last_word("привет", "ghbdtn", None, None,
                                        "count", 7, " "),
        "ghbdtn "))

    # 5. Нативный edit Ctrl+Backspace НЕ понимает (печатает \x7f) —
    #    поэтому движок в нём всегда стирает числом Backspace'ов
    results.append(run_case(
        "edit  tail from screen (auto-paren)",
        "print(",
        lambda: fixer.replace_last_word("print", "зкште", None, None,
                                        "count", 7, "("),
        "зкште("))

    # ---------------- RichEdit: режим 'word' (Ctrl+Backspace) ----------
    if richedit_available():
        _current_window[0] = open_window("RICHEDIT50W", "rich")
    else:
        print("RichEdit недоступен — тесты режима 'word' пропущены")
    if richedit_available() and focus_is_ours(*_current_window[0]):
        results.append(run_case(
            "rich  word mode: Ctrl+Backspace",
            "print ",
            lambda: fixer.replace_last_word("print", "зкште", None, None,
                                            "word", None, " "),
            "зкште "))
        results.append(run_case(
            "rich  word mode + auto-paren tail",
            "print(",
            lambda: fixer.replace_last_word("print", "зкште", None, None,
                                            "word", None, "("),
            "зкште("))
    else:
        print("rich-тест пропущен: фокус не у нашего окна")

    for hwnd in list(_windows):
        user32.PostMessageW(hwnd, WM_DESTROY, 0, 0)
    pump(0.4)
    print("E2E EDIT TEST:", "PASS" if all(results) else "FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
