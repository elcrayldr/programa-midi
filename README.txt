# CRAY LDR MIDI DECK v0.2

Aplicación Windows para convertir un Alesis V Mini en una superficie de control tipo Stream Deck para FL Studio, Cubase, OBS y Windows.

## Estado de esta versión
- Entrada MIDI seleccionable y monitor en directo.
- Pads configurables por perfil: atajo, abrir programa/archivo/carpeta, URL, texto o macro.
- Knobs CC14, CC15, CC16 y CC17 detectados y configurables por separado.
- Remapeo de CC de entrada a CC de salida, canal, rango mínimo/máximo y puerto MIDI de salida.
- Gestor de perfiles integrados y personalizados.
- Editor de macros multipaso con esperas mediante wait:milisegundos.
- Configuración persistente en %APPDATA%\\CrayLDR\\MidiDeck\\config.json.

## MIDI y FL Studio / Cubase
Los cuatro knobs identificados en el Alesis V Mini envían CC14–17 en canal 1. La aplicación puede reenviarlos por un puerto MIDI de salida, por ejemplo un puerto virtual creado con loopMIDI.

1. Instala y abre loopMIDI; crea un puerto virtual.
2. En MIDI DECK, actualiza Salida MIDI, selecciona el puerto y pulsa Abrir salida.
3. En FL Studio o Cubase, selecciona ese puerto como entrada MIDI.
4. Usa MIDI Learn o la función de asignación del DAW para vincular cada CC al parámetro deseado.

La aplicación no asigna directamente parámetros internos de plugins VST: esa vinculación debe realizarse desde el DAW.

## Configurar knobs
En Configurar knobs puedes modificar para cada control el CC y canal de entrada, CC y canal de salida, y valor mínimo/máximo. El valor de entrada 0–127 se escala al rango de salida elegido. La casilla Enviar CC14–17 debe estar activada y el puerto de salida abierto para reenviar datos.

## Pads
Las notas 36, 38, 42 y 46 son las observadas en las pruebas iniciales. Verifica cada pad físicamente en el monitor antes de asignarle una acción definitiva.

Tipos: none, shortcut, open, url, text y macro.

Ejemplo de macro:

    shortcut:ctrl+s
    wait:300
    open:C:\\Windows\\System32\\notepad.exe
    wait:500
    text:Texto de prueba

Esperas admitidas: wait:milisegundos (0–10000 ms).

## Perfiles
Incluye GLOBAL, FL Studio, Cubase, OBS y Windows. Puedes crear perfiles adicionales desde Perfiles. La detección automática identifica procesos conocidos; los perfiles personalizados quedan disponibles para asignación manual, pero todavía no tienen detección automática por ejecutable.

## Instalación
Requisitos: Windows 10/11 de 64 bits y Python 3.12.

1. Instala Python 3.12 de 64 bits.
2. Ejecuta INSTALL_DEPENDENCIES.bat.
3. Ejecuta RUN_MIDI_DECK.bat.
4. Selecciona Alesis V Mini y pulsa Conectar.

## Crear EXE
Ejecuta BUILD_EXE.bat. El ejecutable quedará en dist\\CRAY_LDR_MIDI_DECK.exe. También se añade un workflow de GitHub Actions para compilar en Windows y publicar un artefacto. Solo se considera validada la compilación cuando el workflow termina correctamente.

## Limitaciones conocidas
- La asignación de controles dentro de FL Studio/Cubase se completa desde el propio DAW usando el puerto MIDI virtual.
- Los perfiles personalizados no se detectan automáticamente por proceso todavía.
- Inicio automático con Windows aún no está implementado.
- No se ha validado todavía en el ordenador físico del usuario tras los últimos cambios.
- No se debe considerar lista para una sesión comercial hasta completar pruebas de pads, knobs y acciones.
