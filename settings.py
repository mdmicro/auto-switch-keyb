# -*- coding: utf-8 -*-
"""Окно «Настройки» (Tkinter): горячая клавиша отмены и список исключаемых
приложений. Окно немодальное, открывается из меню трея в отдельном потоке,
сохраняет config.json и немедленно применяет настройки к движку.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from hotkey_config import format_hotkey, load_config, parse_hotkey, save_config
from version import __version__

MODIFIER_OPTIONS = ["Ctrl", "Shift", "Alt"]
BASE_KEYS = (
    list("abcdefghijklmnopqrstuvwxyz")
    + [str(i) for i in range(10)]
    + [f"f{i}" for i in range(1, 13)]
)


def open_settings(engine, log=None):
    """Открыть окно настроек неблокирующим потоком.

    engine.refresh_now() вызывается после сохранения, чтобы движок подхватил
    настройки без рестарта. Любое падение окна логируется, а не рушит
    поток меню иконки.
    """

    def target():
        try:
            _run_window(engine, log)
        except Exception:
            if log:
                import traceback

                log("ошибка окна настроек:\n" + traceback.format_exc())

    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def _run_window(engine, log):
    cfg = load_config()
    hotkey_text = tk.Tk()
    hotkey_text.withdraw()

    root = tk.Toplevel(hotkey_text)
    root.title(f"Auto Switch Keyb {__version__} — настройки")
    root.geometry("440x420")

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    # ---------- горячая клавиша отмены ----------
    hot = ttk.LabelFrame(frame, text="Горячая клавиша отмены исправления", padding=8)
    hot.pack(fill="x")

    mods_vars = {}
    mods_row = ttk.Frame(hot)
    mods_row.pack(fill="x")
    ttk.Label(mods_row, text="Модификаторы:").pack(side="left")
    for name in MODIFIER_OPTIONS:
        var = tk.BooleanVar(value=name in parse_mods(cfg.get("undo_hotkey", "")))
        mods_vars[name] = var
        ttk.Checkbutton(mods_row, text=name, variable=var).pack(side="left", padx=4)

    base_row = ttk.Frame(hot)
    base_row.pack(fill="x", pady=(6, 0))
    ttk.Label(base_row, text="Клавиша:").pack(side="left")
    base_var = tk.StringVar(value=base_of(cfg.get("undo_hotkey", "ctrl+z")))
    base_box = ttk.Combobox(base_row, textvariable=base_var, values=BASE_KEYS,
                            width=8, state="normal")
    base_box.pack(side="left", padx=4)

    ttk.Label(hot, text="Одиночная клавиша допускается только F1–F12.",
              foreground="#666").pack(anchor="w", pady=(4, 0))
    current = ttk.Label(hot, text=f"Текущая: {cfg.get('undo_hotkey', '')}",
                        foreground="#444")
    current.pack(anchor="w")

    # ---------- исключаемые приложения ----------
    apps = ttk.LabelFrame(frame, text="Не исправлять в приложениях", padding=8)
    apps.pack(fill="both", expand=True, pady=(10, 0))

    list_var = tk.StringVar(value=cfg.get("excluded_apps", []))
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

    add_var = tk.StringVar()
    entry = ttk.Entry(side, textvariable=add_var, width=22)
    entry.pack()
    ttk.Button(side, text="Добавить", command=add_app).pack(pady=(4, 0))
    ttk.Button(side, text="Удалить", command=remove_app).pack(pady=(4, 0))
    ttk.Label(side, text="Или «Навести окно…»", foreground="#666").pack(pady=(8, 0))
    ttk.Button(side, text="Навести окно…", command=lambda: pick_window(box, root)).pack()

    # ---------- лог ----------
    log_frame = ttk.Frame(frame)
    log_frame.pack(fill="x", pady=(10, 0))
    log_var = tk.BooleanVar(value=bool(cfg.get("log_fixes", True)))
    ttk.Checkbutton(log_frame, text="Писать исправления в локальный лог",
                    variable=log_var).pack(anchor="w")

    # ---------- кнопки ----------
    btns = ttk.Frame(frame)
    btns.pack(fill="x", pady=(12, 0))

    def save():
        mods = frozenset(n for n, v in mods_vars.items() if v.get())
        text = "+".join(sorted(mods) + [base_var.get().strip().lower()])
        if parse_hotkey(text) is None:
            messagebox.showerror(
                "Настройки",
                "Некорректная горячая клавиша. Нужен модификатор (Ctrl/Shift/Alt) "
                "и буква/цифра, либо одиночная F1–F12.",
                parent=root,
            )
            return
        new_cfg = {
            "undo_hotkey": text,
            "excluded_apps": list(box.get(0, "end")),
            "log_fixes": log_var.get(),
        }
        if save_config(new_cfg):
            current.config(text=f"Текущая: {text}")
            if engine is not None:
                engine.refresh_now()
            if log:
                log("настройки сохранены")
            root.destroy()
        else:
            messagebox.showerror("Настройки", "Не удалось записать config.json",
                                 parent=root)

    ttk.Button(btns, text="Сохранить и применить", command=save).pack(side="right")
    ttk.Button(btns, text="Отмена", command=root.destroy).pack(side="right", padx=6)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
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
