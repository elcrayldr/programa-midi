
@echo off
title CRAY LDR MIDI DECK
cd /d "%~dp0"

echo Iniciando CRAY LDR MIDI DECK con Python 3.12...
py -3.12 main.py

if errorlevel 1 (
    echo.
    echo ERROR al iniciar CRAY LDR MIDI DECK.
    pause
)
