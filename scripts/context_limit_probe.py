"""로컬 모델이 100% GPU 적재를 유지하는 컨텍스트 상한을 실측한다.

설계·판정 기준·안전장치는 Docs/context_limit_experiment.md 를 따른다.
게이트웨이는 num_ctx / num_predict 를 전달하지 못하므로(섹션 17) Ollama 를 직접 호출한다.

측정만 하고 아무것도 바꾸지 않는다 — 모델 생성·삭제·설정 변경 없음.
"""
import argparse
import json
import os
import statistics
import sys
import time
from typing import Optional

import requests

# 한국어 Windows 콘솔(cp949)에서 표가 깨지지 않게 한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLLAMA = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

CTX_CANDIDATES = [2048, 4096, 8192, 16384, 32768, 65536]
PREDICT_CANDIDATES = [128, 512, 1024, 2048]
PROBE_PROMPT = "안녕"
GEN_PROMPT = "로컬 LLM 운영에서 관측성이 왜 중요한지 설명해줘."


# ---------------------------------------------------------------- 기본 조작

def unload(model: str) -> None:
    """다음 모델과 VRAM 을 다투지 않도록 명시적으로 퇴거시킨다."""
    try:
        requests.post(
            f"{OLLAMA}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=30,
        )
    except Exception:
        pass
    time.sleep(3)


def model_max_ctx(model: str) -> Optional[int]:
    """모델이 선언한 최대 컨텍스트. 후보값을 넘어서 시도하지 않기 위해 쓴다."""
    try:
        info = requests.post(f"{OLLAMA}/api/show", json={"model": model}, timeout=30).json()
        for key, value in (info.get("model_info") or {}).items():
            if key.endswith(".context_length"):
                return int(value)
    except Exception:
        pass
    return None


def chat(model: str, prompt: str, options: dict, timeout: int) -> dict:
    resp = requests.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": options,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def ps_entry(model: str) -> Optional[dict]:
    """/api/ps 는 size 와 size_vram 을 함께 준다 — CLI 표를 파싱하는 것보다 정확하다."""
    try:
        for entry in requests.get(f"{OLLAMA}/api/ps", timeout=15).json().get("models", []):
            if entry.get("name") == model or entry.get("model") == model:
                return entry
    except Exception:
        pass
    return None


def gpu_ratio(entry: dict) -> Optional[float]:
    """VRAM 에 올라간 비율. 1.0 이면 100% GPU."""
    size, vram = entry.get("size"), entry.get("size_vram")
    if not size:
        return None
    return (vram or 0) / size


def tokens_per_sec(data: dict) -> Optional[float]:
    count, dur = data.get("eval_count"), data.get("eval_duration")
    if not count or not dur:
        return None
    return round(count / (dur / 1e9), 1)


def gb(n) -> str:
    return f"{n / 1e9:.2f}GB" if n else "-"


# ---------------------------------------------------------------- 실험

def experiment_a(models, timeout: int, max_ctx: int) -> list:
    """컨텍스트 상한 탐색. 첫 실패에서 그 모델을 중단한다(단조 증가 전제)."""
    rows = []
    print("\n## 실험 A — 정적 컨텍스트 상한\n")
    for model in models:
        declared = model_max_ctx(model)
        suffix = f"  (모델 최대 컨텍스트 {declared:,})" if declared else ""
        print(f"### {model}{suffix}")
        best = None
        # 왜 멈췄는지를 구분해서 들고 간다. "상한을 찾았다"와 "더 시도하지
        # 않고 멈췄다"는 다르다 — 뭉뚱그리면 캡에 걸린 값을 상한으로 오독한다.
        stopped = "미탐색"
        for ctx in CTX_CANDIDATES:
            if ctx > max_ctx:
                print(f"  num_ctx={ctx:<6} 건너뜀 — --max-ctx({max_ctx}) 초과")
                stopped = "캡 도달"
                break
            if declared and ctx > declared:
                print(f"  num_ctx={ctx:<6} 건너뜀 — 모델 최대 컨텍스트 초과")
                stopped = "모델 최대 도달"
                break

            unload(model)
            started = time.perf_counter()
            try:
                # num_predict=1 — 적재만 시키고 생성은 하지 않는다.
                chat(model, PROBE_PROMPT, {"num_ctx": ctx, "num_predict": 1}, timeout)
            except Exception as exc:
                rows.append({"model": model, "num_ctx": ctx, "verdict": "적재 실패",
                             "note": f"{type(exc).__name__}: {str(exc)[:60]}"})
                print(f"  num_ctx={ctx:<6} [FAIL] 적재 실패 — {type(exc).__name__}")
                stopped = "적재 실패"
                break
            elapsed = round(time.perf_counter() - started, 1)

            entry = ps_entry(model)
            if not entry:
                rows.append({"model": model, "num_ctx": ctx, "verdict": "ps 조회 실패"})
                print(f"  num_ctx={ctx:<6} [WARN] /api/ps 에서 찾지 못함")
                stopped = "ps 조회 실패"
                break

            ratio = gpu_ratio(entry)
            row = {
                "model": model, "num_ctx": ctx,
                "applied_ctx": entry.get("context_length"),
                "size": entry.get("size"), "size_vram": entry.get("size_vram"),
                "gpu_pct": round(ratio * 100, 1) if ratio is not None else None,
                "load_sec": elapsed,
            }
            if ratio is not None and ratio >= 0.999:
                row["verdict"] = "100% GPU"
                best = ctx
                rows.append(row)
                print(f"  num_ctx={ctx:<6} [OK] 100% GPU   size={gb(entry.get('size'))} "
                      f"적용ctx={entry.get('context_length')} load={elapsed}s")
            else:
                row["verdict"] = "CPU 분할"
                rows.append(row)
                print(f"  num_ctx={ctx:<6} [FAIL] CPU 분할 — GPU {row['gpu_pct']}% "
                      f"(vram={gb(entry.get('size_vram'))} / size={gb(entry.get('size'))}) "
                      f"-> 여기서 중단")
                stopped = "CPU 분할"
                break

        # 판정은 3상태다. "상한을 찾았다"(다음 후보에서 CPU 분할)와
        # "더 시도하지 않고 멈췄다"(캡·모델 최대 도달)를 뭉뚱그리면,
        # 캡에 걸린 값을 하드웨어 상한으로 오독한다.
        if best is None:
            print(f"  -> **{model}: 최소 후보(2048)에서도 100% GPU 실패** ({stopped})\n")
        elif stopped == "CPU 분할":
            print(f"  -> **{model} 상한 확정: num_ctx={best:,}** (다음 후보에서 CPU 분할)\n")
        else:
            print(f"  -> **{model}: num_ctx={best:,} 까지 100% GPU 확인 — 상한 미확정** "
                  f"({stopped}로 탐색 중단)\n")
        unload(model)
    return rows


def experiment_b(model: str, num_ctx: int, timeout: int) -> list:
    """생성 길이에 따른 처리량 곡선."""
    rows = []
    print(f"\n## 실험 B — 처리량 곡선 ({model}, num_ctx={num_ctx:,})\n")
    unload(model)
    # 워밍업 — 적재 시간이 첫 측정에 섞이지 않게 한다.
    try:
        chat(model, PROBE_PROMPT, {"num_ctx": num_ctx, "num_predict": 1}, timeout)
    except Exception as exc:
        print(f"  워밍업 실패: {exc}")
        return rows

    for predict in PREDICT_CANDIDATES:
        try:
            data = chat(model, GEN_PROMPT, {"num_ctx": num_ctx, "num_predict": predict}, timeout)
        except Exception as exc:
            print(f"  num_predict={predict:<5} [FAIL] {type(exc).__name__}")
            continue
        tps = tokens_per_sec(data)
        rows.append({"model": model, "num_predict": predict, "tps": tps,
                     "eval_count": data.get("eval_count"),
                     "done_reason": data.get("done_reason")})
        print(f"  num_predict={predict:<5} {tps} tok/s  "
              f"eval_count={data.get('eval_count')}  done={data.get('done_reason')}")
    unload(model)
    return rows


def experiment_c(models, runs: int, timeout: int) -> list:
    """상한 없이 자연 생성량 분포 — 막으려는 대상의 크기를 잰다."""
    rows = []
    print(f"\n## 실험 C — 자연 생성량 분포 ({runs}회)\n")
    for model in models:
        unload(model)
        counts = []
        for i in range(1, runs + 1):
            try:
                # num_predict 를 주지 않는다 — 자유 생성이 이 실험의 대상이다.
                data = chat(model, GEN_PROMPT, {}, timeout)
            except Exception as exc:
                print(f"  {model} #{i} [FAIL] {type(exc).__name__}")
                continue
            count = data.get("eval_count")
            counts.append(count)
            rows.append({"model": model, "run": i, "eval_count": count,
                         "done_reason": data.get("done_reason"),
                         "tps": tokens_per_sec(data)})
            print(f"  {model} #{i}  eval_count={count}  done={data.get('done_reason')}  "
                  f"{tokens_per_sec(data)} tok/s")
        if counts:
            print(f"  -> 중앙값 {int(statistics.median(counts))}  "
                  f"최대 {max(counts)}  최소 {min(counts)}\n")
        unload(model)
    return rows


# ---------------------------------------------------------------- 진입점

def agents_running() -> bool:
    """FastAPI 툴 서버가 떠 있으면 백그라운드 에이전트도 도는 중으로 본다."""
    try:
        requests.get("http://127.0.0.1:9000/docs", timeout=2)
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=["a", "b", "c", "all"], default="a")
    parser.add_argument("--models", default="qwen2.5-coder:7b,qwen3.5:9b",
                        help="쉼표 구분. 실험 C 는 thinking 모델만 넣는 편이 의미 있다")
    parser.add_argument("--timeout", type=int, default=300, help="요청당 타임아웃(초)")
    parser.add_argument("--max-ctx", type=int, default=65536, help="시도할 num_ctx 상한 캡")
    parser.add_argument("--runs", type=int, default=3, help="실험 C 반복 횟수")
    parser.add_argument("--ctx", type=int, default=4096, help="실험 B 에서 쓸 num_ctx")
    parser.add_argument("--out", default="", help="결과 JSON 저장 경로")
    parser.add_argument("--allow-concurrent", action="store_true",
                        help="백그라운드 에이전트가 떠 있어도 강행한다")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print("=" * 72)
    print("컨텍스트 상한 실측 — 설계: Docs/context_limit_experiment.md")
    print(f"엔드포인트 {OLLAMA} · 타임아웃 {args.timeout}s · num_ctx 캡 {args.max_ctx:,}")
    print("=" * 72)

    if agents_running() and not args.allow_concurrent:
        print("\n[중단] FastAPI 툴 서버(:9000)가 응답합니다 — 백그라운드 에이전트가 도는 중입니다.")
        print("       같은 GPU 를 다투면 측정값이 오염되고 에이전트가 타임아웃으로 죽을 수 있습니다.")
        print("       shutdown.bat 으로 먼저 정지하거나, 감수하겠다면 --allow-concurrent 를 주세요.")
        sys.exit(1)

    results = {}
    if args.experiment in ("a", "all"):
        results["a"] = experiment_a(models, args.timeout, args.max_ctx)
    if args.experiment in ("b", "all"):
        results["b"] = experiment_b(models[0], args.ctx, args.timeout)
    if args.experiment in ("c", "all"):
        results["c"] = experiment_c(models, args.runs, args.timeout)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {args.out}")


if __name__ == "__main__":
    main()
