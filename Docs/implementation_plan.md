# 🔭 로컬 LLM 시스템 확장 로드맵 v3.2 — 2차 피드백 반영 최종본

> 기반 문서: [로컬 LLM 시스템 최대화 가이드.md](file:///c:/local_LLM/Docs/로컬%20LLM%20시스템%20최대화%20가이드.md), [LLM_system_extend_loadmap.md](file:///c:/local_LLM/Docs/LLM_system_extend_loadmap.md)
> 기준일: 2026-07-15

---

## 1. 에이전트 프레임워크

### 1-1. PydanticAI — 별도 프레임워크로 도입 불필요

> **질문: "너무 프레임워크가 많게 느껴지는데 어디에 사용하나요?"**

**결론: PydanticAI를 별도 프레임워크로 도입하지 않습니다.** 그 기능은 이미 다른 방법으로 충족됩니다.

| PydanticAI가 하는 일 | 대체 방법 (추가 프레임워크 없이) |
|---|---|
| LLM 출력을 Pydantic 스키마로 검증 | LangGraph 노드에서 `model.with_structured_output(PydanticModel)` — LangChain에 이미 내장 |
| 검증 실패 시 자동 재시도 | LangGraph 노드에 `try/except` + 재시도 엣지(edge)로 직접 구현 (3~5줄) |
| 타입 안전한 에이전트 응답 | `pydantic` 라이브러리 자체(이미 설치됨)로 스키마 정의 → 별도 프레임워크 불필요 |

### 1-2. 최종 프레임워크 목록 (4종 → 3종 + 1라이브러리)

| 프레임워크 | 역할 | 언어 |
|---|---|---|
| **LangGraph** | 메인 오케스트레이터 | Python |
| **CrewAI** | 빠른 프로토타이핑 (Python 스택 내) | Python |
| **Google ADK** | 포트폴리오 다각화용 독립 프로젝트 | **Java** |
| **Hermes Agent** | 상시 구동 자기학습 에이전트 PoC | Python |
| ~~PydanticAI~~ | ❌ **제거** — `pydantic` 라이브러리로 대체 | — |

```
선택 기준표 (최종):

1. 상태 분기·재진입·checkpointing 필요?  ──→ LangGraph
2. 역할 분담형 프로토타입을 하루만에?      ──→ CrewAI
3. Java로 구현해서 포트폴리오에?          ──→ Google ADK Java
4. 상시 구동, 자기학습, 다플랫폼 연동?    ──→ Hermes Agent (실험)
5. 단순 선형 파이프라인?                  ──→ 프레임워크 불필요 (순수 파이썬)
6. LLM 출력 스키마 검증이 필요?           ──→ pydantic + with_structured_output
```

---

## 2. Bifrost 게이트웨이 — 확정

**Bifrost 메인 채택 확정.** LiteLLM은 사전 설정하지 않으며, Bifrost에 이슈 발생 시에만 마이그레이션합니다.

---

## 3. OpenTelemetry(OTel) — 이 시스템에서 할 수 있는 것 전체 정리

> OTel은 **애플리케이션의 동작을 관측(Observability)하기 위한 업계 표준 프레임워크**입니다. "로그를 남기는 것"의 진화된 버전이라고 생각하면 됩니다.

### 3-1. OTel의 3가지 기둥(Pillar)

| 기둥 | 설명 | 비유 |
|---|---|---|
| **Traces (추적)** | 하나의 요청이 시스템을 통과하는 **전체 여정**을 기록. 부모-자식 관계로 중첩된 "스팬(Span)"들의 그래프 | 택배 추적번호: "주문 → 포장 → 배송 → 도착" 각 단계의 시간·상태를 볼 수 있음 |
| **Metrics (지표)** | 시간에 따른 **수치 데이터** 집계. 카운터, 히스토그램, 게이지 등 | 자동차 계기판: 속도, 연비, 엔진 온도를 실시간 표시 |
| **Logs (로그)** | 특정 시점의 **이벤트 기록**. Trace ID와 연결되어 어떤 추적의 어떤 시점에서 발생했는지 파악 가능 | 블랙박스 녹화: 사고 발생 시 해당 시점의 상세 내용 확인 |

### 3-2. 이 시스템에서 OTel로 할 수 있는 6가지

| # | 기능 | 구체적 활용 | 없을 때 vs 있을 때 |
|---|---|---|---|
| **①** | **요청별 비용 추적** | 모든 LLM 호출의 입력/출력 토큰 수를 자동 기록 → "이번 달 Sonnet 5에 $8.50, Haiku에 $3.20 썼다" | 없을 때: 월말 Anthropic 청구서만 보고 어디서 많이 썼는지 모름 |
| **②** | **모델별 응답 속도 비교** | 요청→응답 지연 시간 히스토그램 → "Groq 평균 0.3초, 로컬 qwen3-coder 평균 4.2초" | 없을 때: "좀 느린 것 같은데..." 감에 의존 |
| **③** | **에이전트 디버깅** | LangGraph 그래프의 노드 실행 순서·시간을 스팬으로 기록 → "classify 노드에서 3초, compile 노드에서 12초 걸렸다" → 병목 식별 | 없을 때: print문으로 디버깅, 프로덕션에선 재현 어려움 |
| **④** | **폴백 체인 모니터링** | "Groq 무료 → 429 → Cerebras 폴백 → 성공" 경로를 추적 → 어떤 제공사가 자주 실패하는지 통계 | 없을 때: 폴백이 작동하는지조차 모름 |
| **⑤** | **프롬프트/응답 기록** | 옵트인(선택적)으로 실제 프롬프트와 모델 응답을 저장 → 품질 평가, 프롬프트 개선 재료 | 없을 때: "그때 어떤 프롬프트를 썼더라?" 기억 의존 |
| **⑥** | **로컬 모델 품질 추세** | 주간 LLM-as-judge 채점(v2 8-3절)을 Langfuse 스코어로 기록 → "프롬프트 변경 후 요약 품질이 10% 향상됨" 그래프 | 없을 때: 모델/프롬프트 변경이 개선인지 퇴보인지 판단 불가 |

### 3-3. 데이터 흐름

```
Bifrost 게이트웨이 ──(OTel/HTTP)──→ Langfuse
                                      ├─ Traces (요청 여정)
                                      ├─ Metrics (토큰·비용·지연)
                                      └─ Scores (품질 평가)
                                           ↓
                                     Langfuse 대시보드
                                      ├─ 월 클라우드 지출
                                      ├─ 로컬 대체율 (로컬 vs 클라우드 비율)
                                      ├─ 요청별 지연 분포
                                      └─ 모델·프롬프트별 품질 추세
```

---

## 4. 작업별 모델 배치 맵 (수정 — 테이블 포맷 정리)

### 4-1. 라우팅 전략

| 작업 | 1순위 모델 | 폴백 |
|---|---|---|
| 일상 코딩 보조 | 로컬 `qwen3-coder:30b-a3b` | Groq 무료 → Mistral Codestral 무료 |
| 멀티파일 리팩토링 | Gemini Pro (8월까지 무료) | Sonnet 5 API ($20 종량제) |
| 아키텍처 설계 | Gemini Pro → Sonnet 5 | — |
| 코드리뷰 (pre-push) | Haiku 4.5 API (저가) | Groq 무료 |
| 위키 분류·태깅 | 로컬 `exaone4.0:1.2b` | — |
| 위키 RAG 질의응답 | 로컬 `qwen3.5:9b` / `gemma4:e4b` | — |
| 빠른 채점·단답 검증 | Groq 무료 (LPU 초고속) | Cerebras 무료 |
| 긴 문서 크로스체크 | Gemini Pro (8월까지) → Gemini Flash 무료 | Cerebras 무료 |
| 야간 배치 요약 | Cerebras 무료 (일 1M 토큰) | SambaNova 무료 |
| 복습 질문 대량 생성 | SambaNova 무료 | Cerebras 무료 |
| 모의면접 종합평가 | Sonnet 5 API (세션당 1회) | — |
| 이력서 최종 첨삭 | Claude Code 또는 Sonnet 5 (수동 선택) | — |
| 다이어그램·이미지 해석 | Gemini 3.5 Flash 무료 | — |
| 스크린샷 1차 분류 | 로컬 `gemma4:e4b` | — |
| JD 매칭 분석 | Gemini Flash 무료 (JD=공개 데이터) | 로컬 모델 (자기 데이터) |
| 다양한 모델 실험 | OpenRouter `:free` 라우터 | — |

### 4-2. 프라이버시 경계 (최종)

| 데이터 분류 | 사용 가능 모델 |
|---|---|
| `#personal`, 이력서, 회고 | ✅ **로컬 LLM** + ✅ **유료 API** (Claude, Gemini 유료) |
| `#tech`, 공개 기술 문서 | ✅ **로컬 LLM (우선)** + 무료 API + 유료 API |
| `#career` (비개인 부분) | ✅ **로컬 LLM** + 유료 API |

> [!NOTE]
> `#tech` 공개 기술 문서도 **로컬 LLM을 우선 사용**합니다. 프롬프트 엔지니어링과 하네스 엔지니어링의 성숙도를 올리기 위해 로컬 모델 경험을 최대한 축적하는 것이 목표입니다. 무료/유료 API는 로컬 모델의 한계가 명확한 경우(긴 컨텍스트, 멀티파일 리팩토링 등)에만 사용합니다.

---

## 5. 추가 기능 상세 (2차 피드백 반영)

### 기능 ① 📊 포트폴리오 자동 생성 — 편집 환경 변경

| 항목 | v3.1 | v3.2 변경 |
|---|---|---|
| **편집 도구** | Obsidian | ✅ **현재 IDE (Antigravity/VSCode)** — 코드가 HTML 기반이므로 IDE가 적합. 마크다운/HTML 미리보기 + 터미널 통합 |
| **출력 형식** | Obsidian 마크다운 | ✅ **마크다운 + HTML 이중 출력** — 마크다운(원본), HTML(프레젠테이션용) |
| **저장 위치** | `Obsidian/portfolio/` | ✅ **프로젝트 디렉토리** (예: `C:\local_LLM\portfolio\`) — IDE에서 직접 편집 |

나머지 동작 방식은 v3.1과 동일 (수정 제안 → 피드백 → 확정 Human-in-the-Loop).

### 기능 ② 🧠 간격 반복 학습 — 응답 평가 + 음성/영상 지원

#### DB 선택: 기존 DB 활용

| 데이터 유형 | 저장소 | 이유 |
|---|---|---|
| 카드 본문 (Q&A 텍스트) + 벡터 검색 | ✅ **ChromaDB** (기존) | 유사 질문 검색, 관련 위키 연결에 벡터 유사도 활용 |
| 구조화 메타데이터 (난이도, 복습일, 점수 이력, 약점 통계) | ✅ **PostgreSQL** (기존 보유) | 관계형 쿼리("이번 주 오답률 높은 카테고리 Top 5") + 집계/통계에 적합 |
| ~~SQLite~~ | ❌ 제거 | 기존 DB로 충분, 관리 포인트 추가 불필요 |

#### 응답 → 평가 → 저장 → 반복 학습 루프

```
[질문 출제] Discord/Open WebUI로 카드 전송
     ↓
[사용자 응답] 텍스트 / 음성 / 영상
     ↓
[전처리] (음성/영상인 경우)
  ├─ 음성: faster-whisper (로컬 STT) → 텍스트 변환
  └─ 영상: FFmpeg 프레임 추출 + faster-whisper + VLM(gemma4:e4b) 분석
     ↓
[평가] LLM이 응답을 채점 (로컬 모델 + 채점 루브릭)
  ├─ 기술적 정확성 (0-5)
  ├─ 설명의 명확성 (0-5)
  ├─ 실무 적용 수준 (0-5)
  └─ (영상) 발표 태도·논리 구조 (0-5)
     ↓
[저장] PostgreSQL에 카드 ID + 점수 + 응답 원문 + 평가 코멘트 저장
     ↓
[SM-2 간격 조정] 점수 기반으로 다음 복습일 자동 계산
     ↓
[약점 분석] 주간 리포트: "자주 틀리는 영역 Top 5" + 추천 학습 자료
     ↓
[반복] 다음 복습일에 같은 카드(또는 심화 카드) 재출제
```

#### 음성/영상 답변 분석 — 가능 여부

| 입력 | 가능 여부 | 방법 | 하드웨어 적합성 |
|---|---|---|---|
| **음성** | ✅ **가능** | `faster-whisper` (Whisper 최적화 버전) → STT → 텍스트 평가 | CPU로도 구동 가능 (small/medium 모델) |
| **영상** | ⚠️ **조건부 가능** | FFmpeg 프레임 추출 → `gemma4:e4b` (로컬 VLM) 비언어 분석 + faster-whisper 음성 변환 | 8GB VRAM에서 VLM과 LLM 동시 구동 어려움 → **순차 처리** 필요 |
| **텍스트** | ✅ **가능** | 직접 LLM 평가 | 제한 없음 |

> [!TIP]
> **추천 시작 방식:** 텍스트 답변으로 시작 → 음성(faster-whisper 추가) → 영상(여유 시 VLM 추가). 면접 대비 관점에서 **음성 답변 연습이 실전에 가장 효과적**이므로, 2단계(음성)까지가 실용적 목표입니다.

### 기능 ③ 🔍 CI/CD 파이프라인 — 영향도 + 보안 + 성능 분석

| 파이프라인 | 도구 | 비용 | 트리거 |
|---|---|---|---|
| **영향도 분석** (AI 기반) | LLM 에이전트 (Bifrost 경유) + MCP wiki 검색 | Groq 무료 → Haiku 4.5 | PR 생성 시 |
| **보안 분석 (SAST)** | **Semgrep** (빠르고 오탐 낮음) + **CodeQL** (심층, 공개 repo 무료) | 무료 | push/PR |
| **의존성 취약점 (SCA)** | **Trivy** (의존성+컨테이너+IaC 올인원 스캐너) | 무료 | push/PR |
| **시크릿 탐지** | **Gitleaks** (하드코딩된 API키·비밀번호 탐지) | 무료 | push/PR |
| **성능 분석** | **Lighthouse CI** (웹앱) / **JMH** (Java 벤치마크) / 커스텀 스크립트 | 무료 | PR 또는 주간 |

#### GitHub Actions 워크플로우 구조

```yaml
# .github/workflows/quality-gate.yml (개념적)
name: Quality Gate
on: [pull_request]

jobs:
  # 1. 보안 분석
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Semgrep SAST
        uses: semgrep/semgrep-action@v1
      - name: Trivy SCA
        uses: aquasecurity/trivy-action@master
        with: { scan-type: 'fs', severity: 'CRITICAL,HIGH' }
      - name: Gitleaks
        uses: gitleaks/gitleaks-action@v2

  # 2. AI 영향도 분석
  impact-analysis:
    runs-on: self-hosted  # Tailscale 네트워크에서 Bifrost 접근
    steps:
      - uses: actions/checkout@v4
      - name: AI Impact Analysis
        run: python scripts/impact_analysis.py
        # → diff 수집 → Bifrost → LLM 분석 → PR 코멘트

  # 3. 성능 분석 (선택적)
  performance:
    if: contains(github.event.pull_request.labels.*.name, 'perf')
    runs-on: ubuntu-latest
    steps:
      - name: Run Benchmarks
        run: ./scripts/benchmark.sh
```

> [!IMPORTANT]
> **각 분석 결과는 PR 코멘트로 자동 게시**됩니다. 개발자가 별도 대시보드를 확인할 필요 없이 PR 화면에서 보안·영향도·성능 피드백을 한눈에 볼 수 있습니다.

### 기능 ④ 📈 JD 매칭 — 기존 MCP 서버 활용

> **질문: "사용 가능한 MCP가 있나요?"**

✅ **있습니다! 직접 구축할 필요 없습니다.**

| MCP 서버 | 지원 사이트 | GitHub |
|---|---|---|
| **job-search-mcp** | ✅ **잡코리아 + 사람인** | [PJW2004/job-search-mcp](https://github.com/PJW2004/job-search-mcp) |
| jobspy-mcp-server | LinkedIn, Indeed, Glassdoor (해외) | borgius/jobspy-mcp-server |

#### 설정 방법

```json
// claude_desktop_config.json 또는 Open WebUI MCP 설정
{
  "mcpServers": {
    "job-search": {
      "command": "npx",
      "args": ["-y", "job-search-mcp"]
    }
  }
}
```

#### 매칭 파이프라인 (수정)

```
[기존 MCP] job-search-mcp (잡코리아/사람인 스크래핑)
     ↓
[LangGraph 매칭 파이프라인]
  ① MCP로 "백엔드", "Java", "Spring" 등 키워드 채용공고 수집
  ② 각 JD에서 요구 기술/경험 추출 (Groq 무료 — 빠른 파싱)
  ③ 자신의 #career + #tech 위키에서 매칭 경험 검색 (wiki MCP, 로컬)
  ④ 매칭 리포트 생성 (매칭률, 강점, 약점, 면접 예상 질문)
  ⑤ threshold% 이상만 필터링
  ⑥ 약점 → 기능②의 복습 대상에 자동 추가
     ↓
[스케줄] 매일 오전 9시 → Discord #job-matching 채널에 보고

※ 주의: 웹 스크래핑 기반이므로 사이트 구조 변경 시 MCP 업데이트 필요
```

### 기능 ⑤ 🏗️ 인프라 비용 예측기 — ⏸️ 추후 구현 (변경 없음)

---

## 6. 확정 현황 — 모든 미결정 사항 해결 완료

| # | 항목 | 확정 값 |
|---|---|---|
| 1 | 프레임워크 | LangGraph + CrewAI + ADK Java + Hermes (PydanticAI 제거) |
| 2 | 게이트웨이 | Bifrost 확정 (LiteLLM 미설정, 이슈 시만 전환) |
| 3 | 유료 API | Claude Code 33,000원 + API $20/월 + Gemini Pro 무료(8월) |
| 4 | 무료 API | 8종 + 작업별 매핑 확정 |
| 5 | 모델 설치 | `qwen3-coder`, `bge-m3`, `exaone4.0:1.2b`, `gemma4:e4b` |
| 6 | 포트폴리오 도구 | IDE (Antigravity/VSCode) |
| 7 | 학습 시스템 DB | ChromaDB + PostgreSQL (기존 활용) |
| 8 | JD 매칭 MCP | `job-search-mcp` 기존 서버 활용 |
| 9 | CI/CD | 영향도(AI) + 보안(Semgrep/Trivy/Gitleaks) + 성능 |
| 10 | 음성/영상 | 텍스트 → 음성(faster-whisper) → 영상(VLM) 단계적 도입 |

---

## 7. 실행 로드맵 (v3.2 최종)

| 단계 | 작업 | 공수 | 선행 |
|---|---|---|---|
| **1** | 모델 설치: `qwen3-coder`, `bge-m3`, `exaone4.0:1.2b`, `gemma4:e4b` | 30분 | — |
| **2** | Bifrost Docker + Ollama/Anthropic/Gemini 등록 + 가상 키 | 반나절~1일 | API 키 발급 |
| **3** | Langfuse OTel 연동 | 반나절 | 2 |
| **4** | Open WebUI·Claude Code 엔드포인트 전환 | 1~2시간 | 2 |
| **5** | bge-m3 재임베딩 (ChromaDB 초기화 → 신규) | 1~2시간 | 1 |
| **6** | FastMCP 위키 서버 구축 → 클라이언트 연결 | 1~2일 | 5 |
| **7** | 무료 API 키 일괄 발급 + Bifrost 폴백 체인 | 반나절 | 2 |
| **8** | 하이브리드 기능: 모의면접·pre-push 리뷰 | 각 반나절 | 4 |
| **9** | job-search-mcp 설정 + JD 매칭 파이프라인 | 1~2일 | 6, 7 |
| **10** | 간격 반복 학습 시스템 (5계층 면접 + 평가 루프) | 1~2일 | 6 |
| **11** | 포트폴리오 자동 생성 파이프라인 | 1일 | 6 |
| **12** | CI/CD 파이프라인 (보안 + 영향도 + 성능) | 1일 | 2, 6 |
| **13** | CrewAI 이력서 3단 파이프라인 PoC | 반나절 | 7 |
| **14** | 멀티에이전트 복습 파이프라인 | 1일 | 6, 7 |
| **15** | Google ADK Java 독립 프로젝트 PoC | 1~2일 | 2 |
| **16** | Hermes Agent PoC | 1일 | 6 |
| **17** | 음성 답변 지원 (faster-whisper 통합) | 반나절 | 10 |
| **18** | gemma4:e4b 비전 + OpenCode | 각 반나절 | 여유 시 |
| **—** | 인프라 비용 예측기 | — | ⏸️ 인프라 프로젝트 시 |

---

## 8. v3.1 → v3.2 변경 요약

| 영역 | v3.1 | v3.2 |
|---|---|---|
| PydanticAI | 프레임워크로 포함 | ❌ **제거** — `pydantic` + `with_structured_output`로 대체 |
| OTel | 미설명 | ✅ **6가지 활용 기능 + 데이터 흐름 상세 설명** |
| 모델 배치 표 | 깨진 포맷 | ✅ **단순 테이블로 재작성** |
| #tech 데이터 | 무료 API 포함 전체 | ✅ **로컬 LLM 우선** (프롬프트 엔지니어링 성숙도 목적) |
| 포트폴리오 도구 | Obsidian | ✅ **IDE (Antigravity/VSCode)** |
| 학습 시스템 DB | SQLite | ✅ **ChromaDB + PostgreSQL** (기존 DB 활용) |
| 학습 루프 | 질문 출제만 | ✅ **응답 평가 → 저장 → 반복 학습** 전체 루프 |
| 음성/영상 | 미언급 | ✅ **faster-whisper(음성) + VLM(영상)** 단계적 도입 |
| CI/CD | 영향도 분석만 | ✅ **보안(Semgrep/Trivy/Gitleaks) + 성능 분석** 추가 |
| JD 매칭 MCP | 직접 구축 예정 | ✅ **기존 MCP 서버 발견** (`PJW2004/job-search-mcp`) |
