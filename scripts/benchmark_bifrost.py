"""Bifrost 게이트웨이 경유 모델들의 생성 성능을 측정해 회귀를 감지한다.

지표는 **토큰/초**다. 지연시간을 그대로 쓰지 않는 이유는 아래 CAP_NOTE 참조.
"""
import os
import time

import requests

MODELS = os.environ.get("BENCHMARK_MODELS", "qwen3.5:9b,qwen2.5-coder:7b").split(",")
PROMPT = "간단히 자기소개를 1문장으로 해줘."
WARMUP_PROMPT = "안녕"
MAX_TOKENS = 128

CAP_NOTE = (
    "**지표는 토큰/초다.** Bifrost의 Ollama 프로바이더가 출력 상한을 전달하지 않아"
    " (`max_tokens` / `max_completion_tokens` / 네이티브 `num_predict` 모두 무시됨,"
    " 2026-08-22 실측) 총 지연시간이 모델의 수다스러움에 좌우된다."
    " 생성량으로 나눠 정규화해야 회귀 신호로 쓸 수 있다."
)


def unload_ollama_model(ollama_url: str, model: str) -> None:
    """모델 전환 시 8GB VRAM 경합(로딩 지연/타임아웃)을 막기 위해, 벤치마크한
    모델을 다음 모델을 부르기 전에 명시적으로 퇴거한다 (wiki_agent.py와 동일 패턴).
    Ollama 모델이 아닌 경우 그냥 실패하고 무시된다."""
    try:
        requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=15,
        )
    except Exception:
        pass
    time.sleep(5)


def _post(base_url: str, api_key: str, model: str, prompt: str, timeout: int) -> requests.Response:
    return requests.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            # 게이트웨이가 지금은 버리지만 계속 보낸다. 나중에 변환이 생기면
            # 그때부터 상한이 걸리고, 아래 cap_applied 가 그 변화를 잡아낸다.
            "max_tokens": MAX_TOKENS,
        },
        timeout=timeout,
    )


def benchmark_model(base_url: str, api_key: str, model: str) -> dict:
    # 워밍업 — 타이머 밖에서 모델을 VRAM에 올린다. 이걸 빼면 측정값에 로딩
    # 시간이 섞여, 회귀가 아니라 로딩 편차를 보게 된다.
    try:
        _post(base_url, api_key, model, WARMUP_PROMPT, timeout=180).raise_for_status()
    except Exception:
        pass  # 워밍업 실패는 본 측정에서 어차피 드러난다

    start = time.perf_counter()
    resp = _post(base_url, api_key, model, PROMPT, timeout=180)
    elapsed = time.perf_counter() - start
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens")
    finish_reason = (data.get("choices") or [{}])[0].get("finish_reason")

    return {
        "model": model,
        "latency_sec": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": (
            round(completion_tokens / elapsed, 1)
            if completion_tokens and elapsed > 0
            else None
        ),
        # 보낸 제약이 실제로 적용됐는지 응답으로 확인한다 (섹션 17 교훈).
        # 자연 종료(짧은 답변)와 "상한이 걸렸다"는 구분해야 하므로 3상태다 —
        # 생성량이 상한을 넘으면 무시된 것이 확정, finish=length면 걸린 것이 확정,
        # 그 외에는 답이 짧아서 판정할 수 없다.
        "cap_state": (
            "무시됨"
            if completion_tokens is not None and completion_tokens > MAX_TOKENS
            else "적용됨"
            if finish_reason == "length"
            else "미확정"
        ),
        "finish_reason": finish_reason,
    }


def main() -> None:
    # 아래 _post()가 "/v1/chat/completions"를 직접 붙이므로, 값에 이미
    # "/v1"이 들어있으면 떼어낸다 (impact_analysis.py와 동일한 이유 — 그쪽 주석 참고).
    base_url = os.environ["BIFROST_BASE_URL"].rstrip("/").removesuffix("/v1")
    api_key = os.environ["BIFROST_API_KEY"]
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    rows = []
    for i, model in enumerate(MODELS):
        model = model.strip()
        if not model:
            continue
        try:
            rows.append(benchmark_model(base_url, api_key, model))
        except Exception as e:
            rows.append({"model": model, "error": str(e)})
        finally:
            # 마지막 모델까지 굳이 퇴거할 필요는 없지만, 중간 모델은 다음
            # 모델 로딩과 VRAM을 다투지 않도록 매번 퇴거한다.
            if i < len(MODELS) - 1:
                unload_ollama_model(ollama_url, model)

    lines = [
        "| 모델 | 토큰/초 | 지연시간(초) | 생성 토큰 | 출력 상한 | 비고 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['model']} | - | - | - | - | 실패: {row['error']} |")
            continue
        cap = row["cap_state"]
        if cap == "무시됨":
            cap = f"무시됨 (> {MAX_TOKENS})"
        elif cap == "미확정":
            cap = "미확정 (자연 종료)"
        lines.append(
            f"| {row['model']} | {row['tokens_per_sec']} | {row['latency_sec']} |"
            f" {row['completion_tokens']} | {cap} | finish={row['finish_reason']} |"
        )
    table = "\n".join(lines) + f"\n\n{CAP_NOTE}"
    print(table)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(f"## Bifrost 성능 벤치마크\n\n{table}\n")


if __name__ == "__main__":
    main()
