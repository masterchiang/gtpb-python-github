# GameToyProtocolBridge (GTPB)

**Leer en otros idiomas:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) es un **puente de protocolo Buttplug v3** que permite a los juegos (por ejemplo, MultiFunPlayer) controlar dispositivos de hardware a través de WebSocket.

**Ruta de datos:**

```
Juego (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → análisis / mapeo / transformación → Intiface Central → juguete de hardware
```

## Características

- **Proxy de protocolo doble WebSocket + TCP** — comunicación bidireccional entre juegos e Intiface Central
- **Mapeo de canales** — configuración flexible del mapeo de canales del juego a los actuadores de hardware
- **Modo de seis ejes OSR6** — mapea la salida de seis ejes OSR6 del juego al hardware real (L0 recorrido principal / L1 adelante-atrás / L2 izquierda-derecha / R0 torsión / R1 balanceo / R2 cabeceo)
- **Parada de emergencia** — bloqueo con un clic de todos los comandos de los dispositivos, envía StopAllDevices
- **Soporte multilingüe** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **Gestión de perfiles** — cargar, guardar, guardar como para diferentes configuraciones de conexión y esquemas de mapeo de canales
- **Detección de conflictos de puertos** — comprueba automáticamente al inicio los conflictos entre el puerto del juego y el del backend
- **Sistema de registro** — registro del sistema, registro de protocolo GameRx/Tx, registro de captura

## Inicio rápido

### Requisitos previos

1. Instala y inicia [Intiface Central](https://intiface.com/central/)
2. Asegúrate de que tu juguete esté conectado a través de Intiface Central

### Ejecutar

```bash
# Instalar dependencias
pip install -r requirements.txt

# Modo GUI
python main.py

# Modo sin interfaz
python main.py --headless

# Especificar perfil y parámetros
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### Empaquetar como EXE

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## Configuración de puertos (importante)

**¡Los dos puertos deben ser diferentes!**

| Puerto | Predeterminado | Descripción |
|--------|---------------|-------------|
| Puerto WebSocket | 12345 | Puerto por el que los juegos se conectan a GTPB (convención del lado del juego, normalmente sin cambios) |
| Backend Intiface | ws://127.0.0.1:12346 | Puerto por el que GTPB se conecta a Intiface Central |

Si son iguales, el flujo de datos entra en un bucle infinito. GTPB lo detecta automáticamente y advierte al iniciar.

Solución: Intiface Central → Settings → Server → cambiar el Listening Port (se recomienda 12346), y luego actualizar el «Backend Intiface» de GTPB en consecuencia.

## Estructura de archivos

```
gtpb-python/
├── gtpb/                    # Módulos principales
│   ├── __init__.py
│   ├── backend.py           # Conexión del backend Intiface
│   ├── buttplug.py          # Análisis del protocolo Buttplug v3
│   ├── config.py            # Carga de configuración (INI + perfil JSON)
│   ├── gui.py               # Interfaz gráfica Tkinter
│   ├── i18n.py              # Soporte multilingüe
│   ├── logs.py              # Gestor de registros
│   ├── mapping.py           # Motor de mapeo de canales
│   ├── models.py            # Modelos de datos
│   ├── proxy.py             # Núcleo del servicio puente
│   ├── safety.py            # Mecanismo de seguridad (parada de emergencia)
│   └── transform.py         # Transformaciones de valores
├── profiles/default.json    # Perfil por defecto
├── tests/                   # Pruebas unitarias
├── tools/                   # Herramientas de ayuda al desarrollo
├── configsetting.ini        # Configuración de fábrica (no modificar)
├── main.py                  # Punto de entrada del programa
└── requirements.txt         # Dependencias de Python
```

## Archivos en tiempo de ejecución

| Archivo | Descripción |
|---------|-------------|
| `profiles/*.json` | Tus perfiles (ajustes de conexión + mapeo de canales) |
| `.gtpb_settings` | Estado interno (idioma, ruta del último perfil cargado) |
| `gtpb.log` | Registro rotatorio (límite de 10 KB, recorta automáticamente los antiguos) |

## Argumentos de línea de comandos

| Argumento | Descripción |
|-----------|-------------|
| `--headless` | Modo sin interfaz |
| `--profile <ruta>` | Especificar archivo de perfil |
| `--listen <dirección>` | Dirección de escucha (anula el perfil) |
| `--ws-port <puerto>` | Puerto WebSocket (anula el perfil) |
| `--tcp-port <puerto>` | Puerto TCP (anula el perfil) |
| `--backend <url>` | Dirección del backend Intiface (anula el perfil) |

## Licencia

MIT