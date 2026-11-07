@echo off
cd /d "%~dp0"
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name CRAY_LDR_MIDI_DECK main.py
if errorlevel 1 goto error
echo.
echo EXE creado en dist\CRAY_LDR_MIDI_DECK.exe
pause
exit /b 0
:error
echo.
echo ERROR al preparar o compilar. Copia el mensaje completo para diagnosticarlo.
pause
exit /b 1
