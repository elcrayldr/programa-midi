# CRAY LDR MIDI DECK v0.1

Windows 10/11 x64. Primera versión funcional de monitor MIDI y asignación de macros por perfil para Alesis V Mini.

## Qué incluye
- Selección y conexión a una entrada MIDI.
- Monitor MIDI en directo.
- Identificación de los cuatro pads observados en la captura: notas 36, 38, 42 y 46 en canal 1.
- Perfiles automáticos por proceso en primer plano: FL Studio, Cubase, OBS y Windows.
- Asignación de cada pad a: ninguna acción, atajo, abrir archivo/programa, URL, escribir texto o macro secuencial.
- Configuración guardada en `%APPDATA%\CrayLDR\MidiDeck\config.json`.
- Interfaz oscura con acentos amarillos.

## Limitaciones importantes de v0.1
- Los knobs CC14–17 se muestran como candidatos en el monitor; aún no tienen asignación de acciones. Hay que confirmar cada knob con captura aislada.
- El mapeo de pads se basa en una captura MIDI combinada; las notas 36, 38, 42 y 46 fueron observadas, pero conviene probar cada pad individualmente.
- La detección de FL Studio/Cubase/OBS se basa en el nombre del proceso y puede requerir ajuste para versiones concretas.
- Los perfiles son automáticos por ventana activa. No se inyectan comandos internos no documentados de los DAW.
- No usar macros que envíen texto o atajos mientras se está escribiendo información sensible. Prueba cada macro antes de usarla en una sesión real.
- v0.1 no instala todavía el inicio automático; esa opción se añadirá tras validar la conexión y evitar arranques duplicados.

## Instalación desde código
1. Instalar Python 3.11 o 3.12 de 64 bits desde python.org y marcar "Add Python to PATH".
2. Ejecutar `INSTALL_DEPENDENCIES.bat`.
3. Ejecutar `RUN_MIDI_DECK.bat`.
4. Seleccionar la entrada Alesis V Mini y pulsar Conectar.

## Tipos de acción
- `none`: no hacer nada.
- `shortcut`: por ejemplo `ctrl+shift+r`.
- `open`: ruta a un programa, archivo o carpeta.
- `url`: por ejemplo `https://www.lazetamusic.es`.
- `text`: texto a escribir.
- `macro`: una acción por línea:
  `shortcut:ctrl+s`
  `open:C:\Windows\System32\notepad.exe`
  `text:Texto de prueba`

Para acciones macro, separar cada acción con una línea nueva. No se admiten macros de espera personalizadas en esta versión.

## Crear EXE
Ejecutar `BUILD_EXE.bat`. El ejecutable quedará en `dist\CRAY_LDR_MIDI_DECK.exe`.
La compilación debe realizarse en Windows para obtener un ejecutable Windows fiable.
