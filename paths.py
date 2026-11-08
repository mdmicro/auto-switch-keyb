# -*- coding: utf-8 -*-
"""Пути к данным: одинаково для `python punto_switch.py` и для EXE от Nuitka.

Словари (words/*.json) ищутся в первом найденном месте: рядом с exe
(для onefile-сборки это временный каталог распаковки), рядом с исходником,
в текущей папке.

config.json всегда в %LOCALAPPDATA%\\punto_switch\\config.json: для
onefile-сборки каталог exe временный, настройки там не переживут перезапуск.
"""

import os
import sys


def _candidate_dirs():
    dirs = []
    try:
        dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    dirs.append(os.getcwd())
    seen, uniq = set(), []
    for d in dirs:
        d = os.path.abspath(d)
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def resource_path(name):
    """Путь к файлу данных проекта (words/words_ru.json, config.json...)."""
    for base in _candidate_dirs():
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return cand
    return os.path.join(_candidate_dirs()[0], name)


def app_data_dir():
    """Постоянный каталог программы: логи и настройки."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "punto_switch")
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(app_data_dir(), "config.json")
