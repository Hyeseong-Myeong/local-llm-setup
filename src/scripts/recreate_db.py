import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from chromadb.utils import embedding_functions

# 1. 시놀로지 NAS ChromaDB 연결
CHROMA_HOST = "192.168.x.x"  # TODO: 실제 NAS IP로 변경하세요 (또는 config.py의 settings.CHROMA_HOST 사용)
CHROMA_PORT = 8000
chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

print(f"✅ ChromaDB 연결 완료: {CHROMA_HOST}:{CHROMA_PORT}")

# ==========================================
# [수동 삭제 영역]
# 사용자님께서 직접 삭제를 원하실 때 아래 주석을 풀고 실행하세요.
# ==========================================
# try:
#     chroma_client.delete_collection(name="my_wiki_db")
#     print("🗑️ 기존 'my_wiki_db' 컬렉션 삭제 완료")
# except Exception as e:
#     print(f"⚠️ 컬렉션 삭제 실패 (이미 없거나 에러): {e}")

# ==========================================
# [새 컬렉션 생성 및 bge-m3 임베딩 설정]
# ==========================================

# 대안 1. Ollama 기반 임베딩 (GPU VRAM 사용)
ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url="http://127.0.0.1:11434/api/embeddings",
    model_name="bge-m3:latest"
)

# 대안 2. FastEmbed 기반 임베딩 (CPU RAM만 사용 - 모델 스위칭 방지용)
# 사용하시려면 터미널에서: pip install fastembed
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from fastembed import TextEmbedding


class CustomFastEmbed(EmbeddingFunction):
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model = TextEmbedding(model_name=model_name)
    def __call__(self, input: Documents) -> Embeddings:
        return [e.tolist() for e in self._model.embed(input)]

# fast_ef = CustomFastEmbed(model_name="BAAI/bge-m3")

print("✨ 새로운 컬렉션을 생성합니다...")
collection = chroma_client.get_or_create_collection(
    name="my_wiki_db",
    embedding_function=ollama_ef  # VRAM 스위칭이 우려된다면 이 부분을 fast_ef로 변경하세요.
)

print("🎉 'my_wiki_db' 컬렉션(bge-m3 임베딩 장착) 준비 완료!")
