"""위키 조회 로직 — FastAPI 엔드포인트와 LangChain 도구가 함께 쓰는 순수 함수.

Docs/local_model_feature_proposals.md ① 1-1 의 확정 사양을 구현한다.

왜 여기로 뺐는가: 기존에는 로직이 `fastapi_wiki_server.py` 의 엔드포인트 함수 본문에
`Depends(verify_api_key)` 와 엉켜 있어 재사용이 불가능했다. ① 의 ReAct 에이전트가 같은
조회를 해야 하는데, 엔드포인트를 하나 더 만들면 로직이 두 벌이 된다.

이 모듈은 FastAPI·LangChain 에 의존하지 않는다 — ChromaDB 조회만 한다.
"""
import logging

# `from tools import reranker` 여야 한다 — 맨몸 `import reranker` 는 src/tools 가
# sys.path 에 있을 때만 동작해서, 이 모듈을 `tools.wiki_tools` 로 임포트하는
# 소비처(wiki_qa_agent · nightly_batch)에서 ModuleNotFoundError 가 난다.
# 소비처 3곳 모두 src/ 를 path 에 올리고 `from tools...` 로 부르므로 그쪽에 맞춘다.
from tools import reranker

logger = logging.getLogger(__name__)

# `category` 는 프라이버시 경계의 집행 수단이다(① 1-1 부수 발견).
# 외부로 나가는 경로(⑥ Jev 등)는 이 값으로 필터를 강제해야 한다.
PUBLIC_CATEGORY = "tech"


# 리랭킹 전 1단계에서 넉넉히 가져올 개수. 2단계(cross-encoder)가 이 중에서 고른다.
# 재현율 위주로 넓게 받아 정확도 위주로 좁히는 것이 2단계 검색의 요점이다.
RERANK_FETCH_K = 20


def search_wiki(
    collection,
    query: str,
    n_results: int = 3,
    category: str | None = None,
    use_rerank: bool | None = None,
) -> str:
    """위키를 검색해 사람이 읽는 문자열로 돌려준다.

    리랭커를 쓸 수 있으면 2단계로 돈다 —
      1단계: bge-m3 벡터 검색으로 top-RERANK_FETCH_K (빠르고 재현율 위주)
      2단계: cross-encoder 로 재채점해 top-n_results (정확도 위주)
    못 쓰면 1단계 결과를 그대로 쓴다. 리랭커 장애가 검색을 멈추지 않는다.

    use_rerank: None=환경변수 플래그를 따름(기본 꺼짐) / True=강제 켬(야간 배치) /
    False=강제 끔. 대화형 경로는 기본값(None)을 그대로 쓴다 — 실측 지연이 커서
    에이전트 루프에 넣을 수 없다(reranker.py 상단 주석 참조).

    category 를 주면 그 분류 안에서만 찾는다 — 외부 전송 경로에서 `#personal` 을
    배제하는 데 쓴다(주의에 맡기지 않고 쿼리로 강제).
    """
    if collection is None:
        return "오류: 위키 데이터베이스(ChromaDB)에 연결되어 있지 않습니다."

    # use_rerank 는 3상태다 —
    #   None  : 환경변수 플래그를 따른다(기본값은 꺼짐)
    #   True  : 플래그를 무시하고 켠다 — ④ 야간 배치가 쓰는 경로
    #   False : 끈다
    if use_rerank is False:
        rerank_on = False
    else:
        rerank_on = reranker.available(force=bool(use_rerank))
    fetch_n = max(n_results, RERANK_FETCH_K) if rerank_on else n_results

    kwargs = {"query_texts": [query], "n_results": fetch_n}
    if category:
        kwargs["where"] = {"category": category}

    try:
        results = collection.query(**kwargs)
    except Exception:
        # 예외 내용을 호출자에게 돌려주지 않는다 — CodeQL "Information exposure
        # through an exception". 전체 트레이스백은 logger.exception 이 서버 로그에
        # 남기므로 진단 정보를 잃지 않는다.
        logger.exception("위키 검색 실패: query=%r", query)
        return "위키 검색 중 오류가 발생했습니다."

    docs = (results.get("documents") or [[]])[0]
    if not docs:
        return f"'{query}'에 대한 위키 지식을 찾을 수 없습니다."

    metas = (results.get("metadatas") or [[]])[0]

    if rerank_on:
        order = reranker.rerank(query, list(docs), n_results, force=bool(use_rerank))
        if order is not None:
            docs = [docs[i] for i in order]
            metas = [metas[i] if i < len(metas) else None for i in order]
        else:
            # 리랭커가 실패했다 — 벡터 검색 순서를 그대로 쓴다(검색을 멈추지 않는다).
            docs, metas = docs[:n_results], metas[:n_results]
    else:
        docs, metas = docs[:n_results], metas[:n_results]
    parts = []
    for meta, doc in zip(metas, docs):
        meta = meta or {}
        parts.append(
            f"▶ 출처: {meta.get('source', 'Unknown')} "
            f"(카테고리: {meta.get('category', 'Unknown')})\n내용: {doc}"
        )
    return "\n\n---\n\n".join(parts)


def list_wiki_documents(collection, limit: int = 10, category: str | None = None) -> str:
    """색인된 문서를 **문서 단위**로 나열한다. `modified_at` 이 있으면 최신순.

    구 `get_recent_wiki_titles` 의 결함 두 개를 고친 것이다(① 1-1):
      1. limit 이 청크 단위라 문서 N개를 보장하지 못했다 → 문서 단위로 집계 후 자른다.
      2. "최근"이라 이름 붙였으나 정렬 근거가 없었다 → `modified_at` 으로 정렬한다.

    `modified_at`(문서 파일의 mtime)은 재색인 이후에만 존재한다. 없는 문서는 뒤로 보내고,
    **반환 문자열에 정렬 근거가 없다는 사실을 명시한다** — 에이전트가 순서를
    사실로 오해하지 않게 하는 것이 이 함수의 핵심 책임이다.
    """
    if collection is None:
        return "오류: 위키 데이터베이스에 연결되어 있지 않습니다."

    try:
        got = collection.get(where={"category": category} if category else None)
    except Exception:
        logger.exception("문서 목록 조회 실패")
        return "문서 목록 조회 중 오류가 발생했습니다."

    metas = got.get("metadatas") or []
    if not metas:
        return "저장된 문서가 없습니다."

    # source 단위로 접는다 — 청크가 아니라 문서를 센다.
    docs = {}
    for meta in metas:
        meta = meta or {}
        src = meta.get("source")
        if not src:
            continue
        cur = docs.setdefault(
            src, {"chunks": 0, "category": meta.get("category", "Unknown"), "modified_at": None}
        )
        cur["chunks"] += 1
        at = meta.get("modified_at")
        if at and (cur["modified_at"] is None or at > cur["modified_at"]):
            cur["modified_at"] = at

    if not docs:
        return "저장된 문서가 없습니다."

    # modified_at 있는 것을 최신순으로 먼저, 날짜 없는 것은 뒤로 몬다.
    dated = [kv for kv in docs.items() if kv[1]["modified_at"]]
    undated = [kv for kv in docs.items() if not kv[1]["modified_at"]]
    dated.sort(key=lambda kv: kv[1]["modified_at"], reverse=True)
    ordered = dated + undated

    total = len(ordered)
    shown = ordered[:limit]

    lines = [f"색인된 위키 문서 {total}개 중 {len(shown)}개:"]
    for src, info in shown:
        at = info["modified_at"] or "날짜 미상"
        lines.append(f"- {src} (카테고리: {info['category']}, 청크 {info['chunks']}개, 색인: {at})")

    if undated:
        lines.append("")
        lines.append(
            f"※ 주의: {len(undated)}개 문서에 색인 날짜가 없어 최신순 정렬에서 제외됐습니다 "
            "— 이 목록의 순서를 최신순으로 신뢰하지 마십시오."
        )
    return "\n".join(lines)


def read_wiki_document(collection, source: str) -> str:
    """한 문서의 전체 청크를 순서대로 이어 돌려준다.

    검색은 청크 조각만 주므로 에이전트가 원문 전체를 볼 수 없다 — 그 구멍을 메운다.
    `chunk_index` 가 있으면 그것으로, 없으면 id 의 `_chunk_N` 접미사로 정렬한다
    (현재 id 형태: `{source}_chunk_{N}`).
    """
    if collection is None:
        return "오류: 위키 데이터베이스에 연결되어 있지 않습니다."

    try:
        got = collection.get(where={"source": source})
    except Exception:
        logger.exception("문서 읽기 실패: source=%r", source)
        return "문서를 읽는 중 오류가 발생했습니다."

    docs = got.get("documents") or []
    if not docs:
        return f"'{source}' 문서를 찾을 수 없습니다. list_wiki_documents 로 정확한 제목을 확인하십시오."

    ids = got.get("ids") or []
    metas = got.get("metadatas") or []

    def order_key(i):
        meta = (metas[i] if i < len(metas) else None) or {}
        idx = meta.get("chunk_index")
        if isinstance(idx, int):
            return idx
        raw = ids[i] if i < len(ids) else ""
        tail = raw.rsplit("_chunk_", 1)
        if len(tail) == 2 and tail[1].isdigit():
            return int(tail[1])
        return 10**6  # 판정 불가는 뒤로

    order = sorted(range(len(docs)), key=order_key)
    body = "\n\n".join(docs[i] for i in order)
    category = ((metas[0] if metas else None) or {}).get("category", "Unknown")
    return f"▶ 문서: {source} (카테고리: {category}, 청크 {len(docs)}개)\n\n{body}"
