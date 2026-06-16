# LLM Credit Monitor

Claude와 ChatGPT API 크레딧 사용량을 실시간으로 모니터링하는 시스템 트레이 앱입니다.

## 기능

- **시스템 트레이 아이콘** — 전체 사용률(%)을 숫자로 표시, 색상으로 단계 구분
- **컨텍스트 메뉴** — Claude / ChatGPT 각각의 오늘 사용량, 이번 달 사용량, 잔여 크레딧 즉시 확인
- **자세히 보기** — 일별 사용량 그룹 바차트(Claude 빨강 / ChatGPT 검정), 모델별 토큰·비용 통합 테이블
- **기간 선택** — 이번 달 / 지난 달 / 최근 30일
- **설정** — 서비스별 티어·한도 독립 설정, 업데이트 주기(10–600초), 로그인 시 자동 시작
- **크로스 플랫폼** — Windows 10+ / Ubuntu 20.04+

## 설치

### Windows

**인스톨러 (권장)**

[Releases](../../releases/latest) 페이지에서 `LLMCreditMonitor-Setup-x.x.x.exe` 다운로드 후 실행합니다.

**단독 실행 파일**

`LLMCreditMonitor-x.x.x-windows.exe`를 다운로드해 더블클릭으로 바로 실행합니다 (설치 불필요).

### Ubuntu / Debian

**.deb 패키지 (권장)**

```bash
sudo dpkg -i llmcreditmonitor_x.x.x_amd64.deb
sudo apt-get install -f   # 의존성 자동 해결
llmcreditmonitor &
```

**단독 실행 파일**

```bash
# 시스템 트레이 라이브러리 설치 (미설치 시)
sudo apt-get install libayatana-appindicator3-1

chmod +x LLMCreditMonitor-x.x.x-linux
./LLMCreditMonitor-x.x.x-linux &
```

## 로컬 사용량 로그 경로

앱은 로컬에 저장된 API 사용 로그를 직접 읽습니다. 별도 API 키나 네트워크 요청이 없습니다.

| 서비스 | 로그 경로 |
|---|---|
| Claude Code | `~/.claude/projects/` |
| ChatGPT (Codex) | `~/.codex/sessions/` |

## 설정

| 항목 | 설명 | 기본값 |
|---|---|---|
| 티어 | Tier1 / Tier2 / Tier3 / Tier4 / Tier4 Half | Tier4 |
| 월 크레딧 한도 | 티어 선택 시 자동 입력, 직접 수정 가능 | $5,000 |
| 업데이트 주기 | 10 – 600초 | 60초 |
| 자동 시작 | 로그인 시 자동 실행 여부 | 꺼짐 |

설정 파일 위치:

- **Windows**: `%APPDATA%\LLMCreditMonitor\config.json`
- **Linux**: `~/.config/llmcreditmonitor/config.json`

## 개발 환경 설정

```bash
git clone https://github.com/kost0806/llm-credit-monitor.git
cd llm-credit-monitor

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
python -m app.main
```

**디버그 모드**

```bash
python -m app.main --debug    # 상세 로그 출력
python -m app.main --mock     # 실제 로그 없이 모의 데이터로 동작
python -m app.main --headless # 트레이 없이 터미널에 스냅샷 출력
```

## 빌드

### Windows

```powershell
pip install pyinstaller
python -m PyInstaller --clean build/llmcreditmonitor.spec

# 인스톨러 (Inno Setup 필요)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=x.x.x build\installer.iss
```

### Ubuntu

```bash
sudo apt-get install fakeroot dpkg-dev libayatana-appindicator3-1
pip install pyinstaller
bash build/build_linux.sh x.x.x
```

### GitHub Actions (자동 릴리즈)

Actions 탭 → **Release** → **Run workflow** → bump 유형 선택 (patch / minor / major).  
버전 태그를 자동 생성하고 Windows·Ubuntu 빌드를 병렬로 수행한 뒤 단일 GitHub Release에 첨부합니다.

## 라이선스

MIT
