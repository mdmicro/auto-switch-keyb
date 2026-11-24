# -*- coding: utf-8 -*-
"""Auto Switch Keyb — аналог Punto Switcher на Python для Windows 10.

Исправляет слова, набранные «в не той раскладке» (русская <-> английская),
и сам переключает раскладку на язык результата. Работает в фоне, иконка в
системном трее — флаг текущей раскладки.

Запуск:      py -3.10 auto_switch_keyb.py   (pythonw.exe — без консоли)
Словари:     py -3.10 build_words.py      (один раз, до первого запуска)
Сборка EXE:  powershell -File build_exe.ps1

Модули:
    engine.py        глобальный клавиатурный хук + распознавание
    corrector.py     словари и эвристика «зеркального» слова
    layout_map.py    соответствие клавиш RU/EN
    fixer.py         SendInput: замена слова и смена раскладки
    tray.py          иконка в трее, автозапуск
    settings.py      окно «Настройки»: хоткей отмены, исключения приложений
    hotkey_config.py чтение/запись config.json
    paths.py         пути к данным (исходники / Nuitka EXE)
    flags.py         иконки-флаги раскладок
"""

import ctypes
import sys
import time

from engine import SwitchEngine
from hotkey_config import load_config
from paths import app_data_dir
from tray import run_tray
from version import __version__, APP_NAME

MAX_LOG_BYTES = 512 * 1024
LOG_ENABLED_KEY = "log_fixes"

# Одна копия программы на сессию. Две запущенные копии означают ДВА
# глобальных хука WH_KEYBOARD_LL на одном вводе: обе стирают и печатают
# последнее слово, вторая печатает «поверх» результата первой — на экране
# получается смесь раскладок. Именованный мьютекс на процесс-сеанс.
SINGLE_INSTANCE_MUTEX = "Local\\AutoSwitchKeyb.single.instance"


def acquire_single_instance():
    """True, если это первый запуск. Уже запущенный экземпляр — False."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
    if not handle:
        return True                     # мьютекс не создали — не мешаем запуску
    ERROR_ALREADY_EXISTS = 183
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def current_log_enabled():
    try:
        return bool(load_config().get(LOG_ENABLED_KEY, True))
    except Exception:
        return True


def logger(message, force=False):
    """Строчка лога с отметкой времени; локальный файл, автоповорот.

    Логи пишутся ТОЛЬКО в %LOCALAPPDATA%\\auto-switch-keyb\\log.txt. Приложение
    не содержит сетевых вызовов: ни один символ, набранный пользователем,
    не покидает машину.

    По умолчанию запись отключается галочкой «Писать исправления в лог»
    (log_fixes=false). force=True — служебные строки без пользовательского
    текста (запуск/остановка с версией): пишутся всегда, иначе по логу
    нельзя понять, какая версия вообще работала.
    """
    if not force and not current_log_enabled():
        return
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n"
    try:
        path = app_data_dir()
        log_path = f"{path}\\log.txt"
        import os

        if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_BYTES:
            os.replace(log_path, log_path + ".1")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def main():
    if not acquire_single_instance():
        # вторая копия: её хук удвоил бы чужие исправления (см. выше)
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"{APP_NAME} уже запущен (смотрите значок-флаг в трее).\n"
                "Запустите вторую копию нельзя: два экземпляра исправляют "
                "одно слово дважды, и на экране появляется смесь раскладок.",
                APP_NAME, 0x30,
            )
        except Exception:
            pass
        return
    # настройки передаём движку как callable: изменения из окна «Настройки»
    # подхватываются без рестарта (рабочий поток перечитывает config.json)
    engine = SwitchEngine(load_config, logger)
    engine.start()

    def on_exit():
        engine.stop()
        logger("остановка", force=True)

    logger(f"запуск v{__version__}", force=True)
    try:
        # служебная строка без пользовательского текста: размеры словарей
        # подтверждают, что встроенные/внешние словари реально загрузились
        d = engine.dicts
        logger(f"словари: ru={len(d.ru)} en={len(d.en)}", force=True)
    except Exception:
        pass
    try:
        run_tray(engine, on_exit, log=logger)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
