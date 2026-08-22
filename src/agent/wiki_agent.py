import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import re
import subprocess
import time

import logger_setup

logger_setup.setup_logger('wiki_agent.log')
import datetime
import queue
import shutil
import threading
import traceback
from typing import TypedDict

import requests
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

# pyrefly: ignore [missing-import]
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, StateGraph
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import prompts  # 새로 생성한 프롬프트 파일을 가져옵니다.
from chroma_client import get_chroma_client
from config import settings
from embedding_function import get_embedding_function

load_dotenv()

# ==========================================
# 유틸: 디스코드 웹훅 알림 및 실시간 진행 상태 수정
# ==========================================
def send_discord_notification(message: str):
    webhook_url = settings.DISCORD_WEBHOOK_URL
    if not webhook_url or webhook_url == "여기에_웹훅_주소를_입력하세요":
        return
    try:
        requests.post(webhook_url, json={"content": message}, timeout=5)
    except Exception as e:
        print(f"디스코드 웹훅 전송 실패: {e}")

def send_discord_progress(message: str, message_id: str = None) -> str:
    webhook_url = settings.DISCORD_WEBHOOK_URL
    if not webhook_url or webhook_url == "여기에_웹훅_주소를_입력하세요":
        return None
    try:
        if message_id:
            patch_url = f"{webhook_url}/messages/{message_id}"
            requests.patch(patch_url, json={"content": message}, timeout=5)
            return message_id
        else:
            url = f"{webhook_url}?wait=true"
            resp = requests.post(url, json={"content": message}, timeout=5)
            if resp.status_code in [200, 201]:
                return resp.json().get('id')
    except Exception as e:
        print(f"디스코드 프로그레스 전송/수정 실패: {e}")
    return None

def kill_zombie_llama_servers():
    """좀비 llama-server 프로세스를 강제 사살하여 점거된 VRAM을 해방.
    taskkill 자체가 실패(예: 권한 거부)하면 ollama.exe를 통째로 재시작하는 폴백을 수행한다."""
    try:
        result = subprocess.run(
            ["taskkill", "/f", "/im", "llama-server.exe"],
            capture_output=True, text=True, timeout=10
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            print(f"   -> 🧟 좀비 llama-server 프로세스 사살 완료. ({output})")
            return
        if "찾을 수 없습니다" in output or "not found" in output.lower():
            print("   -> 좀비 llama-server 없음 (정상 상태).")
            return
        print(f"   -> ⚠️ 좀비 llama-server 강제 종료 실패 (returncode={result.returncode}): {output}")
    except Exception as e:
        print(f"   -> ⚠️ 좀비 사살 명령 자체가 실패: {e}")

    # [폴백] taskkill로 llama-server를 못 죽인 경우 (권한 거부 등), ollama.exe 자체를 재시작해 좀비를 정리
    print("   -> 🔁 [폴백] ollama.exe를 재시작하여 좀비 프로세스를 정리합니다...")
    try:
        subprocess.run(["taskkill", "/f", "/im", "ollama.exe"], capture_output=True, text=True, timeout=10)
        subprocess.run(["taskkill", "/f", "/im", "llama-server.exe"], capture_output=True, text=True, timeout=10)
        time.sleep(2)
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("   -> ✅ ollama.exe 재시작 완료.")
        send_discord_notification("🔧 **[자가 치유]** 좀비 llama-server를 강제 종료하지 못해 `ollama.exe`를 재시작했습니다.")
        time.sleep(3)
    except Exception as e:
        print(f"   -> ❌ ollama.exe 재시작 폴백도 실패: {e}")
        send_discord_notification(f"🚨 **[심각] Ollama 자동 복구 실패**\n좀비 프로세스를 자동으로 정리하지 못했습니다. 수동 확인이 필요합니다.\n에러: {e}")

def wait_for_vram_clear(max_wait: int = 10):
    """ollama ps API를 폴링하여 VRAM이 실제로 비워질 때까지 대기 (최대 max_wait초)"""
    for i in range(max_wait):
        try:
            resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/ps", timeout=3)
            if resp.status_code == 200:
                models = resp.json().get('models', [])
                if not models:
                    print(f"   -> VRAM 비움 확인 완료. ({i+1}초 소요)")
                    return True
        except Exception:
            pass
        time.sleep(1)
    print(f"   -> ⚠️ {max_wait}초 경과. VRAM이 완전히 비워지지 않았을 수 있음.")
    return False

def unload_ollama_model(model_name: str):
    """모델 퇴거 + 좀비 사냥 + VRAM 비움 확인까지 일관 수행"""
    print(f"🧹 [메모리 관리] VRAM 확보를 위해 '{model_name}' 강제 퇴거 시도 중...")
    try:
        url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {"model": model_name, "keep_alive": 0}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("   -> 퇴거 명령 전송 성공.")
        else:
            print(f"   -> 퇴거 명령 실패 (HTTP {resp.status_code}). 좀비 사냥으로 전환.")
            kill_zombie_llama_servers()
    except Exception as e:
        print(f"   -> 퇴거 요청 에러: {e}. 좀비 사냥으로 전환.")
        kill_zombie_llama_servers()

    # VRAM이 실제로 비워졌는지 확인 (GPU 드라이버 해제 지연 대응)
    wait_for_vram_clear()

# ==========================================
# 유틸: 파일 이동 시 충돌 방지 (archive/error 이동 공용)
# ==========================================
def safe_move(src: str, dst_dir: str, file_name: str):
    """파일 이동 시 대상 경로에 동일 파일이 있으면 타임스탬프 접미사를 부여하여 충돌 방지"""
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, file_name)
    if os.path.exists(dst):
        base, ext = os.path.splitext(file_name)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(dst_dir, f"{base}_{timestamp}{ext}")
    shutil.move(src, dst)

# ChromaDB 원격 연결 (실패 시 웹훅 알림 후 종료)
try:
    chroma_client = get_chroma_client()
    print("⏳ 임베딩(bge-m3) 연결 중 — Bifrost 경유...")

    embedding_fn = get_embedding_function()

    collection = chroma_client.get_or_create_collection(name="my_wiki_db", embedding_function=embedding_fn)
    print(f"✅ ChromaDB 연결 및 임베딩 설정 완료: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
except Exception as e:
    error_msg = f"❌ ChromaDB 연결 실패: {e}\nNAS 또는 ChromaDB 서버가 실행 중인지 확인하세요."
    print(error_msg)
    send_discord_notification(f"🚨 **Wiki Agent 시작 실패**\n- 원인: ChromaDB 연결 불가\n- 상세: {e}")
    raise SystemExit(1)

# 모델 초기화
llm = ChatOpenAI(model=settings.MODEL_NAME, base_url=settings.BIFROST_BASE_URL, api_key=settings.BIFROST_API_KEY, temperature=0.1)

class AgentState(TypedDict):
    file_name: str
    raw_content: str
    category: str
    context: str
    cleaned_content: str
    compiled_content: str
    discord_msg_id: str

# ==========================================
# 노드 1: 분류기 (Tech vs Personal) + 짧은 문서는 정제까지 통합
# ==========================================
def _normalize_category(raw: str) -> str:
    """분류 결과를 tech/career/personal 중 하나로 정규화. 셋 다 아니면 안전 기본값(tech)."""
    value = raw.strip().lower()
    if "personal" in value:
        return "personal"
    if "career" in value:
        return "career"
    return "tech"

def _parse_classify_and_clean(raw_response: str) -> tuple:
    """'CATEGORY: tech\\n---\\n(본문)' 형식을 파싱. 형식이 어긋나면 전체를 본문으로,
    카테고리는 안전 기본값(tech)으로 취급한다."""
    match = re.match(r'^\s*CATEGORY:\s*(\w+)\s*\n-{3,}\s*\n(.*)$', raw_response, re.DOTALL | re.IGNORECASE)
    if match:
        category = _normalize_category(match.group(1))
        cleaned = match.group(2).strip()
        return category, cleaned
    return "tech", raw_response.strip()

def classify_document(state: AgentState) -> AgentState:
    print(f"\n🔍 [1/4] '{state['file_name']}' 카테고리 분석 중...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1. 대기열 진입 및 파일 읽기\n⏳ 2. 카테고리 분석 중...", state['discord_msg_id'])

    raw_text = state['raw_content']

    if len(raw_text) <= settings.SPLIT_THRESHOLD:
        # 짧은 문서는 어차피 clean_data도 원문 전체를 한 번에 읽으므로, 분류 미리보기(1000자)
        # 때문에 같은 원문을 LLM에게 두 번 읽히지 않도록 분류+정제를 한 호출로 통합한다.
        prompt = prompts.CLASSIFY_AND_CLEAN_PROMPT.format(text=raw_text)
        messages = [
            SystemMessage(content="You are a document classifier and data cleaner. Follow the exact output format: 'CATEGORY: <word>' then '---' then the cleaned markdown body."),
            HumanMessage(content=prompt)
        ]
        bound_llm = llm.bind(max_tokens=2500)
        response = bound_llm.invoke(messages)
        category, cleaned = _parse_classify_and_clean(response.content)
        state['category'] = category
        state['cleaned_content'] = cleaned  # clean_data가 이미 완료된 것으로 보고 재작업을 생략함
    else:
        # 긴 문서는 청크 단위로 정제되므로 분류를 위한 별도의 가벼운 미리보기 호출만 수행
        prompt = prompts.CLASSIFY_PROMPT.format(raw_content_preview=raw_text[:1000])
        messages = [
            SystemMessage(content="You are a document classifier. Output ONLY one word: tech, career, or personal."),
            HumanMessage(content=prompt)
        ]
        response = llm.invoke(messages)
        state['category'] = _normalize_category(response.content)

    return state
# ==========================================
#  노드 2: 과거 지식 검색 (RAG)
# ==========================================
def retrieve_memory(state: AgentState) -> AgentState:
    print("🧠 [2/4] NAS ChromaDB에서 연관 지식 검색 중...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1. 대기열 진입 및 파일 읽기\n✅ 2. 카테고리 분석 완료 (결과: `{state['category']}`)\n⏳ 3. 연관 지식 검색 중...", state['discord_msg_id'])
    results = collection.query(
        query_texts=[state['raw_content'][:500]],
        n_results=2,
        where={"category": state['category']}
    )

    if results['documents'] and results['documents'][0]:
        # 과거 문서의 실제 내용은 넘기지 않고 링크 후보(제목)만 전달한다.
        # 내용을 함께 주면 모델이 본문 주제를 과거 문서 내용으로 대체해버리는 문제가 있어,
        # 관련 있을 때만 옵시디언 [[링크]]로 연결하도록 강제하기 위함.
        link_names = []
        for metadata in results['metadatas'][0]:
            source = metadata.get('source', '')
            if source.endswith('.md'):
                # 구버전 호환: source가 'Discord_123.md' 였고, 실제 파일명은 'AI_Discord_123.md'
                link_name = f"AI_{source}"
            else:
                # 신버전: source가 '[키워드] 제목'
                link_name = source
            if link_name not in link_names:
                link_names.append(link_name)
        state['context'] = "\n".join(f"[[{name}]]" for name in link_names)
    else:
        state['context'] = "검색된 과거 지식 없음."

    # [NEW] 검색 끝났으므로 임베딩 모델 VRAM 강제 퇴거
    unload_ollama_model("bge-m3:latest")

    return state

# ==========================================
#  노드 2.5: 1차 정제 및 요약 (Hybrid)
# ==========================================
def clean_data(state: AgentState) -> AgentState:
    if state.get('cleaned_content'):
        # 짧은 문서는 classify_document 단계에서 분류와 함께 이미 정제까지 완료됨 (중복 LLM 호출 방지)
        print("🧹 [2.5/4] 원문 정제: 분류 단계에서 이미 완료됨 (중복 호출 생략)")
        return state

    print(f"🧹 [2.5/4] 원문 정제 및 압축 중 (길이: {len(state['raw_content'])}자)...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1. 대기열 진입 및 파일 읽기\n✅ 2. 카테고리 분석 완료 (결과: `{state['category']}`)\n✅ 3. 연관 지식 검색 완료\n⏳ 4. 원문 정제 및 요약 중 (길이: {len(state['raw_content'])}자)...", state['discord_msg_id'])

    raw_text = state['raw_content']

    # config의 SPLIT_THRESHOLD 이하면 단일 통과 압축 (코드 밀도 높은 문서나 추론형 모델 고려)
    if len(raw_text) <= settings.SPLIT_THRESHOLD:
        prompt_text = prompts.CLEAN_PROMPT.format(text=raw_text)
        messages = [
            SystemMessage(content="You are a data cleansing assistant. Output ONLY the cleansed markdown text. NO conversational filler."),
            HumanMessage(content=prompt_text)
        ]
        # OOM 방지를 위해 extra_body 제거, 추론형 모델 고려하여 max_tokens 상향
        bound_llm = llm.bind(max_tokens=2500)
        response = bound_llm.invoke(messages)
        state['cleaned_content'] = response.content
    else:
        # 긴 원문: 문단 단위 분할 후 병합 (Map-Reduce)
        print("   [!] 텍스트가 매우 깁니다. 메모리 안정성을 위해 세밀하게 분할합니다.")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1800,
            chunk_overlap=150,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_text(raw_text)

        cleaned_chunks = []
        bound_llm = llm.bind(max_tokens=1024)
        for i, chunk in enumerate(chunks):
            print(f"   -> 청크 [{i+1}/{len(chunks)}] 정제 중...")
            prompt_text = prompts.CLEAN_PROMPT.format(text=chunk)
            messages = [
                SystemMessage(content="You are a data cleansing assistant. Output ONLY the cleansed markdown text. NO conversational filler."),
                HumanMessage(content=prompt_text)
            ]
            response = bound_llm.invoke(messages)
            cleaned_chunks.append(response.content)

        state['cleaned_content'] = "\n\n".join(cleaned_chunks)

    return state

# ==========================================
#  노드 3: 위키 컴파일 (순차 생성 아키텍처)
# ==========================================
_LC_ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant"}

def _call_ollama_native(messages: list, part_name: str, max_tokens: int, num_ctx: int = 12288) -> str:
    """Bifrost는 항상 OpenAI 스키마로 변환해서 Ollama의 OpenAI 호환 레이어(/v1/chat/completions)를
    호출하는데, 이 레이어는 Ollama 전용 옵션(options.num_ctx, think)을 지원하지 않아 조용히 무시한다
    (Bifrost raw_request 디버그로 실측 확인함). 그래서 compile_wiki는 Bifrost를 우회해 Ollama
    네이티브 API(/api/chat)를 직접 호출한다. 대신 LangChain 콜백 트레이싱을 못 타므로, 현재
    langgraph 트레이스(app.invoke의 CallbackHandler가 연 span)의 자식으로 Langfuse generation을
    수동으로 붙여서 트레이싱 공백이 생기지 않게 한다."""
    ollama_messages = [
        {"role": _LC_ROLE_MAP.get(m.type, "user"), "content": m.content}
        for m in messages
    ]
    payload = {
        "model": settings.MODEL_NAME,
        "messages": ollama_messages,
        "stream": False,
        "think": False,
        "options": {"num_ctx": num_ctx, "num_predict": max_tokens, "temperature": 0.1},
    }

    lf_client = get_client()
    with lf_client.start_as_current_observation(
        name=part_name,
        as_type="generation",
        model=settings.MODEL_NAME,
        input=ollama_messages,
        model_parameters={"max_tokens": max_tokens, "num_ctx": num_ctx, "think": False},
    ) as generation:
        resp = requests.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()
        generation.update(
            output=content,
            usage_details={
                "input": data.get("prompt_eval_count", 0),
                "output": data.get("eval_count", 0),
            },
        )
    return content

def _invoke_compile_part(messages: list, part_name: str, base_max_tokens: int, fallback_max_tokens: int) -> str:
    """기본 num_ctx(4096)는 [스키마 규칙 + 정제된 원문] 입력만으로도 꽉 차서 답변을 쓸 자리가
    안 남는 경우가 있어, Ollama 네이티브 API로 num_ctx를 넉넉히 확대하고 think(사고 모드)도 꺼서
    토큰을 답변에 전부 쓰도록 한다. 그래도 빈 문자열이 오면 더 큰 max_tokens로 1회 재시도.
    재시도 후에도 비어있으면 ValueError로 상위에 알린다."""
    try:
        content = _call_ollama_native(messages, part_name, base_max_tokens)
    except Exception as e:
        print(f"   [!] {part_name} 작성 중 오류 발생: {e}")
        content = ""

    if not content:
        print(f"   [!] {part_name} 응답이 비어 있습니다 (사고 과정에서 토큰 소진 추정). {fallback_max_tokens} 토큰으로 재시도...")
        content = _call_ollama_native(messages, part_name, fallback_max_tokens)

    if not content:
        raise ValueError(f"{part_name} 응답이 재시도({fallback_max_tokens} 토큰) 후에도 비어 있습니다.")

    return content

def compile_wiki(state: AgentState) -> AgentState:
    print(f"✍️  [3/4] {state['category'].upper()} 형식에 맞춰 위키 작성 중 (순차 생성)...")

    with open(settings.SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_rules = f.read()

    compiled_parts = []

    # ---------------------------
    # Part 1: 개요 및 배경
    # ---------------------------
    print("   -> [Part 1] 개요 및 배경 작성 중...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1~4. 대기열 진입부터 원문 정제 완료\n⏳ 5-1. 개요 및 배경 작성 중...", state['discord_msg_id'])

    prompt_part1 = prompts.WIKI_COMPILE_PART1_PROMPT.format(
        schema_rules=schema_rules,
        cleaned_content=state['cleaned_content'],
        original_file_name=state['file_name']
    )

    messages1 = [
        SystemMessage(content="You are an expert Obsidian knowledge manager. Output ONLY the requested markdown template. NO conversational filler. Start exactly with '---'."),
        HumanMessage(content=prompt_part1)
    ]

    compiled_parts.append(_invoke_compile_part(messages1, "[Part 1] 개요 및 배경", 2048, 4096))

    # ---------------------------
    # Part 2: 주요 핵심 내용
    # ---------------------------
    print("   -> [Part 2] 주요 핵심 내용 작성 중...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1~4. 대기열 진입부터 원문 정제 완료\n✅ 5-1. 개요 및 배경 작성 완료\n⏳ 5-2. 본문(주요 핵심 내용) 작성 중...", state['discord_msg_id'])

    prompt_part2 = prompts.WIKI_COMPILE_PART2_PROMPT.format(
        context=state['context'],
        cleaned_content=state['cleaned_content']
    )

    messages2 = [
        SystemMessage(content="You are an expert Obsidian knowledge manager. Output ONLY the requested markdown template. NO conversational filler."),
        HumanMessage(content=prompt_part2)
    ]

    compiled_parts.append(_invoke_compile_part(messages2, "[Part 2] 주요 핵심 내용", 3500, 5120))

    # ---------------------------
    # Part 3: 인사이트 및 결론
    # ---------------------------
    print("   -> [Part 3] 인사이트 및 결론 작성 중...")
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1~4. 대기열 진입부터 원문 정제 완료\n✅ 5-1. 개요 및 배경 작성 완료\n✅ 5-2. 본문 작성 완료\n⏳ 5-3. 결론 및 인사이트 작성 중...", state['discord_msg_id'])

    prompt_part3 = prompts.WIKI_COMPILE_PART3_PROMPT.format(
        cleaned_content=state['cleaned_content']
    )

    messages3 = [
        SystemMessage(content="You are an expert Obsidian knowledge manager. Output ONLY the requested markdown template. NO conversational filler."),
        HumanMessage(content=prompt_part3)
    ]

    compiled_parts.append(_invoke_compile_part(messages3, "[Part 3] 인사이트 및 결론", 1536, 3072))

    # 최종 마크다운 조립: 인사이트 및 결론을 최상단(헤더 바로 다음)에 노출시키기 위해
    # Part1 출력을 [헤더(프론트매터+제목+링크)]와 [개요 섹션]으로 분리한 뒤,
    # 헤더 -> 결론(1) -> 개요(2) -> 본문(3) 순서로 재배열한다.
    part1_content, part2_content, part3_content = compiled_parts
    split_idx = part1_content.find("## 2. 개요 및 배경")
    if split_idx != -1:
        header = part1_content[:split_idx].rstrip()
        overview_section = part1_content[split_idx:].strip()
    else:
        header = part1_content
        overview_section = ""

    state['compiled_content'] = "\n\n".join(
        part for part in [header, part3_content, overview_section, part2_content] if part
    )

    # [NEW] 텍스트 생성 완료했으므로 LLM 강제 퇴거
    unload_ollama_model(settings.MODEL_NAME)

    return state

# ==========================================
# 노드 4: 저장 및 벡터 DB 학습 (Upsert)
# ==========================================
def save_wiki(state: AgentState) -> AgentState:
    if state.get('discord_msg_id'):
        send_discord_progress(f"🔄 **[분석 진행 중]** `{state['file_name']}`\n\n✅ 1. 대기열 진입 및 파일 읽기\n✅ 2. 카테고리 분석 완료\n✅ 3. 연관 지식 검색 완료\n✅ 4. 원문 정제 완료\n✅ 5. 최종 위키 형식으로 컴파일 완료\n⏳ 6. 임베딩 및 지식베이스 저장 중...", state['discord_msg_id'])
    if state['category'] == "tech":
        target_dir = settings.TECH_DIR
    elif state['category'] == "career":
        target_dir = settings.CAREER_DIR
    else:
        target_dir = settings.PERSONAL_DIR

    os.makedirs(target_dir, exist_ok=True)

    compiled_content = state['compiled_content']

    # 제목 추출: "# [키워드] 제목" 형식의 첫 번째 줄 찾기
    title_match = re.search(r'^#\s+(.+)$', compiled_content, re.MULTILINE)
    if title_match:
        raw_title = title_match.group(1)
        # 모델이 제목과 "🔗 원본 링크" 줄을 한 줄에 붙여 쓴 경우를 대비해 그 이후는 제목에서 제외
        raw_title = raw_title.split("🔗", 1)[0].strip()
        # 파일명으로 사용할 수 없는 문자 제거
        safe_title = re.sub(r'[\\/*?:"<>|\[\]]', "", raw_title).strip()
        new_file_name = f"{safe_title}.md" if safe_title else f"AI_{state['file_name']}"
    else:
        new_file_name = f"AI_{state['file_name']}"

    save_path = os.path.join(target_dir, new_file_name)

    # 파일명 충돌 방지: 동일 파일이 존재하면 타임스탬프 접미사 추가
    if os.path.exists(save_path):
        base, ext = os.path.splitext(save_path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = f"{base}_{timestamp}{ext}"
        print(f"   [!] 파일명 충돌 감지. 변경된 경로로 저장: {os.path.basename(save_path)}")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(compiled_content)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_text(compiled_content)

    # 파일명 확정 후 base_name 계산 (충돌 시 접미사 반영)
    final_file_name = os.path.basename(save_path)
    base_name = final_file_name.replace(".md", "")

    docs = []
    ids = []
    metadatas = []
    for i, chunk in enumerate(chunks):
        docs.append(chunk)
        ids.append(f"{base_name}_chunk_{i}")
        metadatas.append({"category": state['category'], "source": base_name})

    if docs:
        # 구버전 청크 삭제: 동일 source의 이전 데이터가 남지 않도록 정리
        try:
            existing = collection.get(where={"source": base_name})
            if existing['ids']:
                collection.delete(ids=existing['ids'])
        except Exception:
            pass  # 기존 데이터 없으면 무시

        collection.upsert(
            documents=docs,
            ids=ids,
            metadatas=metadatas
        )
        print(f"✅ [4/4] 저장 및 DB 학습 완료: {save_path}\n")
    else:
        print(f"⚠️ [경고] 저장할 문서 청크가 없습니다. AI가 빈 문자열을 반환했을 수 있습니다: {save_path}\n")
    return state

# ==========================================
# 워크플로우(LangGraph) 조립
# ==========================================
workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_document)
workflow.add_node("retrieve", retrieve_memory)
workflow.add_node("clean_data", clean_data)
workflow.add_node("compile", compile_wiki)
workflow.add_node("save", save_wiki)

workflow.set_entry_point("classify")
workflow.add_edge("classify", "retrieve")
workflow.add_edge("retrieve", "clean_data")
workflow.add_edge("clean_data", "compile")
workflow.add_edge("compile", "save")
workflow.add_edge("save", END)
app = workflow.compile()

# ==========================================
# 파일 처리 로직 (에러 핸들링, 자가 치유, 디스코드, 아카이브)
# ==========================================
SCRAPE_FAILURE_MARKERS = ("스크래핑 실패:", "스크래핑 에러:")

def _is_failed_scrape_only(content: str) -> bool:
    """discord_bot.py가 URL 스크래핑에 실패하면 '(스크래핑 실패: 403)' 같은 문구만 남긴 채
    저장한다. 이런 파일을 정상 원문처럼 파이프라인에 태우면 LLM이 실질적 내용 없이
    그럴듯한 문서를 지어내는(환각) 문제가 생기므로, URL/출처/실패 안내 줄을 제외하고도
    남는 실질 텍스트가 거의 없으면 '스크래핑 실패만 있는 파일'로 판단한다."""
    if not any(marker in content for marker in SCRAPE_FAILURE_MARKERS):
        return False
    remaining = "\n".join(
        line for line in content.splitlines()
        if line.strip()
        and not line.strip().startswith("http")
        and not line.strip().startswith("### Source:")
        and not any(marker in line for marker in SCRAPE_FAILURE_MARKERS)
    ).strip()
    return len(remaining) < 50

def _invoke_agent(file_path: str, file_name: str):
    """에이전트 파이프라인 실행. 성공 시 True, 실패 시 예외 발생."""

    # [선제적 VRAM 정리] 파이프라인 시작 전 좀비 프로세스를 사전 제거하여 OOM 방지
    print("🔍 [선제 점검] 파이프라인 시작 전 좀비 llama-server 점검 중...")
    kill_zombie_llama_servers()
    wait_for_vram_clear(max_wait=15)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print(f"⚠️ [경고] '{file_name}' 파일이 비어 있습니다. Error 폴더로 이동합니다.")
        safe_move(file_path, settings.ERROR_DIR, file_name)
        return None  # 빈 파일은 재시도 대상 아님

    if _is_failed_scrape_only(content):
        print(f"⚠️ [경고] '{file_name}'은 URL 스크래핑이 전부 실패해 실질적인 원문이 없습니다. 위키 생성을 건너뛰고 Error 폴더로 이동합니다.")
        safe_move(file_path, settings.ERROR_DIR, file_name)
        send_discord_notification(f"⚠️ **Wiki Agent 건너뜀**\n- 파일명: `{file_name}`\n- 원인: URL 스크래핑이 전부 실패해(예: 403 차단) 실질적인 원문이 없어 위키 생성을 건너뛰었습니다.")
        return None  # 스크래핑 실패 파일은 재시도 대상 아님


    initial_state = {
        "file_name": file_name,
        "raw_content": content,
        "category": "",
        "context": "",
        "cleaned_content": "",
        "compiled_content": "",
        "discord_msg_id": ""
    }

    msg_id = send_discord_progress(f"🔄 **[분석 대기 중]** `{file_name}`\n\n⏳ 대기열 진입 및 파일 읽기 준비 중...")
    if msg_id:
        initial_state["discord_msg_id"] = msg_id

    lf_handler = CallbackHandler()
    final_state = app.invoke(initial_state, config={"callbacks": [lf_handler], "run_name": file_name})

    safe_move(file_path, settings.ARCHIVE_DIR, file_name)

    # 완료 알림은 진행 메시지를 수정(PATCH)하지 않고 항상 새 메시지로 보냄 (수정 시 디스코드 알림이 오지 않는 문제 방지)
    send_discord_notification(f"✅ **Wiki Agent 작성 완료!**\n- 문서: `{file_name}`\n- 카테고리: `{final_state.get('category', 'unknown')}`\n지식 DB에 성공적으로 저장되었습니다.")
    return True

def _is_ollama_server_error(error_msg: str) -> bool:
    """Ollama 서버 레벨 에러(OOM, 좀비, 프로세스 종료)인지 판별"""
    markers = ["out-of-memory", "llama-server", "TerminateProcess", "exit status", "Vulkan", "timeout", "504", "request_timed_out"]
    return any(m in error_msg for m in markers)

def process_file(file_path: str):
    file_name = os.path.basename(file_path)

    try:
        _invoke_agent(file_path, file_name)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ [에러] '{file_name}' 처리 중 오류 발생: {error_msg}")
        traceback.print_exc()

        # [자가 치유] Ollama 서버 에러(OOM/좀비)일 경우 1회 재시도
        if _is_ollama_server_error(error_msg) and os.path.exists(file_path):
            print("🔧 [자가 치유] Ollama 서버 에러 감지! 좀비 프로세스 정리 후 재시도합니다...")
            send_discord_notification(f"🔧 **[자가 치유 가동]** `{file_name}`\nOllama 서버 에러 감지. 좀비 프로세스 정리 후 재시도합니다...")

            # 1. 좀비 사살
            kill_zombie_llama_servers()
            # 2. VRAM 완전 해제 대기
            time.sleep(5)
            wait_for_vram_clear(max_wait=15)

            # 3. 재시도 (1회만)
            try:
                print(f"🔄 [재시도] '{file_name}' 다시 처리합니다...")
                _invoke_agent(file_path, file_name)
                print(f"✅ [자가 치유 성공] '{file_name}' 재시도 성공!")
                return  # 재시도 성공 시 여기서 종료
            except Exception as retry_e:
                print(f"❌ [자가 치유 실패] 재시도도 실패: {retry_e}")
                error_msg = str(retry_e)  # 최종 에러 메시지 갱신

        # 최종 실패: 디스코드 알림 + Error 폴더 이동
        send_discord_notification(f"🚨 **Wiki Agent 에러 발생**\n- 파일명: `{file_name}`\n- 원인: {error_msg}")
        try:
            if os.path.exists(file_path):
                safe_move(file_path, settings.ERROR_DIR, file_name)
        except Exception as move_e:
            print(f"⚠️ [경고] 에러 폴더 이동 실패: {move_e}")

# ==========================================
# 워커 스레드 및 큐 (다중 파일 순차 처리)
# ==========================================
file_queue = queue.Queue()

def worker():
    while True:
        file_path = file_queue.get()
        if file_path is None:
            break

        file_basename = os.path.basename(file_path)

        while True:
            # 1. 업무 시간 체크 (08:00~12:00 및 13:00~22:00)
            # 사용자의 업무 미진행 시간(점심 12:00~13:00)은 허용하여 AI가 작업할 수 있도록 함
            now = datetime.datetime.now().time()
            morning_start = datetime.time(8, 0)
            morning_end = datetime.time(12, 0)
            afternoon_start = datetime.time(13, 0)
            afternoon_end = datetime.time(22, 0)

            is_working_time = (morning_start <= now < morning_end) or (afternoon_start <= now < afternoon_end)

            if is_working_time:
                print(f"⏳ [워커 대기] 업무 시간 중입니다. 대기 중: {file_basename}")
                time.sleep(10 * 60)  # 10분 단위로 체크
                continue

            # 2. Ollama 상태 체크 (타 모델 실행 여부)
            try:
                resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/ps", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    loaded_models = [m['name'] for m in data.get('models', [])]

                    my_model = settings.MODEL_NAME
                    # 현재 지정된 Wiki 모델이 아닌 다른 모델이 로드되어 있는지 확인
                    other_models = [m for m in loaded_models if my_model not in m]

                    if other_models:
                        print(f"⏸️ [모델 충돌 방지] 타 모델({', '.join(other_models)}) 사용 감지! 30분 대기합니다...")
                        time.sleep(30 * 60)  # 30분 대기 후 다시 시간/모델 체크로 돌아감
                        continue
            except Exception as e:
                print(f"⚠️ Ollama 상태 확인 실패 (무시하고 진행): {e}")

            # 업무 시간도 아니고 타 모델도 없으면 루프 탈출 후 위키 처리
            break

        # 쓰기 작업이 완료될 때까지 약간 대기
        time.sleep(1)
        process_file(file_path)
        file_queue.task_done()

        # 큐 잔여량 출력
        remaining = file_queue.qsize()
        if remaining > 0:
            print(f"📋 대기열: {remaining}개 남음")

# ==========================================
# 데몬: 폴더 감시 (Watchdog)
# ==========================================
class RawFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            print(f"📥 [큐 대기열 추가] 새 파일 감지: {os.path.basename(event.src_path)}")
            file_queue.put(event.src_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wiki Agent Daemon and Batch Processor")
    parser.add_argument("--batch", action="store_true", help="Process all files in RAW_DIR sequentially")
    args = parser.parse_args()

    os.makedirs(settings.RAW_DIR, exist_ok=True)

    # schema.md 존재 검증 (없으면 모든 문서가 compile 단계에서 실패하므로 시작 차단)
    if not os.path.exists(settings.SCHEMA_PATH):
        msg = f"❌ schema.md 파일을 찾을 수 없습니다: {settings.SCHEMA_PATH}"
        print(msg)
        send_discord_notification(f"🚨 **Wiki Agent 시작 실패**\n- 원인: {msg}")
        raise SystemExit(1)

    if args.batch:
        files = [f for f in os.listdir(settings.RAW_DIR) if f.endswith(".md")]
        total = len(files)
        print(f"🚀 [배치 모드] 총 {total}개의 마크다운 파일을 감지했습니다. 처리를 시작합니다.")

        for i, f_name in enumerate(files, 1):
            print("\n======================================")
            print(f"📦 [{i}/{total}] 처리 중: {f_name}")
            print("======================================")
            file_path = os.path.join(settings.RAW_DIR, f_name)
            process_file(file_path)

        print("\n✅ 배치 처리가 모두 완료되었습니다.")

    else:
        print(f"🚀 [시스템 시작] '{settings.RAW_DIR}' 폴더 감시 데몬이 실행되었습니다. (Ctrl+C 종료)")

        # [자동 재개 로직] 기존에 방치된 파일들을 스캔하여 큐에 적재
        existing_files = [f for f in os.listdir(settings.RAW_DIR) if f.endswith(".md")]
        if existing_files:
            print(f"🔍 [자동 재개] 기존 미처리 파일 {len(existing_files)}개를 발견하여 대기열에 추가합니다.")
            for f_name in existing_files:
                file_queue.put(os.path.join(settings.RAW_DIR, f_name))

        # 순차 처리를 위한 백그라운드 워커 실행
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        event_handler = RawFolderHandler()
        observer = Observer()
        observer.schedule(event_handler, settings.RAW_DIR, recursive=False)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
