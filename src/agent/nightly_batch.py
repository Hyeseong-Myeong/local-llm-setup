"""야간 배치 — vault 전체 교차 점검 (Docs/local_model_feature_proposals.md ④).

하는 일: 임베딩 유사도로 "관련 있어 보이는데 서로 연결되지 않은 문서 쌍"을 찾고,
고컨텍스트 로컬 모델이 그 쌍을 판정해 제안문을 쓴다. **문서를 직접 고치지 않는다** —
제안 파일만 남기고 채택은 사람이 한다.

🔴 설계에서 고친 것 — 단계 순서:
  원래 설계는 "[2] 임베딩 언로드 -> [4] vault 크로스체크" 였다. 그런데 크로스체크의
  첫 단계인 "관련 있으나 연결되지 않은 문서 쌍 찾기"가 **임베딩 유사도 조회**다 —
  임베딩을 내린 뒤에는 할 수 없다. 그래서 순서를 바꿨다:
      벡터 단계(임베딩 필요) -> 임베딩 언로드 -> LLM 단계(고ctx 모델)
  구현하면서 드러났고, 설계 시점에 놓친 부분이다.

🔴 왜 Ollama 를 직접 부르는가:
  야간 모델(gemma4-e4b-128k)은 Bifrost 에 등록하지 않기로 했다 — 등록하면 Open WebUI
  목록에 떠서 사람이 실수로 부르고, 그러면 복구 책임 지점 없이 임베딩이 축출된다
  (적재 시 임베딩 축출은 2026-10-17 실측 확인). 그 대가로 이 호출은 게이트웨이를
  지나지 않아 Langfuse 에 안 잡힌다 — 배치 자체 로그와 메트릭으로 메운다.

실행:
    python src/agent/nightly_batch.py            # 실제 실행
    python src/agent/nightly_batch.py --dry-run  # 모델 전환 없이 벡터 단계까지만
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logger_setup

logger_setup.setup_logger("nightly_batch.log")

import requests

from chroma_client import get_chroma_client
from config import settings
from embedding_function import get_embedding_function
from tools.wiki_tools import search_wiki

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# exporter 가 이 파일의 존재와 mtime 을 읽어 nightly_batch_mode /
# nightly_batch_lock_age_seconds 를 낸다.
LOCK_PATH = os.path.join(REPO_ROOT, "tmp", "nightly_batch.lock")
SUGGEST_DIR = os.path.join(REPO_ROOT, "tmp", "nightly_suggestions")

EMBEDDING_MODEL = "bge-m3:latest"
NIGHTLY_MODEL = "gemma4-e4b-128k:latest"

# 코사인 유사도가 이보다 높으면 "관련 있어 보인다"로 본다. 0.65 는 보수적으로 잡은
# 출발값이다 — 제안이 너무 많거나 적으면 조정한다.
SIMILARITY_THRESHOLD = 0.65
MAX_PAIRS = 15  # LLM 단계 비용 상한

GPU_RATIO_MIN = 0.99  # 100% GPU 적재가 아니면 작업하지 않는다

# 실행을 허용하는 시각 구간 [시작, 끝) — 05:00 정규 실행 + 늦어진 보충 실행의 여유.
#
# 왜 필요한가: 작업 스케줄러에 "놓친 시작은 가능한 한 빨리 실행"을 켜 두는데, PC 가
# 최대 절전/종료 상태였으면 그 보충 실행이 **낮에** 걸릴 수 있다. 그러면 사용자가
# 작업하는 중에 임베딩이 약 2분간 내려가 RAG 가 끊긴다. 시각으로 막는다.
# 수동 실행은 --now 로 무시한다.
ALLOWED_HOUR_RANGE = (4, 9)


def _log(msg):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    print("[" + stamp + "] " + msg, flush=True)


def notify_discord(message):
    url = settings.DISCORD_WEBHOOK_URL
    if not url or url == "여기에_웹훅_주소를_입력하세요":
        return
    try:
        requests.post(url, json={"content": message}, timeout=5)
    except Exception as exc:
        _log("Discord 전송 실패(무시): " + str(exc))


def _ollama(path):
    return settings.OLLAMA_BASE_URL.rstrip("/") + path


def ollama_ps():
    try:
        r = requests.get(_ollama("/api/ps"), timeout=10)
        r.raise_for_status()
        return r.json().get("models", [])
    except Exception as exc:
        _log("/api/ps 조회 실패: " + str(exc))
        return []


def is_resident(model):
    return any(m.get("name") == model for m in ollama_ps())


def unload(model):
    try:
        requests.post(_ollama("/api/generate"), json={"model": model, "keep_alive": 0}, timeout=30)
    except Exception as exc:
        _log(model + " 언로드 요청 실패: " + str(exc))


def load_and_check_gpu(model):
    """모델을 적재하고 GPU 비율을 돌려준다. 실패하면 None."""
    try:
        payload = {
            "model": model,
            "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1},
        }
        requests.post(_ollama("/api/generate"), json=payload, timeout=900).raise_for_status()
    except Exception as exc:
        _log(model + " 적재 실패: " + str(exc))
        return None
    for m in ollama_ps():
        if m.get("name") == model:
            size = m.get("size") or 0
            if not size:
                return 0.0
            return (m.get("size_vram") or 0) / size
    return None


# 락이 이 시간보다 오래되면 PID 가 살아있어 보여도 버려진 것으로 본다.
# PID 는 재사용되므로 생존 확인만으로는 부족하다.
LOCK_STALE_SECONDS = 3 * 3600


def lock_is_stale():
    """락이 버려진 것인지 — 기록된 PID 가 죽었거나 너무 오래됐으면 참.

    2026-10-19 고장 주입 시험에서 드러난 문제다. 강제 종료(TerminateProcess)는
    finally 를 건너뛰므로 락이 남는다. 임베딩은 exporter 의 5분 주기 임베딩 체크가
    알아서 되살렸지만(실측 30초), **락은 아무도 치우지 않는다.** 그대로 두면
    nightly_batch_mode 가 계속 1 이라 장애 알림 조건을 가리고, 다음 배치도 막힌다.

    exporter(local_exporter.collect_nightly_batch_metrics)에도 같은 판정이 있다 —
    그쪽은 메트릭을 가리지 않기 위해, 여기는 다음 실행을 막지 않기 위해 필요하다.
    """
    try:
        age = time.time() - os.path.getmtime(LOCK_PATH)
    except OSError:
        return True
    if age > LOCK_STALE_SECONDS:
        return True
    try:
        with open(LOCK_PATH, encoding="utf-8") as f:
            pid = int(json.load(f).get("pid", 0))
    except (OSError, ValueError, TypeError):
        return True  # 읽을 수 없는 락은 쓰레기로 본다
    if not pid:
        return True
    try:
        import psutil

        return not psutil.pid_exists(pid)
    except ImportError:
        return False  # 판정할 수 없으면 보수적으로 "살아있다"로 둔다


def gate(ignore_hours=False):
    """사전 점검 — 하나라도 걸리면 아무것도 건드리지 않고 중단한다."""
    hour = datetime.datetime.now().hour
    start, end = ALLOWED_HOUR_RANGE
    if not ignore_hours and not (start <= hour < end):
        _log(
            "중단: 현재 %d시는 허용 구간(%d~%d시) 밖이다. "
            "놓친 시작을 낮에 보충 실행해 RAG 를 끊는 것을 막는다(--now 로 무시 가능)."
            % (hour, start, end)
        )
        return False

    if os.path.isfile(LOCK_PATH):
        age_min = (time.time() - os.path.getmtime(LOCK_PATH)) / 60
        if lock_is_stale():
            # 버려진 락이다 — 치우고 진행한다. 치우지 않으면 한 번의 강제 종료가
            # 이후 모든 배치를 영구히 막는다.
            _log("버려진 락 발견(나이 %.1f분, 프로세스 없음) — 정리하고 진행한다." % age_min)
            notify_discord(
                "🟡 야간 배치: 지난 실행이 비정상 종료된 흔적(버려진 락, 나이 %.0f분)을 "
                "정리하고 진행한다." % age_min
            )
            try:
                os.unlink(LOCK_PATH)
            except OSError as exc:
                _log("락 정리 실패 — 중단한다: %s" % exc)
                return False
        else:
            _log("중단: 락 파일이 있고 해당 프로세스가 살아있다(나이 %.1f분)." % age_min)
            return False

    raw_dir = settings.RAW_DIR
    if os.path.isdir(raw_dir):
        pending = [f for f in os.listdir(raw_dir) if f.endswith(".md")]
        if pending:
            _log("중단: RAW_DIR 에 미처리 파일 %d건 — wiki_agent 와 모델 적재를 다툰다." % len(pending))
            return False

    _log("사전 점검 통과. 현재 적재: " + str([m.get("name") for m in ollama_ps()]))
    return True


def _doc_centroids(collection):
    """문서(source)별 임베딩 중심(L2 정규화)과 메타데이터를 모은다."""
    got = collection.get(include=["embeddings", "metadatas"])
    embs = got.get("embeddings")
    metas = got.get("metadatas") or []
    sums, counts, meta_by_src = {}, {}, {}
    for i, meta in enumerate(metas):
        src = (meta or {}).get("source")
        if not src or embs is None or i >= len(embs):
            continue
        vec = [float(v) for v in embs[i]]
        if src not in sums:
            sums[src] = [0.0] * len(vec)
            counts[src] = 0
            meta_by_src[src] = meta or {}
        sums[src] = [a + b for a, b in zip(sums[src], vec)]
        counts[src] += 1

    centroids = {}
    for src, vec in sums.items():
        n = counts[src] or 1
        avg = [v / n for v in vec]
        norm = sum(v * v for v in avg) ** 0.5 or 1.0
        centroids[src] = [v / norm for v in avg]
    return centroids, meta_by_src


def _vault_links():
    """vault 각 문서가 참조하는 위키링크 집합. [[...]] 를 긁는다."""
    links = {}
    for directory in (settings.TECH_DIR, settings.CAREER_DIR, settings.PERSONAL_DIR):
        for path in glob.glob(os.path.join(directory, "*.md")):
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            links[stem] = set(m.strip() for m in re.findall(r"\[\[([^\]]+)\]\]", body))
    return links


def _already_linked(a, b, links):
    """두 문서가 이미 서로를 참조하는가. 위키링크에 확장자가 붙기도 해서 느슨하게 본다."""
    for link in links.get(a, set()):
        if b in link or link in b:
            return True
    for link in links.get(b, set()):
        if a in link or link in a:
            return True
    return False


def vector_stage(collection):
    """임베딩이 올라온 상태에서만 가능한 조회를 모두 끝낸다.

    리랭커를 **강제로 켠다**(use_rerank=True) — 배치는 지연이 무관하고, 교차 문서
    비교는 검색 정확도가 곧 결과 품질이라 리랭킹 이득이 가장 큰 자리다.
    """
    centroids, meta_by_src = _doc_centroids(collection)
    links = _vault_links()
    link_count = sum(len(v) for v in links.values())
    _log("문서 %d개 중심 계산 완료. vault 위키링크 %d건." % (len(centroids), link_count))

    srcs = sorted(centroids)
    pairs = []
    for i, a in enumerate(srcs):
        for b in srcs[i + 1:]:
            sim = sum(x * y for x, y in zip(centroids[a], centroids[b]))
            if sim < SIMILARITY_THRESHOLD:
                continue
            if _already_linked(a, b, links):
                continue
            pairs.append({
                "a": a,
                "b": b,
                "similarity": round(sim, 4),
                "a_category": meta_by_src.get(a, {}).get("category"),
                "b_category": meta_by_src.get(b, {}).get("category"),
            })

    pairs.sort(key=lambda p: -p["similarity"])
    pairs = pairs[:MAX_PAIRS]
    _log("연결 안 된 고유사도 쌍 %d건 (임계값 %.2f)." % (len(pairs), SIMILARITY_THRESHOLD))

    # 각 쌍에 리랭커를 거친 근거 발췌를 붙인다 — LLM 판정의 입력이 된다.
    for idx, p in enumerate(pairs, 1):
        _log("근거 검색 %d/%d (리랭커 켜짐)" % (idx, len(pairs)))
        query = p["a"] + " 와 " + p["b"] + " 의 공통 주제"
        p["evidence"] = search_wiki(collection, query, n_results=3, use_rerank=True)
    return pairs


def _ask_nightly(prompt):
    """야간 모델에 직접 묻는다(Bifrost 미경유 — 모듈 docstring 참조)."""
    payload = {
        "model": NIGHTLY_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    r = requests.post(_ollama("/api/chat"), json=payload, timeout=1800)
    r.raise_for_status()
    return (r.json().get("message") or {}).get("content", "")


def llm_stage(pairs):
    """후보 쌍을 판정해 제안문을 만든다."""
    results = []
    for i, p in enumerate(pairs, 1):
        _log("판정 %d/%d: %s <-> %s" % (i, len(pairs), p["a"][:28], p["b"][:28]))
        prompt = (
            "다음은 개인 위키의 두 문서다. 임베딩 유사도상 관련이 있어 보이는데 서로 링크가 없다.\n\n"
            "문서 A: " + p["a"] + "\n"
            "문서 B: " + p["b"] + "\n"
            "유사도: " + str(p["similarity"]) + "\n\n"
            "검색으로 찾은 공통 주제 근거:\n" + str(p.get("evidence", "")) + "\n\n"
            "너의 기본 입장은 '없다' 다. 유사도가 높은 것은 같은 분야의 단어가\n"
            "겹쳐서일 뿐인 경우가 대부분이다. 아래를 모두 만족할 때만 '있다' 로 답해라:\n"
            "  - 한 문서를 읽는 사람이 다른 문서를 실제로 찾아가야 할 구체적 이유가 있다\n"
            "  - 그 이유를 위 근거에서 인용할 수 있다 (추론으로 메우면 안 된다)\n"
            "'같은 분야다', '함께 알면 도움이 된다', 'A 를 알면 B 에 유용하다' 류는\n"
            "연결 이유가 아니다 — 그런 경우는 '없다' 다.\n\n"
            "형식:\n"
            "1) 있다 / 없다  (이 두 단어 중 하나로만 시작할 것)\n"
            "2) '있다' 면: 어떤 관계인지 한 문장 + 근거에서 인용한 문구\n"
            "3) '없다' 면: 유사도만 높았던 이유 한 문장"
        )
        try:
            verdict = _ask_nightly(prompt)
        except Exception as exc:
            verdict = "(판정 실패: " + type(exc).__name__ + ")"
        results.append(dict(p, verdict=verdict))
    return results


def write_suggestions(results):
    os.makedirs(SUGGEST_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SUGGEST_DIR, "suggestions_" + stamp + ".md")
    lines = [
        "# 야간 배치 제안 — " + stamp,
        "",
        "모델: `" + NIGHTLY_MODEL + "` · 유사도 임계값 "
        + str(SIMILARITY_THRESHOLD) + " · 리랭커 켜짐",
        "",
        "> 이 파일은 제안이다. 문서를 직접 고치지 않았다 — 채택은 사람이 한다.",
        "",
    ]
    if not results:
        lines.append("제안할 항목이 없다(연결 안 된 고유사도 쌍을 찾지 못했다).")
    for r in results:
        lines.extend([
            "## " + r["a"] + "  ↔  " + r["b"],
            "",
            "* 유사도: **" + str(r["similarity"]) + "**",
            "* 분류: " + str(r["a_category"]) + " / " + str(r["b_category"]),
            "",
            "### 판정",
            "",
            (r.get("verdict") or "").strip() or "(비어 있음)",
            "",
            "---",
            "",
        ])
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def restore_embedding():
    """임베딩을 되돌린다. **재적재 확인까지가 복구다** — 3회 재시도."""
    for attempt in range(1, 4):
        try:
            payload = {"model": EMBEDDING_MODEL, "input": "복구 확인"}
            requests.post(_ollama("/api/embed"), json=payload, timeout=300).raise_for_status()
        except Exception as exc:
            _log("임베딩 복구 시도 %d/3 실패: %s" % (attempt, exc))
        if is_resident(EMBEDDING_MODEL):
            _log("임베딩 복구 확인 (시도 %d/3)." % attempt)
            return True
        time.sleep(5)
    return False


def main():
    ap = argparse.ArgumentParser(description="야간 배치 — vault 교차 점검")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="모델 전환 없이 벡터 단계까지만 돌린다(임베딩을 내리지 않는다).",
    )
    ap.add_argument(
        "--now",
        action="store_true",
        help="허용 시각 구간(%d~%d시)을 무시하고 지금 실행한다. 수동 실행용."
        % ALLOWED_HOUR_RANGE,
    )
    args = ap.parse_args()

    if not gate(ignore_hours=args.now):
        return 1

    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started": int(time.time())}, f)
    _log("배치 모드 진입(락 생성).")

    switched = False
    try:
        collection = get_chroma_client().get_or_create_collection(
            name="my_wiki_db", embedding_function=get_embedding_function()
        )
        pairs = vector_stage(collection)

        if args.dry_run:
            _log("--dry-run: 모델 전환 없이 종료. 후보 %d건." % len(pairs))
            dry = [dict(p, verdict="(dry-run — 판정 생략)") for p in pairs]
            print(write_suggestions(dry))
            return 0

        if not pairs:
            _log("후보가 없어 모델을 전환하지 않는다.")
            print(write_suggestions([]))
            return 0

        _log("임베딩 언로드.")
        unload(EMBEDDING_MODEL)
        switched = True

        _log(NIGHTLY_MODEL + " 적재.")
        ratio = load_and_check_gpu(NIGHTLY_MODEL)
        if ratio is None:
            _log("적재 실패 — 작업하지 않고 복구로 간다.")
            return 1
        if ratio < GPU_RATIO_MIN:
            # CPU 분할 상태로 밤새 도는 것이 가장 나쁜 조합이다.
            _log("GPU 비율 %.1f%% — 100%% 가 아니라 작업하지 않고 복구로 간다." % (ratio * 100))
            return 1
        _log("적재 확인: GPU %.1f%%" % (ratio * 100))

        results = llm_stage(pairs)
        path = write_suggestions(results)
        _log("제안 파일 기록: " + path)
        print(path)
        return 0
    finally:
        # 예외·조기 return 어느 경로로 왔든 반드시 실행된다.
        if switched:
            _log("야간 모델 언로드.")
            unload(NIGHTLY_MODEL)
            if not restore_embedding():
                msg = (
                    "🔴 야간 배치: 임베딩(bge-m3) 복구 실패. "
                    "RAG 검색이 깨진 상태일 수 있다 — 수동 확인이 필요하다."
                )
                _log(msg)
                notify_discord(msg)
        try:
            os.unlink(LOCK_PATH)
            _log("락 해제.")
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
