# -*- coding: utf-8 -*-
"""Auto Switch Keyb: глобальный клавиатурный хук + распознавание слов.

WH_KEYBOARD_LL слушает весь ввод клавиатуры в системе. Символы копятся в
«буфер текущего слова». На границе слова (пробел, Enter, Tab) слово
анализируется: если набранное слово бессмысленно, а его «зеркало» в другой
раскладке — настоящее слово, то слово заменяется и раскладка переключается
на язык результата.

Три важных правила:
1. Исправление исполняется СИНХРОННО в колбэке хука и ОДНОЙ атомарной
   пачкой SendInput («Backspace'ы + исправленное слово + терминатор»):
   так пачка гарантированно попадает в поток ввода раньше следующих
   клавиш пользователя, и каретка не разъезжается.
2. Клавиша-терминатор (пробел/Enter/Tab), на которой слово ушло в
   исправление, «съедается» хуком (и её keyup тоже), а терминатор
   дописывает сама пачка — на экране слово занимает ровно своё место.
3. Собственные события SendInput помечаются magic-значением dwExtraInfo
   и игнорируются хуком, чтобы не исправлять собственный вывод.
   Файловый лог из колбэка не пишется (I/O замедляет хук) — строки
   лога складываются в очередь, их пишет рабочий поток.
4. Ctrl+Z — ручная отмена последнего исправления (как в Punto Switcher):
   откат стирает исправленное слово, печатает исходное и возвращает
   раскладку. Отменяется ровно одно последнее исправление; после отмены
   Ctrl+Z снова работает как обычная «отменить» приложения.
"""

import ctypes
import queue
import threading
import time
from ctypes import wintypes

from corrector import MIN_WORD_LEN, WordDicts, decide
from fixer import INJECTED_MAGIC, replace_last_word, switch_layout
from hotkey_config import parse_hotkey
from layout_map import LAYOUT_EN, LAYOUT_RU, lang_of_chars

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

HC_ACTION = 0
WH_KEYBOARD_LL = 13
LLKHF_INJECTED = 0x10
WM_KEYDOWN = 0x100
WM_KEYUP = 0x101
WM_SYSKEYDOWN = 0x104
WM_SYSKEYUP = 0x105

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_CAPITAL = 0x14
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT = 0xA0
VK_LCONTROL = 0xA2
VK_LMENU = 0xA4
VK_PACKET = 0xE7
VK_Z = ord("Z")

# базовая клавиша хоткея -> VK-код (для распознавания в хуке)
def _base_to_vk(base):
    """'z'->0x5A, '5'->0x35, 'f7'->0x76."""
    b = base.lower()
    if len(b) == 1:
        return ord(b.upper())
    if b.startswith("f") and b[1:].isdigit():
        n = int(b[1:])
        if 1 <= n <= 12:
            return 0x70 + (n - 1)
    return None

# символы, которыми слово может заканчиваться (само слово анализируется до них)
WORD_TERMINATORS = set(" ,;:!?)]}~\t\r\n")
# символы, которые могут стоять внутри слова
WORD_INNER = set("-'’")

PROCESS_NAME_MAX = 260

# минимум между двумя исправлениями подряд (сек)
FIX_DEBOUNCE = 0.25
# как часто перечитывать настройки из config.json (callable-источник)
CONFIG_TTL = 2.0

EXCLUDED_APPS = {
    "logonui.exe",        # экран входа / поле пароля
    "credentialui.exe",
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.POINTER(KBDLLHOOKSTRUCT)
)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD,
)
user32.CallNextHookEx.restype = ctypes.c_long
user32.CallNextHookEx.argtypes = (
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(KBDLLHOOKSTRUCT),
)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
user32.ToUnicodeEx.restype = ctypes.c_int
user32.ToUnicodeEx.argtypes = (
    wintypes.UINT, wintypes.UINT,
    ctypes.POINTER(ctypes.c_ubyte * 256),
    ctypes.POINTER(wintypes.WCHAR),
    ctypes.c_int, wintypes.UINT, wintypes.HANDLE,
)
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
user32.GetWindowThreadProcessId.restype = wintypes.UINT
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = ()
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
)
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)


class SwitchEngine:
    """Состояние и логика распознавания «набрано не в той раскладке»."""

    def __init__(self, config, logger):
        # config -- dict ИЛИ callable, возвращающий актуальный dict
        # (callable позволяет подхватывать изменения config.json на лету)
        self._config_source = config
        self.config = config() if callable(config) else (config or {})
        self._config_at = 0.0
        self.log = logger
        self.dicts = WordDicts()
        self.enabled = True
        self.word = []                      # символы текущего слова
        self.layout = self._layout_code()
        self.intent = self.layout           # эту раскладку выбрал сам пользователь
        self._hkl = None                    # HKL фокусного окна (для ToUnicodeEx)
        self._last_fix = 0.0
        # последнее исправление для ручной отмены (Ctrl+Z по умолчанию):
        # (набранное, исправленное, раскладка_набора, раскладка_результата,
        #  терминатор_vk, терминатор_char)
        self._last_applied = None
        # сколько символов пользователь набрал после последнего исправления
        self._typed_since_fix = 0
        self._app_cache = {}
        self._name_buf = ctypes.create_unicode_buffer(PROCESS_NAME_MAX)
        self.hook = None
        self._hook_cb = None                # держать callback живым обязательно
        self._fix_logs = queue.Queue()       # строки лога из хука: пишет рабочий поток
        self._worker = None
        self._running = False
        # клавиша-терминатор, съеденная на keydown (её keyup тоже надо съесть)
        self._swallow_vk = None
        # горячая клавиша отмены исправления: модификаторы + базовая клавиша
        self._undo_mods = frozenset()
        self._undo_vk = None
        self._apply_hotkey()
        # диагностика: сколько событий дошло до колбэка / слов проверено
        self.stats = {"keys": 0, "words": 0, "fixes": 0}

    # ---------- утилиты ----------

    def _layout_code(self):
        """Код раскладки фокусного окна: 'ru' | 'en' | None.

        Заодно сохраняет HKL фокусного окна в self._hkl: им конвертируем
        клавиши в символы (у потока-установщика хука своя раскладка,
        она может не поспевать за фокусом — пользоваться ToUnicode
        с ней нельзя, иначе буквы «зеркалятся» уже в буфере слова).
        """
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hkl = user32.GetKeyboardLayout(tid)
        if not hkl:
            # в терминалах GetKeyboardLayout чужого потока иногда возвращает
            # NULL -> берём раскладку текущего потока (она синхронизирована
            # с фокусом через WM_INPUTLANGCHANGEREQUEST)
            hkl = user32.GetKeyboardLayout(0)
        if not hkl:
            return None
        self._hkl = hkl
        lcid = hkl & 0xFFFF
        if lcid == 0x0419:
            return LAYOUT_RU
        if lcid == 0x0409:
            return LAYOUT_EN
        return None

    def _foreground_app(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        cached = self._app_cache.get(pid.value)
        if cached is not None:
            return cached
        name = ""
        hproc = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if hproc:
            size = wintypes.DWORD(PROCESS_NAME_MAX)
            if kernel32.QueryFullProcessImageNameW(
                hproc, 0, self._name_buf, ctypes.byref(size)
            ):
                name = self._name_buf.value.rsplit("\\", 1)[-1].lower()
            kernel32.CloseHandle(hproc)
        self._app_cache[pid.value] = name
        return name

    def _in_excluded_app(self):
        excluded = set(self.config.get("excluded_apps", EXCLUDED_APPS))
        app = self._foreground_app()
        if app in excluded:
            self.word = []
            return True
        return False

    def _to_unicode(self, kb):
        """Символ от клавиши kb в раскладке ФОКУСНОГО окна (self._hkl).

        GetKeyboardState тут нельзя: он отражает состояние потока-угонщика
        хука (наш поток), а не реального ввода. Состояние Shift/Caps/Ctrl/Alt
        читаем GetAsyncKeyState, раскладку берём у окна в фокусе: в
        low-level хуке это единственно надёжная пара (иначе при активной
        русской раскладке буквы конвертируются в англ. и RU->EN направление
        молча не работает).
        """
        hkl = self._hkl
        if not hkl:
            return None
        state = (ctypes.c_ubyte * 256)()
        if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
            state[VK_SHIFT] = 0x80
            state[VK_LSHIFT] = 0x80
        if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
            state[VK_CONTROL] = 0x80
            state[VK_LCONTROL] = 0x80
        if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
            state[VK_MENU] = 0x80
            state[VK_LMENU] = 0x80
        if state[VK_CONTROL] & 0x80:
            return None                     # Ctrl+буква — хоткеи, не текст
        if state[VK_MENU] & 0x80:
            return None                     # Alt-комбинации — не обычный текст
        if user32.GetAsyncKeyState(VK_CAPITAL) & 0x0001:
            state[VK_CAPITAL] |= 0x01       # Caps Lock в состоянии «вкл»
        buf = (wintypes.WCHAR * 4)()
        res = user32.ToUnicodeEx(
            kb.vkCode, kb.scanCode, ctypes.byref(state), buf, 1, 0, hkl
        )
        if res <= 0:
            return None
        return buf[0]

    # ---------- разбор слов ----------

    def _finish_word(self, terminator_vk=None, terminator_char=None):
        """Проверить накопленное слово.

        Возвращает действие (tuple) для немедленного исполнения ИЛИ None.
        Исправление исполняется СИНХРОННО внутри колбэка хука: пачка
        «Backspace'ы + слово + терминатор» уходит в очередь ввода раньше
        следующих клавиш пользователя, поэтому каретка не разъезжается.
        Слово на исправлении означает, что хук обязан «съесть»
        клавишу-терминатор (клавиатура не должна отдать её приложению).
        """
        if not self.word:
            return None
        word = "".join(self.word)
        self.word = []
        if len(word) < MIN_WORD_LEN:
            return None
        if lang_of_chars(word) is None:
            return None                      # смешанное слово не трогаем
        self.stats["words"] += 1
        if not self.enabled:
            return None
        result = decide(word, self.layout, self.intent, self.dicts)
        if self.config.get("debug"):
            # диагностика: тоже пишем нераспознанные слова, чтобы
            # разбираться в проблемах от имени пользователя
            self._fix_logs.put(
                f"слово {word!r}: layout={self.layout} intent={self.intent} "
                f"реш={result['fixed']!r}/{result['layout']!r}"
            )
        fixed = result["fixed"]
        if not fixed:
            return None
        now = time.time()
        if now - self._last_fix < FIX_DEBOUNCE:
            return None
        self._last_fix = now
        typed_layout = self.layout   # раскладка, в которой слово было набрано
        return (word, fixed, typed_layout, result["layout"],
                terminator_vk, terminator_char)

    def _apply_fix(self, action):
        word, fixed, typed_layout, layout, term_vk, term_char = action
        self.stats["fixes"] += 1
        replace_last_word(word, fixed, term_vk, term_char)
        # раскладку МЕНЯЕМ ТОЛЬКО если она реально сменилась (ru <-> en):
        # WM_INPUTLANGCHANGEREQUEST без смены языка перемыкает ввод в
        # приложениях-исключениях (терминал) и хук там больше не срабатывает
        if layout and layout != typed_layout:
            switch_layout(layout)
            self.layout = layout
            self.intent = layout
        # запоминаем исправление для ручной отмены горячей клавишей
        self._last_applied = (word, fixed, typed_layout, layout, term_vk, term_char)
        self._typed_since_fix = 0
        # писать лог из колбэка хука нельзя (файловый I/O замедляет хук) —
        # строку в очередь, печатает рабочий поток
        self._fix_logs.put(f"исправлено: {word!r} -> {fixed!r} ({layout})")

    # ---------- настройки и горячая клавиша отмены ----------

    def _apply_hotkey(self):
        spec = parse_hotkey(self.config.get("undo_hotkey", "ctrl+z"))
        if spec is None:
            self._undo_mods = frozenset()
            self._undo_vk = None
            return
        self._undo_mods, base = spec
        self._undo_vk = _base_to_vk(base)

    def _refresh_config(self):
        """Перечитать config.json (только из рабочего потока, не из хука)."""
        if not callable(self._config_source):
            return
        now = time.time()
        if now - self._config_at < CONFIG_TTL:
            return
        self._config_at = now
        try:
            cfg = self._config_source()
        except Exception:
            return
        if isinstance(cfg, dict):
            self.config = cfg
            self._apply_hotkey()

    def refresh_now(self):
        """Немедленно перечитать настройки (окно «Настройки» жмёт «Применить»)."""
        self._config_at = 0.0
        self._refresh_config()

    def _sync_layout(self):
        """Перечитать раскладку фокусного окна; обновить intent при смене.

        Вызывается: на keyup модификатора (пользователь переключил раскладку
        комбинацией Alt+Shift / Ctrl+Shift), на обычной клавише (обычный путь),
        и из потока иконки (опрос: переключение горячими клавишами, смена
        раскладки средствами Windows). Намерение пользователя важнее
        автоматического языка последнего фикса.
        """
        lay = self._layout_code()
        if lay and lay != self.layout:
            self.layout = lay
            self.intent = lay

    def _mods_match(self):
        """Нажеты ли ровно те модификаторы, что заданы для хоткея."""
        mods = self._undo_mods
        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
        alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        return (ctrl == ("Ctrl" in mods)
                and shift == ("Shift" in mods)
                and alt == ("Alt" in mods))

    def _undo_last_fix(self):
        """Ручная отмена последнего исправления (как Ctrl+Z в Punto Switcher).

        Откатываем, только если пользователь после исправления ничего не
        набрал (слово не изменилось). Иначе хоткей проходит приложению как
        обычная «отменить».
        """
        act = self._last_applied
        if not act or self._typed_since_fix:
            return False
        word, fixed, typed_layout, _fixed_layout, term_vk, term_char = act
        replace_last_word(fixed, word, term_vk, term_char)
        if typed_layout and typed_layout != self.layout:
            switch_layout(typed_layout)
            self.layout = typed_layout
            self.intent = typed_layout
        self._last_applied = None
        self._typed_since_fix = 0
        self._fix_logs.put(f"отменено исправление: {fixed!r} -> {word!r}")
        return True

    # ---------- обработчик хука ----------

    def _on_key(self, ncode, msg, lparam):
        try:
            if ncode == HC_ACTION and msg in (WM_KEYUP, WM_SYSKEYUP):
                # keyup терминатора, который мы съели на keydown, тоже съедаем
                if (self._swallow_vk is not None
                        and lparam.contents.vkCode == self._swallow_vk):
                    self._swallow_vk = None
                    return 1
                if lparam.contents.vkCode in (VK_SHIFT, VK_CONTROL, VK_MENU,
                                              VK_CAPITAL, VK_LWIN, VK_RWIN):
                    # отпустили модификатор / Caps Lock: Alt+Shift, Ctrl+Shift,
                    # Win+Space (переключатель раскладки Windows) или Caps
                    # (на некоторых машинах он и есть переключатель раскладки,
                    # см. HKCU\Keyboard Layout\Toggle) уже успели сменить
                    # раскладку - перечитываем её, чтобы иконка-флаг поменялась
                    # СРАЗУ, а не на следующей напечатанной клавише
                    self._sync_layout()
                return self._pass(ncode, msg, lparam)
            if ncode == HC_ACTION and msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = lparam.contents
                self.stats["keys"] += 1
                if kb.flags & LLKHF_INJECTED:
                    extra = ctypes.cast(kb.dwExtraInfo, ctypes.c_void_p).value or 0
                    if extra == INJECTED_MAGIC:
                        return self._pass(ncode, msg, lparam)
                if kb.vkCode in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE):
                    return self._pass(ncode, msg, lparam)
                # горячая клавиша отмены последнего исправления
                if self._undo_vk is not None and kb.vkCode == self._undo_vk:
                    ok_mods = self._mods_match()
                    ok_undo = ok_mods and self._undo_last_fix()
                    if not ok_undo and self.config.get("debug"):
                        self._fix_logs.put(
                            f"hotkey: mods={ok_mods} typed_since_fix={self._typed_since_fix} "
                            f"applied={bool(self._last_applied)}"
                        )
                    if ok_undo:
                        return 1              # съели: откатили своё исправление
                lay = self._layout_code()
                if lay and lay != self.layout:
                    self.layout = lay
                    self.intent = lay
                if kb.vkCode == VK_BACK:
                    if self.word:
                        self.word.pop()
                    self._typed_since_fix += 1
                    return self._pass(ncode, msg, lparam)
                if kb.vkCode in (VK_RETURN, VK_TAB):
                    self._typed_since_fix += 1
                    action = self._finish_word(terminator_vk=kb.vkCode)
                    if action:
                        self._swallow_vk = kb.vkCode
                        self._apply_fix(action)
                        return 1
                    return self._pass(ncode, msg, lparam)
                if self._in_excluded_app():
                    return self._pass(ncode, msg, lparam)
                if kb.vkCode == VK_PACKET:
                    # KEYEVENTF_UNICODE: символ лежит в scanCode (VK_PACKET)
                    ch = chr(kb.scanCode & 0xFFFF)
                else:
                    ch = self._to_unicode(kb)
                if ch is None:
                    return self._pass(ncode, msg, lparam)
                self._typed_since_fix += 1
                if ch in WORD_TERMINATORS:
                    action = self._finish_word(terminator_char=ch)
                    if action:
                        self._swallow_vk = kb.vkCode
                        self._apply_fix(action)
                        return 1
                elif lang_of_chars(ch) is not None:
                    self.word.append(ch.lower())
                elif ch in WORD_INNER:
                    self.word.append(ch)
                else:
                    self._finish_word()
        except Exception:                   # хук не должен ронять приложение
            import traceback

            self._fix_logs.put(
                "ошибка в хуке:\n" + traceback.format_exc()
            )
            self.word = []
        return self._pass(ncode, msg, lparam)

    @staticmethod
    def _pass(ncode, msg, lparam):
        return user32.CallNextHookEx(None, ncode, msg, lparam)

    # ---------- жизненный цикл ----------

    def _log_worker(self):
        """Пишет строки лога, накопленные хуком (в колбэке I/O быть не должно),
        и перечитывает настройки из config.json."""
        while self._running:
            self._refresh_config()
            try:
                line = self._fix_logs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.log(line)
            except Exception:
                pass

    def start(self):
        self._running = True
        self._worker = threading.Thread(target=self._log_worker, daemon=True)
        self._worker.start()
        self._hook_cb = HOOKPROC(self._on_key)
        self.hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_cb, kernel32.GetModuleHandleW(None), 0
        )
        if not self.hook:
            raise RuntimeError("не удалось установить WH_KEYBOARD_LL")
        self.log("хук клавиатуры установлен")

    def stop(self):
        if self.hook:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None
            self.log("хук снят")
        self._running = False
