# -*- coding: utf-8 -*-
"""Соответствие символов раскладок RU (ЙЦУКЕН) и EN (QWERTY).

Соответствие по физическим клавишам: одна и та же клавиша на клавиатуре
печатает латинскую и кириллическую букву. «Зеркалом» английского слова
называется то, что набралось бы на русской раскладке, и наоборот.
"""

# физическая клавиша QWERTY -> русская буква
KEY_TO_RU = {
    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н", "u": "г",
    "i": "ш", "o": "щ", "p": "з", "[": "х", "]": "ъ", "\\": "ё",
    "a": "ф", "s": "ы", "d": "в", "f": "а", "g": "п", "h": "р", "j": "о",
    "k": "л", "l": "д", ";": "ж", "'": "э",
    "z": "я", "x": "ч", "c": "с", "v": "м", "b": "и", "n": "т", "m": "ь",
    ",": "б", ".": "ю",
}

EN_TO_RU = dict(KEY_TO_RU)
RU_TO_EN = {v: k for k, v in KEY_TO_RU.items()}
RU_TO_EN["`"] = "ё"
EN_TO_RU["ё"] = "`"

LAYOUT_RU = "ru"
LAYOUT_EN = "en"


def convert(word, layout):
    """«Зеркало» слова: слово набрано в layout -> что вышло бы в другой раскладке.

    Буквы конвертируются по таблице клавиш, прочие символы (.,-') сохраняются.
    """
    table = RU_TO_EN if layout == LAYOUT_RU else EN_TO_RU
    return "".join(table.get(ch, ch) for ch in word.lower())


def lang_of_chars(word):
    """Определяем язык слова по символам: 'ru', 'en' или None."""
    has_cyr = any("а" <= c <= "я" or c == "ё" for c in word.lower())
    has_lat = any("a" <= c <= "z" for c in word.lower())
    if has_cyr and not has_lat:
        return LAYOUT_RU
    if has_lat and not has_cyr:
        return LAYOUT_EN
    return None
