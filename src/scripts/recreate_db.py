import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromadb.utils import embedding_functions

from chroma_client import get_chroma_client
from config import settings

# 1. 시놀로지 NAS ChromaDB 연결 (접속 정보는 .env -> config.settings 에서 온다)
chroma_client = get_chroma_client()

print(f"✅ ChromaDB 연결 완료: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")

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

ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url="http://127.0.0.1:11434/api/embeddings",
    model_name="bge-m3:latest"
)

print("✨ 새로운 컬렉션을 생성합니다...")
collection = chroma_client.get_or_create_collection(
    name="my_wiki_db",
    embedding_function=ollama_ef
)

print("🎉 'my_wiki_db' 컬렉션(bge-m3 임베딩 장착) 준비 완료!")
