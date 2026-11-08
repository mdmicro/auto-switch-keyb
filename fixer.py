# -*- coding: utf-8 -*-
"""Вмешательство во ввод: печать исправленного слова и смена раскладки.

Исправление слова (replace_last_word): SendInput шлёт ОДНОЙ атомарной
пачкой N раз VK_BACK (стираем набранное слово), текст исправленного слова
через KEYEVENTF_UNICODE (VK_PACKET) и клавишу-терминатор (пробел/Enter),
которую хук «съел», чтобы пачка заняла ровно то место на экране, где
лежало набранное слово.

Все наши события помечаются magic-значением в dwExtraInfo: хук из engine.py
узнаёт их и игнорирует, чтобы не исправлять собственный вывод.

Смена раскладки: PostMessage(WM_INPUTLANGCHANGEREQUEST) фокусному окну.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_CONTROL = 0x11

WM_INPUTLANGCHANGEREQUEST = 0x0050

LANG_RU_LCID = 0x00000419
LANG_EN_LCID = 0x00000409
LAYOUT_LCIDS = {"ru": LANG_RU_LCID, "en": LANG_EN_LCID}

# опознавательный номер наших SendInput-событий
INJECTED_MAGIC = 0x50535731  # "PSW1"


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDUNION(ctypes.Union):
    """Union как в WinAPI: MOUSEINPUT — самый большой член.
    От него зависит sizeof(INPUT)==40 на x64; если union меньше,
    SendInput отбивает ошибку 87 и не отправляет ни одного события."""
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", KEYBDUNION),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.PostMessageW.argtypes = (
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)
user32.PostMessageW.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = ()


def _key_input(vk, scan, flags):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = scan
    inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = ctypes.cast(
        ctypes.c_void_p(INJECTED_MAGIC), ctypes.POINTER(ctypes.c_ulong)
    )
    return inp


def _send(inputs):
    n = len(inputs)
    if not n:
        return 0
    arr = (INPUT * n)(*inputs)
    return user32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _unicode_pair(text):
    inputs = []
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            continue
        inputs.append(_key_input(0, code, KEYEVENTF_UNICODE))
        inputs.append(_key_input(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    return inputs


def send_text(text):
    """Напечатать текст через KEYEVENTF_UNICODE (раскладка не важна)."""
    _send(_unicode_pair(text))


def send_backspaces(count):
    """Стереть count последних символов."""
    inputs = []
    for _ in range(count):
        inputs.append(_key_input(VK_BACK, 0, 0))
        inputs.append(_key_input(VK_BACK, 0, KEYEVENTF_KEYUP))
    _send(inputs)


def replace_last_word(old_word, new_word, terminator_vk=None, terminator_char=None):
    """Заменить последнее набранное слово на экране ОДНОЙ атомарной пачкой:

        N раз Backspace  ->  new_word  ->  терминатор

    Хук «съедает» клавишу-терминатор (пробел/Enter/Tab), когда отправляет
    слово на исправление, и передаёт её сюда: пачка дописывает терминатор
    сама. Так пачка встает ровно на место слова, а всё, что пользователь
    успел набрать, придёт строго после пачки.

    terminator_vk  -- код клавиши (VK_RETURN, VK_TAB), если терминатор —
                      служебная клавиша;
    terminator_char -- символ (пробел, запятая...), печатается Unicode-парой.
    """
    if not old_word:
        return
    inputs = []
    for _ in range(len(old_word)):
        inputs.append(_key_input(VK_BACK, 0, 0))
        inputs.append(_key_input(VK_BACK, 0, KEYEVENTF_KEYUP))
    inputs.extend(_unicode_pair(new_word))
    if terminator_vk is not None:
        inputs.append(_key_input(terminator_vk, 0, 0))
        inputs.append(_key_input(terminator_vk, 0, KEYEVENTF_KEYUP))
    elif terminator_char is not None:
        inputs.extend(_unicode_pair(terminator_char))
    _send(inputs)


def switch_layout(layout):
    """Сменить раскладку фокусного окна. layout: 'ru' | 'en'."""
    lcid = LAYOUT_LCIDS.get(layout)
    if lcid is None:
        return
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return
    user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, lcid)
