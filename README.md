# Local LLM Setup

Windows 데스크톱에서 로컬 LLM 서비스를 구축한 프로젝트입니다.
외부 API 의존 없이 자체 하드웨어에서 다중 모델을 운영하고,
용도에 따라 자동으로 최적 모델을 선택하는 라우팅 시스템을 구현했습니다.

## 하드웨어 환경

| 항목 | 사양 |
|------|------|
| CPU | AMD Ryzen 5 5600X |
| GPU | AMD RX 6600 XT (VRAM 8GB) |
| RAM | 32GB |
| OS | Windows 10 |

## 아키텍처
사용자 (브라우저 / Tailscale 외부 접속)
↓
Open WebUI (Docker, port 3000)
↓
LLM Router (Open WebUI Filter Function)
├─ 키워드 분류 → 로컬 모델 선택
├─ 슬래시 명령 → 모델 강제 지정
└─ /gemini    → Google Gemini API
↓
Ollama (port 11434, Vulkan GPU 가속)
├─ llm-coder  (Qwen2.5-Coder 7B)
├─ llm-exaone (EXAONE Deep 7.8B)
├─ llm-qwen3  (Qwen3 8B)
└─ llm-r1     (DeepSeek-R1 7B)


## 기술 스택

- **Ollama** — 로컬 LLM 런타임, Vulkan 백엔드로 AMD GPU 가속
- **Open WebUI** — 채팅 프론트엔드, Functions로 라우팅 로직 삽입
- **Docker** — Open WebUI 컨테이너 격리 실행
- **Tailscale** — VPN 기반 외부 접속 (MagicDNS)
- **Google Gemini API** — 고난이도 작업 외부 API 폴백

## 모델 선택 근거

8GB VRAM 제약 하에서 각 용도별 최적 모델을 선택했습니다.

| 모델 | 용도 | 선택 근거 |
|------|------|-----------|
| Qwen2.5-Coder 7B Q4_K_M | 코딩 / 기본 응답 | 코딩 특화 파인튜닝, 상주 모델로 빠른 응답 |
| EXAONE Deep 7.8B | 한국어 문서 | LG AI Research 한국어 특화 모델 |
| Qwen3 8B | 복잡한 추론 | Thinking mode ON/OFF 전환 가능, Qwen2.5-14B 동급 성능 |
| DeepSeek-R1 7B | 수학 / 논리 | R1 추론 DNA 증류, `<think>` 블록으로 추론 과정 투명화 |
| nomic-embed-text | RAG 임베딩 | 경량 임베딩 모델, Ollama 네이티브 |

## LLM Router 설계

핵심 구현물입니다. Open WebUI Filter Function으로 동작하며
매 요청마다 최적 모델을 선택합니다.

### 라우팅 우선순위
/gemini /claude → 외부 API 직접 전달
/coder /exaone 등 → 슬래시 명령으로 모델 강제 지정
파일 첨부 감지 → 현재 모델 유지 (RAG 모드)
키워드 매칭 → 즉시 분류 (LLM 호출 없음)
미매칭 → 기본값 llm-coder

### 설계 의사결정: LLM 분류 → 키워드 분류

초기 설계에서는 분류 자체에 LLM을 호출했습니다.
매 요청마다 llm-coder에 분류 요청을 보내는 방식으로,
정확도는 높지만 **5~10초의 오버헤드**가 발생했습니다.

이를 키워드 기반 즉시 분류로 교체해 오버헤드를 제거했습니다.
정확도가 필요한 경우 `/gemini` 슬래시 명령으로 외부 API를 직접 호출하도록
사용자에게 선택권을 부여했습니다.

### 슬래시 명령

| 명령 | 동작 |
|------|------|
| `/coder` | Qwen2.5-Coder 강제 지정 |
| `/exaone` | EXAONE Deep 강제 지정 |
| `/qwen3` | Qwen3 (추론 모드) 강제 지정 |
| `/r1` | DeepSeek-R1 강제 지정 |
| `/gemini` | Gemini 2.5 Flash 호출 |
| `/claude` | Claude API (추후 연결 예정) |

## 레포 구조
├── functions/
│   ├── llm_router.py            # 자동 라우팅 Filter Function (핵심)
│   └── google_genai_manifold.py # Gemini API 연동 Manifold Function
│
├── modelfiles/
│   ├── Modelfile.coder          # Qwen2.5-Coder 시스템 프롬프트 + 파라미터
│   ├── Modelfile.exaone         # EXAONE Deep 설정
│   ├── Modelfile.qwen3          # Qwen3 설정
│   └── Modelfile.r1             # DeepSeek-R1 설정
│
├── prompts/
│   ├── coder.md                 # 코딩 모델 시스템 프롬프트
│   ├── exaone.md                # 한국어 모델 시스템 프롬프트
│   ├── qwen3.md                 # 추론 모델 시스템 프롬프트
│   └── r1.md                    # R1 모델 시스템 프롬프트
│
├── agents/                      # 추후 에이전트 구현 예정
│
└── scripts/
├── start.ps1                # 스택 자동 시작 스크립트
└── setup.ps1                # 신규 PC 초기 설치 스크립트


## 설치 방법

### 사전 요구사항

- [Ollama](https://ollama.com/download) 설치
- [Docker Desktop](https://www.docker.com/products/docker-desktop) 설치
- [Tailscale](https://tailscale.com/download) 설치 (외부 접속 시)

### 설치

```powershell
# 1. 레포 클론
git clone https://github.com/Hyeseong-Myeong/local-llm-setup.git
cd local-llm-setup

# 2. 설치 스크립트 실행
# setup.ps1 상단의 $ConfigDir 경로를 본인 환경에 맞게 수정 후 실행
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1
```

### Open WebUI Functions 등록

설치 완료 후 `http://localhost:3000` 접속 → Admin Panel → Functions에서
`functions/llm_router.py`와 `functions/google_genai_manifold.py` 코드를 붙여넣어 등록합니다.

## 성능

RX 6600 XT (Vulkan) 기준 측정값입니다.

| 모델 | eval rate | VRAM 사용 |
|------|-----------|-----------|
| llm-coder | ~28 tok/s | ~6.5GB |
| llm-exaone | ~26 tok/s | ~6.5GB |
| llm-qwen3 | ~25 tok/s | ~6.5GB |
| llm-r1 | ~25 tok/s | ~6.5GB |
