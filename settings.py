# -*- coding: utf-8 -*-
"""Окно «Настройки» (Tkinter): горячая клавиша отмены и список исключаемых
приложений. Окно немодальное, открывается из меню трея в отдельном потоке,
сохраняет config.json и немедленно применяет настройки к движку.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from hotkey_config import (
    DEFAULT_CONFIG,
    format_hotkey,
    load_config,
    parse_hotkey,
    save_config,
)
from version import __version__

MODIFIER_OPTIONS = ["Ctrl", "Shift", "Alt"]
BASE_KEYS = (
    list("abcdefghijklmnopqrstuvwxyz")
    + [str(i) for i in range(10)]
    + [f"f{i}" for i in range(1, 13)]
)


def open_settings(engine, log=None, on_ready=None):
    """Открыть окно настроек неблокирующим потоком.

    engine.refresh_now() вызывается после сохранения, чтобы движок подхватил
    настройки без рестарта. Любое падение окна логируется, а не рушит
    поток меню иконки. on_ready(root) вызывается в потоке окна после
    построения интерфейса (для тестов: опрос виджетов потокобезопасен
    только изнутри потока Tk).
    """

    def target():
        try:
            _run_window(engine, log, on_ready)
        except Exception:
            if log:
                import traceback

                log("ошибка окна настроек:\n" + traceback.format_exc())

    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def _run_window(engine, log, on_ready=None):
    cfg = load_config()
    hotkey_text = tk.Tk()
    hotkey_text.withdraw()
    # ВАЖНО: все tk-переменные этого окна создаются с master=hotkey_text.
    # Без master BooleanVar/StringVar привязываются к глобальному
    # tk._default_root - интерпретатору ПЕРВОГО когда-либо окна. После его
    # закрытия такой интерпретатор мёртв: при повторном открытии .set()
    # писал бы в мёртвый интерпретатор, и поля нового окна оставались бы
    # пустыми (значения из config.json «не подгружались»).

    root = tk.Toplevel(hotkey_text)
    root.title(f"Auto Switch Keyb {__version__} — настройки")
    # Высота с запасом: содержимое требует ~530 px (плюс pady), при жёстком
    # размере меньше требуемого Tkinter сжимает фреймы, и нижняя панель
    # кнопок («Сохранить и применить») схлопывалась в 1 px и исчезала.
    root.geometry("480x680")
    root.minsize(440, 560)

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    # ---------- панель кнопок: пачкуем ПЕРВОЙ и прижимаем к низу ----------
    # Порядок pack определяет выделяемое место: панель кнопок резервирует
    # свою высоту сразу, поэтому не схлопнется, если окно окажется ниже
    # содержимого (на малых экранах / при высоком DPI).
    btns = ttk.Frame(frame)
    btns.pack(side="bottom", fill="x", pady=(12, 4))

    # ---------- горячая клавиша отмены ----------
    hot = ttk.LabelFrame(frame, text="Горячая клавиша отмены исправления", padding=8)
    hot.pack(fill="x")

    mods_vars = {}
    mods_row = ttk.Frame(hot)
    mods_row.pack(fill="x")
    ttk.Label(mods_row, text="Модификаторы:").pack(side="left")
    for name in MODIFIER_OPTIONS:
        var = tk.BooleanVar(master=hotkey_text)
        mods_vars[name] = var
        ttk.Checkbutton(mods_row, text=name, variable=var).pack(side="left", padx=4)

    base_row = ttk.Frame(hot)
    base_row.pack(fill="x", pady=(6, 0))
    ttk.Label(base_row, text="Клавиша:").pack(side="left")
    base_var = tk.StringVar(master=hotkey_text)
    base_box = ttk.Combobox(base_row, textvariable=base_var, values=BASE_KEYS,
                            width=8, state="normal")
    base_box.pack(side="left", padx=4)

    ttk.Label(hot, text="Одиночная клавиша допускается только F1–F12.",
              foreground="#666").pack(anchor="w", pady=(4, 0))
    current = ttk.Label(hot, text=f"Текущая: {cfg.get('undo_hotkey', '')}",
                        foreground="#444")
    current.pack(anchor="w")

    # ---------- горячая клавиша ручной смены раскладки слова ----------
    swt = ttk.LabelFrame(frame, text="Горячая клавиша смены раскладки последнего слова",
                         padding=8)
    swt.pack(fill="x", pady=(10, 0))

    swt_mods_vars = {}
    swt_mods_row = ttk.Frame(swt)
    swt_mods_row.pack(fill="x")
    ttk.Label(swt_mods_row, text="Модификаторы:").pack(side="left")
    for name in MODIFIER_OPTIONS:
        var = tk.BooleanVar(master=hotkey_text)
        swt_mods_vars[name] = var
        ttk.Checkbutton(swt_mods_row, text=name, variable=var).pack(side="left", padx=4)

    swt_base_row = ttk.Frame(swt)
    swt_base_row.pack(fill="x", pady=(6, 0))
    ttk.Label(swt_base_row, text="Клавиша:").pack(side="left")
    swt_base_var = tk.StringVar(master=hotkey_text)
    ttk.Combobox(swt_base_row, textvariable=swt_base_var, values=BASE_KEYS,
                 width=8, state="normal").pack(side="left", padx=4)

    ttk.Label(swt, text="Слово перепечатывается в другой раскладке (по физическим клавишам).",
              foreground="#666").pack(anchor="w", pady=(4, 0))
    swt_current = ttk.Label(swt, text=f"Текущая: {cfg.get('switch_hotkey', '')}",
                            foreground="#444")
    swt_current.pack(anchor="w")

    # ---------- исключаемые приложения ----------
    apps = ttk.LabelFrame(frame, text="Не исправлять в приложениях", padding=8)
    apps.pack(fill="both", expand=True, pady=(10, 0))

    list_var = tk.StringVar(master=hotkey_text)
    box = tk.Listbox(apps, listvariable=list_var, height=8, exportselection=False)
    box.pack(side="left", fill="both", expand=True)
    scroll = ttk.Scrollbar(apps, command=box.yview)
    scroll.pack(side="left", fill="y")
    box.configure(yscrollcommand=scroll.set)

    side = ttk.Frame(apps)
    side.pack(side="left", fill="y", padx=(6, 0))

    def add_app():
        name = add_var.get().strip().lower()
        if not name:
            return
        if not name.endswith(".exe"):
            name += ".exe"
        items = list(box.get(0, "end"))
        if name in items:
            return
        items.append(name)
        box.delete(0, "end")
        box.insert(0, *items)
        add_var.set("")

    def remove_app():
        for idx in reversed(box.curselection()):
            box.delete(idx)

    add_var = tk.StringVar(master=hotkey_text)
    entry = ttk.Entry(side, textvariable=add_var, width=22)
    entry.pack()
    ttk.Button(side, text="Добавить", command=add_app).pack(pady=(4, 0))
    ttk.Button(side, text="Удалить", command=remove_app).pack(pady=(4, 0))
    ttk.Label(side, text="Или «Навести окно…»", foreground="#666").pack(pady=(8, 0))
    ttk.Button(side, text="Навести окно…", command=lambda: pick_window(box, root)).pack()

    # ---------- лог ----------
    log_frame = ttk.Frame(frame)
    log_frame.pack(fill="x", pady=(10, 0))
    log_var = tk.BooleanVar(master=hotkey_text)
    ttk.Checkbutton(log_frame, text="Писать исправления в локальный лог",
                    variable=log_var).pack(anchor="w")

    # ---------- заполнение формы текущими настройками ----------
    # Значения применяем ЯВНО через .set() после создания всех виджетов:
    # инициализация через конструктор Variable(value=...) в некоторых
    # сборках (Nuitka onefile) не отображается в интерфейсе, из-за чего
    # окно выглядело «пустым» — без текущих и без значений по умолчанию.
    def apply_saved():
        hotkey = cfg.get("undo_hotkey", DEFAULT_CONFIG["undo_hotkey"])
        mods = parse_mods(hotkey)
        for name, v in mods_vars.items():
            v.set(name in mods)
        base_var.set(base_of(hotkey))
        swt_hotkey = cfg.get("switch_hotkey", DEFAULT_CONFIG["switch_hotkey"])
        swt_mods = parse_mods(swt_hotkey)
        for name, v in swt_mods_vars.items():
            v.set(name in swt_mods)
        swt_base_var.set(base_of(swt_hotkey))
        list_var.set(list(cfg.get("excluded_apps", [])))
        log_var.set(bool(cfg.get("log_fixes", True)))

    apply_saved()
    root.after(50, apply_saved)     # страховка: применить и на тике цикла событий

    # ---------- значения по умолчанию (кнопка, не сохранение) ----------
    def reset_defaults():
        mods = parse_mods(DEFAULT_CONFIG["undo_hotkey"])
        for name, v in mods_vars.items():
            v.set(name in mods)
        base_var.set(base_of(DEFAULT_CONFIG["undo_hotkey"]))
        swt_mods = parse_mods(DEFAULT_CONFIG["switch_hotkey"])
        for name, v in swt_mods_vars.items():
            v.set(name in swt_mods)
        swt_base_var.set(base_of(DEFAULT_CONFIG["switch_hotkey"]))
        list_var.set(list(DEFAULT_CONFIG["excluded_apps"]))
        log_var.set(bool(DEFAULT_CONFIG["log_fixes"]))

    # ---------- обработчик кнопки «Сохранить» ----------
    def save():
        mods = frozenset(n for n, v in mods_vars.items() if v.get())
        text = "+".join(sorted(mods) + [base_var.get().strip().lower()])
        if parse_hotkey(text) is None:
            messagebox.showerror(
                "Настройки",
                "Некорректная горячая клавиша отмены. Нужен модификатор (Ctrl/Shift/Alt) "
                "и буква/цифра, либо одиночная F1–F12.",
                parent=root,
            )
            return
        swt_mods = frozenset(n for n, v in swt_mods_vars.items() if v.get())
        swt_text = "+".join(sorted(swt_mods) + [swt_base_var.get().strip().lower()])
        if parse_hotkey(swt_text) is None:
            messagebox.showerror(
                "Настройки",
                "Некорректная горячая клавиша смены раскладки. Нужен модификатор "
                "(Ctrl/Shift/Alt) и буква/цифра, либо одиночная F1–F12.",
                parent=root,
            )
            return
        new_cfg = {
            "undo_hotkey": text,
            "switch_hotkey": swt_text,
            "excluded_apps": list(box.get(0, "end")),
            "log_fixes": log_var.get(),
        }
        if save_config(new_cfg):
            current.config(text=f"Текущая: {text}")
            swt_current.config(text=f"Текущая: {swt_text}")
            if engine is not None:
                engine.refresh_now()
            if log:
                log("настройки сохранены")
            root.destroy()
        else:
            messagebox.showerror("Настройки", "Не удалось записать config.json",
                                 parent=root)

    ttk.Button(btns, text="По умолчанию", command=reset_defaults).pack(side="left")
    ttk.Button(btns, text="Сохранить и применить", command=save).pack(side="right")
    ttk.Button(btns, text="Отмена", command=root.destroy).pack(side="right", padx=6)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    if on_ready:
        root.after(80, lambda: on_ready(root))
    root.mainloop()
    hotkey_text.destroy()


def parse_mods(text):
    """'ctrl+z' -> ['Ctrl'] (для галочек интерфейса)."""
    spec = parse_hotkey(text)
    if not spec:
        return []
    return sorted(spec[0])


def base_of(text):
    spec = parse_hotkey(text)
    return spec[1] if spec else ""


def pick_window(box, parent):
    """Добавить в список процесс активного окна (пользователю не нужно знать имён exe)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    hproc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not hproc:
        return
    buf = ctypes.create_unicode_buffer(260)
    size = wintypes.DWORD(260)
    name = ""
    if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
        name = buf.value.rsplit("\\", 1)[-1].lower()
    kernel32.CloseHandle(hproc)
    if not name:
        return
    items = list(box.get(0, "end"))
    if name not in items:
        items.append(name)
        box.delete(0, "end")
        box.insert(0, *items)
