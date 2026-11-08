# -*- coding: utf-8 -*-
"""Словари и эвристика «слово набрано не в той раскладке»."""

import json
import os

from layout_map import LAYOUT_EN, LAYOUT_RU, convert, lang_of_chars
from paths import resource_path

# минимальная длина слова, которую вообще рассматриваем
MIN_WORD_LEN = 3


class WordDicts:
    """Загружает words_ru.json / words_en.json в множество для O(1) проверок."""

    def __init__(self):
        self.ru = self._load("words_ru.json")
        self.en = self._load("words_en.json")

    @staticmethod
    def _load(name):
        # путь ищем через paths.resource_path: работает и в исходниках,
        # и в Nuitka EXE (словари лежат рядом с exe)
        path = resource_path(os.path.join("words", name))
        if not os.path.exists(path):
            raise SystemExit(
                f"Нет словаря {path}. Сначала выполните: py -3.10 build_words.py"
            )
        with open(path, "r", encoding="utf-8") as fh:
            return set(json.load(fh))

    def has(self, word, layout):
        w = word.lower().replace("ё", "е")
        if layout == LAYOUT_RU:
            return w in self.ru
        return w in self.en


def score_word(word, layout, dicts):
    """Оценка «осмысленности» слова при предполагаемой раскладке набора layout."""
    lang = lang_of_chars(word)
    s = 0.0
    if lang and dicts.has(word, lang):
        s += 2.0                      # слово есть в словаре своего письма
        if lang == layout:
            s += 0.5                 # и язык совпадает с раскладкой набора
    return s


def decide(word, layout, intent_layout, dicts):
    """Анализ завершённого слова.

    word          -- набранный текст слова (как появилось на экране)
    layout        -- активная раскладка в момент набора
    intent_layout -- раскладка, которую пользователь выбрал сам (Ctrl+Shift),
                     или None, если он раскладку не переключал

    Возвращает dict:
        {"fixed": str|None, "layout": str|None, "score": float}
        fixed  -- чем заменить слово (None = не трогать)
        layout -- раскладка, к которой надо переключиться после исправления
    """
    typed = word.lower()
    if len(typed) < MIN_WORD_LEN:
        return {"fixed": None, "layout": None, "score": 0.0}

    typed_lang = lang_of_chars(typed)
    if typed_lang is None:
        return {"fixed": None, "layout": None, "score": 0.0}  # смешанное слово

    mirror = convert(typed, typed_lang)
    if mirror == typed:
        return {"fixed": None, "layout": None, "score": 0.0}

    typed_ok = dicts.has(typed, typed_lang)
    mirror_lang = LAYOUT_EN if typed_lang == LAYOUT_RU else LAYOUT_RU
    mirror_ok = dicts.has(mirror, mirror_lang)

    if not mirror_ok:
        return {"fixed": None, "layout": None, "score": 0.0}
    if typed_ok:
        # набранное слово тоже настоящее -> не вмешиваемся
        return {"fixed": None, "layout": None, "score": 0.0}

    # зеркало — настоящее слово, набранное — нет: исправляем
    score = 2.0
    if typed_lang == intent_layout:
        # пользователь сам выбрал раскладку, в которой вышло «мусорное» слово;
        # всё равно зеркало сильнее, т.к. оно словарьно
        score += 0.5
    if layout == mirror_lang:
        score += 0.5

    fixed = apply_case(word, mirror)
    return {"fixed": fixed, "layout": mirror_lang, "score": score}


def apply_case(original, fixed_lower):
    """Переносим регистр оригинала на исправленное слово.

    ALL CAPS -> ALL CAPS; First -> first... сохраним шаблон заглавных букв.
    """
    out = []
    for i, ch in enumerate(fixed_lower):
        if i < len(original) and original[i].isupper():
            out.append(ch.upper())
        else:
            out.append(ch)
    return "".join(out)
