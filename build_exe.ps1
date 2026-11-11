# Build Auto Switch Keyb into a single EXE with Nuitka (onefile).
#
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# Result: dist\auto-switch-keyb.exe (one file). The word banks are embedded
# into the exe (an external words\*.json folder next to it overrides them).
# Settings and log live in %LOCALAPPDATA%\auto-switch-keyb.
#
# Nuitka needs a C compiler: MSVC (Visual Studio Build Tools) or MinGW gcc.
# Nuitka downloads MinGW by itself when no compiler is found.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 parses files
# without a BOM using the system OEM codepage, so non-ASCII comments here
# break parsing.

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
Set-Location $Here

# Python 3.10 must be available through the py launcher
try {
    & py -3.10 -c "import sys" | Out-Null
} catch {
    Write-Host "Python 3.10 not found (py -3.10). Install it first." -ForegroundColor Red
    exit 1
}

# word banks must be built
if (-not (Test-Path "$Here\words\words_ru.json") -or -not (Test-Path "$Here\words\words_en.json")) {
    Write-Host "No word banks. Building them: py -3.10 build_words.py" -ForegroundColor Yellow
    & py -3.10 build_words.py
    if ($LASTEXITCODE -ne 0) { Write-Host "build_words.py failed" -ForegroundColor Red; exit 1 }
}

Write-Host "Installing build dependencies..." -ForegroundColor Cyan
& py -3.10 -m pip install --quiet --disable-pip-version-check nuitka ordered-set pywin32 pystray Pillow zstandard comtypes
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed" -ForegroundColor Red; exit 1 }

# comtypes generates its typelib wrappers into comtypes.gen at runtime.
# In a frozen app generation may fail, so pre-generate the UIA wrapper
# now (password_guard.py uses IUIAutomation for password field detection);
# at runtime the existing module is imported, not regenerated.
& py -3.10 -c "import comtypes.client as c; c.GetModule('UIAutomationCore.dll')" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "comtypes.GetModule(UIAutomationCore) failed" -ForegroundColor Yellow }

# Work around a Nuitka 4.3.4 bug: MetaPathBasedLoaderResourceReader.c forward-declares
# _kw_list_get_data, but MSVC compiles the sources with /TP (C++ mode) where a static
# declaration without initializer counts as a second definition -> error C2086.
# The declaration is not needed (the file is #included after the definition), so strip it.
$StaticSrc = ((& py -3.10 -c "import nuitka, os; print(os.path.join(os.path.dirname(nuitka.__file__), 'build', 'static_src'))") | Out-String).Trim()
$ReaderC = Join-Path $StaticSrc "MetaPathBasedLoaderResourceReader.c"
if (Test-Path $ReaderC) {
    $c = Get-Content $ReaderC -Raw
    if ($c -match 'static char const \*_kw_list_get_data\[\];') {
        $c = $c -replace 'static char const \*_kw_list_get_data\[\];', ''
        Set-Content -Path $ReaderC -Value $c -NoNewline
        Write-Host "Applied Nuitka MSVC fix (C2086) to MetaPathBasedLoaderResourceReader.c" -ForegroundColor Yellow
    }
}

Write-Host "Building EXE (Nuitka onefile)..." -ForegroundColor Cyan
$NuitkaArgs = @(
    "-3.10", "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--windows-console-mode=disable",
    "--include-package=pystray",
    "--include-package=PIL",
    "--include-package=win32",
    "--include-package=comtypes",
    "--include-module=password_guard",
    "--include-module=tkinter",
    "--enable-plugin=tk-inter",
    "--include-module=engine",
    "--include-module=fixer",
    "--include-module=corrector",
    "--include-module=layout_map",
    "--include-module=tray",
    "--include-module=settings",
    "--include-module=flags",
    "--include-module=paths",
    "--include-module=hotkey_config",
    "--include-module=version",
    "--include-data-files=words/words_ru.json=words/words_ru.json",
    "--include-data-files=words/words_en.json=words/words_en.json",
    "--output-dir=dist",
    "--output-filename=auto-switch-keyb.exe",
    "auto_switch_keyb.py"
)
if (Test-Path "$Here\app.ico") {
    $NuitkaArgs += "--windows-icon-from-ico=app.ico"
}
& py $NuitkaArgs
if ($LASTEXITCODE -ne 0) { Write-Host "Nuitka failed" -ForegroundColor Red; exit 1 }

# copy word banks next to the exe as an OPTIONAL override: the exe carries
# them embedded, an external words\*.json takes precedence (no rebuild needed
# to swap dictionaries)
$Dist = "$Here\dist"
if (-not (Test-Path "$Dist\words")) { New-Item -ItemType Directory -Path "$Dist\words" | Out-Null }
Copy-Item "$Here\words\words_ru.json" "$Dist\words\" -Force
Copy-Item "$Here\words\words_en.json" "$Dist\words\" -Force
if (Test-Path "$Here\config.json") { Copy-Item "$Here\config.json" "$Dist\" -Force }

Write-Host ""
Write-Host "Done: $Dist\auto-switch-keyb.exe" -ForegroundColor Green
Write-Host "Word banks are embedded in the exe; an external words folder (if present) overrides them." -ForegroundColor Green
Write-Host "Settings and log: %LOCALAPPDATA%\auto-switch-keyb" -ForegroundColor Green
