# -*- coding: utf-8 -*-
"""Сценарий пользователя: открыть окно -> изменить -> сохранить -> закрыть,
затем ОТКРЫТЬ ВТОРОЙ РАЗ и проверить, что сохранённые значения подгружены."""

import sys
import threading
import time

sys.path.insert(0, r"C:\Users\mdm\PycharmProjects\punto_switch")

import settings
from hotkey_config import load_config, save_config

RESULT = {}
DONE1 = threading.Event()
DONE2 = threading.Event()
BEFORE = {}


class Engine:
    def refresh_now(self):
        pass


def find(root, cls, text=None):
    found = []
    def walk(w):
        for sub in w.winfo_children():
            if sub.winfo_class() == cls and (text is None
                                             or str(sub.cget("text")) == text):
                found.append(sub)
            walk(sub)
    walk(root)
    return found


def dump(root):
    out = {"checks": [], "combos": [], "apps": []}
    def walk(w):
        for sub in w.winfo_children():
            cls = sub.winfo_class()
            if cls == "TCheckbutton":
                try:
                    out["checks"].append((str(sub.cget("text")),
                                          bool(root.getvar(sub.cget("variable")))))
                except Exception:
                    pass
            elif cls == "TCombobox" and sub.cget("textvariable"):
                out["combos"].append(sub.get())
            elif cls == "Listbox":
                out["apps"] = list(sub.get(0, "end"))
            walk(sub)
    walk(root)
    return out


def on_first(root):
    """Меняем: отмена = Ctrl+X (Shift off, база x), лог on -> сохранить."""
    try:
        checks = find(root, "TCheckbutton")
        checks[1].invoke()          # Shift(отмена) -> off
        find(root, "TCombobox")[0].set("x")
        checks[6].invoke()          # лог -> toggle
        root.after(80, lambda: (
            find(root, "TButton", "Сохранить и применить")[0].invoke(),
            DONE1.set(),
        ))
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
        DONE1.set()


def on_second(root):
    """Второе открытие: поля обязаны показать СОХРАНЁННОЕ."""
    try:
        RESULT["second"] = dump(root)
        find(root, "TButton", "Отмена")[0].invoke()
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
    finally:
        DONE2.set()


def main():
    global BEFORE
    BEFORE = load_config()
    print("конфиг до:", BEFORE)

    settings.open_settings(Engine(), None, on_ready=on_first)
    if not DONE1.wait(10):
        print("FAIL: первое окно не отработало")
        return 1
    time.sleep(0.6)
    mid = load_config()
    print("конфиг после сохранения:", mid)

    settings.open_settings(Engine(), None, on_ready=on_second)
    if not DONE2.wait(10):
        print("FAIL: второе окно не отработало")
        return 1
    time.sleep(0.4)

    if "error" in RESULT:
        print("ERROR:\n" + RESULT["error"])
        return 1
    st = RESULT["second"]
    print("второе окно:", st)
    # ожидания: undo = Ctrl+X (Ctrl True, Shift False, база x), лог = on
    checks = st["checks"]
    ok = (len(st["combos"]) >= 2
          and st["combos"][0] == "x"
          and ("Ctrl", True) in checks and ("Shift", False) in checks
          and ("Писать исправления в локальный лог", True) in checks)
    print("сохранённое подгружено во второе окно:", "PASS" if ok else "FAIL")

    # вернуть пользователю его конфиг
    save_config({
        "undo_hotkey": BEFORE["undo_hotkey"],
        "switch_hotkey": BEFORE.get("switch_hotkey", "ctrl+shift+f"),
        "log_fixes": BEFORE.get("log_fixes", True),
    })
    print("конфиг восстановлен:", load_config())
    print("REOPEN TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
