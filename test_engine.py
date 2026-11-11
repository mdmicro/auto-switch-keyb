# -*- coding: utf-8 -*-
"""Юнит-тест движка: разбор слова, решение о замене, дебаунс, «съедание» терминатора.

Реальный SendInput не проверяем (в безголовом окружении пачки не доходят
до окон) — функции ввода подменены записывающими заглушками.
"""

import time

import engine
import fixer
from engine import SwitchEngine


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, *args):
        self.events.append(args)


def make_engine(rec_replace, rec_layout):
    engine.replace_last_word = rec_replace
    engine.switch_layout = rec_layout
    log = Recorder()
    e = SwitchEngine({}, lambda m: log(m))
    e.layout = "en"
    e.intent = "en"
    return e, log


def main():
    rec_replace, rec_layout = Recorder(), Recorder()

    # 1. ghbdtn (набрано в en, зеркало «привет») -> действие на исправление
    e, _ = make_engine(rec_replace, rec_layout)
    e.word = list("ghbdtn")
    action = e._finish_word(terminator_char=" ")
    print("action:", action)
    assert (action and action[0] == "ghbdtn" and action[1] == "привет"
            and action[2] == "en" and action[3] == "ru"), "ghbdtn -> привет"

    # 2. Настоящее английское слово print не исправляется
    e2, _ = make_engine(rec_replace, rec_layout)
    e2.word = list("print")
    assert e2._finish_word(terminator_char=" ") is None, "print не исправляется"

    # 3. Короткое слово игнорируется
    e3, _ = make_engine(rec_replace, rec_layout)
    e3.word = list("ab")
    assert e3._finish_word(terminator_char=" ") is None, "ab игнорируется"

    # 4. Дебаунс: второе исправление сразу после первого
    e4, _ = make_engine(rec_replace, rec_layout)
    e4.word = list("ghbdtn")
    assert e4._finish_word(terminator_char=" ") is not None
    e4.word = list("cbvf")
    assert e4._finish_word(terminator_char=" ") is None, "дебаунс работает"

    # 5. _apply_fix вызывает замену и смену раскладки
    e5, log5 = make_engine(rec_replace, rec_layout)
    e5._running = True
    e5._apply_fix(("ghbdtn", "привет", "en", "ru", None, " "))
    print("replace calls:", rec_replace.events)
    print("layout calls:", rec_layout.events)
    assert ("ghbdtn", "привет", None, " ") in rec_replace.events, "замена вызвана"
    assert ("ru",) in rec_layout.events, "раскладка сменена"
    e5._fix_logs.get_nowait()

    # 5b. без реальной смены раскладки switch_layout не вызывается
    rec_replace.events.clear()
    rec_layout.events.clear()
    e5b, _ = make_engine(rec_replace, rec_layout)
    e5b._apply_fix(("xyz", "abc", "en", "en", None, " "))
    assert rec_layout.events == [], "лишний switch_layout не дёргается"

    # 6. Съедание терминатора: keydown пробела с исправлением -> return 1
    e6, _ = make_engine(rec_replace, rec_layout)
    # foreground-окном в тестовой сессии является консоль (pwsh) — она по
    # умолчанию в исключениях, отключаем исключения для этого теста
    e6.config = {"excluded_apps": set()}
    e6._app_cache.clear()
    e6.word = list("ghbdtn")
    import ctypes
    from engine import KBDLLHOOKSTRUCT, WM_KEYDOWN

    kb = KBDLLHOOKSTRUCT()
    kb.vkCode = 0xE7            # VK_PACKET: символ лежит в scanCode
    kb.scanCode = ord(" ")
    kb.flags = 0x10             # INJECTED, extra=0 (не наш magic)
    lparam = ctypes.pointer(kb)   # колбэк хука получает POINTER(KBDLLHOOKSTRUCT)
    orig_pass = engine.SwitchEngine._pass
    engine.SwitchEngine._pass = staticmethod(lambda n, m, l: 0)
    res = e6._on_key(0, WM_KEYDOWN, lparam)
    engine.SwitchEngine._pass = orig_pass
    while not e6._fix_logs.empty():
        print("hook log:", e6._fix_logs.get_nowait())
    print("space keydown result:", res, "swallow:", e6._swallow_vk)
    assert res == 1 and e6._swallow_vk == 0xE7, "пробел съеден"

    print("ENGINE TEST: PASS")


if __name__ == "__main__":
    main()
