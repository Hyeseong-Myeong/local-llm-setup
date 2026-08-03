from config import settings
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
import uvicorn
from contextlib import asynccontextmanager

# 1. ChromaDB 및 Ollama 임베딩 초기화
print("⏳ Ollama (bge-m3) 임베딩 모델 연결 중...")

ollama_ef = OllamaEmbeddingFunction(
    url=f"{settings.OLLAMA_BASE_URL}/api/embeddings",
    model_name="bge-m3:latest"
)

try:
    chroma_client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    collection = chroma_client.get_or_create_collection(name="my_wiki_db", embedding_function=ollama_ef)
    print("✅ ChromaDB 위키 지식베이스 연결 성공")
except Exception as e:
    print(f"❌ ChromaDB 연결 실패: {e}")
    collection = None

# 2. FastMCP 서버 객체 생성
# dependencies=["fastembed", "chromadb"]
# 외부(Docker)에서 접근할 수 있도록 기본 host를 0.0.0.0으로 명시합니다. (보안상 공유기 내부망에서만 접근되도록 윈도우 방화벽 확인 필요)
mcp = FastMCP("Local_Wiki_Server", host="0.0.0.0", port=9000)

@mcp.tool()
def search_wiki_knowledge(query: str, n_results: int = 3) -> str:
    """
    사용자의 질문(query)을 기반으로 시놀로지 NAS의 로컬 위키(ChromaDB)에서 
    가장 관련성 높은 지식을 검색하여 반환합니다.
    
    Args:
        query: 검색할 질문이나 키워드
        n_results: 반환할 검색 결과의 수 (기본값: 3)
    """
    if not collection:
        return "오류: 위키 데이터베이스(ChromaDB)에 연결되어 있지 않습니다."
        
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        if not results['documents'] or not results['documents'][0]:
            return f"'{query}'에 대한 위키 지식을 찾을 수 없습니다."
            
        formatted_results = []
        for metadata, doc in zip(results['metadatas'][0], results['documents'][0]):
            source = metadata.get('source', 'Unknown')
            category = metadata.get('category', 'Unknown')
            formatted_results.append(f"▶ 출처: {source} (카테고리: {category})\n내용: {doc}")
            
        return "\n\n---\n\n".join(formatted_results)
    except Exception as e:
        return f"위키 검색 중 오류가 발생했습니다: {str(e)}"

@mcp.tool()
def get_recent_wiki_titles(limit: int = 10) -> str:
    """
    위키에 저장된 최근 문서들의 제목(출처) 목록을 가져옵니다.
    """
    if not collection:
        return "오류: 위키 데이터베이스에 연결되어 있지 않습니다."
        
    try:
        results = collection.get(limit=limit)
        if not results['metadatas']:
            return "저장된 문서가 없습니다."
            
        titles = set()
        for meta in results['metadatas']:
            if 'source' in meta:
                titles.add(meta['source'])
                
        return "최근 위키 문서 목록:\n- " + "\n- ".join(list(titles)[:limit])
    except Exception as e:
        return f"문서 목록 조회 중 오류가 발생했습니다: {str(e)}"

if __name__ == "__main__":
    print("\n🚀 FastMCP 위키 서버를 시작합니다. (Transport: SSE, Port: 9000)")
    print("Open WebUI의 Connections > MCP 섹션에서 다음 주소를 추가하세요:")
    print("👉 http://host.docker.internal:9000/sse")
    print("=" * 60)
    
    # FastMCP의 기본 run 메서드 사용 (SSE 프로토콜 지원)
    # 인자로 transport 등을 직접 넣기보다 mcp.run()이 스스로 서버를 띄우도록 합니다.
    # 만약 직접 포트를 제어해야 한다면 FastAPI/Uvicorn 코드를 별도로 사용해야 할 수 있습니다.
    try:
        # FastMCP 버전에 따라 host, port 인자가 mcp.run()에 들어갈 수도 있고 클래스 초기화에 들어갈 수도 있습니다.
        mcp.run(transport="sse")
    except TypeError:
        # 혹시 mcp 버전에 따라 run 인자가 다를 경우를 위한 폴백
        print("\n[⚠️ 경고] mcp.run(transport='sse')가 지원되지 않습니다.")
        print("터미널에서 직접 `mcp dev mcp_wiki_server.py` 명령어로 실행해 보세요.")
