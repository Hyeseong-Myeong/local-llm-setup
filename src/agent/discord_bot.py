import os
import re
import sys
import json
import aiohttp
import aiofiles
from urllib.parse import urlparse

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logger_setup
logger_setup.setup_logger('discord_bot.log')
# pyrefly: ignore [missing-import]
import discord
from dotenv import load_dotenv
from config import settings
from datetime import datetime

load_dotenv()

def sanitize_content(text: str) -> str:
    """스크래핑된 콘텐츠에서 위험한 HTML 태그 및 스크립트를 제거"""
    # 위험한 태그와 내용 제거 (script, iframe, object, embed, form, style)
    text = re.sub(r'<(script|iframe|object|embed|form|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 셀프클로징 위험 태그 제거
    text = re.sub(r'<(script|iframe|object|embed|form|style)[^>]*/>', '', text, flags=re.IGNORECASE)
    # javascript: URI 제거
    text = re.sub(r'javascript\s*:', '', text, flags=re.IGNORECASE)
    # on* 이벤트 핸들러 속성 제거 (예: onclick="...", onerror='...')
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
    return text

# Discord intents 설정 (메시지 내용을 읽기 위해 필수)
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# URL 감지를 위한 정규식 패턴
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

# Jina Reader 등 외부 스크래퍼를 정책적으로 차단하는 것이 확인된 도메인 목록(시드값).
# 새로운 차단 사례가 발견되면 여기에 추가해도 되지만, 아래 자동 학습 로직이 런타임에
# 403을 만난 도메인을 data/blocked_domains.json에 자동으로 기록해준다.
SCRAPE_BLOCKED_DOMAINS_SEED = {
    "x.com",
    "twitter.com",
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCKED_DOMAINS_FILE = os.path.join(PROJECT_ROOT, "data", "blocked_domains.json")

def _load_blocked_domains() -> set:
    """시드 목록 + 이전에 403으로 학습해서 저장해둔 도메인 목록을 합쳐서 로드"""
    domains = set(SCRAPE_BLOCKED_DOMAINS_SEED)
    try:
        if os.path.exists(BLOCKED_DOMAINS_FILE):
            with open(BLOCKED_DOMAINS_FILE, "r", encoding="utf-8") as f:
                domains.update(json.load(f))
    except Exception as e:
        print(f"⚠️ 차단 도메인 목록 로드 실패: {e}")
    return domains

SCRAPE_BLOCKED_DOMAINS = _load_blocked_domains()

def _get_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc

def _is_scrape_blocked_domain(url: str) -> bool:
    domain = _get_domain(url)
    return any(domain == blocked or domain.endswith("." + blocked) for blocked in SCRAPE_BLOCKED_DOMAINS)

def _learn_blocked_domain(domain: str):
    """403을 만난 도메인을 차단 목록에 추가하고 학습분(시드 제외)을 파일에 영속화"""
    if not domain or domain in SCRAPE_BLOCKED_DOMAINS:
        return
    SCRAPE_BLOCKED_DOMAINS.add(domain)
    try:
        os.makedirs(os.path.dirname(BLOCKED_DOMAINS_FILE), exist_ok=True)
        learned = sorted(SCRAPE_BLOCKED_DOMAINS - SCRAPE_BLOCKED_DOMAINS_SEED)
        with open(BLOCKED_DOMAINS_FILE, "w", encoding="utf-8") as f:
            json.dump(learned, f, ensure_ascii=False, indent=2)
        print(f"🚫 [자동 학습] '{domain}' 을(를) 스크래핑 차단 목록에 추가했습니다.")
    except Exception as e:
        print(f"⚠️ 차단 도메인 저장 실패: {e}")

@client.event
async def on_ready():
    print(f"✅ 로그인 완료: {client.user}")
    print(f"🚀 디스코드 봇이 실행되었습니다. 메시지와 URL을 감시합니다...")

@client.event
async def on_message(message):
    # 봇(웹훅 포함)이 보낸 메시지는 무시
    if message.author.bot:
        return

    # 수신된 메시지를 CMD 창에 출력 (디버깅용)
    channel_name = message.channel.name if hasattr(message.channel, 'name') else 'DM'
    print(f"[{channel_name}] {message.author.name}: {message.content}")

    urls = URL_PATTERN.findall(message.content)
    content_to_save = message.content

    # 알려진 스크래핑 차단 도메인은 시도조차 하지 않고 바로 걸러낸 뒤 직접 복붙을 요청
    blocked_urls = [u for u in urls if _is_scrape_blocked_domain(u)]
    scrapable_urls = [u for u in urls if u not in blocked_urls]

    if blocked_urls:
        blocked_list = "\n".join(f"- {u}" for u in blocked_urls)
        await message.channel.send(
            f"🚫 아래 링크는 자동 스크래핑이 차단된 사이트라 내용을 가져올 수 없습니다:\n{blocked_list}\n"
            f"본문 내용을 직접 복사해서 다시 보내주시면 그걸로 위키를 만들어드릴게요."
        )
        # URL만 덩그러니 남은 무의미한 노트가 저장되지 않도록 본문에서 제거
        for u in blocked_urls:
            content_to_save = content_to_save.replace(u, "").strip()

    # URL이 존재할 경우 스크래핑 진행
    if scrapable_urls:
        await message.channel.send("🔍 URL이 감지되었습니다. Jina Reader로 스크래핑을 시작합니다...")
        scraped_texts = []
        success_count = 0
        async with aiohttp.ClientSession() as session:
            for url in scrapable_urls:
                try:
                    target_url = url
                    # 네이버 블로그 URL인 경우 모바일(m.blog.naver.com) 버전으로 변경하여 iframe 우회
                    if "blog.naver.com" in target_url and "m.blog.naver.com" not in target_url:
                        target_url = target_url.replace("blog.naver.com", "m.blog.naver.com")

                    # Jina Reader API를 활용하여 본문 스크래핑 (비동기)
                    async with session.get(f"https://r.jina.ai/{target_url}", timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            text = await response.text()
                            scraped_texts.append(f"### Source: {url}\n\n{text}")
                            success_count += 1
                        else:
                            scraped_texts.append(f"### Source: {url}\n\n(스크래핑 실패: {response.status})")
                            if response.status == 403:
                                domain = _get_domain(url)
                                if domain not in SCRAPE_BLOCKED_DOMAINS:
                                    _learn_blocked_domain(domain)
                                    await message.channel.send(f"🚫 **[자동 학습]** `{domain}` 에서 403(접근 거부)이 발생해 차단 목록에 추가했습니다. 다음부터는 이 도메인 링크는 자동으로 건너뜁니다.")
                except Exception as e:
                    scraped_texts.append(f"### Source: {url}\n\n(스크래핑 에러: {e})")

        # 원본 메시지와 스크래핑 결과를 결합
        content_to_save = content_to_save + "\n\n" + "\n\n---\n\n".join(scraped_texts)

        if success_count == 0:
            await message.channel.send("⚠️ 모든 URL 스크래핑에 실패했습니다 (403 차단 등 — X/Twitter 같은 사이트는 외부 스크래퍼를 막는 경우가 많습니다). 원본 내용을 가져오지 못해 Wiki Agent가 위키 생성을 건너뜁니다.")
        
    # 빈 메시지 방지
    if not content_to_save.strip():
        return

    # 악성 마크다운 필터링 (스크래핑 결과의 위험한 HTML 태그 제거)
    content_to_save = sanitize_content(content_to_save)

    # 피드백 반영: 알아보기 쉬운 날짜 포맷 (Discord_20260709_205325.md)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"Discord_{timestamp_str}.md"
    file_path = os.path.join(settings.RAW_DIR, file_name)
    
    os.makedirs(settings.RAW_DIR, exist_ok=True)
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(content_to_save)
        
    # 글자 수에 따른 처리 방식 안내 메시지 추가
    text_length = len(content_to_save)
    if text_length <= settings.SPLIT_THRESHOLD:
        method_msg = f"단일 정제 방식(길이: {text_length}자)으로 처리를 시작합니다!"
    else:
        method_msg = f"분할 정제 방식(길이: {text_length}자)으로 안전하게 처리를 시작합니다!"
        
    await message.channel.send(f"✅ 메모가 `{file_name}`으로 RAW 폴더에 저장되었습니다.\n(Wiki Agent가 {method_msg})")

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token or token == "여기에_디스코드_봇_토큰_입력":
        print("❌ 에러: .env 파일에 DISCORD_BOT_TOKEN을 설정해주세요.")
    else:
        client.run(token)
