# GameToyProtocolBridge (GTPB)

**Lire dans d'autres langues :** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) est un **pont de protocole Buttplug v3** qui permet aux jeux (ex : MultiFunPlayer) de contrôler des périphériques matériels via WebSocket.

**Chemin des données :**

```
Jeu (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → analyse / mappage / transformation → Intiface Central → matériel de jouet
```

## Fonctionnalités

- **Proxy double protocole WebSocket + TCP** — communication bidirectionnelle entre les jeux et Intiface Central
- **Mappage de canaux** — configuration flexible du mappage des canaux du jeu vers les actionneurs matériels
- **Mode six axes OSR6** — mappe la sortie six axes OSR6 du jeu sur le matériel réel (L0 course principale / L1 avant-arrière / L2 gauche-droite / R0 torsion / R1 roulis / R2 tangage)
- **Arrêt d'urgence** — interception en un clic de toutes les commandes des périphériques, envoie StopAllDevices
- **Prise en charge multilingue** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **Gestion des profils** — charger, enregistrer, enregistrer sous pour différentes configurations de connexion et schémas de mappage de canaux
- **Détection de conflit de ports** — vérifie automatiquement au démarrage les conflits entre le port du jeu et le port du backend
- **Système de journalisation** — journal système, journal de protocole GameRx/Tx, journal de capture

## Démarrage rapide

### Prérequis

1. Installer et démarrer [Intiface Central](https://intiface.com/central/)
2. Vérifier que votre périphérique de jouet est connecté via Intiface Central

### Exécution

```bash
# Installer les dépendances
pip install -r requirements.txt

# Mode GUI
python main.py

# Mode sans interface
python main.py --headless

# Spécifier le profil et les paramètres
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### Empaqueter en EXE

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## Configuration des ports (important)

**Les deux ports doivent être différents !**

| Port | Par défaut | Description |
|------|-----------|-------------|
| Port WebSocket | 12345 | Port par lequel les jeux se connectent à GTPB (convention côté jeu, généralement inchangé) |
| Backend Intiface | ws://127.0.0.1:12346 | Port par lequel GTPB se connecte à Intiface Central |

S'ils sont identiques, le flux de données entre dans une boucle infinie. GTPB détecte automatiquement et avertit au démarrage.

Solution : Intiface Central → Settings → Server → modifier le Listening Port (12346 recommandé), puis mettre à jour le « Backend Intiface » de GTPB en conséquence.

## Structure des fichiers

```
gtpb-python/
├── gtpb/                    # Modules principaux
│   ├── __init__.py
│   ├── backend.py           # Connexion backend Intiface
│   ├── buttplug.py          # Analyse du protocole Buttplug v3
│   ├── config.py            # Chargement de la configuration (INI + profil JSON)
│   ├── gui.py               # Interface graphique Tkinter
│   ├── i18n.py              # Prise en charge multilingue
│   ├── logs.py              # Gestionnaire de journaux
│   ├── mapping.py           # Moteur de mappage de canaux
│   ├── models.py            # Modèles de données
│   ├── proxy.py             # Cœur du service de pont
│   ├── safety.py            # Mécanisme de sécurité (arrêt d'urgence)
│   └── transform.py         # Transformations de valeurs
├── profiles/default.json    # Profil par défaut
├── tests/                   # Tests unitaires
├── tools/                   # Outils d'aide au développement
├── configsetting.ini        # Configuration d'usine (ne pas modifier)
├── main.py                  # Point d'entrée du programme
└── requirements.txt         # Dépendances Python
```

## Fichiers d'exécution

| Fichier | Description |
|---------|-------------|
| `profiles/*.json` | Vos profils (paramètres de connexion + mappage de canaux) |
| `.gtpb_settings` | État interne (langue, chemin du dernier profil chargé) |
| `gtpb.log` | Journal à roulement (limite de 10 Ko, supprime automatiquement les anciens) |

## Arguments de ligne de commande

| Argument | Description |
|----------|-------------|
| `--headless` | Mode sans interface |
| `--profile <chemin>` | Spécifier le fichier de profil |
| `--listen <adresse>` | Adresse d'écoute (écrase le profil) |
| `--ws-port <port>` | Port WebSocket (écrase le profil) |
| `--tcp-port <port>` | Port TCP (écrase le profil) |
| `--backend <url>` | Adresse backend Intiface (écrase le profil) |

## Licence

MIT