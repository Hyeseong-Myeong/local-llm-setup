# 모니터링 설계 — Alloy · Loki · Prometheus · Grafana

> ⚠️ **"PLG(Promtail·Loki·Grafana)" 라는 이름으로 시작했으나 Promtail 은 쓸 수 없다.**
> **Promtail 은 2026-03-02 부로 EOL** 이며 유지보수·상업 지원이 종료됐다. 후속은 **Grafana Alloy** 다.
> 설계 착수 시점에 확인해 반영했다 — 근거와 파급은 **0장** 참조.

> **작성일:** 2026-08-23
> **관련 문서:** [`troubleshooting.md`](troubleshooting.md) 섹션 14·16·17, [`context_limit_experiment.md`](context_limit_experiment.md)
> **성격:** 구축 **전에** 무엇을 왜 모으는지 확정하는 설계 문서. 구축 결과는 이후 별도 절에 기록한다.
> **상태:** 설계 단계. **아직 아무것도 배포하지 않았다.**

---

## 인계 — 이 문서로 구축을 시작하는 세션에게

**지금 상태:** 설계만 끝났다. 코드도 컨테이너도 없다. 브랜치 `design/plg-monitoring`.

**이 문서의 결정은 대부분 실측에 근거한다.** 다시 논의하기 전에 근거를 먼저 읽을 것. 특히 아래 다섯 가지는 **한 번 뒤집혔던 결정**이라 배경을 모르고 되돌리기 쉽다.

| 결정 | 왜 그렇게 정했나 | 참조 |
|---|---|---|
| Promtail 대신 **Alloy** | Promtail 은 2026-03-02 EOL | 0장 |
| 앱 로그 **날짜 기반 파일명** | Alloy 의 Windows 로테이션 결함(alloy#2292, OPEN). 같은 이름으로 재생성하면 **수집이 멈춘다** | 4-1 |
| 컨테이너 로그는 **syslog 드라이버** | 파일 마운트는 `config.v2.json` 으로 **API 키가 함께 노출**된다(실측). syslog 는 dual-logging 덕에 `docker logs` 도 유지된다(실측) | 4-2 |
| Bifrost `/metrics` **인증 유지** | 화이트리스트는 인증을 없애는 것이다. 관리자 `basic_auth` 로 스크랩한다 | 6-3 |
| NAS exporter 는 **호스트 스크립트** | 컨테이너 + 소켓 마운트는 탈출이 곧 호스트 장악. Synology 의 `docker` 그룹은 사실상 root | 12-2 |

**시작 지점:** 10장 구축 순서 1번(NAS 에 Loki + Grafana). 한 번에 하나씩 올린다.

**구축 전 반드시 할 것:** 12-3 의 **로그 샘플 육안 확인**. 시크릿이 한 번 Loki 에 들어가면 지우기 어렵다.

**아직 모르는 것은 11-2 에 모아 두었다.** 설계로는 정할 수 없고 올려봐야 아는 것들이다.

**관련 문서** — 이 설계의 문제의식은 [`troubleshooting.md`](troubleshooting.md) 섹션 14·16·17 과 [`context_limit_experiment.md`](context_limit_experiment.md) 에서 나왔다. 1장의 실패 목록이 그 요약이다.

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

**⚠️ Alloy 는 현행이지만 미해결 결함이 하나 있다.** [grafana/alloy#2292](https://github.com/grafana/alloy/issues/2292) — Windows 에서 **같은 이름으로 로테이션된 로그 파일을 다시 tail 하지 못한다.** 2024-12-17 등록, 2026-08-18 갱신, **OPEN**. 설계에 우회책을 반영했다(4-1 · 6-4).

> **"현행"과 "결함 없음"은 다르다.** EOL 확인만으로는 부족하고, **채택할 도구의 열린 이슈까지 봐야** 한다.

### 0-1. Alloy 채택이 설계를 바꾸는 지점

Alloy 는 **로그·메트릭·트레이스를 모두 다룬다**(Promtail 은 로그 전용). 그래서 원래 설계보다 단순해지고, **보안상 이득도 있다.**

| | 원래(Promtail 기준) | 변경(Alloy) |
|---|---|---|
| 로그 수집 | Promtail | Alloy |
| 메트릭 수집 | **Prometheus 가 개발 PC exporter 를 tailnet 으로 pull** | **Alloy 가 로컬에서 scrape 해 NAS 로 push** |
| 개발 PC 노출 | 🔴 exporter 포트를 tailnet 에 열어야 함 | ✅ **exporter 를 `127.0.0.1` 에만 바인딩. 인바운드 포트가 없다** |
| 에이전트 수 | 2종 | **1종** |


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
 앱 로그 3종   ─┤ 파일 tail                 ┌── Loki       (로그 30일)
 Docker 로그   ─┤ syslog(127.0.0.1)         │
 Ollama 로그   ─┼─ Alloy ──push(tailnet)──▶ ├── Prometheus (메트릭 90일)
 local exporter ┘   (127.0.0.1 에서 scrape)  │      ▲
   ↑ 인바운드 포트 없음                       │      └── NAS exporter ← Alloy(NAS)
                                             │
 [NAS] 컨테이너 4종 ─syslog─ Alloy(NAS) ───▶ └── Grafana    (조회 · 알림 → Discord)
```

* **Alloy 를 개발 PC 와 NAS 양쪽에 둔다.** 로그가 양쪽에서 나오고, 메트릭도 각자 로컬에서 긁는다.
* **컨테이너 로그는 파일이 아니라 syslog 로 받는다.** Alloy 가 `127.0.0.1` 에 수신기를 열고 Docker 가 거기로 보낸다 — 파일 접근도 소켓 마운트도 없다(4-2).
* **Alloy 가 push 한다.** 그래서 **개발 PC 는 인바운드 포트를 열지 않는다** — exporter 는 `127.0.0.1` 에만 바인딩한다(0-1).
* **상태 exporter 도 양쪽에 둔다.** 개발 PC 것은 Ollama·Bifrost 를, NAS 것은 chromadb 를 본다. 서로의 상태를 원격으로 조회하면 네트워크 장애와 대상 장애를 구분하지 못한다.

---

## 4. 로그 수집 대상

| 출처 | 위치 | 수집 방법 | 비고 |
|---|---|---|---|
| `wiki_agent.log` | 개발 PC `logs/` | Alloy 파일 tail | |
| `discord_bot.log` | 개발 PC `logs/` | 〃 | |
| `fastapi_wiki_server.log` | 개발 PC `logs/` | 〃 | |
| Bifrost 컨테이너 | 개발 PC Docker | **`syslog` 드라이버 → Alloy** | 4-2 |
| Open WebUI 컨테이너 | 개발 PC Docker | 〃 | 4-2 |
| **Ollama** | **현재 버려짐** | 6-4 참조 | **기동 방식 변경 필요** |
| chromadb · couchdb · hyeseongkit-hub · hyeseongkit-jenkins | NAS Docker | 〃 (NAS Alloy 가 수신) | |

### 4-1. 🔴 Windows 로테이션 — Alloy 의 미해결 결함에 걸린다

`src/logger_setup.py` 는 10MB 를 넘으면 **파일 이름을 `.bak` 으로 바꾸고 같은 이름으로 새로 연다.**

**이 방식은 Windows 에서 Alloy 와 함께 쓸 수 없다.**

> [grafana/alloy#2292](https://github.com/grafana/alloy/issues/2292) — *"Alloy - not scraping logs after log rotation in Windows"*
> **2024-12-17 등록, 2026-08-18 갱신, 여전히 OPEN.** 20개월째 미해결이다.
>
> Windows 에서는 파일이 지워지면 tailer 가 **즉시 멈춘다.** 새 파일이 생겨도 **이름이 같으면** `local.file_match` 가 캐시된 것과 동일하다고 보아 변경을 전파하지 않는다 → **그 파일은 다시 tail 되지 않는다.** 유닉스에서는 파일이 사라졌다고 보고될 때까지 재열기를 시도하므로 이 문제가 없다.

* **처음 세운 "50MB 로 키운다"는 대책은 무효다.** 크기를 키우면 로테이션이 드물어질 뿐, **한 번 발생하면 그 뒤로 수집이 통째로 멈춘다.** 유실 구간이 늘 뿐 아니라 **아무도 모른 채 영구히 끊긴다** — 이 설계가 잡으려는 실패 유형 그 자체다.
* **공식 우회책은 "로테이션마다 파일명을 다르게 하는 것"** 이다.

**✅ 결정: 활성 로그 파일명 자체에 날짜를 넣는다.**

```
logs/wiki_agent-20260823.log      ← 오늘 쓰는 파일
logs/wiki_agent-20260822.log      ← 어제 것 (그대로 남는다)
```

* `logger_setup.py` 를 **날짜 기반 파일명 + 이름 변경 없음** 으로 바꾼다. 날이 바뀌면 **새 경로**가 생기므로 Alloy 가 새 파일로 인식한다.
* Alloy 는 `logs/wiki_agent-*.log` 글롭으로 수집한다.
* 오래된 파일 정리는 **Loki 보존(30일)과 별개로** 로컬에서 해야 한다 — 날짜 기준 삭제. **구축 시 정한다.**
* 크기 상향(50MB)은 **더 이상 필요 없다.** 날짜 단위로 갈리므로 한 파일이 커질 일이 줄고, 커지더라도 tail 이 끊기지 않는다.

> **이것이 설계 단계 검증의 값이다.** 

### 4-2. Docker 로그 — `syslog` 드라이버로 Alloy 에 보낸다

#### 검토한 네 가지

| 방식 | 시크릿 노출 | `docker logs` | 판정 |
|---|---|---|---|
| ① Docker 소켓 마운트 | 전부 (API 로 조회 가능) | 유지 | ❌ 소켓은 사실상 root. 컨테이너 탈출이 곧 호스트 장악 |
| ② `/var/lib/docker/containers` 통째 마운트 | 🔴 **전부** | 유지 | ❌ 아래 참조 |
| ③ Loki 로깅 드라이버 | 없음 | 유지 | 🟡 dual-logging 으로 `docker logs` 는 살아 있으나 **third-party 등급**. 내장 드라이버(⑤)를 쓸 이유가 있다 |
| ④ `local` 드라이버 + `local-logs/` 만 마운트 | 없음 | 유지 | 🟡 시크릿은 해결하나 **ID 경로 문제**가 남음 |
| **⑤ `syslog` 드라이버 → Alloy** | **없음** | **유지**(dual-logging) | ✅ **채택** |

#### ② 를 배제한 이유 (실측)

마운트 자체는 동작한다. 그러나 같은 디렉터리에 `config.v2.json` 이 있고 **컨테이너 환경변수가 평문으로** 들어 있다. Bifrost 것에서 `GEMINI_API_KEY` · `GROQ_API_KEY` · `ANTHROPIC_API_KEY` · `LANGFUSE_AUTH_B64` 가 모두 값을 갖는 것을 확인했다.

**로그를 읽으려고 이 디렉터리를 마운트하면 API 키 전부를 함께 내주게 된다.**

#### ④ 채택 — 실측 근거

`local` 드라이버는 로그를 **하위 디렉터리**에 쓴다.

```
/var/lib/docker/containers/<id>/
├── config.v2.json          ← 시크릿. 마운트 대상에서 제외된다
├── hostconfig.json
└── local-logs/             ← 이것만 마운트한다
    └── container.log
```

* `local-logs` 만 바인드하면 **상위의 `config.v2.json` 에 접근할 수 없다.** 시크릿 노출이 사라진다.
* **`docker logs` 가 그대로 동작한다** — 실측 확인. ③ 의 가장 큰 대가가 없다.
* `max-size` · `max-file` 로 **드라이버가 스스로 로테이션**한다. 4-1 의 Windows 결함은 이 경로에 해당하지 않는다 — 리눅스 파일시스템 위에서 Alloy 컨테이너가 읽기 때문이다.

#### 🔴 남는 문제 — 경로에 컨테이너 ID 가 들어간다

컨테이너를 재생성하면 ID 가 바뀌고 **마운트가 조용히 끊긴다.** Docker 는 없는 호스트 경로를 빈 디렉터리로 만들어 주므로 **에러도 나지 않는다.**

##### "로그 경로를 미리 만들고 컨테이너가 그걸 마운트하면 되지 않나"

**발상은 옳지만 Docker 로깅 드라이버에는 적용되지 않는다.**

* 우리가 경로를 정할 수 있는 것은 **애플리케이션이 파일로 로그를 쓸 때**다. 그 경우 호스트 디렉터리를 바인드하면 ID 문제가 없다.
* 그러나 **대상 컨테이너들은 stdout/stderr 로 쓴다**(12-factor 관행). chromadb · bifrost · open-webui 모두 그렇다. stdout 은 **Docker 로깅 드라이버가 받아 Docker 가 정한 경로에 저장**하며, **그 경로는 설정할 수 없다.**
* 앱 설정으로 파일 로깅을 켤 수 있는 것은 일부뿐이고(예: CouchDB), **컨테이너마다 방식이 달라 일관되게 관리할 수 없다.**
* 명령을 `sh -c 'exec ... | tee /logs/app.log'` 로 감싸는 방법도 있으나 **이미지의 entrypoint 를 덮어써야 하고 종료 신호 처리가 깨질 수 있다.** 채택하지 않는다.

##### ✅ 더 나은 대안 — 원격 로깅 드라이버 (채택)

**Docker 20.10 부터 dual-logging 캐시가 있어, 원격 드라이버를 써도 `docker logs` 가 동작한다.** 실측으로 확인했다 — Docker 28.0.1 에서 `--log-driver syslog` 컨테이너에 `docker logs` 가 정상 출력했다.

**이것이 ③(Loki 드라이버)을 배제한 근거를 무너뜨린다.** `docker logs` 를 잃지 않는다.

| | `local` + 하위 마운트 | **syslog → Alloy** |
|---|---|---|
| 시크릿 노출 | 없음 | **없음** |
| `docker logs` | 유지 | **유지** (dual-logging) |
| 파일 접근 | 필요 | **불필요** |
| Docker 소켓 | 불필요 | **불필요** |
| 컨테이너 ID 경로 | 🔴 **재생성 시 끊김** | ✅ **해당 없음** |
| 갱신 스크립트 | 필요 | **불필요** |

**→ `syslog` 드라이버로 Alloy 의 `loki.source.syslog` 에 보낸다.**

* **`syslog` 는 Docker 내장 드라이버**다. Loki 플러그인처럼 별도 설치가 필요 없고 third-party 등급 문제도 없다.
* Alloy 가 syslog 수신기를 열고 그대로 Loki 로 넘긴다.
* 🔴 **전송 실패 시 동작을 정해야 한다.** UDP 는 조용히 유실되고, TCP 는 수집기가 죽으면 **컨테이너가 블로킹될 수 있다.**
  * **`mode=non-blocking` + `max-buffer-size` 를 명시한다.** 수집기가 죽어도 컨테이너는 계속 돈다.
  * **유실되더라도 `docker logs` 로는 남는다**(dual-logging). 이중 안전망이다.
* **수신기 바인딩:** Alloy 의 syslog 포트는 **`127.0.0.1` 에만** 연다. 같은 호스트의 Docker 만 보낸다.

#### 적용 대상과 전환 비용

드라이버를 바꾸려면 **컨테이너 재생성이 필요하다.**

| 위치 | 컨테이너 | 현재 드라이버 |
|---|---|---|
| 개발 PC | `bifrost` · `open-webui` | `json-file` (실측) |
| NAS | `chromadb` · `couchdb-obsidian-sync` · `hyeseongkit-hub` · `hyeseongkit-jenkins` | 확인 필요 |

```yaml
logging:
  driver: syslog
  options:
    syslog-address: "udp://127.0.0.1:51400"
    tag: "{{.Name}}"          # 컨테이너 이름이 라벨로 들어간다
    mode: "non-blocking"
    max-buffer-size: "4m"
```

* **한 번에 하나씩 전환한다**(섹션 14·16 원칙). chromadb 는 재생성을 수반하므로 섹션 16 의 바인딩 검증 절차를 다시 밟는다.
* 🔴 **드라이버를 바꾸면 기존 로그가 사라진다.** 필요하면 전환 전에 `docker logs > 파일` 로 받아 둔다.
* `tag` 로 컨테이너 이름이 붙으므로 **ID 를 이름으로 매핑할 필요가 없다** — ② 방식의 또 다른 문제도 함께 해소된다.

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
| `bifrost_request_timeout_seconds` | gauge | `config.db` `config_providers.network_config_json` | 설정 오입력(`600` → `6`). **대시보드에 상시 표시하지 않는다.** 값이 임계 미만일 때만 알림으로 쓴다 |
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

#### 모델별 성능 — 앱 계측으로 얻는다

`/api/ps` 로는 적재 상태만 보인다. **응답 품질 지표는 호출하는 쪽만 안다.** `wiki_agent` 가 이미 모든 LLM 호출을 하므로, 거기서 기록해 exporter 가 노출한다.

| 메트릭 | 타입 | 라벨 | 내용 |
|---|---|---|---|
| `llm_request_duration_seconds` | histogram | `model` · `stage` | 호출 전체 소요 |
| `llm_ttft_seconds` | histogram | `model` | **첫 토큰까지의 시간.** 스트리밍 호출에서만 얻는다 |
| `llm_tokens_per_second` | gauge | `model` | `eval_count / eval_duration` |
| `llm_completion_tokens` | histogram | `model` · `stage` | 생성량 분포 — **사고 폭주 추적** |
| `llm_thinking_chars` | histogram | `model` | 사고 길이. 폭주의 직접 지표 |
| `llm_empty_content_total` | counter | `model` | **본문이 빈 응답 횟수.** 실험 D-2 의 실패 |
| `llm_finish_reason_total` | counter | `model` · `reason` | `length` 비중이 곧 상한 압박 |
| `llm_timeout_total` | counter | `model` | **타임아웃 발생 횟수**(7번 피드백) |
| `llm_request_total` | counter | `model` · `outcome` | 성공/실패 |

**문서 길이와 처리 시간의 관계** — 위키 파이프라인 고유 지표다.

| 메트릭 | 타입 | 라벨 | 내용 |
|---|---|---|---|
| `wiki_document_chars` | histogram | `category` | 입력 문서 길이 |
| `wiki_stage_duration_seconds` | histogram | `stage` · `category` | 정제·컴파일 등 단계별 소요 |
| `wiki_chars_per_second` | gauge | `stage` | **길이 대비 처리 속도.** 문서가 길어질수록 느려지는지 본다 |
| `wiki_chunks_per_document` | histogram | — | 분할 개수 |

> **부하 주의.** 이 지표들은 **이미 일어나는 호출에 계측만 붙이는 것**이라 추가 LLM 호출이 없다. 다만 `llm_ttft_seconds` 는 **스트리밍 호출에서만** 얻을 수 있으므로, 현재 비스트리밍인 경로를 바꾸면 동작이 달라진다. **TTFT 는 후순위로 두고, 스트리밍 전환이 필요해질 때 함께 넣는다.**

#### PC 자원

| 메트릭 | 타입 | 출처 |
|---|---|---|
| `host_cpu_percent` | gauge | `psutil` |
| `host_memory_used_bytes` · `host_memory_total_bytes` | gauge | 〃 |
| `host_disk_used_bytes{mount}` | gauge | 〃 — 로그·모델 저장소 포함 |
| `host_disk_free_bytes{mount}` | gauge | 〃 |
| `host_uptime_seconds` | gauge | 〃 |

* **GPU 는 별도다.** AMD + Windows 에서 신뢰할 만한 조회 수단이 확인되지 않았다(실험 3-3). **`ollama_model_gpu_ratio` 가 대리 지표**이며, VRAM 절대량은 재지 않는다.
* `windows_exporter` 같은 별도 서비스를 붙이지 않는다. **서비스 하나를 더 늘리는 대가**가 얻는 것보다 크고, `psutil` 로 필요한 범위는 덮인다.

#### 부하 관리

* 수집 주기 **30초**. `/api/ps` · `docker inspect` · `psutil` 은 모두 가벼운 조회다.
* 🔴 **`wiki_embedding_up` 은 실제 임베딩을 1회 호출한다.** 30초마다 GPU 를 건드리므로 **주기를 5분으로 따로 둔다.**
* exporter 는 **수집 결과를 캐시**하고 스크랩 요청에 그 값을 낸다. 스크랩마다 조회하지 않는다.

#### exporter 자신의 상주

✅ **결정: 시작 스크립트(`ai-server-start.bat`)에 추가한다.** 에이전트 3종과 같은 방식(`pythonw`)이라 일관되고, 기동 지점이 한 곳으로 유지된다.

* 🔴 **다만 한계가 있다.** 시작 스크립트는 **로그인 시** 실행된다. 재부팅 후 사람이 로그인하기 전까지는 뜨지 않는다. 기존 에이전트도 마찬가지이므로 새로 생기는 문제는 아니지만, **"NAS 는 24시간, 개발 PC 는 로그인 이후"** 라는 비대칭을 알고 있어야 한다.
* 🔴 **exporter 가 죽으면 아무도 되살리지 않는다.** 그리고 **자기가 죽었다는 사실을 스스로 보고할 수 없다.** push 방식이라 `up` 메트릭도 없다(6-1) — **데이터 부재로만 감지된다.**
* ✅ **그래서 워치독을 둔다.** 작업 스케줄러가 10분마다 exporter 생존을 확인하고 없으면 재기동한다(9-4). **시작 스크립트는 로그인 의존이지만 작업 스케줄러는 그렇지 않아** 재부팅 후 공백도 함께 줄인다.
* 워치독이 살리지 못하는 경우를 위해 **9-1 의 No Data 알림을 유지한다.** 자동 복구와 알림은 대체 관계가 아니다.

### 5-2. NAS exporter (`exporter/nas_exporter.py`)

**대상 컨테이너를 chromadb 하나로 두지 않는다.** 같은 방식으로 조회하므로 대상만 늘리면 되고, 부하는 `docker inspect` 한 번씩이라 무시할 수준이다.

| 컨테이너 | 왜 보는가 |
|---|---|
| `chromadb` | 위키 파이프라인의 저장소. 바인딩 감시(섹션 16) |
| `couchdb-obsidian-sync` | 옵시디언 동기화. **끊기면 볼트가 조용히 갈라진다** |
| `hyeseongkit-hub` | 세션 저장소 |
| `hyeseongkit-jenkins` | CI |

#### 공통 컨테이너 지표 — 위 넷에 동일 적용 (`container` 라벨로 구분)

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| `container_running{container}` | gauge 0/1 | `.State.Running` | 사망 |
| `container_restart_count{container}` | gauge | `.RestartCount` | 재시작 루프 |
| `container_last_exit_code{container}` | gauge | `.State.ExitCode` | 발견 4 때 `exit=128` 이 단서였다 |
| `container_state_error_present{container}` | gauge 0/1 | `.State.Error` 가 비었는가 | `bind: address already in use` 가 여기 남는다 |
| **`container_bound_all_interfaces{container}`** | **gauge 0/1** | `NetworkSettings.Ports` 에 `0.0.0.0`/`::` | 🔴 **의도치 않은 전 인터페이스 노출.** chromadb 만의 문제가 아니다 |
| `container_published_ports{container}` | gauge | 퍼블리싱 포트 수 | `0` 이면 매핑이 사라진 것 |
| `container_health_status{container}` | gauge | `.State.Health.Status` 를 0/1/2 로 | |
| `container_log_lines_total{container}` | counter | Alloy 가 받은 로그 라인 수 | 🔴 **전송 끊김.** 증가가 멈추면 드라이버·수집기 문제 |

#### chromadb 전용

| 메트릭 | 타입 | 출처 | 잡으려는 실패 |
|---|---|---|---|
| `chroma_http_up` | gauge | `127.0.0.1:8000/api/v2/heartbeat` | |
| **`chroma_responding_container`** | **gauge 0/1** | 응답 주체가 compose 라벨을 가진 컨테이너인가 | 🔴 **"HTTP 200 은 누가 응답하는지 알려주지 않는다"** — 이번 교훈을 지표로 만든 것 |
| `chroma_data_bytes` | gauge | `/volume1/docker/chromadb/data` 크기 | 백업 계획·이상 증가 |
| `chroma_old_container_exists` | gauge 0/1 | `chromadb_old` 존재 여부 | 지뢰가 남아 있는지 |

#### NAS 호스트 자원

| 메트릭 | 타입 | 내용 |
|---|---|---|
| `host_cpu_percent` · `host_memory_*` · `host_disk_*{mount}` | gauge | 개발 PC 와 같은 형태. `container` 대신 `host="nas"` 라벨 |
| `host_disk_free_bytes{mount="/volume1"}` | gauge | **Loki·Prometheus 저장 공간.** 보존 정책이 디스크를 잠식하는지 본다 |

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

### 6-3. Bifrost `/metrics` — 스크랩한다

**무엇을 주는지 확인했다.** 세 갈래다.

| 갈래 | 대표 지표 |
|---|---|
| HTTP 전송 | `http_requests_total` · `http_request_duration_seconds` · 요청/응답 크기 |
| 업스트림 프로바이더 | `bifrost_upstream_requests_total` · `bifrost_success/error_requests_total` · `bifrost_upstream_latency_seconds` · **`bifrost_input/output_tokens_total`** · **`bifrost_cost_total`** · `bifrost_active_requests` · `bifrost_provider_key_up` · `bifrost_key_rotation_events_total` · `bifrost_request_retries` |
| 스트리밍·MCP | `bifrost_stream_first_token_latency_seconds` · `bifrost_stream_inter_token_latency_seconds` |

**✅ 결정: 스크랩한다. 단 겹치는 지표는 대시보드에 올리지 않는다.**

처음에는 "Langfuse 와 겹친다"는 이유로 배제했으나 **재검토 결과 겹치지 않는 것이 있다.**

| 지표 | Langfuse 가 주는가 | 판단 |
|---|---|---|
| `bifrost_provider_key_up` | ❌ | **키별 헬스.** 클라우드 프로바이더가 조용히 죽는 것을 잡는다 |
| `bifrost_key_rotation_events_total` | ❌ | **폴백 발생.** 어느 프로바이더가 자주 실패하는지 |
| `bifrost_error_requests_total` | 부분 | 게이트웨이 관점의 실패율 |
| `bifrost_request_retries` | ❌ | 재시도 분포 |
| `bifrost_active_requests` | ❌ | **동시 처리 수.** 큐가 밀리는지 |
| `http_request_duration_seconds` | 중복 | 수집하되 대시보드 제외 |
| `bifrost_input/output_tokens_total` · `bifrost_cost_total` | **중복** | 수집하되 대시보드 제외 — Langfuse 를 본다 |

* **중복 지표를 굳이 버리지 않는 이유:** 스크랩 단위가 엔드포인트 하나라 **선별 수집이 오히려 설정을 복잡하게** 만든다. 저장 비용도 미미하다(7-1). **경계는 "무엇을 보느냐"로 지킨다.**
#### 🔴 인증 — 화이트리스트가 아니라 인증을 유지한다

실측 결과 `/metrics` 는 **어떤 방식으로도 통과하지 못했다.**

| 시도 | 결과 |
|---|---|
| 인증 없음 | `401` |
| `Authorization: Bearer <API 키>` | `401` |
| `x-bf-api-key` · `X-API-Key` | `401` |
| Basic `admin:admin` · Basic `admin:<API 키>` | `401` |

공식 문서는 이렇게 안내한다 — *"Bifrost auth 가 활성화돼 있으면 스크랩 설정에 `admin_username` · `admin_password` 로 `basic_auth` 를 넣어야 한다."* **즉 전용 관리자 자격증명이 따로 있고, 이 배포에는 설정돼 있지 않다.**

**✅ 결정: 관리자 자격증명을 설정하고 Prometheus 가 `basic_auth` 로 스크랩한다.**

```yaml
scrape_configs:
  - job_name: bifrost
    basic_auth:
      username: ${BIFROST_ADMIN_USER}
      password: ${BIFROST_ADMIN_PASSWORD}
    static_configs:
      - targets: ["host.docker.internal:18080"]
```

* **`whitelisted_routes_json` 은 쓰지 않는다.** 화이트리스트는 **인증 자체를 없애는 것**이라 tailnet 안의 어떤 기기든 읽을 수 있게 된다. 인증을 유지하는 쪽이 낫다.
* 자격증명은 `.env` 에 두고 커밋하지 않는다.
* 🔴 **관리자 계정을 새로 만드는 것 자체가 자산이 하나 느는 일이다.** 비밀번호를 충분히 길게 잡고, **Grafana admin 비밀번호와 다른 값**을 쓴다(8-3).
* **구축 시 확인:** Bifrost Web UI 에서 관리자 자격증명을 어디서 설정하는지 — 환경변수인지 UI 인지. 설정 후 `curl -u` 로 `200` 을 확인한 뒤 스크랩을 붙인다.

### 6-4. 🔴 Ollama 로그 — 기동 방식을 바꿔야 한다

현재 `ai-server-start.bat` 은 이렇게 띄운다.

```
powershell -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve'"
```

**stdout 이 어디로도 가지 않아 로그가 버려진다.** (`%LOCALAPPDATA%\Ollama\server.log` 는 Ollama 앱으로 띄웠을 때의 경로이고, 현재 것은 갱신되지 않는다.)

**✅ 결정: A — 파일로 리다이렉트한다. 단 파일명에 타임스탬프를 넣는다.**

```bat
:: ai-server-start.bat — Ollama 기동부
:: 4-1 과 같은 이유로 파일명을 매번 다르게 한다. 같은 이름으로 덮으면
:: Alloy 가 Windows 에서 새 파일을 인식하지 못한다 (grafana/alloy#2292).
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set LDT=%%I
set STAMP=%LDT:~0,8%-%LDT:~8,4%
powershell -WindowStyle Hidden -Command ^
  "Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve' ^
   -RedirectStandardOutput '%LOGDIR%\ollama-%STAMP%.log' ^
   -RedirectStandardError  '%LOGDIR%\ollama-%STAMP%.err.log'"
```

* 재기동마다 새 파일명이 생기므로 **Alloy 가 매번 새 경로로 인식한다.**
* Alloy 는 `logs/ollama-*.log` 글롭으로 수집한다.

**왜 A 인가**

* 변경 범위가 가장 작다. **시작 스크립트는 이미 기동의 단일 지점**이다 — `taskkill /F /IM llama-server.exe` 같은 필수 처리가 거기 들어 있다(이번에 고아 러너로 확인).
* Docker 전환(B)은 **ROCm GPU 통과 설정을 다시 잡아야 해 위험이 크다.** 8GB VRAM 에서 겨우 맞춰 둔 구성을 흔들 이유가 없다.
* 서비스화(C)는 도구(NSSM 등)가 하나 늘어난다.

**🔴 그러나 파일 무한 증가 문제가 남는다.** 재기동이 로테이션 시점인데, **Ollama 는 몇 주씩 재기동 없이 돌 수 있다.**

* **대응 1 — `OLLAMA_DEBUG` 를 끈다.** 현재 시작 스크립트는 `set OLLAMA_DEBUG=1` 이다. **디버그 로깅 + 로테이션 없음 = 디스크 위험**이다. 평상시에는 끄고, 문제를 파고들 때만 켠다.
* **대응 2 — 크기를 감시한다.** `log_file_bytes{name="ollama"}` 메트릭으로 임계치를 넘으면 알린다(9-1). **막지는 못해도 조용히 커지지는 않는다.**
* ✅ **대응 3 — 오래된 파일 정리 (채택).** 날짜 기반 파일이 쌓이므로 **앱 로그와 같은 정리 정책**을 쓴다.
  * 대응 1·2 는 완화일 뿐 파일 증가 자체를 막지 못한다. **정리는 결국 필요하다.**
  * Windows 에는 `logrotate` 가 없다. **작업 스케줄러 + PowerShell** 로 처리한다 — 구현은 **9-2** 참조.
  * 앱 로그(`logs/*-YYYYMMDD.log`)와 Ollama 로그(`logs/ollama-*.log`)를 **같은 스크립트가 함께 정리**한다. 정리 주기와 보존 일수를 한 곳에서 관리한다.

> 이 순서가 이번 조사의 방식이다. **막기 전에 먼저 보이게 만든다.** 실제로 문제가 되는지 모른 채 스케줄러부터 붙이면 검증할 수 없는 장치가 하나 늘 뿐이다.

---

## 7. 보존 정책

| 대상 | 보존 | 근거 |
|---|---|---|
| **Loki (로그)** | **30일** | 사후 조사에 충분하다. 압축되어 용량 부담이 적다 |
| **Prometheus (메트릭)** | **90일** | 시계열이라 용량이 로그의 수십 분의 일이다. 그리고 이번 조사에서 **"언제부터 이랬나"에 답하지 못한 항목이 여럿**이었다 — 동적 포트 범위가 언제 바뀌었는지, IPv6 가 얼마나 오래 노출됐는지. **추세를 보려면 길수록 낫다** |

### 7-1. 용량 추정 (2026-08-23 실측 기반)

| 대상 | 실측 | 30일 추정 |
|---|---|---|
| `discord_bot.log` | 127KB / 43일 | 약 **3KB/일** |
| `wiki_agent.log` | 55KB / 43일 | 약 **1.3KB/일** |
| `fastapi_wiki_server.log` | 34KB / 38일 | 약 **0.9KB/일** |
| **앱 로그 합계** | | **약 5KB/일 → 30일 150KB** |

* **앱 로그는 사실상 용량 문제가 아니다.**
* **메트릭도 마찬가지다.** 지표 약 50종 × 30초 주기 × 90일이면 압축 후 수십 MB 수준이다.
* 🔴 **불확실한 것은 두 가지뿐이다 — Ollama 로그와 Docker 로그.** `OLLAMA_DEBUG=1` 상태의 생성량을 측정한 적이 없다. **구축 초기에 실측해 보존 정책을 재조정한다.**

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

### 9-2. 알림 수를 줄이는 이유 — 중요성을 지키기 위해

**알림이 많아지면 하나하나의 무게가 가벼워진다.** 매일 울리는 알림은 읽지 않게 되고, 그러면 **정작 중요한 것이 왔을 때도 넘어간다.** 수를 줄이는 것은 편의가 아니라 **🔴 등급이 실제로 🔴 로 읽히게 하기 위한 조치다.**

* **`*_up == 0` 만으로 울리지 않는다.** 재시작·점검 중에도 뜬다. **지속 시간 조건**을 붙인다.
* **🟢 등급은 일간 요약으로 묶는다.** 개별로 보내면 그 채널 전체가 배경 소음이 된다.
* **새 규칙을 추가할 때 기준:** *"이게 울리면 내가 지금 무엇을 하는가."* 답이 없으면 규칙이 아니라 대시보드 항목이다.

### 9-3. 로그 정리 — Windows 작업 스케줄러

`logrotate` 가 없으므로 **PowerShell + 작업 스케줄러**로 처리한다. 앱 로그와 Ollama 로그를 한 스크립트가 함께 정리한다.

```powershell
# scripts/cleanup_logs.ps1 — 보존 일수를 넘긴 로그 파일을 지운다
param([int]$Days = 30, [string]$LogDir = "C:\local_LLM\logs")

$cutoff = (Get-Date).AddDays(-$Days)
Get-ChildItem -Path $LogDir -File -Include "*-*.log","*.log.*" -Recurse |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Write-Output "delete $($_.Name) ($([math]::Round($_.Length/1MB,1))MB, $($_.LastWriteTime.ToString('yyyy-MM-dd')))"
        Remove-Item $_.FullName -Force
    }
```

* **활성 파일은 지우지 않는다.** 날짜 기반 파일명(4-1)이라 오늘 것은 `LastWriteTime` 이 최신이므로 자연히 제외된다.
* 출력을 로그로 남겨 **무엇을 지웠는지 Loki 에서 확인**할 수 있게 한다.
* 보존 일수는 **Loki 보존(30일)과 맞춘다.** 로컬에서 먼저 지워지면 Loki 에만 남고, 그 반대면 중복 보관이 된다.

### 9-4. 스케줄러 관리 스크립트

작업 스케줄러 항목이 늘어난다 — 로그 정리, exporter 감시, NAS 쪽 마운트 갱신. **매번 GUI 로 등록·해제·재등록하지 않도록 스크립트 하나로 관리한다.**

```powershell
# scripts/manage_tasks.ps1 — 작업 정의를 한 곳에 두고 멱등하게 반영한다
param([ValidateSet("install","remove","status")][string]$Action = "status")

$Tasks = @(
    @{ Name = "LocalLLM-CleanupLogs"
       Script = "C:\local_LLM\scripts\cleanup_logs.ps1"
       Trigger = "Daily"; At = "04:00" }
    @{ Name = "LocalLLM-ExporterWatchdog"
       Script = "C:\local_LLM\scripts\exporter_watchdog.ps1"
       Trigger = "Repeat"; Every = 10 }   # 분
)
# install: 기존 항목을 지우고 다시 만든다 (정의가 유일한 근거)
# remove : 전부 해제
# status : 등록 여부·마지막 실행 결과·다음 실행 시각 출력
```

**설계 원칙**

* **작업 정의를 스크립트 안에 둔다.** GUI 에 흩어져 있으면 무엇이 등록돼 있는지 알 수 없다 — 이번 조사에서 반복된 "설정이 어디 있는지 모르는" 문제와 같다.
* **`install` 은 멱등하다.** 기존 항목을 지우고 다시 만든다. 수정 후 재실행하면 반영된다.
* **`status` 를 만든다.** 등록됐다고 믿는 것과 실제로 등록된 것은 다르다(섹션 16 교훈).
* 🔴 **작업 스케줄러 등록은 관리자 권한이 필요하다.** 시작 스크립트(로그인 시 실행)와 달리 **재부팅 후 로그인 없이도 동작한다** — exporter 감시에는 이쪽이 낫다.

---

## 10. 구축 순서

**한 번에 하나씩 올린다.** 섹션 14·16 에서 반복 확인한 원칙 — 동시에 바꾸면 실패 원인을 특정할 수 없다.

| 순서 | 작업 | 완료 기준 |
|---|---|---|
| 1 | NAS 에 Loki + Grafana 배포, 바인딩 검증 | `netstat` 에 `0.0.0.0`·`:::` 없음 |
| 2 | NAS Alloy → chromadb 로그 수집 | Grafana 에서 조회됨 |
| 3 | Prometheus 배포 + **NAS exporter** | `chroma_bound_all_interfaces` 가 값을 냄 |
| 4 | **개발 PC exporter**(127.0.0.1) + Alloy push | `ollama_model_gpu_ratio` 가 값을 냄 |
| 5 | 개발 PC Alloy → 앱 로그(파일) + syslog 수신기 | |
| 5-1 | 대상 컨테이너에 `syslog` 드라이버 적용 | 🔴 **컨테이너 재생성이 필요하다.** 볼륨은 유지되지만 한 번에 하나씩 바꾸고 확인한다 |
| 6 | Ollama 로그 수집 (6-4 결정 적용) | |
| 7 | 알림 규칙 + Discord 연결 | **의도적으로 조건을 만들어 실제로 울리는지 확인** |
| 8 | 대시보드 구성 | |

> **7번을 형식적으로 넘기지 말 것.** 알림은 **울려야 할 때 울리는지 확인하기 전까지 작동한다고 말할 수 없다.** 이번 조사 전체가 "확인했다고 믿었으나 아니었던" 사례의 연속이었다.

---

## 11. 확정 내역

| # | 항목 | 결정 | 참조 |
|---|---|---|---|
| 1 | 앱 로그 로테이션 | **날짜 기반 파일명**(`wiki_agent-YYYYMMDD.log`). Alloy 결함 우회 | 4-1 |
| 2 | Ollama 로그 | **타임스탬프 파일명 + `OLLAMA_DEBUG` 끄기 + 정기 정리** | 6-4 · 9-3 |
| 3 | **Docker 컨테이너 로그** | **`syslog` 드라이버 → Alloy.** 파일·소켓 접근이 없고 컨테이너 ID 경로 문제도 없다. `docker logs` 는 dual-logging 으로 유지 | 4-2 |
| 4 | Bifrost `/metrics` | **스크랩한다. 인증은 유지** — 화이트리스트가 아니라 관리자 `basic_auth` 로 | 6-3 |
| 5 | NAS 포트 | 13000·13090·13091·13100 가용 확인 | 8-1 |
| 6 | Grafana 로그인 | **권장값 그대로 적용** (6개 항목) | 8-3 |
| 7 | exporter 상주 | 시작 스크립트 + **작업 스케줄러 워치독** | 5-1 · 9-4 |
| 8 | EOL | **Promtail 배제, Alloy 채택** | 0장 |
| 9 | **수집 범위 확대** | NAS 는 chromadb 외 **couchdb · hyeseongkit-hub · hyeseongkit-jenkins** 까지. 모델별 성능·문서 처리·PC 자원 지표 추가 | 5-1 · 5-2 |
| 10 | 타임아웃 지표 | 설정값 gauge 는 알림용으로만. **`llm_timeout_total` 카운터**를 본다 | 5-1 |
| 11 | 로그 정리 | **PowerShell + 작업 스케줄러.** 앱·Ollama 로그를 한 스크립트가 처리 | 9-3 |
| 12 | 스케줄러 관리 | **`manage_tasks.ps1`** — 정의를 코드에 두고 `install`/`remove`/`status` | 9-4 |
| 13 | **노출면** | **Grafana(13000)만 tailnet.** Loki·Prometheus·exporter·syslog 수신기는 루프백 | 12-4 |
| 15 | **로그 시크릿** | **3중 방어** — 앱 로깅 필터 · Alloy 치환 · 본문 미수집 경계. 구축 전 샘플 육안 확인 필수 | 12-3 |
| 14 | **NAS exporter 권한** | **호스트 스크립트 + DSM 스케줄러(root).** 읽기 전용 명령만, 스크립트 권한 `700 root:root` | 12-2 |

### 11-1. 설계 단계에서 검증한 것 (2026-08-23)

11-1 로 미뤄 두었던 항목을 **구축 전에 확인했고, 두 건이 설계를 바꿨다.**

| 항목 | 결과 | 설계 반영 |
|---|---|---|
| Alloy 의 Windows 로테이션 처리 | 🔴 **미해결 결함 확인** (alloy#2292, OPEN 20개월) — 같은 이름 재생성 시 **수집이 멈춘다** | **날짜 기반 파일명으로 전환**(4-1 · 6-4). 크기 상향안 폐기 |
| Docker 로그 수집 방법 4종 | 🔴 **전부 대가 확인.** 특히 로그디렉터리 마운트는 **`config.v2.json` 으로 API 키 전부 노출**(실측) | **수집하지 않기로 결정.** exporter 메트릭으로 대체(4-2) |
| 보존 용량 | ✅ 앱 로그 약 5KB/일, 메트릭 수십 MB — **문제 없음** | Ollama·Docker 로그만 미지수(7-1) |
| Discord 알림 도달 | ✅ **검증 생략** — 기존 웹훅이 다른 곳에서 정상 동작 중임이 확인됨 | 테스트 메시지를 보내지 않는다 |

### 11-2. 여전히 구축 시점에만 확인 가능한 것

* `OLLAMA_DEBUG` 를 끈 상태의 실제 로그 생성량 — 보존 정책 재조정의 근거가 된다.

---

## 12. 보안 검토

수집을 늘리면 **접근 권한과 데이터가 함께 늘어난다.** 설계 전체를 그 관점에서 한 번 더 본다.

### 12-1. 새로 생기는 권한

| 대상 | 권한 | 평가 |
|---|---|---|
| Alloy ← syslog 수신 | 컨테이너가 **보내는 것만** 받는다 | ✅ **파일 접근도 소켓도 없다**(4-2). 다만 로그에 시크릿이 찍히면 그건 그대로 들어온다 — **12-3** |
| exporter → `config.db` | SQLite **읽기(`mode=ro`)** | 🟡 이 파일에 **프로바이더 키가 들어 있다.** exporter 는 타임아웃·모델 목록만 읽지만 **파일 전체를 읽을 수 있는 상태**다. 대안: 키 컬럼을 건드리지 않는다는 코드 규율뿐이며 **강제할 수단이 없다** |
| exporter → Docker | `docker inspect` | 🟡 root 필요. **호스트 스크립트로 돌려 소켓 마운트를 피한다**(12-2) |
| Prometheus → Bifrost `/metrics` | **인증된 읽기**(`basic_auth`) | ✅ 화이트리스트를 쓰지 않아 **인증이 유지된다.** 다만 관리자 자격증명이 하나 늘어난다 |
| Grafana | 대시보드·알림 | 🟡 Discord 웹훅이 `grafana.db` 에 저장된다 |

### 12-2. NAS exporter 와 root

**"하드웨어 메트릭만이라면 root 가 필요한가"** — 필요한 범위가 둘로 갈린다.

| 수집 대상 | 필요 권한 |
|---|---|
| CPU · 메모리 · 디스크 · uptime | **없음.** 일반 사용자로 읽는다 |
| `docker inspect` (컨테이너 상태·바인딩) | **docker 그룹 또는 root** |

🔴 **Synology 에서 `docker` 그룹은 사실상 root 다.** 그룹에 넣으면 소켓 접근이 생기고, 소켓은 컨테이너를 임의로 만들 수 있으므로 권한 상승 경로가 된다. **"docker 그룹이니까 root 보다 낫다"는 성립하지 않는다.**

**✅ 결정: exporter 를 NAS 호스트 스크립트로 두고 DSM 작업 스케줄러(root)로 돌린다.**

* **컨테이너로 만들지 않는다.** 컨테이너에 소켓을 마운트하면 **컨테이너 탈출이 곧 호스트 장악**이 된다(섹션 16 4-3장 9항). 호스트 스크립트에는 그 경로가 없다.
* **DSM 작업 스케줄러는 원래 root 로 실행된다.** 섹션 16 의 부팅 트리거 작업과 같은 방식이라 운영 방식이 새로 늘지 않는다.
* **root 를 쓰되 범위를 좁힌다.**
  * 스크립트는 **읽기 전용 명령만** 쓴다 — `docker inspect` · `docker ps` · `df` · `/proc` 읽기. `docker run` · `exec` · `rm` 을 쓰지 않는다.
  * `config.db` 같은 시크릿 포함 파일은 **NAS exporter 가 건드리지 않는다**(그건 개발 PC exporter 몫이다).
  * 파일 권한을 `700 root:root` 로 두어 **다른 사용자가 스크립트를 바꿔치기할 수 없게** 한다. root 로 도는 스크립트가 쓰기 가능하면 그 자체가 권한 상승 경로다.
* **대안으로 검토했으나 채택하지 않은 것:** 읽기 전용 소켓 프록시. 컨테이너가 하나 늘고 **그 프록시가 결국 소켓을 쥔다.** 얻는 것보다 부품이 는다.

### 12-3. 🔴 로그의 시크릿 — 3중으로 막는다

로그 수집은 **거기 찍힌 것을 그대로 가져온다.** 한 번 Loki 에 들어가면 30일간 남고, Grafana 에 접근할 수 있는 누구나 검색할 수 있다. **가장 중요하게 회피해야 할 문제다.**

**단일 방어에 의존하지 않는다.** 앱이 안 찍는 것이 최선이지만, 앱은 우리가 만들지 않은 것도 있다.

#### 1차 — 앱이 애초에 찍지 않는다 (우리 코드)

`logger_setup.py` 에 **마스킹 필터**를 붙인다. 로그 레코드가 핸들러에 닿기 전에 치환한다.

```python
# src/logger_setup.py 에 추가
import logging, re

_PATTERNS = [
    # .env 로 들어오는 값들 — 이름을 알고 있으므로 값 자체를 치환한다
    (re.compile(r'(?i)(api[_-]?key\s*[=:]\s*)\S+'),            r'<REDACTED>'),
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}'),          r'<REDACTED>'),
    (re.compile(r'(?i)(authorization\s*[=:]\s*)\S+'),           r'<REDACTED>'),
    (re.compile(r'(?i)(token\s*[=:]\s*)\S+'),                   r'<REDACTED>'),
    (re.compile(r'(?i)(webhook[s]?/)[A-Za-z0-9._\-/]+'),         r'<REDACTED>'),
    (re.compile(r'sk-[A-Za-z0-9]{16,}'),                          '<REDACTED>'),
]

class RedactFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        for pat, repl in _PATTERNS:
            msg = pat.sub(repl, msg)
        record.msg, record.args = msg, ()
        return True
```

* **`record.args` 를 비우는 것이 중요하다.** 포맷 인자에 시크릿이 들어 있으면 나중에 다시 합쳐지므로, 치환된 문자열로 확정한다.
* 🔴 **정규식은 아는 형태만 잡는다.** 새로운 시크릿 형태는 못 잡는다 — 그래서 2차·3차가 필요하다.

#### 2차 — 수집 단계에서 다시 거른다 (Alloy)

앱 로그든 컨테이너 로그든 **Loki 로 넘기기 전에** 한 번 더 치환한다. 우리가 만들지 않은 컨테이너(chromadb · couchdb · jenkins)는 여기서만 막을 수 있다.

```alloy
stage.replace {
  expression = "(?i)(api[_-]?key\s*[=:]\s*)\S+"
  replace    = "${1}<REDACTED>"
}
stage.replace {
  expression = "(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"
  replace    = "${1}<REDACTED>"
}
```

* **1차와 같은 패턴을 쓴다.** 한 곳에서 관리하고 양쪽에 반영한다.
* **`.env` 의 실제 값을 패턴에 넣지 않는다.** 설정 파일에 시크릿을 적는 셈이 된다.

#### 3차 — 애초에 본문을 보내지 않는다 (경계)

* **LLM 프롬프트·응답 본문은 Loki 로 보내지 않는다**(2-1). Langfuse 에 있다.
* `wiki_agent` 는 **개인 문서 내용**을 다룬다. 문서 본문을 로그에 찍지 않는다 — 길이·카테고리·소요 시간 같은 **메타데이터만** 남긴다(5-1 의 `wiki_document_chars` 등이 그 형태다).
* **메트릭에는 값이 아니라 수치만 넣는다.** 라벨에 사용자 입력을 넣지 않는다 — 카디널리티 문제이기도 하고, 라벨은 마스킹 대상에서 빠지기 쉽다.

#### 구축 시 반드시 할 것

🔴 **각 로그 소스의 샘플을 눈으로 확인한다.** 정규식이 무엇을 놓치는지는 실제 로그를 봐야 안다.

```bash
docker logs chromadb --tail 200 | grep -iE 'key|token|auth|password|secret'
```

* 대상: `chromadb` · `couchdb-obsidian-sync` · `hyeseongkit-hub` · `hyeseongkit-jenkins` · `bifrost` · `open-webui`, 그리고 앱 로그 4종.
* **Jenkins 를 특히 본다** — CI 는 자격증명을 다루고, 빌드 로그에 환경변수가 찍히는 사고가 흔하다.
* 놓친 형태를 찾으면 **패턴에 추가하고 1차·2차 양쪽에 반영한다.**

> **이미 들어간 시크릿은 지우기 어렵다.** Loki 는 로그 삭제가 번거롭고, 그 사이 Grafana 로 조회됐을 수 있다. **넣지 않는 것이 유일하게 확실한 방법**이므로 구축 전에 확인한다.

### 12-4. 노출면 정리

| | 인바운드 포트 | 바인딩 |
|---|---|---|
| 개발 PC exporter | 13092 | **`127.0.0.1` 전용** — tailnet 에도 열지 않는다 |
| 개발 PC Alloy | 없음 (push) | — |
| NAS Grafana·Loki·Prometheus | 13000·13100·13090 | **tailnet + 루프백만.** `:?` 가드 필수 |
| NAS exporter | 13091 | **`127.0.0.1` 전용** — 같은 호스트의 Alloy 만 |

* **Loki 와 Prometheus 를 tailnet 에 열 필요가 있는가.** Grafana 만 열고 나머지는 `127.0.0.1` 로 두면 노출면이 셋에서 하나로 준다. **Grafana 가 같은 compose 네트워크 안에서 접근**하면 된다.
* ✅ **결정: Grafana(13000)만 tailnet 에 연다.** Loki·Prometheus·exporter 는 전부 루프백/내부 네트워크.

### 12-5. 데이터 자체의 민감도

* Loki 에 쌓이는 것은 **인프라 로그**이지 문서 내용이 아니다(12-3 의 경계를 지키는 한).
* Prometheus 메트릭은 **수치와 라벨뿐**이다. 다만 `container` · `model` 라벨로 **시스템 구성이 드러난다** — tailnet 한정이므로 수용한다.
* **백업 주의:** `grafana.db`(웹훅)와 Loki·Prometheus 볼륨을 저장소에 넣지 않는다. `.gitignore` 확인.

---
