# -*- coding: utf-8 -*-
"""Интеграционный тест кнопки «Сохранить и применить»: значения из формы
должны записываться в config.json и перечитываться движком (on_ready
работает в потоке Tk)."""

import sys
import threading
import time

sys.path.insert(0, r"C:\Users\mdm\PycharmProjects\punto_switch")

import settings
from hotkey_config import load_config

RESULT = {}
DONE = threading.Event()
REFRESHED = []


class Engine:
    def refresh_now(self):
        REFRESHED.append(1)


def find(root, cls, text=None):
    found = []
    def walk(w):
        for sub in w.winfo_children():
            if sub.winfo_class() == cls and (text is None or str(sub.cget("text")) == text):
                found.append(sub)
            walk(sub)
    walk(root)
    return found


def on_ready(root):
    try:
        # ставим в форме: смена раскладки = Ctrl+Alt+G, лог включён
        checks = find(root, "TCheckbutton")
        # порядок обхода: Ctrl, Shift, Alt (отмена), Ctrl, Shift, Alt (смена), лог
        checks[4].invoke()   # Shift(смена) -> off (дефолт True)
        checks[5].invoke()   # Alt(смена)  -> on
        combos = find(root, "TCombobox")
        combos[1].set("g")   # базовая клавиша смены раскладки -> g
        checks[6].invoke()   # лог -> toggle
        root.after(80, lambda: click_save(root))
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
        DONE.set()


def click_save(root):
    try:
        find(root, "TButton", "Сохранить и применить")[0].invoke()
    except Exception:
        import traceback
        RESULT["error"] = traceback.format_exc()
    finally:
        DONE.set()


def main():
    before = load_config()
    print("до:", before)
    settings.open_settings(Engine(), lambda m: print("LOG:", m), on_ready=on_ready)
    if not DONE.wait(10):
        print("FAIL: окно не отработало")
        return 1
    time.sleep(0.5)
    if "error" in RESULT:
        print("ERROR:\n" + RESULT["error"])
        return 1
    after = load_config()
    print("после:", after)
    key_norm = lambda s: "+".join(sorted(s.lower().split("+")))
    ok = (
        key_norm(after["switch_hotkey"]) == key_norm("Ctrl+Alt+g")
        and after["log_fixes"] == (not before.get("log_fixes", True))
        and after["undo_hotkey"] == before["undo_hotkey"]
        and after["excluded_apps"] == before["excluded_apps"]
    )
    print("сохранение в config.json:", "PASS" if ok else "FAIL")
    ok2 = len(REFRESHED) >= 1
    print("движок извещён (refresh_now):", "PASS" if ok2 else "FAIL")

    # возвращаем пользователю его прежние значения (тест не должен менять конфиг)
    from hotkey_config import save_config
    save_config({
        "switch_hotkey": before.get("switch_hotkey", "ctrl+shift+f"),
        "log_fixes": before.get("log_fixes", True),
    })
    restored = load_config()
    ok3 = (restored["switch_hotkey"] == before["switch_hotkey"]
           and restored["log_fixes"] == before["log_fixes"])
    print("конфиг восстановлен:", "PASS" if ok3 else "FAIL")

    good = ok and ok2 and ok3
    print("SAVE TEST:", "PASS" if good else "FAIL")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
