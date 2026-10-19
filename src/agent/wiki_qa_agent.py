"""로컬 모델이 스스로 위키를 검색하는 ReAct 에이전트.

Docs/local_model_feature_proposals.md ① 의 구현이다.

왜 필요했는가: `fastapi_wiki_server.py` 는 Open WebUI 의 OpenAPI 툴로만 연결돼 있어,
사람이 Open WebUI 에서 모델을 고르고 질문해야 위키 검색이 돌았다. 로컬 모델이 스스로
위키를 찾는 경로가 없었다. 그래서 implementation_plan.md 4-2 가 `#personal`·이력서·회고를
"로컬 전용"으로 못박았는데도 **정작 그 데이터를 질의할 로컬 기능이 없었다** — 프라이버시
경계가 설계상으로만 존재하는 상태였다. 이 모듈이 그것을 메운다.

지금 가능해진 이유: 이전 라인업(`exaone3.5`·`phi4`)은 capabilities 가 completion 뿐이라
tool calling 이 원천적으로 불가능했다. 현재 보유 생성 모델은 전부 `tools` 를 지원한다.

실행:
    python src/agent/wiki_qa_agent.py "내 위키에서 Ollama 설정 관련 내용 찾아서 요약해줘"
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logger_setup

logger_setup.setup_logger("wiki_qa_agent.log")

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langgraph.prebuilt import create_react_agent

from chroma_client import get_chroma_client
from config import settings
from embedding_function import get_embedding_function
from tools.wiki_tools import list_wiki_documents, read_wiki_document, search_wiki

# 루프 상한. 로컬 모델의 tool calling 은 클라우드 모델보다 인자 스키마를 틀리는
# 빈도가 높아 같은 도구를 반복 호출하며 맴돌 수 있다. 무한 루프를 막는다.
# LangGraph 는 노드 단위로 세므로 (모델 1 + 도구 1) 왕복이 2 씩 먹는다.
RECURSION_LIMIT = 14

SYSTEM_PROMPT = """당신은 사용자의 개인 위키를 검색해 답하는 조수입니다.

규칙:
- 답은 반드시 위키에서 찾은 내용에 근거해야 합니다. 찾지 못했으면 "위키에 없습니다"라고 말하세요.
- 추측으로 메우지 마세요. 위키에 없는 내용을 일반 지식으로 채우지 마세요.
- 검색 결과가 청크 조각이라 맥락이 부족하면 read_wiki_document 로 문서 전문을 읽으세요.
- 문서 제목이 확실하지 않으면 list_wiki_documents 로 먼저 목록을 확인하세요.
- 답변에는 근거가 된 문서의 출처(source)를 함께 적으세요.
- 문서 목록의 순서를 "최신순"으로 단정하지 마세요. 도구가 날짜 근거가 없다고 알리면 그대로 전하세요.
"""

_collection = None


def _get_collection():
    """ChromaDB 컬렉션을 지연 초기화한다 — 임포트만으로 네트워크를 쓰지 않게 한다."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="my_wiki_db", embedding_function=get_embedding_function()
        )
    return _collection


@tool
def wiki_search(query: str, n_results: int = 3) -> str:
    """위키를 의미 기반으로 검색한다. 키워드나 질문 문장을 그대로 넣어라.

    Args:
        query: 찾을 내용. 키워드보다 문장이 더 잘 맞는다.
        n_results: 가져올 청크 수. 기본 3.
    """
    return search_wiki(_get_collection(), query, n_results)


@tool
def wiki_list(limit: int = 10) -> str:
    """색인된 위키 문서 목록을 본다. 제목과 분류, 마지막 수정 시각을 돌려준다.

    어떤 문서가 있는지 모를 때, 또는 read_wiki_document 에 넣을 정확한 제목이
    필요할 때 쓴다.

    Args:
        limit: 가져올 문서 수(청크가 아니라 문서 단위). 기본 10.
    """
    return list_wiki_documents(_get_collection(), limit)


@tool
def wiki_read(source: str) -> str:
    """문서 하나의 전문을 읽는다. 검색 결과가 조각나서 맥락이 부족할 때 쓴다.

    Args:
        source: 문서의 정확한 제목. wiki_search 결과의 "출처" 또는 wiki_list 에서 얻는다.
    """
    return read_wiki_document(_get_collection(), source)


def build_agent():
    """ReAct 에이전트를 만든다. 모델 호출은 Bifrost 를 경유한다.

    게이트웨이를 거치므로 Langfuse 트레이싱이 멀티스텝 루프까지 자동으로 포착한다 —
    도구 호출 스팬이 중첩 구조로 남는다.
    """
    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        base_url=settings.BIFROST_BASE_URL,
        api_key=settings.BIFROST_API_KEY,
        temperature=0.1,
    )
    return create_react_agent(
        llm,
        tools=[wiki_search, wiki_list, wiki_read],
        prompt=SYSTEM_PROMPT,
        name="wiki_qa_agent",
    )


def ask(question: str) -> str:
    """질문 하나를 처리해 최종 답변 문자열을 돌려준다."""
    agent = build_agent()
    config = {
        "recursion_limit": RECURSION_LIMIT,
        "callbacks": [CallbackHandler()],
        "run_name": "wiki_qa",
    }
    result = agent.invoke({"messages": [("user", question)]}, config=config)
    messages = result.get("messages") or []
    if not messages:
        return "(응답이 비었습니다)"
    return getattr(messages[-1], "content", str(messages[-1]))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print('사용법: python src/agent/wiki_qa_agent.py "질문"')
        return 2
    question = " ".join(sys.argv[1:])
    print(f"질문: {question}")
    print("-" * 60)
    try:
        print(ask(question))
    except Exception as exc:
        # recursion_limit 초과도 여기로 떨어진다 — 맴돌다 멈춘 것인지 구분되게 적는다.
        print(f"실패: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
