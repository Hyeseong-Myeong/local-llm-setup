# 모니터링 설계 — Alloy · Loki · Prometheus · Grafana

> ⚠️ **"PLG(Promtail·Loki·Grafana)" 라는 이름으로 시작했으나 Promtail 은 쓸 수 없다.**
> **Promtail 은 2026-03-02 부로 EOL** 이며 유지보수·상업 지원이 종료됐다. 후속은 **Grafana Alloy** 다.
> 설계 착수 시점에 확인해 반영했다 — 근거와 파급은 **0장** 참조.

> **작성일:** 2026-08-23
> **관련 문서:** [`troubleshooting.md`](troubleshooting.md) 섹션 14·16·17, [`context_limit_experiment.md`](context_limit_experiment.md)
> **성격:** 구축 **전에** 무엇을 왜 모으는지 확정하는 설계 문서. 구축 결과는 이후 별도 절에 기록한다.
> **상태:** 설계 단계. 아직 아무것도 배포하지 않았다.

---

## 0. 설계 시점 확인 — EOL·유지보수 상태

**도구를 고르기 전에 그 도구가 살아 있는지 먼저 본다.** 설계가 끝난 뒤 EOL 을 발견하면 이미 쓴 시간이 매몰된다.

| 구성 요소 | 상태 | 근거 | 설계 반영 |
|---|---|---|---|
| **Promtail** | 🔴 **EOL (2026-03-02)** | Grafana Labs 공지. 유지보수·상업 지원 종료, 기능 개발 중단 | **채택하지 않는다** |
| **Grafana Alloy** | ✅ 현행 | Promtail 의 공식 후속. OpenTelemetry Collector 배포판 | **로그·메트릭 수집 에이전트로 채택** |
| Loki | ✅ 현행 | | 로그 저장소 |
| Prometheus | ✅ 현행 | | 메트릭 저장소 |
| Grafana | ✅ 현행 | | 조회·알림 |

### 0-1. Alloy 채택이 설계를 바꾸는 지점

Alloy 는 **로그·메트릭·트레이스를 모두 다룬다**(Promtail 은 로그 전용). 그래서 원래 설계보다 단순해지고, **보안상 이득도 있다.**

| | 원래(Promtail 기준) | 변경(Alloy) |
|---|---|---|
| 로그 수집 | Promtail | Alloy |
| 메트릭 수집 | **Prometheus 가 개발 PC exporter 를 tailnet 으로 pull** | **Alloy 가 로컬에서 scrape 해 NAS 로 push** |
| 개발 PC 노출 | 🔴 exporter 포트를 tailnet 에 열어야 함 | ✅ **exporter 를 `127.0.0.1` 에만 바인딩. 인바운드 포트가 없다** |
| 에이전트 수 | 2종 | **1종** |

> **이것이 EOL 확인이 준 실질 이득이다.** 단순히 "지원 종료된 도구를 피했다"가 아니라, **개발 PC 의 인바운드 노출 하나를 통째로 없앴다.** 이번 조사 내내 다뤄 온 주제(불필요한 바인딩 제거)와 같은 방향이다.

### 0-2. 마이그레이션 부담은 없다

기존 Promtail 자산이 없으므로 **처음부터 Alloy 로 시작하면 된다.** (기존 설정이 있다면 `alloy convert --source-format=promtail` 로 변환하는 경로가 제공된다.)

---

## 1. 왜 만드는가 — 이번 조사가 남긴 문제

이 시스템에서 반복해 겪은 장애의 공통점은 **"조용한 실패"** 다. 에러가 나지 않고, 헬스체크는 통과하며, 사람이 우연히 발견할 때까지 지속된다.

| 사례 | 증상 | 발견 경위 |
|---|---|---|
| Bifrost 8080 바인딩 소멸 (섹션 14) | 컨테이너는 `healthy`, 포트 매핑만 사라짐 | 접속이 안 돼서 |
| ChromaDB 재부팅 후 원상복귀 (섹션 16 발견 4) | **heartbeat 는 계속 `200`** — 취약한 구 컨테이너가 응답 | 18분 뒤 우연히 |
| 게이트웨이가 `max_tokens` 를 버림 (섹션 17) | 요청은 성공, 상한만 무시 | 벤치마크 수치가 이상해서 |
| 사고 폭주로 빈 응답 | `finish_reason` 은 `stop`, 본문만 0자 | 사용자 체감 |
| 채팅↔임베딩 전환당 5초 재적재 | 아무 신호 없음 | 이번에 처음 측정 |
| 게이트웨이 타임아웃이 `6` 으로 저장됨 | 6초 만에 504 — 타임아웃처럼 보이지 않음 | 검증하다 발견 |

**공통 교훈: 이 실패들은 로그에 남지 않았다.** 전부 **상태를 조회해야** 보였다. 따라서 이 모니터링의 중심은 로그가 아니라 **상태 감시(5장)** 다.

---

## 2. 확정된 설계 결정

| # | 항목 | 결정 |
|---|---|---|
| 1 | 범위 | **로그 + 메트릭** (Alloy + Loki + Prometheus + Grafana) |
| 2 | Langfuse 관계 | **Langfuse 유지.** 이 스택은 인프라·앱 로그와 상태 메트릭만 다룬다 |
| 3 | 배포 위치 | **시놀로지 NAS** |
| 4 | Ollama 로그 | **수집한다** (기동 방식 변경 필요 — 6-4) |
| 5 | 상태 감시 | **포함. 이 설계의 핵심** (5장) |
| 6 | 알림 | **Discord 로 통일** |
| 7 | 보존 | 로그 30일 / **메트릭 90일** (7장) |
| 8 | 포트·바인딩 | 재지정 + **tailnet 한정** (8장) |

### 2-1. Langfuse 와의 경계

**겹치지 않게 나눈다.** 중복 수집은 저장 비용만 늘리고 어느 쪽을 봐야 할지 헷갈리게 한다.

| | Langfuse | 이 스택 |
|---|---|---|
| 대상 | **LLM 호출 자체** — 프롬프트/응답, 토큰, 비용, 트레이스 | **그 호출을 둘러싼 것** — 프로세스·컨테이너·바인딩·자원 |
| 질문 | *"이 문서를 왜 이렇게 정제했나"* | *"왜 응답이 안 왔나"* |
| 이미 있는 것 | `wiki_agent.py:631` LangChain 콜백 | 없음 |

**경계선:** LLM 요청/응답 본문은 이 스택으로 보내지 않는다. Langfuse 에 이미 있고, 로그로 중복 보관하면 개인 문서 내용이 한 곳 더 늘어난다.

---

## 3. 구성 요소

```
[개발 PC]                                  [NAS · tailnet 한정 바인딩]
 앱 로그 3종   ─┐                           ┌── Loki       (로그 30일)
 Docker 로그   ─┤                           │
 Ollama 로그   ─┼─ Alloy ──push(tailnet)──▶ ├── Prometheus (메트릭 90일)
 local exporter ┘   (127.0.0.1 에서 scrape)  │      ▲
   ↑ 인바운드 포트 없음                       │      └── NAS exporter ← Alloy(NAS)
                                             │
 [NAS] chromadb 로그 ─ Alloy(NAS) ─────────▶ └── Grafana    (조회 · 알림 → Discord)
```

* **Alloy 를 개발 PC 와 NAS 양쪽에 둔다.** 로그가 양쪽에서 나오고, 메트릭도 각자 로컬에서 긁는다.
* **Alloy 가 push 한다.** 그래서 **개발 PC 는 인바운드 포트를 열지 않는다** — exporter 는 `127.0.0.1` 에만 바인딩한다(0-1).
* **상태 exporter 도 양쪽에 둔다.** 개발 PC 것은 Ollama·Bifrost 를, NAS 것은 chromadb 를 본다. 서로의 상태를 원격으로 조회하면 네트워크 장애와 대상 장애를 구분하지 못한다.

---

## 4. 로그 수집 대상

| 출처 | 위치 | 수집 방법 | 비고 |
|---|---|---|---|
| `wiki_agent.log` | 개발 PC `logs/` | Alloy 파일 tail | |
| `discord_bot.log` | 개발 PC `logs/` | 〃 | |
| `fastapi_wiki_server.log` | 개발 PC `logs/` | 〃 | |
| Bifrost 컨테이너 | 개발 PC Docker | Docker 로그 드라이버 | 이미 JSON 구조화 |
| Open WebUI 컨테이너 | 개발 PC Docker | 〃 | |
| **Ollama** | **현재 버려짐** | 6-4 참조 | **기동 방식 변경 필요** |
| chromadb 컨테이너 | NAS Docker | NAS 쪽 Alloy | |

### 4-1. 🔴 앱 로그 로테이션이 유실을 만든다

`src/logger_setup.py` 는 10MB 를 넘으면 **파일 이름을 `.bak` 으로 바꾸고 새로 연다.** `.bak` 은 하나만 유지되므로 그 다음 로테이션에서 삭제된다.

* Alloy 는 이름이 바뀐 파일을 계속 따라가지 못할 수 있다 — **로테이션 직전 구간이 유실될 수 있다.**
* ✅ **결정: 로테이션 크기를 키운다** (10MB → **50MB**). 유실 확률을 낮추는 완화책이며 근본 해결은 아니다.
  * 근본 해결(앱이 stdout 으로도 쓰게 하기)은 `pythonw` 백그라운드라 stdout 이 없어 구조 변경이 필요하다. **지금은 하지 않는다.**
  * 대신 **`log_file_bytes{name}` 메트릭으로 파일 크기를 감시**해, 로테이션이 잦아지면 드러나게 한다.
* 현재 로그 크기는 작다 (`discord_bot` 128KB, `wiki_agent` 55KB). **당장 급하지 않으나 방치하면 조용히 유실된다** — 이 설계가 잡으려는 실패 유형과 같은 성질이다.

---

## 5. 상태 exporter — 이 설계의 핵심

로그로는 잡히지 않고 **주기적 조회로만 보이는 것**을 메트릭으로 만든다. 1장의 사례를 하나씩 지표로 옮긴 것이다.

### 5-1. 개발 PC exporter (`exporter/local_exporter.py`)

Prometheus 텍스트 형식을 HTTP 로 노출한다. 수집 주기 **30초**.

#### Ollama 상태

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| `ollama_up` | gauge | `/api/tags` 응답 여부 | 프로세스 사망 |
| `ollama_model_loaded{model}` | gauge 0/1 | `/api/ps` | — |
| `ollama_model_size_bytes{model}` | gauge | `/api/ps` `size` | — |
| `ollama_model_vram_bytes{model}` | gauge | `/api/ps` `size_vram` | — |
| **`ollama_model_gpu_ratio{model}`** | **gauge 0~1** | `size_vram / size` | 🔴 **CPU 분할.** 1.0 미만이면 성능이 조용히 무너진 상태 |
| `ollama_model_context_length{model}` | gauge | `/api/ps` `context_length` | 설정이 의도대로 적용됐는지 |
| `ollama_loaded_models_count` | gauge | `/api/ps` 길이 | 동시 상주 여부 |
| `ollama_orphan_runners` | gauge | `llama-server.exe` 프로세스 수 − 정상치 | 🔴 **고아 러너.** 이번에 VRAM 을 점유해 GPU 를 2% 로 떨어뜨린 원인 |

> `ollama_model_gpu_ratio` 가 가장 중요하다. 실측상 이 값이 1.0 미만이면 추론이 수 배 느려지는데 **에러도 로그도 없다.**

#### Bifrost 게이트웨이

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| `bifrost_up` | gauge | `/api/version` | 게이트웨이 사망 |
| **`bifrost_request_timeout_seconds`** | **gauge** | `config.db` `config_providers.network_config_json` | 🔴 **설정 오입력.** `600` 대신 `6` 으로 저장된 사고를 잡는다 |
| `bifrost_allowed_models{provider}` | gauge | `config_keys.models_json` 길이 | 모델 등록 누락 |
| `bifrost_provider_configured{provider}` | gauge 0/1 | `config_providers` | 프로바이더 유실 |

> `config.db` 는 **읽기 전용(`mode=ro`)으로만** 연다. 운영 중인 게이트웨이의 설정 DB 다.

#### 위키 파이프라인

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| `wiki_collection_documents` | gauge | Chroma `count()` | 재임베딩 사고, 데이터 소실 |
| `wiki_embedding_up` | gauge | 게이트웨이 `/v1/embeddings` 1회 호출 | 임베딩 경로 단절 |
| `wiki_tool_server_up` | gauge | `:9000/docs` | 툴 서버 사망 |
| `wiki_agent_process_count` | gauge | 프로세스 수 | **중복 기동 / 사망** |

#### 프로세스

| 메트릭 | 타입 | 잡으려는 실패 |
|---|---|---|
| `agent_process_count{name}` | gauge | `wiki_agent` · `discord_bot` · `fastapi_wiki_server` 각각. **정상값은 2** (런처 + 인터프리터). 0 이면 사망, 4 이상이면 중복 기동 |
| `log_file_bytes{name}` | gauge | 앱 로그 4종 + Ollama 로그. **로테이션 임박(4-1)과 Ollama 로그 무한 증가(6-4)를 잡는다** |

#### exporter 자신의 상주

✅ **결정: 시작 스크립트(`ai-server-start.bat`)에 추가한다.** 에이전트 3종과 같은 방식(`pythonw`)이라 일관되고, 기동 지점이 한 곳으로 유지된다.

* 🔴 **다만 한계가 있다.** 시작 스크립트는 **로그인 시** 실행된다. 재부팅 후 사람이 로그인하기 전까지는 뜨지 않는다. 기존 에이전트도 마찬가지이므로 새로 생기는 문제는 아니지만, **"NAS 는 24시간, 개발 PC 는 로그인 이후"** 라는 비대칭을 알고 있어야 한다.
* 🔴 **exporter 가 죽으면 아무도 되살리지 않는다.** 그리고 **자기가 죽었다는 사실을 스스로 보고할 수 없다.** push 방식이라 `up` 메트릭도 없다(6-1) — **데이터 부재로만 감지된다.** 9-1 의 No Data 알림이 이 역할을 한다.

### 5-2. NAS exporter (`exporter/nas_exporter.py`)

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| **`chroma_bound_all_interfaces`** | **gauge 0/1** | `docker inspect` `NetworkSettings.Ports` 에 `0.0.0.0` 또는 `::` | 🔴 **섹션 16 발견 4.** 구 컨테이너가 되살아나 원상복귀한 상태 |
| `chroma_published_ports` | gauge | 퍼블리싱된 포트 수 | `{}` 이면 컨테이너가 안 뜬 것 |
| `chroma_container_running` | gauge 0/1 | `.State.Running` | |
| `chroma_container_restart_count` | gauge | `.RestartCount` | 재시작 루프 |
| `chroma_http_up` | gauge | `127.0.0.1:8000/api/v2/heartbeat` | |
| **`chroma_responding_container`** | **gauge 0/1** | 응답 주체가 compose 라벨을 가진 컨테이너인가 | 🔴 **"HTTP 200 은 누가 응답하는지 알려주지 않는다"** — 이번 교훈을 지표로 만든 것 |
| `chroma_data_bytes` | gauge | `/volume1/docker/chromadb/data` 크기 | 백업 계획·이상 증가 |
| `chroma_old_container_exists` | gauge 0/1 | `chromadb_old` 존재 여부 | 지뢰가 남아 있는지 |

### 5-3. 설계 원칙 세 가지

1. **판정 근거를 응답 코드에 두지 않는다.** `heartbeat 200` 은 이번에 18분간 사람을 속였다. **누가 응답하는가**까지 확인한다.
2. **exporter 는 읽기만 한다.** 상태를 바꾸지 않는다. `config.db` 는 `mode=ro`, Docker 는 `inspect` 만.
3. **exporter 자신의 실패를 드러낸다.** 각 수집 항목에 `*_scrape_error{target}` 을 함께 낸다. 지표가 안 나오는 것과 대상이 죽은 것은 다르다.

---

## 6. 수집 경로

### 6-1. 개발 PC → NAS

**Alloy 가 push 한다.** 로그는 Loki 로, 메트릭은 Prometheus 의 remote-write 로 보낸다.

* **개발 PC 는 인바운드 포트를 열지 않는다.** exporter 는 `127.0.0.1:13092` 에만 바인딩하고, 같은 머신의 Alloy 만 긁는다.
* Prometheus 가 tailnet 으로 pull 하는 구조였다면 exporter 포트를 열어야 했다. **EOL 확인이 이 노출을 없앴다**(0-1).
* 🔴 **대가 — push 방식은 `up` 메트릭이 없다.** pull 이면 대상이 죽었을 때 Prometheus 가 `up=0` 을 기록하지만, push 는 **그냥 데이터가 끊긴다.**
  * 대응: **Grafana 알림을 "데이터 없음(No Data)" 조건으로도 건다.** 9-1 의 규칙에 반영.
  * exporter 자신이 죽으면 자기 상태를 보고할 수 없다. **부재로 감지하는 수밖에 없다.**

### 6-2. NAS 내부

Loki · Prometheus · Grafana · NAS exporter · Alloy 를 **compose 하나로** 묶는다. `bifrost/docker-compose.yml` 과 같은 방식이다.

### 6-3. Bifrost `/metrics` — 스크랩하지 않는다

**무엇을 주는지 확인했다.** 세 갈래다.

| 갈래 | 대표 지표 |
|---|---|
| HTTP 전송 | `http_requests_total` · `http_request_duration_seconds` · 요청/응답 크기 |
| 업스트림 프로바이더 | `bifrost_upstream_requests_total` · `bifrost_success/error_requests_total` · `bifrost_upstream_latency_seconds` · **`bifrost_input/output_tokens_total`** · **`bifrost_cost_total`** · `bifrost_active_requests` · `bifrost_provider_key_up` · `bifrost_key_rotation_events_total` · `bifrost_request_retries` |
| 스트리밍·MCP | `bifrost_stream_first_token_latency_seconds` · `bifrost_stream_inter_token_latency_seconds` |

**✅ 결정: 스크랩하지 않는다.**

* 굵게 표시한 것들(**토큰 수·비용·지연**)이 정확히 **Langfuse 가 이미 다루는 영역**이다. 2-1 에서 그은 경계를 스스로 넘게 된다.
* 인증 문제도 있다. 실측상 `/metrics` 는 **API 키를 넣어도 `401`** 이다. 열려면 `config_client.whitelisted_routes_json` 에 `/metrics` 를 넣거나 스크랩 설정에 admin basic auth 를 넣어야 하는데, **관측을 위해 관리 경로를 여는 것은 비용 대비 이득이 낮다.**
* **다시 볼 조건:** 폴백 체인 통계(`bifrost_key_rotation_events_total`)나 프로바이더별 키 상태(`bifrost_provider_key_up`)가 필요해지면 — 그건 Langfuse 가 안 주는 정보다. **그때는 경계를 다시 긋는다.**

### 6-4. 🔴 Ollama 로그 — 기동 방식을 바꿔야 한다

현재 `ai-server-start.bat` 은 이렇게 띄운다.

```
powershell -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve'"
```

**stdout 이 어디로도 가지 않아 로그가 버려진다.** (`%LOCALAPPDATA%\Ollama\server.log` 는 Ollama 앱으로 띄웠을 때의 경로이고, 현재 것은 갱신되지 않는다.)

**✅ 결정: A — 파일로 리다이렉트하고, 기동 시점에 로테이션한다.**

```bat
:: ai-server-start.bat — Ollama 기동부
:: 이전 로그를 한 세대 밀어 두고 새로 시작한다 (logger_setup.py 와 같은 방식)
if exist "%LOGDIR%\ollama.log.1" del "%LOGDIR%\ollama.log.1"
if exist "%LOGDIR%\ollama.log"   move /Y "%LOGDIR%\ollama.log" "%LOGDIR%\ollama.log.1"
powershell -WindowStyle Hidden -Command ^
  "Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve' ^
   -RedirectStandardOutput '%LOGDIR%\ollama.log' -RedirectStandardError '%LOGDIR%\ollama.err.log'"
```

**왜 A 인가**

* 변경 범위가 가장 작다. **시작 스크립트는 이미 기동의 단일 지점**이다 — `taskkill /F /IM llama-server.exe` 같은 필수 처리가 거기 들어 있다(이번에 고아 러너로 확인).
* Docker 전환(B)은 **ROCm GPU 통과 설정을 다시 잡아야 해 위험이 크다.** 8GB VRAM 에서 겨우 맞춰 둔 구성을 흔들 이유가 없다.
* 서비스화(C)는 도구(NSSM 등)가 하나 늘어난다.

**🔴 그러나 파일 무한 증가 문제가 남는다.** 재기동이 로테이션 시점인데, **Ollama 는 몇 주씩 재기동 없이 돌 수 있다.**

* **대응 1 — `OLLAMA_DEBUG` 를 끈다.** 현재 시작 스크립트는 `set OLLAMA_DEBUG=1` 이다. **디버그 로깅 + 로테이션 없음 = 디스크 위험**이다. 평상시에는 끄고, 문제를 파고들 때만 켠다.
* **대응 2 — 크기를 감시한다.** `log_file_bytes{name="ollama"}` 메트릭으로 임계치를 넘으면 알린다(9-1). **막지는 못해도 조용히 커지지는 않는다.**
* **대응 3 — 주기 정리.** 작업 스케줄러로 주 1회 크기 확인 후 로테이션. **필요해지면 추가한다** — 지금은 대응 2 로 관측부터 한다.

> 이 순서가 이번 조사의 방식이다. **막기 전에 먼저 보이게 만든다.** 실제로 문제가 되는지 모른 채 스케줄러부터 붙이면 검증할 수 없는 장치가 하나 늘 뿐이다.

---

## 7. 보존 정책

| 대상 | 보존 | 근거 |
|---|---|---|
| **Loki (로그)** | **30일** | 사후 조사에 충분하다. 압축되어 용량 부담이 적다 |
| **Prometheus (메트릭)** | **90일** | 시계열이라 용량이 로그의 수십 분의 일이다. 그리고 이번 조사에서 **"언제부터 이랬나"에 답하지 못한 항목이 여럿**이었다 — 동적 포트 범위가 언제 바뀌었는지, IPv6 가 얼마나 오래 노출됐는지. **추세를 보려면 길수록 낫다** |

> **Loki 에서는 별도 로테이션을 걸지 않는다.** retention 정책이 그 역할을 한다. 관리해야 할 로테이션은 **앱 쪽**(4-1)과 **Ollama 로그**(6-4) 다.

---

## 8. 포트와 바인딩

### 8-1. 포트 재지정

**Grafana 기본 3000 은 개발 PC 의 Open WebUI 가 이미 쓴다.** 헷갈리지 않게 대역을 통일한다.

| 서비스 | 포트 | 비고 |
|---|---|---|
| Grafana | **13000** | 3000 과 자릿수를 맞춰 기억하기 쉽게 |
| Loki | **13100** | 기본 3100 과 대응 |
| Prometheus | **13090** | 기본 9090 과 대응 |
| NAS exporter | **13091** | |
| 개발 PC exporter | **13092** | 🔒 **`127.0.0.1` 전용.** 같은 머신의 Alloy 만 긁는다 — tailnet 에 열지 않는다 |

* **NAS 에는 winnat 예약 문제가 없다** — 그건 Windows 고유 문제다(섹션 14). 다만 **개발 PC exporter(13092)는 해당된다.** 13000번대는 예약 구간(7435~8663) 밖이라 안전하다.
* ✅ **NAS 포트 가용 확인 완료** — 13000·13090·13091·13100 모두 사용 가능.

### 8-2. 바인딩 — tailnet 한정

**모든 서비스를 tailnet 인터페이스에만 바인딩한다.** 섹션 16 에서 ChromaDB 에 적용한 것과 같은 형태다.

```yaml
ports:
  - "127.0.0.1:13000:3000"                                    # NAS 로컬
  - "${TAILNET_BIND_IP:?TAILNET_BIND_IP is empty - refusing to bind 0.0.0.0}:13000:3000"
```

* **`:?` 가드를 반드시 넣는다.** 값이 비면 `":13000:3000"` 이 되어 **조용히 `0.0.0.0` 에 열린다**(섹션 16 N10). compose 가 에러로 멈추게 한다.
* **Synology 방화벽으로는 막을 수 없다** — Docker 가 DNAT 로 `INPUT` 체인을 우회한다(N7). 바인딩이 유일한 방어다.
* 인터페이스를 명시하면 **IPv6(`::`) 바인딩도 함께 사라진다.**
* Grafana 는 자체 로그인이 있으나 **바인딩이 1차 방어선**이다.

---

### 8-3. Grafana 로그인 정책

**정할 항목은 여섯 가지다.** 전부 환경변수로 주입하며, 값은 `.env` 에 두고 커밋하지 않는다.

| # | 항목 | 환경변수 | 권장 | 이유 |
|---|---|---|---|---|
| 1 | **admin 비밀번호** | `GF_SECURITY_ADMIN_PASSWORD` | **반드시 변경** | 기본값이 `admin/admin` 이다. tailnet 한정이어도 기기 하나가 뚫리면 그대로 열린다 — 섹션 16 N2("계정이 경계 단위") |
| 2 | **익명 조회** | `GF_AUTH_ANONYMOUS_ENABLED` | **`false`** | 켜면 로그인 없이 대시보드가 보인다. 편하지만 **알림 설정·데이터소스 자격증명까지 노출 위험**이 생긴다 |
| 3 | **가입 허용** | `GF_USERS_ALLOW_SIGN_UP` | **`false`** | 기본값도 `false` 지만 명시한다. 1인 운영이라 가입이 필요 없다 |
| 4 | **세션 서명 키** | `GF_SECURITY_SECRET_KEY` | **직접 생성** | 기본값을 쓰면 세션 쿠키를 위조할 수 있다 |
| 5 | **쿠키 Secure 플래그** | `GF_SECURITY_COOKIE_SECURE` | **`false`** | HTTPS 가 아니면 `true` 로 두면 로그인이 안 된다. **tailnet 자체가 WireGuard 로 암호화**되므로 평문 HTTP 로 둔다 |
| 6 | **Discord 웹훅 저장 위치** | — | 볼륨 백업 시 주의 | Grafana DB(`grafana.db`)에 저장된다. **백업을 저장소에 넣지 않는다** |

> **1번이 실질적으로 가장 중요하다.** 바인딩이 1차 방어선이지만, tailnet 안의 기기 하나가 침해되면 그 다음 방어선은 이 비밀번호뿐이다.

---

## 9. 알림 — Discord 통일

`wiki_agent.py` 가 이미 Discord 웹훅을 쓴다(`DISCORD_WEBHOOK_URL`). Grafana Alerting 의 Discord contact point 를 같은 방식으로 연결한다.

### 9-1. 알림 규칙 초안

**"조용한 실패"를 깨우는 것이 목적이므로, 사람이 알아채지 못하는 것만 울린다.**

| 심각도 | 조건 | 근거가 된 사례 |
|---|---|---|
| 🔴 즉시 | `chroma_bound_all_interfaces == 1` | 발견 4 — 취약 상태로 원상복귀 |
| 🔴 즉시 | `chroma_responding_container == 0` **이면서** `chroma_http_up == 1` | 다른 컨테이너가 응답 중 |
| 🔴 즉시 | `bifrost_request_timeout_seconds < 60` | 설정 오입력(`6`) |
| 🟡 5분 지속 | `ollama_model_gpu_ratio < 1.0` | CPU 분할 |
| 🟡 5분 지속 | `ollama_orphan_runners > 0` | 고아 러너가 VRAM 점유 |
| 🟡 5분 지속 | `agent_process_count{name} != 2` | 사망 또는 중복 기동 |
| 🟡 즉시 | `wiki_collection_documents` 가 이전 값 대비 급감 | 재임베딩 사고 |
| 🟢 일간 | `chroma_old_container_exists == 1` | 지뢰가 남아 있음 |
| 🔴 10분 지속 | **데이터 없음(No Data)** — 개발 PC 메트릭이 끊김 | push 방식이라 `up` 이 없다(6-1). **부재로만 감지된다** |
| 🟡 일간 | `log_file_bytes{name="ollama"} > 2e9` | Ollama 로그 무한 증가(6-4) |
| 🟡 일간 | `log_file_bytes{name} > 4e7` | 앱 로그가 로테이션(50MB)에 근접 — 유실 임박(4-1) |

### 9-2. 알림 피로 방지

* **`*_up == 0` 만으로 울리지 않는다.** 재시작·점검 중에도 뜬다. **지속 시간 조건**을 붙인다.
* 이 시스템은 **1인 운영**이다. 울려도 손댈 수 없는 시간대의 알림은 소음이다. **🟢 등급은 일간 요약**으로 묶는다.

---

## 10. 구축 순서

**한 번에 하나씩 올린다.** 섹션 14·16 에서 반복 확인한 원칙 — 동시에 바꾸면 실패 원인을 특정할 수 없다.

| 순서 | 작업 | 완료 기준 |
|---|---|---|
| 1 | NAS 에 Loki + Grafana 배포, 바인딩 검증 | `netstat` 에 `0.0.0.0`·`:::` 없음 |
| 2 | NAS Alloy → chromadb 로그 수집 | Grafana 에서 조회됨 |
| 3 | Prometheus 배포 + **NAS exporter** | `chroma_bound_all_interfaces` 가 값을 냄 |
| 4 | **개발 PC exporter**(127.0.0.1) + Alloy push | `ollama_model_gpu_ratio` 가 값을 냄 |
| 5 | 개발 PC Alloy → 앱·Docker 로그 | |
| 6 | Ollama 로그 수집 (6-4 결정 적용) | |
| 7 | 알림 규칙 + Discord 연결 | **의도적으로 조건을 만들어 실제로 울리는지 확인** |
| 8 | 대시보드 구성 | |

> **7번을 형식적으로 넘기지 말 것.** 알림은 **울려야 할 때 울리는지 확인하기 전까지 작동한다고 말할 수 없다.** 이번 조사 전체가 "확인했다고 믿었으나 아니었던" 사례의 연속이었다.

---

## 11. 확정 내역

설계 착수 시 미결이던 항목을 전부 확정했다.

| # | 항목 | 결정 | 근거 |
|---|---|---|---|
| 1 | 앱 로그 로테이션 유실 | **크기 상향 10MB → 50MB.** 근본 해결은 보류 | 4-1 |
| 2 | Ollama 로그 수집 | **파일 리다이렉트 + 기동 시 로테이션.** `OLLAMA_DEBUG` 는 끄고, 크기를 메트릭으로 감시 | 6-4 |
| 3 | Bifrost `/metrics` | **스크랩하지 않는다.** 토큰·비용·지연이 Langfuse 와 겹치고, 여는 비용이 이득보다 크다 | 6-3 |
| 4 | NAS 포트 | **13000·13090·13091·13100 사용 가능 확인** | 8-1 |
| 5 | Grafana 로그인 | **6개 항목 확정** — admin 비밀번호 변경, 익명 조회 차단, 가입 차단, 서명 키 생성, 쿠키 Secure 해제, 웹훅 백업 주의 | 8-3 |
| 6 | 개발 PC exporter 상주 | **시작 스크립트에 추가.** 한계(로그인 의존·자가 감지 불가)를 알림으로 보완 | 5-1 |
| 7 | **EOL 확인** | **Promtail 배제, Alloy 채택.** 부수적으로 개발 PC 인바운드 노출 제거 | 0장 |

### 11-1. 구축 시 다시 확인할 것

설계로는 정할 수 없고 **실제로 올려봐야 아는 것들**이다.

* Alloy 가 **Windows 에서 파일 로테이션(이름 변경)을 어떻게 따라가는지** — 4-1 의 유실 가정이 맞는지 실측
* Synology 에서 Alloy 컨테이너가 **호스트 Docker 소켓 없이** chromadb 로그를 읽을 수 있는지 (읽으려면 소켓 마운트가 필요할 수 있고, 그건 blast radius 를 키운다 — 섹션 16 4-3장 9항)
* Loki 30일 · Prometheus 90일 보존이 **NAS 디스크에서 실제로 얼마를 쓰는지**
* Discord 웹훅 알림이 **실제로 도착하는지** (10장 7번 — 형식적으로 넘기지 말 것)
