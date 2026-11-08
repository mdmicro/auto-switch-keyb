@echo off
rem Запуск Punto Switch без окна консоли.
rem pythonw.exe берём из того же Python, что и для py -3.10
start "" pyw -3.10 "%~dp0punto_switch.py"
