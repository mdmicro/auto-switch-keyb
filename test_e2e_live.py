# -*- coding: utf-8 -*-
"""Живая E2E-проверка хоткеев через НАСТОЯЩЕЕ приложение.

В отличие от test_e2e_edit.py (там replace_last_word вызывает сам тест),
здесь работает запущенная копия программы: её глобальный хук WH_KEYBOARD_LL
видит наш ввод и сам исполняет замену. Проверяется весь путь целиком:

    печать слова -> хук движка -> хоткей (или автоисправление)
    -> движок стирает «слово + хвост» и печатает результат -> экран.

Требование: запущена ОДНА копия приложения (значок-флаг в трее), и за
машиной в этот момент никто не работает.

Клавиши шлются КАК ПОЛЬЗОВАТЕЛЬСКИЕ: без dwExtraInfo-магии INJECTED_MAGIC
(собственные пачки движка помечены магией и хуком игнорируются), и перед
КАЖДЫМ посылом проверяется фокус — не наш клавиши не шлются.

Контролы: EDIT (Notepad-подобный, режим стирания 'count') и RICHEDIT50W
(офис/мессенджер-подобный, режим 'word' = Ctrl+Backspace).
"""
import ctypes
import time
from ctypes import wintypes

import fixer
from hotkey_config import load_config, parse_hotkey
from test_e2e_edit import (
    clear, focus_is_ours, get_text, open_window, pump, richedit_available,
    _windows,
)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

VK_CONTROL, VK_SHIFT, VK_MENU = 0x11, 0x10, 0x12
VK_BACK, KEYUP = 0x08, 0x0002
KEYEVENTF_UNICODE = 0x0004
INJECTED_MAGIC = fixer.INJECTED_MAGIC


SINGLE_INSTANCE_MUTEX = "Local\\AutoSwitchKeyb.single.instance"
ERROR_ALREADY_EXISTS = 183

kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = ()
user32.GetWindowThreadProcessId.restype = wintypes.UINT
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)


def app_running():
    """Запущена ли копия приложения: по мьютексу единственного экземпляра.

    CreateMutex возвращает существующий мьютекс с ERROR_ALREADY_EXISTS, если
    его создал другой процесс, — значит приложение работает и его хук
    слышит наш ввод. Перечисление процессов (Toolhelp32) здесь не годится:
    на части машин отдаёт ERROR_BAD_LENGTH, а имя процесса в onefile-сборке
    не отличить от бутстрапа.
    """
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS and bool(handle)


def _key(vk, scan=0, flags=0):
    """Клавиша БЕЗ magic-метки: движок должен увидеть её как пользовательскую."""
    inp = fixer.INPUT()
    inp.type = fixer.INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = scan
    inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = ctypes.cast(ctypes.c_void_p(0),
                                           ctypes.POINTER(ctypes.c_ulong))
    return inp


def type_plain(text):
    """Напечатать текст как пользователь (KEYEVENTF_UNICODE, без магии)."""
    inputs = []
    for ch in text:
        inputs.append(_key(0, ord(ch), KEYEVENTF_UNICODE))
        inputs.append(_key(0, ord(ch), KEYEVENTF_UNICODE | KEYUP))
    return fixer._send(inputs)


def press(mods, vk):
    """Нажать комбинацию как реальные клавиши (модификаторы — ванильные VK)."""
    inputs = []
    for mod in mods:
        inputs.append(_key(mod))
    inputs.append(_key(vk))
    inputs.append(_key(vk, 0, KEYUP))
    for mod in reversed(mods):
        inputs.append(_key(mod, 0, KEYUP))
    return fixer._send(inputs)


def base_vk(base):
    """'z' -> 0x5A, 'f1' -> 0x70 (та же логика, что в engine._base_to_vk)."""
    b = base.lower()
    if len(b) == 1:
        return ord(b.upper())
    if b.startswith("f") and b[1:].isdigit():
        n = int(b[1:])
        if 1 <= n <= 12:
            return 0x70 + (n - 1)
    return None


def hotkey(spec):
    """'Ctrl+Shift+f1' -> ([VK_SHIFT, VK_CONTROL], vk) (порядок: Shift, Ctrl)."""
    mods, base = parse_hotkey(spec)
    vk = base_vk(base)
    order = []
    if "Shift" in mods:
        order.append(VK_SHIFT)
    if "Ctrl" in mods:
        order.append(VK_CONTROL)
    if "Alt" in mods:
        order.append(VK_MENU)
    return order, vk


def layout_of_foreground():
    """Раскладка фокусного окна: 'ru' | 'en' | None (как читает движок)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    hkl = user32.GetKeyboardLayout(tid) or user32.GetKeyboardLayout(0)
    if not hkl:
        return None
    lcid = hkl & 0xFFFF
    return {0x0419: "ru", 0x0409: "en"}.get(lcid)


results = []


def case(tag, typed, keys, expected, expected_layout=None):
    """Один сценарий: напечатать, послать клавиши, сверить экран и раскладку.

    keys -- список (mods, vk) для поссылки хоткеев (пусто = без хоткеев).
    """
    hwnd, edit = CURRENT[0]
    if not focus_is_ours(hwnd, edit):
        print("%-40s ПРОПУСК: фокус не у нашего окна (клавиши не шлём)" % tag)
        results.append(False)
        return
    clear(edit)
    pump(0.25)
    type_plain(typed)
    pump(1.0)
    before = get_text(edit)
    for mods, vk in keys:
        press(mods, vk)
        pump(1.1)
    after = get_text(edit)
    layout = layout_of_foreground()
    ok = after == expected and (expected_layout is None or layout == expected_layout)
    print("%-40s before=%r after=%r layout=%r  %s" %
          (tag, before, after, layout, "OK" if ok else
           "FAIL (want %r / layout %r)" % (expected, expected_layout)))
    results.append(ok)


CURRENT = [None]


def run_suite(cls):
    CURRENT[0] = open_window(cls, cls)
    hwnd, edit = CURRENT[0]
    if not focus_is_ours(hwnd, edit):
        print("%s: нет доступа к фокусу — сюита пропущена" % cls)
        return
    tag = "EDIT" if cls == "EDIT" else "RICH"
    sw_mods, sw_vk = hotkey(CONFIG["switch_hotkey"])
    un_mods, un_vk = hotkey(CONFIG["undo_hotkey"])

    # 1. Ручная смена раскладки словарного слова (EN -> RU) + хвост-пробел
    fixer.switch_layout("en")
    pump(0.5)
    case("%s  Ctrl+Shift hotkey: print -> зеркало" % tag,
         "print ", [(sw_mods, sw_vk)], "зкште ", "ru")

    # 2. Откат хоткеем отмены: зеркало -> исходное слово, раскладка назад
    case("%s  undo hotkey: зеркало -> print" % tag,
         "print ", [(sw_mods, sw_vk), (un_mods, un_vk)], "print ", "en")

    # 3. Ручная смена в русскую раскладку (RU -> EN)
    fixer.switch_layout("ru")
    pump(0.5)
    case("%s  Ctrl+Shift hotkey: привет -> ghbdtn" % tag,
         "привет ", [(sw_mods, sw_vk)], "ghbdtn ", "en")

    # 4. Автоисправление: ghbdtn + пробел (пробел хук съедает, пачка его
    #    печатает) -> 'привет ', раскладка ru
    fixer.switch_layout("en")
    pump(0.5)
    case("%s  autofix: ghbdtn -> привет" % tag,
         "ghbdtn ", [], "привет ", "ru")

    # 5. Автоисправление в русскую сторону, затем откат
    fixer.switch_layout("en")
    pump(0.5)
    case("%s  autofix + undo hotkey" % tag,
         "ghbdtn ", [(un_mods, un_vk)], "ghbdtn ", "en")

    # 6. Слово, которое автокорректор не трогает, меняется руками: 5 символов
    fixer.switch_layout("en")
    pump(0.5)
    case("%s  hotkey on word w/o comma-space tail" % tag,
         "world ", [(sw_mods, sw_vk)], "цщкдв ", "ru")


def main():
    global CONFIG
    CONFIG = load_config()
    if not app_running():
        print("ЖИВОЙ ТЕСТ ПРЕРВАН: приложение не запущено "
              "(нужна одна копия: dist\\auto-switch-keyb.exe)")
        return 1
    print("приложение запущено (мьютекс единственного экземпляра занят)")
    for key in ("switch_hotkey", "undo_hotkey"):
        if parse_hotkey(CONFIG.get(key, "")) is None:
            print("ЖИВОЙ ТЕСТ ПРЕРВАН: в config.json некорректный", key)
            return 1
    print("хоткеи:", CONFIG["switch_hotkey"], "/", CONFIG["undo_hotkey"])

    run_suite("EDIT")
    if richedit_available():
        run_suite("RICHEDIT50W")
    else:
        print("RichEdit недоступен — его сюита пропущена")

    for hwnd in list(_windows):
        user32.PostMessageW(hwnd, 0x0002, 0, 0)      # WM_DESTROY
    pump(0.5)
    print("E2E LIVE TEST:", "PASS" if all(results) and results else "FAIL")
    return 0 if all(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
