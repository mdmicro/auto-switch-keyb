# -*- coding: utf-8 -*-
"""Юнит-тест движка: разбор слова, решение о замене, дебаунс, «съедание»
терминатора, стирание «слово + хвост», ручная смена раскладки слова.

Реальный SendInput не проверяем (в безголовом окружении пачки не доходят
до окон) — функции ввода подменены записывающими заглушками.
"""

import ctypes
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
    engine.release_modifiers = lambda: None   # в юнит-тесте клавиши не шлём
    log = Recorder()
    e = SwitchEngine({}, lambda m: log(m))
    e.layout = "en"
    e.intent = "en"
    # экран в тесте не читается (заглушка): движок действует вслепую.
    # Режим стирания фиксируем моком: тест не должен зависеть от того,
    # какое окно реально находится в фокусе во время запуска теста
    e._screen_tail = lambda word: None
    e._word_at_caret = lambda: None
    e._erase_mode = lambda: "word"
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
    e5._apply_fix(("ghbdtn", "привет", "en", "ru", None, " ", None))
    print("replace calls:", rec_replace.events)
    print("layout calls:", rec_layout.events)
    # пробел на исправлении «съеден» хуком -> на экране хвоста нет; текст
    # экрана в тесте не читается -> стирание по режиму контрола ('word')
    assert ("ghbdtn", "привет", None, " ", "word", None, "") in rec_replace.events, \
        "замена вызвана (терминатор съеден -> хвоста нет)"
    assert ("ru",) in rec_layout.events, "раскладка сменена"
    e5._fix_logs.get_nowait()

    # 5b. без реальной смены раскладки switch_layout не вызывается
    rec_replace.events.clear()
    rec_layout.events.clear()
    e5b, _ = make_engine(rec_replace, rec_layout)
    e5b._apply_fix(("xyz", "abc", "en", "en", None, " ", None))
    assert rec_layout.events == [], "лишний switch_layout не дёргается"

    # 5c. ручная смена раскладки последнего слова: словарное print -> зкште
    # (зеркало по физическим клавишам; в отличие от автоисправления,
    #  трогается и настоящее слово - пользователь просит руками)
    e5c, _ = make_engine(rec_replace, rec_layout)
    e5c._last_word = "print"
    e5c._last_word_tail = " "
    e5c._typed_after_word = 0
    assert e5c._switch_last_word_layout() is True, "print -> зкште руками"
    # стирается «слово + пробел» (6 Backspace'ов), зеркало печатается с пробелом
    assert ("print", "зкште", None, None, "count", 6, " ") in rec_replace.events, \
        "стерто слово вместе с хвостом"
    assert ("ru",) in rec_layout.events[-1:], "раскладка переключена"
    assert e5c.layout == "ru" and e5c._last_word == "зкште"

    # 5c2. хвост, который приложение добавило само (автозакрытая скобка):
    # стираем «слово + хвост» и печатаем хвост обратно - слово заменяется
    # ЦЕЛИКОМ, начало старой раскладки не остаётся
    rec_replace.events.clear()
    e5c2, _ = make_engine(rec_replace, rec_layout)
    e5c2._last_word = "print"
    e5c2._last_word_tail = None
    e5c2._screen_tail = lambda word: "()"
    assert e5c2._switch_last_word_layout() is True
    assert ("print", "зкште", None, None, "count", 7, "()") in rec_replace.events, \
        "хвост автодополнения стирается и возвращается"

    # 5d. после слова что-то напечатали -> ручная смена отказ
    e5d, _ = make_engine(rec_replace, rec_layout)
    e5d._last_word = "print"
    e5d._last_word_tail = " "
    e5d._typed_after_word = 2
    assert e5d._switch_last_word_layout() is False, "не последнее слово - отказ"

    # 5e. слова нет -> отказ; смешанное слово -> отказ
    e5e, _ = make_engine(rec_replace, rec_layout)
    assert e5e._switch_last_word_layout() is False, "нет слова - отказ"
    e5e._last_word = "abcдеф"
    e5e._last_word_tail = " "
    assert e5e._switch_last_word_layout() is False, "смешанное - отказ"

    # 5e2. у каретки нет нашего слова (поле с автодополнением) -> отказ
    e5e2, _ = make_engine(rec_replace, rec_layout)
    e5e2._last_word = "print"
    e5e2._last_word_tail = " "
    e5e2._screen_tail = lambda word: False
    assert e5e2._switch_last_word_layout() is False, "у каретки нет слова - отказ"
    rec_replace.events.clear()
    e5e3, _ = make_engine(rec_replace, rec_layout)
    e5e3.word = list("ghbdtn")
    e5e3._screen_tail = lambda word: False
    assert e5e3._finish_word(terminator_char=" ") is None, "автоисправление тоже отказ"
    assert rec_replace.events == [], "ничего не стёрто"

    # 5f. смена раскладки отменяется как обычное исправление (_undo_last_fix)
    rec_replace.events.clear()
    rec_layout.events.clear()
    e5f, _ = make_engine(rec_replace, rec_layout)
    e5f._last_word = "print"
    e5f._last_word_tail = " "
    assert e5f._switch_last_word_layout() is True
    assert e5f._undo_last_fix() is True, "смена откатывается хоткеем отмены"
    assert e5f.layout == "en", "раскладка возвращена при откате"
    assert ("зкште", "print", None, None, "count", 6, " ") in rec_replace.events, \
        "откат стирает зеркало с хвостом"

    # 5g. исправление закончили Enter -> откат хоткеем не делается
    # (Enter в консоли исполняет команду, стереть перевод строки посимвольно
    #  надёжно нельзя)
    rec_replace.events.clear()
    e5g, _ = make_engine(rec_replace, rec_layout)
    e5g.word = list("ghbdtn")
    action = e5g._finish_word(terminator_vk=0x0D)
    assert action is not None
    e5g._apply_fix(action)
    assert e5g._undo_last_fix() is False, "после Enter откат не делается"

    # 5h. хвост печатного терминатора: пробел ушёл в приложение, и пачка
    # стирает слово ВМЕСТЕ с ним, а не только слово (иначе первый Backspace
    # съедает пробел и на экране остается половина старой раскладки)
    rec_replace.events.clear()
    e5h, _ = make_engine(rec_replace, rec_layout)
    e5h._last_word = "print"
    e5h._last_word_tail = " "
    assert e5h._switch_last_word_layout() is True
    mode_count = rec_replace.events[-1]
    assert mode_count[5] == len("print") + 1, "стираем слово + пробел"

    # 6. Съедание терминатора: keydown пробела с исправлением -> return 1
    e6, _ = make_engine(rec_replace, rec_layout)
    # исключения фиксируем моком: тест не должен зависеть от того, какое
    # окно находится в фокусе во время запуска теста
    e6.config = {"excluded_apps": set()}
    e6._app_cache.clear()
    e6.word = list("ghbdtn")
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

    # 7. Слово из текста перед кареткой (ручная смена, когда слово не
    # закончено пробелом)
    e7, _ = make_engine(rec_replace, rec_layout)
    e7._screen_tail = lambda word: ""
    e7._word_at_caret = lambda: ("print", "")
    rec_replace.events.clear()
    assert e7._switch_last_word_layout() is True, "слово перед кареткой меняется"
    assert rec_replace.events[-1][5] == len("print"), "хвоста нет -> стираем слово"

    print("ENGINE TEST: PASS")


if __name__ == "__main__":
    main()
