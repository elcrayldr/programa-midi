@echo off
setlocal
title CRAY LDR MIDI DECK - Reparar dependencias
cd /d "%~dp0"

echo ========================================
echo       CRAY LDR MIDI DECK
echo       Reparacion del backend MIDI
echo ========================================
echo.

py -3.12 --version
if errorlevel 1 (
  echo ERROR: No se encuentra Python 3.12.
  pause
  exit /b 1
)

echo.
echo [1/3] Actualizando pip...
py -3.12 -m pip install --upgrade pip
if errorlevel 1 goto error

echo.
echo [2/3] Reinstalando Mido y python-rtmidi...
py -3.12 -m pip install --upgrade --force-reinstall --no-cache-dir "mido>=1.3.2" "python-rtmidi>=1.5.8" "pyautogui>=0.9.54"
if errorlevel 1 goto error

echo.
echo [3/3] Comprobando que el backend MIDI se puede importar...
py -3.12 -c "import mido; import mido.backends.rtmidi; import rtmidi; print('Mido:', mido.__version__); print('python-rtmidi:', getattr(rtmidi, '__version__', 'instalado')); print('Backend MIDI: OK')"
if errorlevel 1 goto backend_error

echo.
echo ========================================
echo REPARACION COMPLETADA
echo Ya puedes ejecutar RUN_MIDI_DECK.bat
echo ========================================
pause
exit /b 0

:backend_error
echo.
echo ERROR: Python sigue sin poder importar mido.backends.rtmidi.
echo Comprueba que no exista un archivo o carpeta llamada mido
echo dentro de esta carpeta del proyecto.
pause
exit /b 1

:error
echo.
echo ERROR instalando dependencias. Revisa la conexion y vuelve a intentarlo.
pause
exit /b 1
