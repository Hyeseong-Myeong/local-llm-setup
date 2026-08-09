# Local LLM Stack

Windows 데스크톱(AMD RX 6600 XT, 8GB VRAM)에서 로컬 LLM을 자체 운영하며,
Obsidian 지식 관리와 Discord 자동화를 결합한 개인용 AI 인프라 프로젝트입니다.
외부 API 의존을 최소화하되, 로컬 모델의 한계(긴 컨텍스트, 멀티파일 리팩토링 등)는
Bifrost 게이트웨이를 통해 클라우드 API로 폴백합니다.

## 아키텍처

```
사용자 (브라우저 / Discord / Tailscale 외부 접속)
        │
        ├── Open WebUI (Docker) ──────────┐
        │                                 │
        └── Discord Bot (discord_bot.py)  │
                    │                     ▼
                    ▼              Bifrost Gateway (Docker, :8080)
            RAW_DIR (스크래핑 원문)        │
                    │           ┌─────────┼─────────┬──────────┐
                    ▼           ▼         ▼          ▼          ▼
            Wiki Agent      Ollama    Gemini      Groq /     Anthropic
          (wiki_agent.py)  (로컬 모델)  (클라우드)  Cerebras /   (클라우드)
                    │                              Mistral
                    ▼
            ChromaDB (RAG 벡터 DB)
                    ▲
                    │
      FastAPI Wiki Tool Server (fastapi_wiki_server.py)
                    │
              Open WebUI Tool 연동
```

- **Bifrost**: Ollama(로컬)/Gemini/Groq/Cerebras/Mistral/Anthropic을 하나의 게이트웨이 뒤로 통합. Langfuse로 OTel 트레이싱 연동.
- **Ollama**: 로컬 LLM 런타임 (Vulkan 백엔드로 AMD GPU 가속)
- **Wiki Agent**: LangGraph 기반 파이프라인(classify → clean → compile)으로 스크래핑 원문을 Obsidian 위키 문서로 자동 컴파일, ChromaDB에 RAG 인덱싱
- **Discord Bot**: 지정 채널의 URL/메시지를 비동기로 스크래핑해 원문 저장
- **FastAPI Wiki Tool Server**: Open WebUI와 표준 OpenAPI로 연동되는 위키 검색 툴 서버

## 모델 라인업 (Bifrost 기준)

| 역할 | 모델 | Provider |
|---|---|---|
| 기본 대화 | `qwen3.5:9b` | Ollama (로컬) |
| 코딩 | `qwen2.5-coder:7b` | Ollama (로컬) |
| 비전 | `gemma4:e4b` | Ollama (로컬) |
| 임베딩 | `bge-m3` | Ollama (로컬) |
| RAG 폴백 | `exaone4.0:1.2b` | Ollama (로컬) |
| 면접/추론 | `deepseek-r1:14b` | Ollama (로컬) |
| 클라우드 폴백 | Gemini 1.5 Pro/Flash, Claude 3.5 Sonnet, Llama3 (Groq/Cerebras), Codestral (Mistral) | 각 API |

## 레포 구조

```
├── .github/
│   ├── workflows/pipeline.yml  # CI: secret-scan/lint/codeql(병렬) → impact-analysis, performance(독립)
│   └── dependabot.yml           # pip/github-actions/bifrost docker 이미지 자동 업데이트
├── bifrost/            # Bifrost 게이트웨이 설정 (bifrost.yaml, docker-compose.yml, start_bifrost.py)
├── src/
│   ├── agent/          # discord_bot.py, wiki_agent.py
│   ├── tools/           # fastapi_wiki_server.py (Open WebUI 툴 서버)
│   ├── scripts/         # recreate_db.py, reembed_chroma.py (ChromaDB 유지보수)
│   ├── config.py        # .env 기반 설정 (pydantic-settings)
│   ├── logger_setup.py  # UTF-8 안전 로거 + 로테이션
│   └── prompts.py       # Wiki Agent 분류/컴파일 프롬프트
├── scripts/             # CI 보조 스크립트 (impact_analysis.py, benchmark_bifrost.py)
├── archive/             # 폐기된 이전 구현체 (참고용)
├── Docs/                # 아키텍처, 튜닝 가이드, 트러블슈팅 로그, 로드맵
├── requirements.txt / pyproject.toml  # 의존성 명세 및 ruff lint 설정
└── restart.bat / shutdown.bat  # 백그라운드 프로세스 및 Bifrost 컨테이너 재시작/종료
```

## 설치 및 실행

### 사전 요구사항
- [Ollama](https://ollama.com/download)
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Python 3.11+
- [Tailscale](https://tailscale.com/download) (외부 접속 시)

### 설정
```powershell
cp .env.example .env
# .env에 VAULT_PATH, CHROMA_HOST/PORT, DISCORD_BOT_TOKEN, BIFROST_*, 각 API 키 등을 채워 넣습니다.
```

### Bifrost 게이트웨이 시작
```powershell
python bifrost/start_bifrost.py
```

### 위키 에이전트 / Discord 봇 / 툴 서버 실행
```powershell
python src/agent/wiki_agent.py
python src/agent/discord_bot.py
python src/tools/fastapi_wiki_server.py
```

### 전체 스택 재시작/종료
```powershell
.\restart.bat
.\shutdown.bat
```
자동 배포는 없습니다 — `main`이 바뀌면(예: 다른 기기에서 머지) `git pull` 후 위 `restart.bat`을 직접 실행해 반영하세요.

## 더 자세한 내용

- [`Docs/README.md`](Docs/README.md) — 전체 시스템 구성도 상세 설명
- [`Docs/model_tuning.md`](Docs/model_tuning.md) — 모델별 파라미터 튜닝 가이드
- [`Docs/llm_webui_config.md`](Docs/llm_webui_config.md) — Open WebUI 커스텀 설정 가이드
- [`Docs/troubleshooting.md`](Docs/troubleshooting.md) — 운영 중 발생한 에러/해결 로그
- [`Docs/implementation_plan.md`](Docs/implementation_plan.md) — 확장 로드맵
- [`Docs/persona_prompts_reference.md`](Docs/persona_prompts_reference.md) — 이전 버전 페르소나 프롬프트 아카이브
