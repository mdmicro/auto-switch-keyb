@echo off
rem Запуск Auto Switch Keyb без окна консоли.
rem pythonw.exe берём из того же Python, что и для py -3.10
start "" pyw -3.10 "%~dp0auto_switch_keyb.py"
