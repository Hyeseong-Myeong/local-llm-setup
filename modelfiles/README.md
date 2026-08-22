# Modelfile — 컨텍스트 상한을 모델에 내장한다

게이트웨이(Bifrost)가 `num_ctx` 를 전달하지 못하므로(`Docs/context_limit_experiment.md` D-1),
컨텍스트를 늘리려면 **모델 자체에 기본값을 넣는 방법밖에 없다.** 요청에 옵션이 없어도 적용된다.

| 파일 | 파생 모델명 | num_ctx | 적재 크기 |
|---|---|---|---|
| `qwen3.5-16k.Modelfile` | `qwen3.5-16k` | 16,384 | 6.06GB |
| `qwen2.5-coder-16k.Modelfile` | `qwen2.5-coder-16k` | 16,384 | 5.46GB |
| `gemma4-e4b-64k.Modelfile` | `gemma4-e4b-64k` | 65,536 | 3.37GB |

전부 100% GPU 이며, 임베딩 모델(`bge-m3`, 0.66GB)과 동시 상주가 가능한 값이다.
근거와 측정 과정은 `Docs/context_limit_experiment.md` 7장.

## 왜 `num_ctx` 만 적는가

`FROM` 이 원본의 `PARAMETER` · `SYSTEM` · `TEMPLATE` 을 **모두 상속**한다 (2026-08-22 실측 확인).
따라서 바꿀 값만 적으면 되고, 원본 설정을 옮겨 적으면 원본이 바뀔 때 어긋난다.

* `qwen3.5:9b` — `presence_penalty 1.5` · `temperature 1` · `top_k 20` · `top_p 0.95` 상속
* `qwen2.5-coder:7b` — `PARAMETER` 는 없고 **`SYSTEM` 메시지(68자)** 상속
* `gemma4:e4b` — `top_k 64` · `top_p 0.95` · `temperature 1` 상속

## 1. 모델 생성

```bash
ollama create qwen3.5-16k        -f modelfiles/qwen3.5-16k.Modelfile
ollama create qwen2.5-coder-16k  -f modelfiles/qwen2.5-coder-16k.Modelfile
ollama create gemma4-e4b-64k     -f modelfiles/gemma4-e4b-64k.Modelfile
```

디스크는 거의 늘지 않는다 — 원본의 blob 을 공유하고 매니페스트만 새로 생긴다.
되돌리려면 `ollama rm <이름>`.

**확인:**

```bash
ollama show --parameters qwen3.5-16k     # num_ctx 와 상속된 값이 함께 보여야 한다
```

## 2. Bifrost 에 모델 등록 (필수)

**Bifrost 는 등록되지 않은 모델을 거부한다** — `403 model_blocked` 또는
`400 could not auto resolve a provider`. 생성만 하고 등록하지 않으면 게이트웨이로 쓸 수 없다.

> 🔴 **`Allowed Models` 가 `All Models` 여도 새 모델은 자동으로 잡히지 않는다.**
> 그 값은 실시간 와일드카드가 아니라 **설정 시점에 발견된 목록의 스냅샷**이다.
> 2026-08-22 실측 — `qwen3.5-16k` 생성 직후 `403 model_blocked`, **Bifrost 컨테이너를
> 재시작해도 그대로**였다. 반면 기존 `bge-m3:latest` 는 200 이다.
> 즉 **파생 모델은 반드시 직접 추가해야 한다.**

설정은 `bifrost.yaml` 이 아니라 **내부 SQLite(`bifrost/data/config.db`)** 에 있고
**Web UI 로만 관리한다** (`archive/bifrost.yaml` 은 쓰이지 않는 파일이다).

1. 브라우저에서 **`http://127.0.0.1:18080`** 을 연다.
2. **Providers → `ollama`** 를 선택한다.
3. 모델 목록에 위에서 만든 파생 모델명을 추가한다.
   * 🔴 **태그까지 적어야 한다 — `qwen3.5-16k:latest`.** `ollama create` 로 만든 모델은
     `:latest` 가 붙으며, **태그 없이 부르면 `400 could not auto resolve a provider`** 다
     (2026-08-22 실측). `bge-m3:latest` 와 같은 규칙이다.
   * 원본 모델은 태그가 이름에 포함돼 있다 (`qwen3.5:9b`).
   * **allow list 에 저장되는 이름도 태그까지 포함해야 한다.** 이름은 정규화되지 않고
     그대로 비교된다 — `qwen3.5-16k:latest` 가 등록돼 있을 때 `ollama/qwen3.5-16k`
     요청은 `403 model_blocked` 다 (2026-08-22 실측).
4. 저장한다. 설정은 볼륨(`./data`)에 남아 컨테이너를 다시 만들어도 유지된다.

> **`All Models` 를 명시 목록으로 바꾼다면** 현재 쓰이는 모델을 **전부** 넣어야 한다.
> 빠뜨리면 조용히 `403` 이 된다. Ollama 서버 기준 전수:
>
> | 모델 | 쓰는 곳 |
> |---|---|
> | `qwen3.5:9b` | `wiki_agent` (`.env` 의 `MODEL_NAME`), 벤치마크 |
> | `qwen2.5-coder:7b` | 벤치마크 (`BENCHMARK_MODELS` 기본값) |
> | `bge-m3:latest` | **임베딩 4곳** — 태그까지 정확히 |
> | `qwen3.5-16k:latest` · `qwen2.5-coder-16k:latest` · `gemma4-e4b-64k:latest` | 위에서 만든 파생 모델 — **태그 필수** |
>
> `impact_analysis.py` 는 `groq/openai/gpt-oss-120b` 를 쓰므로 **groq 프로바이더** 쪽이고
> Ollama 서버 목록과 무관하다. Open WebUI 에서 직접 고르는 모델은 지금은 Ollama 를
> 직접 부르므로 무관하지만, 게이트웨이 경유로 바꾸면 함께 등록해야 한다.
>
> **권장: `All Models` 를 유지하고 파생 모델만 추가한다.** 명시 목록으로 바꾸면
> 앞으로 모델을 추가할 때마다 등록을 기억해야 하고, 빠뜨린 것이 조용히 실패한다.

**확인:**

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H "Authorization: Bearer $BIFROST_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-16k","messages":[{"role":"user","content":"안녕"}]}'
```

`403` / `400` 이면 등록이 안 된 것이다.

## 3. 소비처 전환

`.env` 의 `MODEL_NAME` 을 파생 모델명으로 바꾸면 `wiki_agent` 가 그것을 쓴다.
**`:latest` 를 빼먹지 말 것** — `MODEL_NAME=qwen3.5-16k:latest`.
Open WebUI 는 모델 선택 목록에서 고른다.

> ⚠️ **원본 모델은 그대로 둔다.** 파생 모델은 컨텍스트가 커서 임베딩과의 동시 상주 여유가
> 줄어든다. 상한이 필요 없는 용도까지 전부 옮길 이유는 없다.
