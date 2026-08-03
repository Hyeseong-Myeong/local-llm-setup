# Local LLM System Architecture & Wiki Agent

이 문서는 사용자의 로컬 하드웨어 환경(AMD 기반)에 맞춰 최적화된 **로컬 거대 언어 모델(LLM) 구동 시스템**과 **옵시디언(Obsidian) 기반 지식 관리 자동화(Wiki Agent) 시스템**의 구성도를 정리한 문서입니다.

## 💻 하드웨어 환경 (Hardware Specifications)
- **OS:** Windows 10/11 64-bit
- **CPU:** AMD Ryzen 5 5600X 6-Core Processor (3.70 GHz)
- **RAM:** 32.0 GB
- **GPU:** AMD Radeon RX 6600 XT (8 GB VRAM)
---

## 🏗️ 시스템 아키텍처 (System Architecture)

본 시스템은 로컬 환경에서 데이터를 외부로 유출하지 않고 완벽하게 프라이빗한 AI 지식 관리 환경을 구축하도록 설계되었습니다.

### 1. 코어 백엔드 (AI Engine & Database)
* **Ollama (로컬 LLM 서버):** 
  * 사용 모델: `qwen3.5:9b` (OpenWebUI나 API 요청 파라미터를 통해 온도, 프롬프트 등 제어)
  * AMD RX 6600 XT 그래픽 카드의 하드웨어 가속(ROCm)을 사용하기 위해 시스템 부팅 시 `HSA_OVERRIDE_GFX_VERSION=10.3.0` 환경 변수를 강제로 주입하여 GPU 성능을 100% 활용합니다.
* **ChromaDB (벡터 데이터베이스):**
  * 도커(Docker Desktop) 컨테이너로 구동되며, 문서 검색 시 RAG(검색 증강 생성)를 위한 임베딩 데이터를 저장합니다.
  * Host: `.env`의 `CHROMA_HOST` / `CHROMA_PORT`로 설정 (Tailscale IP 사용)

### 2. 자동화 에이전트 (Wiki Agent & Discord Bot)
* **`discord_bot.py`:**
  * 지정된 디스코드 채널(archy 등)을 모니터링하여 웹 URL이나 메시지를 가져오고, Jina Reader 등을 통해 마크다운으로 스크래핑한 뒤 로컬 `RAW_DIR`에 저장합니다.
* **`wiki_agent.py`:**
  * Obsidian 볼트(`D:\LLM\Obsidian`)를 지속적으로 모니터링 및 관리하는 백그라운드 파이썬 에이전트입니다.
  * **프롬프트 템플릿 (`prompts.py`):** 카테고리 분류(tech, career, personal) 및 마크다운 기반의 위키 문서 자동 컴파일(태그 생성, 제목 생성, 본문 내 원문 역링크 자동 연결 등)을 수행합니다.
  * 생성된 문서 내부의 `# [키워드] 제목`을 파싱하여 동적으로 파일명을 생성하고, 기존 및 신규 문서의 RAG 역링크 구조를 호환 유지합니다.
  * **설정 관리 (`config.py` & `.env`):** 환경 변수를 통해 Vault 경로, DB 주소, Langfuse 관측(Observability) 설정을 주입받아 동작합니다.

---

## 🚀 부팅 및 실행 흐름 (Startup Sequence)

윈도우 부팅 시, 시작 프로그램 폴더에 등록된 `ai-server-start.bat` 스크립트가 다음과 같은 순서로 시스템을 조용히 자동 구성합니다.

1. **환경 변수 주입:** AMD GPU 인식 및 최적화를 위한 설정 세팅
2. **좀비 프로세스 정리:** 꼬여있는 기존 Ollama 프로세스 완전 종료
3. **Docker Desktop 구동:** 벡터 DB(Chroma) 실행을 위한 도커 컨테이너 로드 대기 (최대 30초)
4. **Ollama 백그라운드 실행:** `powershell` 명령어를 통해 CMD 창 팝업 없이 완전한 **숨김(Hidden) 상태**로 `ollama serve` 실행
5. **Discord Bot 실행:** 디스코드 채널 모니터링을 담당하는 봇을 백그라운드로 구동
6. **Wiki Agent 실행:** `pythonw.exe`를 사용하여 콘솔 창 없이 백그라운드에서 `wiki_agent.py` 실행 및 자동화 모니터링 개시

---

## 📂 주요 파일 및 디렉토리 구조

```text
C:\local_LLM\
│
├── .env                  # 모델명, DB 주소, Langfuse API 키 등 비밀 환경변수 모음
├── config.py             # .env의 환경변수를 파이썬 앱 내 설정 객체로 로드
├── prompts.py            # AI 에이전트에게 지시할 카테고리 분류 및 위키 컴파일 프롬프트
├── discord_bot.py        # 디스코드 채널(archy 등) 모니터링 및 스크래핑 봇
├── wiki_agent.py         # 핵심 백그라운드 AI 에이전트 실행 파일
├── shutdown.bat          # 관련 백그라운드 데몬(pythonw.exe) 일괄 강제 종료 스크립트
└── README.md             # 현재 문서
```

---

## 🛠️ 유지보수 및 팁

* **모델 및 프롬프트 관리:** 프롬프트, 온도, 컨텍스트 길이 등은 커스텀 Modelfile 대신 클라이언트(OpenWebUI 또는 API 요청 바디) 측에서 유연하게 주입하여 사용합니다.
* **프로세스 확인 및 종료:** 백그라운드로 돌아가고 있는 Ollama나 Wiki Agent, Discord 봇이 정상 동작하는지 확인하려면, 작업 관리자(Task Manager)의 세부 정보 탭에서 `ollama.exe` 및 `pythonw.exe`를 확인하세요.
  * 수정 사항 적용이나 중복 실행된 좀비 프로세스를 정리하려면 프로젝트 루트에 있는 **`shutdown.bat`** 스크립트를 더블클릭하여 파이썬 봇 관련 프로세스를 일괄 종료할 수 있습니다.
