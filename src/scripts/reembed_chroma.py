import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter
import datetime

# 1. 시놀로지 NAS ChromaDB 연결
try:
    chroma_client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    print(f"✅ ChromaDB 연결 성공: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
except Exception as e:
    print(f"❌ ChromaDB 연결 실패: {e}")
    exit(1)

# 2. Ollama 기반 임베딩 (GPU VRAM 사용)
print("⏳ Ollama (bge-m3) 임베딩 모델 연결 중...")
ollama_ef = OllamaEmbeddingFunction(
    url=f"{settings.OLLAMA_BASE_URL}/api/embeddings",
    model_name="bge-m3:latest"
)

# 3. 빈 컬렉션 연결 (사전에 수동으로 빈 상태여야 함)
collection = chroma_client.get_or_create_collection(
    name="my_wiki_db",
    embedding_function=ollama_ef
)

# 4. 대상 폴더 목록
target_dirs = [
    ("tech", settings.TECH_DIR),
    ("career", settings.CAREER_DIR),
    ("personal", settings.PERSONAL_DIR)
]

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

total_files = 0
total_chunks = 0

for category, dir_path in target_dirs:
    if not os.path.exists(dir_path):
        continue
        
    md_files = [f for f in os.listdir(dir_path) if f.endswith('.md')]
    if not md_files:
        continue
        
    print(f"\n📂 [{category.upper()}] 폴더 처리 중... ({len(md_files)}개 파일)")
    
    for file_name in md_files:
        file_path = os.path.join(dir_path, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            chunks = text_splitter.split_text(content)
            base_name = file_name.replace(".md", "")
            
            docs = []
            ids = []
            metadatas = []
            
            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                ids.append(f"{base_name}_chunk_{i}")
                metadatas.append({"category": category, "source": base_name})
                
            if docs:
                collection.upsert(documents=docs, ids=ids, metadatas=metadatas)
                total_files += 1
                total_chunks += len(docs)
                print(f"   ✓ {file_name} -> {len(docs)}개 청크 임베딩 완료")
        except Exception as e:
            print(f"   ❌ [오류] {file_name} 처리 실패 (건너뜀): {e}")

print(f"\n🎉 전체 재임베딩 완료! (총 {total_files}개 파일, {total_chunks}개 벡터 조각)")
