
@echo off
title CRAY LDR MIDI DECK - Instalador
cd /d "%~dp0"

echo ========================================
echo       CRAY LDR MIDI DECK
echo       Instalando dependencias
echo ========================================
echo.

echo Comprobando Python 3.12...
py -3.12 --version

if errorlevel 1 (
    echo.
    echo ERROR: No se encuentra Python 3.12.
    pause
    exit /b 1
)

echo.
echo Actualizando pip para Python 3.12...
py -3.12 -m pip install --upgrade pip

echo.
echo Instalando dependencias...
py -3.12 -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR instalando dependencias.
    pause
    exit /b 1
)

echo.
echo ========================================
echo INSTALACION COMPLETADA CORRECTAMENTE
echo ========================================
pause
