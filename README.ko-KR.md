# GameToyProtocolBridge (GTPB)

**다른 언어로 읽기:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge(GTPB)는 **게임(예: MultiFunPlayer)이 WebSocket을 통해 하드웨어 장치를 제어**할 수 있게 해주는 **Buttplug v3 프로토콜 브리지**입니다.

**데이터 흐름:**

```
게임(MultiFunPlayer 등) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → 파싱 / 매핑 / 변환 → Intiface Central → 토이 하드웨어
```

## 기능

- **WebSocket + TCP 이중 프로토콜 프록시** — 게임과 Intiface Central 간의 양방향 통신 지원
- **채널 매핑** — 게임 채널에서 하드웨어 액추에이터로의 매핑을 유연하게 구성
- **OSR6 6축 모드** — 게임의 OSR6 6축 출력을 실제 하드웨어에 매핑(L0 왕복 / L1 전후 / L2 좌우 / R0 비틀기 / R1 롤 / R2 피치)
- **비상 정지** — 모든 장치 명령을 원클릭으로 차단, StopAllDevices 전송
- **다국어 지원** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **프로필 관리** — 연결 설정과 채널 매핑 구성의 로드·저장·다른 이름으로 저장
- **포트 충돌 감지** — 시작 시 게임 포트와 백엔드 포트의 충돌 자동 확인
- **로그 시스템** — 시스템 로그, GameRx/Tx 프로토콜 로그, 캡처 로그

## 빠른 시작

### 사전 요구 사항

1. [Intiface Central](https://intiface.com/central/) 설치 및 실행
2. 토이 장치가 Intiface Central을 통해 연결되어 있는지 확인

### 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# GUI 모드
python main.py

# 헤드리스 모드
python main.py --headless

# 프로필 및 매개변수 지정
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### EXE로 패키징

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## 포트 설정(중요)

**두 포트는 서로 달라야 합니다!**

| 포트 | 기본값 | 설명 |
|------|--------|------|
| WebSocket 포트 | 12345 | 게임이 GTPB에 연결하는 포트(게임 측 관례, 보통 변경 안 함) |
| 백엔드 Intiface | ws://127.0.0.1:12346 | GTPB가 Intiface Central에 연결하는 포트 |

둘이 같으면 데이터 흐름이 무한 루프에 빠집니다. GTPB는 시작 시 자동으로 감지하여 경고합니다.

해결 방법: Intiface Central → Settings → Server → Listening Port 변경(12346 권장), GTPB의「백엔드 Intiface」도 함께 변경합니다.

## 파일 구조

```
gtpb-python/
├── gtpb/                    # 핵심 모듈
│   ├── __init__.py
│   ├── backend.py           # Intiface 백엔드 연결
│   ├── buttplug.py          # Buttplug v3 프로토콜 파싱
│   ├── config.py            # 설정 로드(INI + JSON 프로필)
│   ├── gui.py               # Tkinter GUI
│   ├── i18n.py              # 다국어 지원
│   ├── logs.py              # 로그 관리자
│   ├── mapping.py           # 채널 매핑 엔진
│   ├── models.py            # 데이터 모델
│   ├── proxy.py             # 브리지 서비스 핵심
│   ├── safety.py            # 안전 메커니즘(비상 정지)
│   └── transform.py         # 값 변환
├── profiles/default.json    # 기본 프로필
├── tests/                   # 단위 테스트
├── tools/                   # 개발 보조 도구
├── configsetting.ini        # 출고 시 설정(수정하지 마세요)
├── main.py                  # 프로그램 진입점
└── requirements.txt         # Python 의존성
```

## 런타임 파일

| 파일 | 설명 |
|------|------|
| `profiles/*.json` | 프로필(연결 설정 + 채널 매핑) |
| `.gtpb_settings` | 내부 상태(언어, 마지막으로 로드한 프로필 경로) |
| `gtpb.log` | 롤링 로그(10KB 상한, 자동으로 오래된 항목 제거) |

## 명령줄 인수

| 인수 | 설명 |
|------|------|
| `--headless` | 헤드리스 모드 |
| `--profile <path>` | 프로필 파일 지정 |
| `--listen <addr>` | 리슨 주소(프로필 덮어쓰기) |
| `--ws-port <port>` | WebSocket 포트(프로필 덮어쓰기) |
| `--tcp-port <port>` | TCP 포트(프로필 덮어쓰기) |
| `--backend <url>` | 백엔드 Intiface 주소(프로필 덮어쓰기) |

## 라이선스

MIT