# Сборка

## EXE через Nuitka (рекомендуется)

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Что делает скрипт:

1. Проверяет `py -3.10` (launcher для нужной версии Python).
2. Если словарей нет — строит их (`build_words.py`).
3. Ставит зависимости: `nuitka`, `ordered-set`, `pywin32`, `pystray`,
   `Pillow`, `zstandard`.
4. Включает плагин `--enable-plugin=tk-inter` — иначе в onefile-сборке
   не будет данных Tcl/Tk (`tcl\init.tcl`), `tk.Tk()` упадёт и окно
   «Настройки» не откроется.
5. Патчит баг Nuitka 4.3.4 (см. ниже) — если файл уже поправлен, ничего не делает.
6. `python -m nuitka --standalone --onefile --windows-console-mode=disable …`
   c включением `pystray`, `PIL`, `win32`, `tkinter` и всех модулей проекта.
7. Кладёт рядом с exe словари (`dist\words\`) и seed `config.json`.

Результат: `dist\punto_switch.exe` (~18 МБ, onefile, сжатие zstd ~28%).
**Не удаляйте папку `words` из каталога с exe** — словари не вшиты в бинарь
(они читаются через `paths.resource_path`, а для onefile каталог exe временный).

### Требования

- Python 3.9+ (3.10 на x64).
- Компилятор C: MSVC (Visual Studio Build Tools, `cl`) **или** MinGW gcc
  (Nuitka скачает MinGW сам, если компилятора нет).
- Для `cl`: сообщение `Nuitka-Scons:WARNING: Support language of Nuitka is
  English...` — предупреждение о локали MSVC, сборке не мешает.

### Известный баг Nuitka 4.3.4 (обход вшит в скрипт)

При сборке MSVC падает:

```
MetaPathBasedLoaderResourceReader.c(17): error C2086: const char *_kw_list_get_data[2]: переопределение
```

Причина: `MetaPathBasedLoaderResourceReader.c` форвард-объявляет
`static char const *_kw_list_get_data[];`, а определение с инициализатором
стоит выше, в `MetaPathBasedLoader.c`, в который файл включается через
`#include`. GCC это проглатывает; MSVC компилирует с `/TP` (C++-режим), где
статическое объявление без инициализатора — вторая дефиниция.
`build_exe.ps1` перед компиляцией вырезает это объявление из файла пакета
Nuitka (в upstream этот код уже поправлен).

### Опционально

- Иконка exe: положите `app.ico` рядом со скриптом — он подключит
  `--windows-icon-from-ico=app.ico`.
- `dist\punto_switch.build`, `dist\punto_switch.dist`,
  `dist\punto_switch.onefile-build` — рабочие каталоги Nuitka, после сборки
  удаляемы.

## Запуск из исходников

```bat
py -3.10 -m pip install -r requirements.txt
py -3.10 punto_switch.py        # или start.bat (pythonw, без консоли)
```

Словари `words/words_*.json` лежат в репозитории. Перестроение:

```bat
py -3.10 build_words.py
```

(требует `words/ru_raw.txt` и `words/en_raw.txt` — см. ссылки в README).

## Тесты

```bat
py -3.10 test_engine.py
py -3.10 test_corrector.py
```

E2E-скрипты (реальный ввод в Блокнот/cmd) — только когда за машиной никто
не работает: они шлют клавиши и конкурируют с открытыми окнами.
