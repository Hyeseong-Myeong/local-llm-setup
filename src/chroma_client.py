import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings


def get_chroma_client() -> "chromadb.ClientAPI":
    """ChromaDB HttpClient를 만든다. 접속 정보는 .env -> config.settings 에서 온다.

    CHROMA_TOKEN이 비어 있으면 무인증으로 접속하고, 값이 있으면 X-Chroma-Token
    헤더를 붙인다. Chroma 서버는 모르는 헤더를 무시하므로 앞단 프록시를 올리기
    전에 토큰을 먼저 넣어 두어도 동작이 달라지지 않는다 — 무중단 전환의 전제다.

    헤더 이름은 반드시 하이픈 표기(X-Chroma-Token)여야 한다. 언더스코어 표기는
    enum '이름'이라 설치된 chromadb 1.5.9에서 ValueError가 난다.
    """
    kwargs = {"host": settings.CHROMA_HOST, "port": settings.CHROMA_PORT}
    if settings.CHROMA_TOKEN:
        kwargs["settings"] = ChromaSettings(
            chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
            chroma_client_auth_credentials=settings.CHROMA_TOKEN,
            chroma_auth_token_transport_header="X-Chroma-Token",
        )
    return chromadb.HttpClient(**kwargs)
