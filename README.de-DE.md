# GameToyProtocolBridge (GTPB)

**In anderen Sprachen lesen:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) ist eine **Buttplug-v3-Protokollbrücke**, mit der Spiele (z. B. MultiFunPlayer) Hardware-Geräte über WebSocket steuern können.

**Datenfluss:**

```
Spiel (MultiFunPlayer usw.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → analysieren / mappen / transformieren → Intiface Central → Toy-Hardware
```

## Funktionen

- **WebSocket- und TCP-Doppelprotokoll-Proxy** — bidirektionale Kommunikation zwischen Spielen und Intiface Central
- **Kanal-Mapping** — flexible Zuordnung von Spielkanälen zu Hardware-Aktuatoren
- **OSR6-Sechs-Achsen-Modus** — bildet die OSR6-Sechs-Achsen-Ausgabe des Spiels auf echte Hardware ab (L0 Hauptweg / L1 vor-zurück / L2 links-rechts / R0 Drehung / R1 Roll / R2 Pitch)
- **Not-Aus** — unterbricht alle Gerätebefehle mit einem Klick und sendet StopAllDevices
- **Mehrsprachigkeit** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **Profilverwaltung** — Laden, Speichern, Speichern unter für verschiedene Verbindungskonfigurationen und Kanal-Mapping-Schemata
- **Portkonflikt-Erkennung** — prüft beim Start automatisch auf Konflikte zwischen Spiel- und Backend-Port
- **Logsystem** — Systemlog, GameRx/Tx-Protokolllog, Capture-Log

## Schnellstart

### Voraussetzungen

1. [Intiface Central](https://intiface.com/central/) installieren und starten
2. Sicherstellen, dass dein Toy-Gerät über Intiface Central verbunden ist

### Ausführen

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# GUI-Modus
python main.py

# Headless-Modus
python main.py --headless

# Profil und Parameter angeben
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### Als EXE paketieren

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## Portkonfiguration (wichtig)

**Die beiden Ports müssen unterschiedlich sein!**

| Port | Standard | Beschreibung |
|------|----------|--------------|
| WebSocket-Port | 12345 | Port, an dem Spiele sich mit GTPB verbinden (Spielseitige Konvention, in der Regel unverändert) |
| Backend Intiface | ws://127.0.0.1:12346 | Port, über den GTPB sich mit Intiface Central verbindet |

Wenn beide gleich sind, gerät der Datenfluss in eine Endlosschleife. GTPB erkennt dies automatisch und warnt beim Start.

Lösung: Intiface Central → Settings → Server → Listening Port ändern (12346 empfohlen), dann auch das GTPB-„Backend Intiface“ entsprechend anpassen.

## Dateistruktur

```
gtpb-python/
├── gtpb/                    # Kernmodule
│   ├── __init__.py
│   ├── backend.py           # Intiface-Backend-Verbindung
│   ├── buttplug.py          # Buttplug-v3-Protokollanalyse
│   ├── config.py            # Konfigurationsladen (INI + JSON-Profil)
│   ├── gui.py               # Tkinter-GUI
│   ├── i18n.py              # Mehrsprachigkeit
│   ├── logs.py              # Logmanager
│   ├── mapping.py           # Kanal-Mapping-Engine
│   ├── models.py            # Datenmodelle
│   ├── proxy.py             # Brückendienst-Kern
│   ├── safety.py            # Sicherheitsmechanismus (Not-Aus)
│   └── transform.py         # Werttransformationen
├── profiles/default.json    # Standardprofil
├── tests/                   # Unit-Tests
├── tools/                   # Entwicklungs-Hilfswerkzeuge
├── configsetting.ini        # Werkskonfiguration (nicht ändern)
├── main.py                  # Programmeinstieg
└── requirements.txt         # Python-Abhängigkeiten
```

## Laufzeitdateien

| Datei | Beschreibung |
|-------|--------------|
| `profiles/*.json` | Deine Profile (Verbindungseinstellungen + Kanal-Mapping) |
| `.gtpb_settings` | Interner Zustand (Sprache, Pfad des zuletzt geladenen Profils) |
| `gtpb.log` | Rollierendes Log (10KB-Obergrenze, schneidet alte Einträge automatisch ab) |

## Befehlszeilenargumente

| Argument | Beschreibung |
|----------|--------------|
| `--headless` | Headless-Modus |
| `--profile <pfad>` | Profildatei angeben |
| `--listen <adresse>` | Lauschadresse (überschreibt Profil) |
| `--ws-port <port>` | WebSocket-Port (überschreibt Profil) |
| `--tcp-port <port>` | TCP-Port (überschreibt Profil) |
| `--backend <url>` | Backend-Intiface-Adresse (überschreibt Profil) |

## Lizenz

MIT