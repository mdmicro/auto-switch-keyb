# -*- coding: utf-8 -*-
"""Иконки-флаги раскладки для системного трея (рисуем PIL, без картинок).

ru  -> бело-сине-красный триколор (Россия)
en  -> юнион-джек (Великобритания, условный «английский» флаг QWERTY)
когда исправление выключено -> тот же флаг, но обесцвеченный и перечёркнутый.
"""

from PIL import Image, ImageDraw

SIZE = (44, 28)

# полосы триколора: белый, синий, красный
RU_STRIPES = [
    (255, 255, 255, 255),
    (0, 51, 153, 255),
    (204, 31, 45, 255),
]

EN_BLUE = (1, 33, 105, 255)
EN_RED = (200, 16, 46, 255)
EN_WHITE = (255, 255, 255, 255)


def _flag_ru(size):
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    stripe = h // 3
    for i, color in enumerate(RU_STRIPES):
        top = i * stripe
        bottom = (i + 1) * stripe if i < 2 else h
        draw.rectangle((0, top, w - 1, bottom - 1), fill=color)
    draw.rectangle((0, 0, w - 1, h - 1), outline=(90, 90, 90, 255), width=1)
    return img


def _flag_en(size):
    w, h = size
    img = Image.new("RGBA", size, EN_BLUE)
    draw = ImageDraw.Draw(img)
    # белые диагонали
    draw.line((0, 0, w, h), fill=EN_WHITE, width=max(2, h // 7))
    draw.line((w, 0, 0, h), fill=EN_WHITE, width=max(2, h // 7))
    # красные диагонали
    draw.line((0, 0, w, h), fill=EN_RED, width=max(1, h // 16))
    draw.line((w, 0, 0, h), fill=EN_RED, width=max(1, h // 16))
    # белый крест + красный крест
    mid_x, mid_y = w // 2, h // 2
    band = max(2, h // 6)
    draw.rectangle((mid_x - band, 0, mid_x + band, h), fill=EN_WHITE)
    draw.rectangle((0, mid_y - band, w, mid_y + band), fill=EN_WHITE)
    red = max(1, h // 12)
    draw.rectangle((mid_x - red, 0, mid_x + red, h), fill=EN_RED)
    draw.rectangle((0, mid_y - red, w, mid_y + red), fill=EN_RED)
    draw.rectangle((0, 0, w - 1, h - 1), outline=(90, 90, 90, 255), width=1)
    return img


def flag_image(layout, enabled=True):
    """Иконка флага текущей раскладки. layout: 'ru' | 'en' | None.

    enabled=False -> обесцвеченный флаг с перечёркиванием.
    """
    img = _flag_ru(SIZE) if layout == "ru" else _flag_en(SIZE)
    if not enabled:
        gray = img.convert("L").convert("RGBA")
        img = gray
        draw = ImageDraw.Draw(img)
        w, h = SIZE
        draw.line((0, h // 2, w, h // 2), fill=(220, 40, 40, 255), width=5)
    return img
