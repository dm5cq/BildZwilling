@echo off
REM Startet BildZwilling direkt aus dem Quellcode (nach einmaligem build-exe.bat)
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (start "" .venv\Scripts\pythonw.exe main.py) else (py -3 main.py)
