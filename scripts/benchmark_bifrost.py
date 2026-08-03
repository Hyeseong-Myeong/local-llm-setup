"""Bifrost 게이트웨이 경유 모델들의 응답 지연시간을 측정해 회귀를 감지한다."""
import os
import time

import requests

MODELS = os.environ.get("BENCHMARK_MODELS", "qwen3.5:9b,qwen2.5-coder:7b").split(",")
PROMPT = "간단히 자기소개를 1문장으로 해줘."


def benchmark_model(base_url: str, api_key: str, model: str) -> dict:
    start = time.perf_counter()
    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 128,
        },
        timeout=120,
    )
    elapsed = time.perf_counter() - start
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return {
        "model": model,
        "latency_sec": round(elapsed, 2),
        "completion_tokens": usage.get("completion_tokens"),
    }


def main() -> None:
    base_url = os.environ["BIFROST_BASE_URL"].rstrip("/")
    api_key = os.environ["BIFROST_API_KEY"]

    rows = []
    for model in MODELS:
        model = model.strip()
        if not model:
            continue
        try:
            rows.append(benchmark_model(base_url, api_key, model))
        except Exception as e:
            rows.append({"model": model, "error": str(e)})

    lines = ["| 모델 | 지연시간(초) | 생성 토큰 | 비고 |", "|---|---|---|---|"]
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['model']} | - | - | 실패: {row['error']} |")
        else:
            lines.append(f"| {row['model']} | {row['latency_sec']} | {row['completion_tokens']} | |")
    table = "\n".join(lines)
    print(table)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(f"## Bifrost 성능 벤치마크\n\n{table}\n")


if __name__ == "__main__":
    main()
