"""ChromaDB 임베딩 함수를 한 곳에서 만든다.

Bifrost 게이트웨이를 경유한다. Ollama 를 직접 부르면 접점이 하나 더 늘고
관측·인증이 갈라지기 때문이다.

경로를 바꿔도 검색 결과는 같다 — 2026-08-22 실측으로 확인했다.
Bifrost 는 임베딩을 L2 정규화해서 돌려주지만(‖v‖=1.0, Ollama 직접은 약 26)
방향은 완전히 같고(코사인 유사도 1.0000000000), my_wiki_db 는 space=cosine 이라
크기에 무관하다. 실제 컬렉션 질의에서도 id 순서가 같고 거리 차는 4.7e-07 이었다.
근거: Docs/context_limit_experiment.md 12-2.
"""
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from config import settings

# 태그를 빼면(`bge-m3`) Bifrost 가 프로바이더를 해석하지 못해 400 을 낸다.
EMBEDDING_MODEL = "bge-m3:latest"


def get_embedding_function() -> OpenAIEmbeddingFunction:
    """Bifrost 의 OpenAI 호환 /v1/embeddings 를 쓰는 임베딩 함수를 만든다."""
    return OpenAIEmbeddingFunction(
        api_key=settings.BIFROST_API_KEY,
        # OpenAIEmbeddingFunction 은 api_base 뒤에 /embeddings 를 붙이므로
        # 여기서는 "/v1" 까지 포함된 형태가 필요하다. .env 값에 이미 있으면
        # 그대로 쓰고, 없으면 붙인다 (impact_analysis.py 와 같은 이유).
        api_base=settings.BIFROST_BASE_URL.rstrip("/").removesuffix("/v1") + "/v1",
        model_name=EMBEDDING_MODEL,
    )
