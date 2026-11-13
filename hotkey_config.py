# -*- coding: utf-8 -*-
"""Чтение и запись user-friendly настроек config.json.

config.json:
{
  "undo_hotkey": "ctrl+z",               # горячая клавиша отмены исправления
  "switch_hotkey": "ctrl+shift+f",       # ручная смена раскладки последнего слова
  "excluded_apps": ["chrome.exe", ...],  # процессы, где автоисправление выключено
  "log_fixes": true                      # писать ли исправления в локальный лог
}

Файл лежит в %LOCALAPPDATA%\\auto-switch-keyb\\config.json; при первом запуске
заполняется из seed-файла config.json рядом с программой.

Движок получает настройки как callable (см. auto_switch_keyb.py), поэтому
изменения из окна «Настройки» подхватываются без рестарта.
"""

import json
import os

from paths import config_path, resource_path

DEFAULT_CONFIG = {
    "undo_hotkey": "ctrl+z",
    "switch_hotkey": "ctrl+shift+f",
    "excluded_apps": ["logonui.exe", "credentialui.exe"],
    "log_fixes": True,
    "debug": False,       # подробные строки диагностики в log.txt
}

MODIFIER_KEYS = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
}

# разрешённые «базовые» клавиши хоткея отмены
BASE_KEY_NAMES = {
    "z", "x", "v", "b", "n", "m", "j", "k", "l", "h", "g", "f", "d", "s", "a",
    "q", "w", "e", "r", "t", "y", "u", "i", "o", "p",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}


def parse_hotkey(text):
    """Строка вида 'ctrl+z' -> (frozenset модификаторов, базовая клавиша).

    Возвращает None, если строка некорректна.
    """
    if not text:
        return None
    parts = [p.strip().lower() for p in text.replace("+", " ").split()]
    mods = set()
    base = None
    for p in parts:
        if p in MODIFIER_KEYS:
            mods.add(MODIFIER_KEYS[p])
        elif p in BASE_KEY_NAMES:
            base = p
        else:
            return None
    if base is None:
        return None
    if not mods:
        # одиночная клавиша-буква небезопасна (печатала бы текст) —
        # разрешаем только F1..F12
        if not base.startswith("f"):
            return None
    return frozenset(mods), base


def format_hotkey(spec):
    """(mods, base) -> 'Ctrl+Z' (для отображения)."""
    mods, base = spec
    return "+".join(sorted(mods) + [base.upper()])


def load_config():
    """dict настроек; при отсутствии/битом файле — значения по умолчанию."""
    path = config_path()
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        seed = resource_path("config.json")
        if os.path.exists(seed):
            try:
                with open(seed, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                data = {}
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config(cfg):
    """Запись настроек; True при успехе. Объединяем с уже записанными
    ключами (в т.ч. отладочными), чтобы ничего не затирать."""
    payload = load_config()
    payload.update(cfg)
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
