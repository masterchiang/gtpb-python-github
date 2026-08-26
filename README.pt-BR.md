# GameToyProtocolBridge (GTPB)

**Leia em outros idiomas:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) é uma **ponte de protocolo Buttplug v3** que permite que jogos (por exemplo, MultiFunPlayer) controlem dispositivos de hardware via WebSocket.

**Caminho dos dados:**

```
Jogo (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → análise / mapeamento / transformação → Intiface Central → brinquedo de hardware
```

## Recursos

- **Proxy de protocolo duplo WebSocket + TCP** — comunicação bidirecional entre jogos e Intiface Central
- **Mapeamento de canais** — configuração flexível do mapeamento dos canais do jogo para os atuadores de hardware
- **Modo de seis eixos OSR6** — mapeia a saída de seis eixos OSR6 do jogo para o hardware real (L0 curso principal / L1 frente-traz / L2 esquerda-direita / R0 torção / R1 rotação / R2 inclinação)
- **Parada de emergência** — intercepta todos os comandos dos dispositivos com um clique, envia StopAllDevices
- **Suporte multilíngue** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **Gerenciamento de perfis** — carregar, salvar, salvar como para diferentes configurações de conexão e esquemas de mapeamento de canais
- **Detecção de conflito de porta** — verifica automaticamente na inicialização conflitos entre a porta do jogo e a do backend
- **Sistema de registro** — registro do sistema, registro de protocolo GameRx/Tx, registro de captura

## Início rápido

### Pré-requisitos

1. Instale e inicie o [Intiface Central](https://intiface.com/central/)
2. Certifique-se de que seu brinquedo esteja conectado via Intiface Central

### Executar

```bash
# Instalar dependências
pip install -r requirements.txt

# Modo GUI
python main.py

# Modo sem interface
python main.py --headless

# Especificar perfil e parâmetros
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### Empacotar como EXE

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## Configuração de portas (importante)

**As duas portas devem ser diferentes!**

| Porta | Padrão | Descrição |
|-------|--------|-----------|
| Porta WebSocket | 12345 | Porta pela qual os jogos se conectam ao GTPB (convenção do lado do jogo, geralmente inalterada) |
| Backend Intiface | ws://127.0.0.1:12346 | Porta pela qual o GTPB se conecta ao Intiface Central |

Se forem iguais, o fluxo de dados entra em um loop infinito. O GTPB detecta automaticamente e avisa na inicialização.

Solução: Intiface Central → Settings → Server → alterar Listening Port (recomendado 12346) e depois atualizar o «Backend Intiface» do GTPB de acordo.

## Estrutura de arquivos

```
gtpb-python/
├── gtpb/                    # Módulos principais
│   ├── __init__.py
│   ├── backend.py           # Conexão backend Intiface
│   ├── buttplug.py          # Análise do protocolo Buttplug v3
│   ├── config.py            # Carregamento de configuração (INI + perfil JSON)
│   ├── gui.py               # Interface gráfica Tkinter
│   ├── i18n.py              # Suporte multilíngue
│   ├── logs.py              # Gerenciador de registros
│   ├── mapping.py           # Mecanismo de mapeamento de canais
│   ├── models.py            # Modelos de dados
│   ├── proxy.py             # Núcleo do serviço de ponte
│   ├── safety.py            # Mecanismo de segurança (parada de emergência)
│   └── transform.py         # Transformações de valores
├── profiles/default.json    # Perfil padrão
├── tests/                   # Testes unitários
├── tools/                   # Ferramentas de ajuda ao desenvolvimento
├── configsetting.ini        # Configuração de fábrica (não modificar)
├── main.py                  # Ponto de entrada do programa
└── requirements.txt         # Dependências Python
```

## Arquivos em tempo de execução

| Arquivo | Descrição |
|---------|-----------|
| `profiles/*.json` | Seus perfis (configurações de conexão + mapeamento de canais) |
| `.gtpb_settings` | Estado interno (idioma, caminho do último perfil carregado) |
| `gtpb.log` | Registro rotativo (limite de 10 KB, remove automaticamente os antigos) |

## Argumentos de linha de comando

| Argumento | Descrição |
|-----------|-----------|
| `--headless` | Modo sem interface |
| `--profile <caminho>` | Especificar arquivo de perfil |
| `--listen <endereço>` | Endereço de escuta (substitui o perfil) |
| `--ws-port <porta>` | Porta WebSocket (substitui o perfil) |
| `--tcp-port <porta>` | Porta TCP (substitui o perfil) |
| `--backend <url>` | Endereço backend Intiface (substitui o perfil) |

## Licença

MIT