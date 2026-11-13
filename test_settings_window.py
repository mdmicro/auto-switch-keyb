# -*- coding: utf-8 -*-
"""Интеграционный тест окна «Настройки»: окно открывается в фоновом
потоке (как из меню трея); опрос и нажатия кнопок выполняются ВНУТРИ
потока Tk через on_ready-хук (tkinter привязан к потоку)."""

import sys
import threading
import time

sys.path.insert(0, r"C:\Users\mdm\PycharmProjects\punto_switch")

import settings
from settings import base_of, parse_mods
from hotkey_config import DEFAULT_CONFIG, load_config

RESULT = {}
DONE = threading.Event()


class StubEngine:
    def __init__(self):
        self.refreshed = 0

    def refresh_now(self):
        self.refreshed += 1


def dump(root):
    out = {"checks": [], "buttons": {}, "combos": []}
    def walk(w):
        for sub in w.winfo_children():
            cls = sub.winfo_class()
            if cls == "TCheckbutton":
                try:
                    name = sub.cget("variable")
                    out["checks"].append(
                        (str(sub.cget("text")), bool(root.getvar(name)))
                    )
                except Exception:
                    pass
            elif cls == "TCombobox" and sub.cget("textvariable"):
                out["combos"].append(sub.get())
            elif cls == "Listbox":
                out["apps"] = list(sub.get(0, "end"))
            elif cls == "TButton":
                out["buttons"][str(sub.cget("text"))] = sub
            walk(sub)
    walk(root)
    return out


def on_ready(root):
    try:
        state = dump(root)
        RESULT["current"] = state
        from hotkey_config import load_config
        cfg = load_config()
        combos = state.get("combos", [])
        checks = state["checks"]
        # ожидания - из фактического конфига, а не хардкод
        ok_current = (
            len(combos) >= 2
            and combos[0] == base_of(cfg["undo_hotkey"])
            and combos[1] == base_of(cfg.get("switch_hotkey", "ctrl+shift+f"))
            and ("Ctrl", "Ctrl" in parse_mods(cfg["undo_hotkey"])) in checks
            and ("Shift", "Shift" in parse_mods(cfg["undo_hotkey"])) in checks
        )
        RESULT["ok_current"] = ok_current

        state["buttons"]["По умолчанию"].invoke()
        root.after(200, lambda: after_default(root))
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
        DONE.set()


def after_default(root):
    try:
        from hotkey_config import DEFAULT_CONFIG
        state = dump(root)
        RESULT["default"] = state
        combos = state.get("combos", [])
        # mods_vars идут раньше swt_mods_vars в обходе: Ctrl(True) от отмены,
        # Ctrl/Shift от смены раскладки тоже True; проверяем главное:
        RESULT["ok_default"] = (
            len(combos) >= 2
            and combos[0] == base_of(DEFAULT_CONFIG["undo_hotkey"])
            and combos[1] == base_of(DEFAULT_CONFIG["switch_hotkey"])
            and ("Ctrl", True) in state["checks"]
            and state.get("apps") == list(DEFAULT_CONFIG["excluded_apps"])
        )
        state["buttons"]["Отмена"].invoke()
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
    finally:
        DONE.set()


def main():
    engine = StubEngine()
    logs = []
    settings.open_settings(engine, lambda m: logs.append(m), on_ready=on_ready)
    if not DONE.wait(10):
        print("FAIL: окно не открылось/не отработало")
        return 1
    time.sleep(0.3)
    if "error" in RESULT:
        print("ERROR:\n" + RESULT["error"])
        return 1
    print("текущее состояние:", RESULT["current"])
    print("после «По умолчанию»:", RESULT["default"])
    print("показаны текущие значения:",
          "PASS" if RESULT["ok_current"] else "FAIL")
    print("сброс по умолчанию:", "PASS" if RESULT["ok_default"] else "FAIL")
    print("refresh_now вызван (не должен был):", engine.refreshed)
    ok = RESULT["ok_current"] and RESULT["ok_default"] and engine.refreshed == 0
    print("SETTINGS TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
