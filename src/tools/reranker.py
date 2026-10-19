"""위키 검색 결과를 재정렬하는 cross-encoder 리랭커.

Docs/local_model_feature_proposals.md ③ 의 구현이다(선택지 A 확정).

왜 인프로세스인가 — 선택이 아니라 제약이다:
  Ollama 에 rerank 엔드포인트가 없고(이슈 #3368, 2026-10 현재 미해결), rerank 는
  OpenAI 표준 스펙이 아니라 Bifrost 가 프록시할 라우트 자체가 존재하지 않는다.
  즉 "모든 호출은 Bifrost 경유" 원칙을 지킬 방법이 없다.

관측 보상:
  이 호출은 Bifrost 를 지나지 않아 Langfuse 트레이스에 안 잡힌다. 그래서 호출수와
  지연을 STATS_PATH 에 적고 local_exporter 가 읽어 PLG 로 보낸다 — 관측이 사라지는
  게 아니라 Langfuse 에서 PLG 로 옮겨간다.

CPU 로 돈다(torch 2.14.1+cpu, CUDA 없음). 이 기기의 VRAM 실효 예산이 약 6.7GB 로
이미 빡빡하므로 **GPU 경합이 0 인 것이 단점이 아니라 장점이다.**

왜 bge-reranker-v2-m3 인가: 품질 서열이 아니라 일관성이다 — 1단계 임베딩(bge-m3)과
같은 계열이라 한국어 토큰화 거동이 어긋나지 않는다.
"""
import json
import logging
import os
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-reranker-v2-m3"

# 🔴 기본값은 꺼져 있다 — 2026-10-19 실측으로 대화형 경로에 쓸 수 없음이 확인됐다.
#
# 이 기기(Ryzen 5 5600X, CPU 전용)에서 568M cross-encoder 의 실측 지연:
#   max_length=512  top-5  4,550ms / top-20 18,932ms  (쌍당 947ms)
#   max_length=256  top-5  2,236ms / top-20  9,406ms  (쌍당 470ms)
#   max_length=128  top-5  1,222ms / top-20  4,917ms  (쌍당 246ms)
#
# 설계 당시 목표는 "질의당 300ms 이내"였는데 최선값도 4배 초과한다. 그리고
# max_length 를 줄이는 것은 해결책이 아니다 — 청크가 평균 845자(약 450토큰)라
# 128 로 자르면 청크의 70% 를 버려서, cross-encoder 가 보려던 신호 자체가 사라진다.
# 즉 지연을 줄이는 만큼 리랭킹의 존재 이유가 깎인다.
#
# 그래도 지우지 않는 이유: 품질 신호는 실재한다 — 질의 10건 중 5건에서 top-3 의
# 순서가 실제로 바뀌었다. 지연이 무관한 경로(야간 배치 ④, 오프라인 평가)에서는
# 그대로 쓸 값이 있다.
#
# 켜는 방법: WIKI_RERANK=1. 대화형 경로(HTTP 툴 서버·ReAct 에이전트)에는 켜지 말 것.
ENABLED = os.environ.get("WIKI_RERANK", "0") not in ("0", "false", "False")

# 입력 절단 길이. 품질을 지키려면 청크 전체가 들어가야 해서 넉넉히 둔다 —
# 줄이면 빨라지지만 위 주석의 이유로 리랭킹 품질을 직접 깎는다.
MAX_LENGTH = int(os.environ.get("WIKI_RERANK_MAX_LENGTH", "512"))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# local_exporter 가 읽는다. tmp/ 는 .gitignore 대상이다.
STATS_PATH = os.path.join(_REPO_ROOT, "tmp", "reranker_stats.json")

_model = None
_model_lock = threading.Lock()
_stats_lock = threading.Lock()


def _get_model():
    """모델을 지연 적재한다 — 임포트만으로 2GB 를 읽지 않게 한다.

    최초 호출 시 HuggingFace 캐시로 약 2.2GB 를 내려받는다(이후 재사용).
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import CrossEncoder

                logger.info("리랭커 적재 시작: %s", MODEL_NAME)
                _model = CrossEncoder(MODEL_NAME, device="cpu", max_length=MAX_LENGTH)
                logger.info("리랭커 적재 완료")
    return _model


def _record(latency_sec: float, n_docs: int, failed: bool = False) -> None:
    """누적 카운터를 파일에 적는다. local_exporter 가 이것을 읽어 메트릭으로 낸다.

    프로세스가 둘(툴 서버·에이전트)이라 동시 쓰기에 카운트가 한 건 유실될 수 있다 —
    추세 지표이므로 감수한다. 쓰기 자체는 os.replace 로 원자적으로 한다(깨진 JSON
    을 exporter 가 읽는 상황을 막는 것이 더 중요하다).
    """
    try:
        with _stats_lock:
            cur = {"calls_total": 0, "failures_total": 0, "docs_total": 0, "latency_sum": 0.0}
            try:
                with open(STATS_PATH, encoding="utf-8") as f:
                    cur.update(json.load(f))
            except (OSError, ValueError):
                pass

            cur["calls_total"] = int(cur.get("calls_total", 0)) + 1
            cur["docs_total"] = int(cur.get("docs_total", 0)) + n_docs
            cur["latency_sum"] = round(float(cur.get("latency_sum", 0.0)) + latency_sec, 4)
            if failed:
                cur["failures_total"] = int(cur.get("failures_total", 0)) + 1
            cur["last_latency_sec"] = round(latency_sec, 4)
            cur["last_updated"] = int(time.time())

            os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(STATS_PATH), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(cur, f)
                os.replace(tmp_path, STATS_PATH)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    except Exception:
        # 메트릭 기록 실패가 검색을 깨뜨리면 안 된다.
        logger.exception("리랭커 통계 기록 실패")


def available() -> bool:
    """리랭커를 쓸 수 있는지 — 플래그와 패키지 설치 여부만 본다(모델은 적재하지 않는다)."""
    if not ENABLED:
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def rerank(query: str, documents: list[str], top_k: int) -> list[int] | None:
    """(query, doc) 쌍을 cross-encoder 로 재채점해 상위 top_k 의 **원본 인덱스**를 돌려준다.

    인덱스를 돌려주는 이유: 호출부가 documents 와 metadatas 를 쌍으로 들고 있어
    문서만 재정렬하면 메타데이터와 어긋난다.

    쓸 수 없거나 실패하면 None 을 돌려준다 — 호출부가 벡터 검색 순서를 그대로
    쓰게 해서, 리랭커 장애가 검색 자체를 멈추지 않게 한다.
    """
    if not documents or not available():
        return None

    start = time.perf_counter()
    try:
        model = _get_model()
        scores = model.predict([(query, doc) for doc in documents])
    except Exception:
        logger.exception("리랭킹 실패 — 벡터 검색 순서로 되돌린다")
        _record(time.perf_counter() - start, len(documents), failed=True)
        return None

    _record(time.perf_counter() - start, len(documents))
    order = sorted(range(len(documents)), key=lambda i: float(scores[i]), reverse=True)
    return order[:top_k]
