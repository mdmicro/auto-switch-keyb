# -*- coding: utf-8 -*-
"""Быстрая проверка словарей и зеркальных преобразований."""

from corrector import WordDicts, decide
from layout_map import convert

d = WordDicts()
print("ru words:", len(d.ru), " en words:", len(d.en))

# пара (набранное, раскладка набора)
pairs = [
    ("привет", "ru"),   # зеркало ghbdtn
    ("ghbdtn", "en"),    # зеркало привет
    ("набор", "ru"),
    ("bdfyonm", "en"),
    ("print", "en"),
    ("ываф", "ru"),
    ("weq", "en"),
    ("cbvf", "en"),      # зеркало «один» -> печатался как cbvf
    ("ывпшдф", "ru"),
]

for w, lay in pairs:
    m = convert(w, lay)
    r = decide(w, lay, None, d)
    print(w, lay, "-> mirror", m,
          "in ru:", d.has(m, "ru"),
          "in en:", d.has(m, "en"),
          "| fixed:", repr(r["fixed"]), "layout:", r["layout"])

# регистр
from corrector import apply_case

print("apply_case:", apply_case("Ghbdtn", "привет"), apply_case("GHBDTN", "привет"))
