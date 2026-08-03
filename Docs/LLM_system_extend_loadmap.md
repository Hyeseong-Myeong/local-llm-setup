# 🔭 로컬 LLM 시스템 확장 로드맵 v3 — 최종 확정본

> 선행 문서: `로컬 LLM 시스템 최대화 가이드.md`
> 대상 하드웨어: Ryzen 5 5600X / 32GB RAM / RX 6600 XT 8GB VRAM (ROCm gfx1032)
> 기준일: 2026-07-15

---

## 1. 하드웨어 한계와 로컬 모델 재선정

최종 피드백을 반영하여 8GB VRAM 환경에 맞춘 현실적인 모델 운용 전략을 확정합니다.

### 1-1. `qwen3-coder:30b-a3b` 구동 불가 및 대안
*   **현재 상태:** `ollama list` 확인 결과 미설치 상태입니다.
*   **하드웨어 한계:** RX 6600 XT (8GB VRAM)에서는 30B 모델(양자화 시 17~22GB 요구)을 VRAM에 온전히 올릴 수 없습니다. 시스템 RAM(32GB)으로 오프로딩하면 초당 2~15토큰의 극심한 속도 저하가 발생하여 실사용이 어렵습니다.
*   **✅ 최종 대안:** 코딩 메인 로컬 모델을 VRAM에 쾌적하게 안착하는 **`qwen2.5-coder:7b`** (또는 기존 설치된 `qwen3.5:9b`)로 하향 조정합니다. 

### 1-2. 비전 모델(VLM)과 LLM의 순차 처리
*   **한계:** 8GB VRAM에서 LLM(모의면접 대화용)과 VLM(`gemma4:e4b` 영상 분석용)을 동시에 구동하면 VRAM 초과로 크래시가 발생합니다.
*   **✅ 확정 아키텍처:**
    *   **실시간 면접 (Ping-pong):** 텍스트 기반 LLM + `faster-whisper`(음성 인식)만 구동하여 실시간 꼬리질문과 대화를 진행합니다.
    *   **종료 후 평가 (순차 처리):** 면접이 완전히 종료된 후, LLM을 메모리에서 내리고 VLM(`gemma4:e4b`)을 올려 녹화된 영상을 바탕으로 발표 태도와 논리 구조를 일괄 평가합니다.

### 1-3. 최종 모델 라인업 (설치 필요)
*   **임베딩 교체:** `bge-m3` (ChromaDB 기본 모델 대체, 한국어 검색 품질 향상)
*   **비전/1차 분류:** `gemma4:e4b`
*   **코딩 보조:** `qwen2.5-coder:7b` (30B 대안)

---

## 2. 에이전트 프레임워크 & 게이트웨이

### 2-1. 에이전트 프레임워크 (PydanticAI 배제)
**PydanticAI를 별도 프레임워크로 도입하지 않습니다.** 
*   **메인 오케스트레이터:** **LangGraph** (상태 분기, 재진입, Human-in-the-loop)
*   **출력 스키마 검증:** `pydantic` 라이브러리 자체 + LangChain의 `with_structured_output`으로 완벽히 대체.
*   **기타 보조:** CrewAI (빠른 프로토타이핑), Google ADK Java (포트폴리오 다각화), Hermes Agent (상시구동 PoC)

### 2-2. Bifrost 게이트웨이 및 OTel 관측성
**Bifrost**를 메인 게이트웨이로 확정하고(LiteLLM은 배제), OpenTelemetry(OTel) 플러그인을 활성화하여 Langfuse와 연동합니다.
*   **OTel 활용 6대 기능:** ① 요청별 비용 추적, ② 모델별 응답 속도 비교, ③ 에이전트 디버깅 (스팬 추적), ④ 폴백 체인 모니터링, ⑤ 프롬프트/응답 기록, ⑥ 로컬 모델 품질 추세 확인.

> **[설계 변경 기록: 2026-07-15]**
> *   **수정 내역:** Bifrost 설정을 파일(`yaml`) 주입 방식에서 **SQLite DB 영구 보존(Volume Mount) + Web UI 입력** 방식으로 전면 수정했습니다. (`bifrost.yaml` 파일 폐기)
> *   **수정 사유:** Bifrost 최신 버전(v1.6+)은 더 이상 YAML 설정 파일을 지원하지 않으며 내부 SQLite(`config.db`)로만 구동됩니다. 매번 환경변수나 스크립트로 임포트할 경우 보안 취약점(Admin 세션 처리)과 재시작 시 초기화 문제가 발생하므로, `- ./data:/app/data` 볼륨을 마운트하여 Web UI에서 단 한 번만 영구적으로 설정하도록 아키텍처 결함을 바로잡았습니다.
> *   **네트워크 연동 확정:** Bifrost(Go 엔진)에서 윈도우 호스트(Ollama) 접속 시 발생하는 SSRF 차단 및 DNS(`host.docker.internal`) 해석 실패 버그를 피하기 위해, 설정에서 **`Allow Private Network`**를 켜고 도메인 대신 Raw IP(**`192.168.65.254`**)를 직접 입력하도록 연동 규격을 확정했습니다.

---

## 3. 작업별 하이브리드 라우팅 맵 (최종)

프라이버시가 중요한 `#personal`, `#career` 데이터는 로컬과 유료 API만 허용하며, 공개 기술 문서는 무료 API를 적극 활용하되 **로컬 LLM을 우선**하여 프롬프트 성숙도를 높입니다.

| 작업 | 1순위 모델 | 폴백 / 2차 평가 |
|---|---|---|
| 일상 코딩 보조 | 로컬 `qwen2.5-coder:7b` | Groq 무료 → Mistral Codestral 무료 |
| 멀티파일 리팩토링 | Gemini Pro (8월 무료) | Sonnet 5 API |
| 아키텍처 설계 / 다이어그램 | Gemini Pro / Gemini 3.5 Flash | Sonnet 5 |
| 코드리뷰 (pre-push) / 단답 | Groq 무료 (Llama 3) / Haiku 4.5 | Cerebras 무료 |
| 위키 분류 / RAG 질의응답 | 로컬 `qwen3.5:9b` / `exaone4.0:1.2b` | — |
| 야간 배치 요약 / 복습 질문 | Cerebras / SambaNova 무료 | — |
| 모의면접 **실시간 대화** | 로컬 `deepseek-r1:14b` | — |
| 모의면접 **종료 후 종합 평가** | Sonnet 5 API + 로컬 VLM(`gemma4:e4b`) | — |
| 이력서 최종 첨삭 | Claude Code / Sonnet 5 (수동) | — |

---

## 4. 확장 기능 아키텍처

### 4-1. 📊 포트폴리오 자동 생성
*   **편집 도구:** 현재 IDE (Antigravity / VSCode) 통합 환경 사용.
*   **출력 형식:** 프로젝트 디렉토리 내 마크다운 + HTML 이중 출력. (Human-in-the-loop 리뷰 후 확정)

### 4-2. 🧠 간격 반복 학습 (5계층 면접 + SM-2)
*   **저장소:** ChromaDB (카드 본문 벡터 검색) + PostgreSQL (난이도, 점수, 복습일 등 구조화 메타데이터).
*   **진행 루프:** 
    1. **실시간 면접:** 텍스트/음성(`faster-whisper`)으로 꼬리질문 핑퐁 (로컬 LLM 단독 구동).
    2. **종료 후 평가:** VRAM 비운 뒤 VLM(`gemma4:e4b`)으로 영상 분석 + Sonnet 5로 종합 채점.
    3. **저장 및 반복:** 점수 기반 SM-2 알고리즘으로 다음 복습일 계산 (PostgreSQL 저장).

### 4-3. 🔍 CI/CD "적대적 검증" 파이프라인 (Velog 방법론 반영)
GitHub Actions에 Semgrep(SAST), Trivy(SCA), Gitleaks(시크릿) 등 전통적 보안 검사를 구성하고, **AI 영향도 분석은 180개 에이전트 투표 논문을 변형한 '적대적 검증 구조'로 설계**합니다.

1. **파인더 (Fan-out):** 로컬 LLM(또는 Groq) 10여 개가 각각 '보안', '성능', '도메인', '로직' 등 **직교하는 렌즈**를 장착하고 PR diff를 병렬 스캔.
    *   *제약:* 환각 방지를 위해 JSON 스키마 강제 (`file`, `line`, `evidence`), "확신 없으면 빈 배열 반환 허용" 프롬프트 적용.
2. **검증자 (적대적 투표):** Haiku 4.5 또는 Gemini Flash가 **"이 발견을 반박하라. 불확실하면 기각하라"**는 프롬프트를 바탕으로 파인더의 버그를 공격. 반박에 **실패한 버그만 생존**. (오탐률 0 목표)
3. **재검증 (Half-fix 방지):** 개발자가 코드를 수정하면 검증자가 4상한 시뮬레이션으로 수리가 완벽한지, 다른 곳을 깨뜨리지 않았는지(Regression) 재확인.
4. **결과 게시:** 생존한 진짜 버그만 PR 코멘트로 자동 게시.

### 4-4. 📈 JD 매칭: 기존 MCP + 국내 플랫폼 확장
*   **기반:** `job-search-mcp` (PJW2004) 기존 서버 채택 (잡코리아 + 사람인 스크래핑 지원).
*   **확장 (원티드, 점핏, 캐치):** 
    *   **원티드(Wanted):** 공식 OpenAPI 발급 받아 플러그인 형태로 추가.
    *   **점핏 / 캐치:** 공식 API 부재 시 `Firecrawl` 기반 웹 스크래핑 MCP 서버를 병용하거나 `job-search-mcp`를 Fork 하여 Playwright 스크래핑 로직을 추가 개발합니다.
*   **매칭 파이프라인:** 수집 → JD 파싱(Groq) → 개인 위키 매칭(로컬 MCP) → 매칭률 및 약점 리포트 생성 → 복습 카드로 약점 자동 주입.

---

## 5. 실행 로드맵 (Execution Plan)

| 단계 | 작업 내용 |
|---|---|
| **Phase 1: 인프라 & 기본 모델 세팅** | 1. 모델 Pull: `qwen2.5-coder:7b`, `bge-m3`, `gemma4:e4b` <br> 2. Bifrost 게이트웨이 Docker 배포 (SQLite DB 영구 보존용 `./data:/app/data` 볼륨 마운트 추가) <br> 3. Web UI(`localhost:8080`)를 통한 Provider(Ollama, Groq, Cerebras 등) 및 Langfuse 모니터링 연동 (YAML 방식 폐기) |
| **Phase 2: RAG 기반 고도화** | 4. ChromaDB 기존 컬렉션 완전 삭제 후 `bge-m3`로 전체 재임베딩 <br> (*`bge-m3`의 용량이 0.5GB에 불과하여 8GB VRAM 내에서 Qwen과 **스위칭 없이 병렬 적재**됨을 확인. 고성능 Ollama 임베딩 유지*) <br> 5. 공식 `mcp` 기반의 **FastMCP 위키 서버 (SSE 방식)** 구축 및 WebUI 클라이언트 연결 |
| **Phase 3: CI/CD & 매칭 자동화** | 6. 적대적 검증 파이프라인 (보안 스크립트 + LangGraph 검증망) GitHub Actions 연동 <br> 7. `job-search-mcp` 구동 및 원티드(API)/점핏 스크래핑 확장 개발 |
| **Phase 4: 에이전트 서비스** | 8. 실시간 모의면접(음성) 및 순차 평가(VLM) 루프 구현 <br> 9. 포트폴리오 자동 생성 IDE 파이프라인 적용 |

모든 미결정 사항이 확정되었습니다. 이 문서를 바탕으로 Phase 1의 모델 설치 및 게이트웨이 배포부터 실행을 시작합니다.