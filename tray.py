# -*- coding: utf-8 -*-
"""Иконка в системном трее: флаг текущей раскладки, вкл/выкл, настройки,
смена раскладки, автозапуск, выход.

Иконка = флаг языка текущей раскладки (RU — триколор, EN — юнион-джек);
при выключенном исправлении флаг обесцвечен и перечёркнут. Поток poll
обновляет иконку, когда пользователь сам сменил раскладку.
"""

import sys
import threading
import time

import pystray

from flags import flag_image
from fixer import switch_layout
from settings import open_settings


def _menu_guard(log, thunk):
    """Запустить действие пункта меню; любое исключение — в лог.

    Без такой обёртки падение обработчика в потоке pystray убивает
    иконку молча: пользователь видит «в трее ничего не происходит».
    """
    try:
        thunk()
    except Exception:
        if log:
            import traceback

            log("ошибка пункта меню:\n" + traceback.format_exc())


def autostart_cmd():
    """Команда автозапуска: exe от Nuitka, иначе pythonw + скрипт."""
    import os

    if getattr(sys, "frozen", False):          # собранная Nuitka сборка
        exe = os.path.abspath(sys.executable).replace("\\", "\\\\")
        return f'"{exe}"'
    exe = sys.executable
    if not exe.lower().endswith("pythonw.exe"):
        candidate = exe[:-4] + "w.exe"
        if os.path.exists(candidate):
            exe = candidate
    script = os.path.abspath(sys.argv[0]).replace("\\", "\\\\")
    return f'"{exe}" "{script}"'


def set_autostart(enable):
    """Запись/удаление значения в HKCU\\...\\Run (автозапуск для текущего пользователя)."""
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value = "PuntoSwitch"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enable:
                winreg.SetValueEx(key, value, 0, winreg.REG_SZ, autostart_cmd())
            else:
                try:
                    winreg.DeleteValue(key, value)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def autostart_enabled():
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.QueryValueEx(key, "PuntoSwitch")
        return True
    except OSError:
        return False


def run_tray(engine, on_exit, log=None):
    """Блокирующий запуск иконки в трее."""
    menu = pystray.Menu(
        pystray.MenuItem(
            "Включено",
            lambda icon, item: _menu_guard(
                log, lambda: setattr(engine, "enabled", not engine.enabled)
            ),
            checked=lambda item: engine.enabled,
            visible=lambda item: True,
            default=True,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Русская раскладка",
            lambda: _menu_guard(log, lambda: switch_layout("ru")),
        ),
        pystray.MenuItem(
            "Английская раскладка",
            lambda: _menu_guard(log, lambda: switch_layout("en")),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Настройки…",
            lambda icon, item: _menu_guard(
                log, lambda: open_settings(engine, log)
            ),
        ),
        pystray.MenuItem(
            "Автозапуск",
            lambda icon, item: _menu_guard(
                log, lambda: set_autostart(not autostart_enabled())
            ),
            checked=lambda item: autostart_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Выход",
            lambda icon, item: _menu_guard(
                log, lambda: (on_exit(), icon.stop())
            ),
        ),
    )

    def snapshot():
        return (engine.layout, engine.enabled)

    icon = pystray.Icon(
        "PuntoSwitch",
        icon=flag_image(engine.layout, engine.enabled),
        title="Punto Switch — исправление раскладки",
        menu=menu,
    )

    def poll():
        """Перерисовываем флаг, когда сменилась раскладка или вкл/выкл.

        _sync_layout нужен для ручной смены раскладки (Alt+Shift, Win+Space,
        языковая панель): хук перечитывает раскладку только на клавишах,
        а иконка обязана реагировать сама, раз в полсекунды.

        ВАЖНО: поток стартует ДО icon.run(), а icon.visible до запуска
        иконки равно False - нельзя писать 'while icon.visible:' как условие
        входа, такой цикл выходил мгновенно и флаг никогда не обновлялся.
        Сначала ждём появления иконки, потом опрашиваем.
        """
        last = snapshot()
        while not icon.visible:            # ждём icon.run()
            time.sleep(0.2)
        while icon.visible:                # иконка сняли (stop) -> выход
            engine._sync_layout()
            current = snapshot()
            if current != last:
                icon.icon = flag_image(current[0], current[1])
                last = current
            time.sleep(0.4)

    threading.Thread(target=poll, daemon=True).start()
    icon.run()
