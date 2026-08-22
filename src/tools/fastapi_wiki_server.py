import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [근본 해결] 인코딩 크래시를 방지하기 위해 프로그램 최상단에서 로거를 먼저 세팅
import logger_setup

logger_setup.setup_logger('fastapi_wiki_server.log')

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from chroma_client import get_chroma_client
from embedding_function import get_embedding_function
from config import settings

# 1. FastAPI 애플리케이션 초기화
app = FastAPI(
    title="Personal Wiki Tool Server",
    description="Open WebUI에서 로컬 위키를 검색하기 위한 OpenAPI 호환 도구 서버",
    version="1.0.0"
)

# 2. ChromaDB 및 임베딩 초기화 (임베딩은 Bifrost 경유)
print("⏳ 임베딩(bge-m3) 연결 중 — Bifrost 경유...")
ollama_ef = get_embedding_function()

try:
    chroma_client = get_chroma_client()
    collection = chroma_client.get_or_create_collection(name="my_wiki_db", embedding_function=ollama_ef)
    print("✅ ChromaDB 위키 지식베이스 연결 성공")
except Exception as e:
    print(f"❌ ChromaDB 연결 실패: {e}")
    collection = None

# 3. 요청 모델 정의 (Pydantic)
class SearchRequest(BaseModel):
    query: str = Field(..., description="위키에서 검색할 키워드나 문장입니다.")
    n_results: int = Field(3, description="가져올 검색 결과의 개수입니다.")

class RecentTitlesRequest(BaseModel):
    limit: int = Field(..., description="가져올 최근 문서 제목의 최대 개수입니다. 기본적으로 10을 입력하세요.")

# 4. API Key 검증 로직
security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != settings.TOOL_SERVER_API_KEY:
        raise HTTPException(status_code=401, detail="유효하지 않은 API Key입니다.")
    return credentials.credentials

# 5. 엔드포인트 정의 (Open WebUI가 이 정보를 바탕으로 툴을 등록합니다)
@app.post("/search_wiki_knowledge", summary="로컬 위키 검색", description="사용자가 '로컬 AI', '위키', '시스템 환경설정', '에러' 등에 대해 구체적으로 질문할 때만 사용하세요. 일반적인 인사나 무관한 질문에는 절대 이 툴을 호출하지 마세요.", operation_id="search_wiki_knowledge")
def search_wiki_knowledge(request: SearchRequest, api_key: str = Depends(verify_api_key)):
    if not collection:
        return {"result": "오류: 위키 데이터베이스(ChromaDB)에 연결되어 있지 않습니다."}

    try:
        results = collection.query(
            query_texts=[request.query],
            n_results=request.n_results
        )

        if not results['documents'] or not results['documents'][0]:
            return {"result": f"'{request.query}'에 대한 위키 지식을 찾을 수 없습니다."}

        formatted_results = []
        for metadata, doc in zip(results['metadatas'][0], results['documents'][0]):
            source = metadata.get('source', 'Unknown')
            category = metadata.get('category', 'Unknown')
            formatted_results.append(f"▶ 출처: {source} (카테고리: {category})\n내용: {doc}")

        return {"result": "\n\n---\n\n".join(formatted_results)}
    except Exception as e:
        return {"result": f"위키 검색 중 오류가 발생했습니다: {str(e)}"}

@app.post("/get_recent_wiki_titles", summary="최근 위키 문서 제목 조회", description="가장 최근에 저장된 위키 문서들의 제목을 가져옵니다.", operation_id="get_recent_wiki_titles")
def get_recent_wiki_titles(request: RecentTitlesRequest, api_key: str = Depends(verify_api_key)):
    if not collection:
        return {"result": "오류: 위키 데이터베이스에 연결되어 있지 않습니다."}

    try:
        results = collection.get(limit=request.limit)
        if not results['metadatas']:
            return {"result": "저장된 문서가 없습니다."}

        titles = set()
        for meta in results['metadatas']:
            if 'source' in meta:
                titles.add(meta['source'])

        return {"result": "최근 위키 문서 목록:\n- " + "\n- ".join(list(titles)[:request.limit])}
    except Exception as e:
        return {"result": f"문서 목록 조회 중 오류가 발생했습니다: {str(e)}"}

if __name__ == "__main__":
    print("\n🚀 FastAPI 기반 OpenAPI 툴 서버를 시작합니다. (Port: 9000)")
    print("Open WebUI의 [관리자 패널] > [설정] > [통합] > [도구 서버 관리] (또는 OpenAPI 서버) 에 다음 주소를 추가하세요:")
    print("👉 http://host.docker.internal:9000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=9000)
