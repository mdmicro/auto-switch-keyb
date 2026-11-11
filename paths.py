# -*- coding: utf-8 -*-
"""Пути к данным: одинаково для `python auto_switch_keyb.py` и для EXE от Nuitka.

Словари (words/*.json) ищутся в первом найденном месте: рядом с exe
(для onefile-сборки это временный каталог распаковки), рядом с исходником,
в текущей папке.

config.json всегда в %LOCALAPPDATA%\\auto-switch-keyb\\config.json: для
onefile-сборки каталог exe временный, настройки там не переживут перезапуск.
"""

import os
import shutil
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
    """Путь к файлу данных проекта (words/words_ru.json, config.json...).

    Порядок поиска: каталог exe (в onefile-сборке это место, откуда
    запущен exe — внешние файлы имеют приоритет), каталог модулей
    (в onefile-сборке это временный каталог распаковки, куда Nuitka
    кладёт встроенные данные --include-data-files), текущий каталог.
    """
    for base in _candidate_dirs():
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return cand
    return os.path.join(_candidate_dirs()[0], name)


def app_data_dir():
    """Каталог программы: логи и настройки.

    Раньше папка называлась punto_switch - при переименовании проекта
    переносим config.json из старой папки, чтобы настройки не «обнулились».
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "auto-switch-keyb")
    old = os.path.join(base, "punto_switch")
    if not os.path.exists(d) and os.path.isdir(old):
        os.makedirs(d, exist_ok=True)
        for name in ("config.json", "log.txt"):
            src, dst = os.path.join(old, name), os.path.join(d, name)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(app_data_dir(), "config.json")
