# -*- coding: utf-8 -*-
"""Построение компактных словарей для Punto Switch.

Вход (сырые списки слов, лежат в ./words):
    words/ru_raw.txt  -- danakt/russian-words: все морфологические формы,
                         ~1.5 млн строк, кодировка cp1251
    words/en_raw.txt  -- dwyl/english-words (words_alpha.txt), ~4.2 млн слов

Выход:
    words/words_ru.json  -- русские слова (нижний регистр, только кириллица, ё -> е)
    words/words_en.json  -- английские слова (нижний регистр, только a-z)

Частотной статистики в этих списках нет, поэтому «популярность» слова
оцениваем эвристикой длины: короткие слова встречаются в речи заметно чаще.
Берём N самых коротких уникальных слов -- этого хватает, чтобы распознавать
практически любой текст, набранный «в не той раскладке».
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
WORDS_DIR = os.path.join(HERE, "words")

RU_RAW = os.path.join(WORDS_DIR, "ru_raw.txt")
EN_RAW = os.path.join(WORDS_DIR, "en_raw.txt")
RU_OUT = os.path.join(WORDS_DIR, "words_ru.json")
EN_OUT = os.path.join(WORDS_DIR, "words_en.json")

RU_LIMIT = 260_000
EN_LIMIT = 170_000
MIN_LEN = 2
MAX_LEN = 20

RU_RE = re.compile(r"^[а-яё]+$", re.UNICODE)
EN_RE = re.compile(r"^[a-z]+$")


def build_ru():
    """Собираем русские слова из списка всех морфологических форм."""
    seen = set()
    with open(RU_RAW, "rb") as fh:
        data = fh.read().decode("cp1251", errors="ignore")
    for line in data.splitlines():
        w = line.strip().strip(".,:;!?\"'()").lower().replace("ё", "е")
        if not (MIN_LEN <= len(w) <= MAX_LEN):
            continue
        if not RU_RE.match(w):
            continue
        seen.add(w)
    # короткие формы -> «частые»; сортировка (длина, слово) детерминирована
    words = sorted(seen, key=lambda w: (len(w), w))[:RU_LIMIT]
    with open(RU_OUT, "w", encoding="utf-8") as fh:
        json.dump(words, fh, ensure_ascii=False)
    return len(words)


def build_en():
    """Собираем английские слова из words_alpha.txt."""
    seen = set()
    with open(EN_RAW, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            w = line.strip().lower()
            if not (MIN_LEN <= len(w) <= MAX_LEN):
                continue
            if not EN_RE.match(w):
                continue
            seen.add(w)
    words = sorted(seen, key=lambda w: (len(w), w))[:EN_LIMIT]
    with open(EN_OUT, "w", encoding="utf-8") as fh:
        json.dump(words, fh, ensure_ascii=False)
    return len(words)


def main():
    for path in (RU_RAW, EN_RAW):
        if not os.path.exists(path):
            raise SystemExit(
                f"Нет входного файла {path}.\n"
                "Скачайте:\n"
                "  ru: https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt -> words/ru_raw.txt\n"
                "  en: https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt -> words/en_raw.txt"
            )
    ru = build_ru()
    en = build_en()
    print(f"words_ru.json: {ru} слов")
    print(f"words_en.json: {en} слов")
    print("Готово. Теперь: py -3.10 punto_switch.py")


if __name__ == "__main__":
    main()
