"""
title: LLM Router
author: Hyeseong-Myeong
version: 2.2.0
type: filter
description: |
    키워드 기반 자동 모델 라우팅 필터.
    LLM 호출 없이 즉시 분류하여 오버헤드를 최소화합니다.
    웹 검색 컨텍스트 감지 시 messages 재구성 없이 그대로 통과합니다.

    지원 모델:
    - llm-coder  : 코딩 및 기술 질의 (Qwen2.5-Coder 7B)
    - llm-exaone : 한국어 문서 작성 (EXAONE Deep 7.8B)
    - llm-qwen3  : 복잡한 추론 (Qwen3 8B)
    - llm-r1     : 수학/논리 추론 (DeepSeek-R1 7B)
    - gemini     : 외부 API (Gemini 2.5 Flash)

    슬래시 명령:
    /coder /exaone /qwen3 /r1 /gemini /claude
"""

from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        OLLAMA_BASE_URL: str = Field(
            default="http://host.docker.internal:11434",
            description="Ollama 서버 주소"
        )
        CONTEXT_TURNS: int = Field(
            default=3,
            description="전환 시 넘길 대화 턴 수"
        )
        SHOW_ROUTING_INFO: bool = Field(
            default=True,
            description="분류 결과 응답 상단 표시"
        )

    def __init__(self):
        self.valves = self.Valves()
        self.routing_info = {}

        self.model_map = {
            "coder":  "llm-coder:latest",
            "exaone": "llm-exaone:latest",
            "qwen3":  "llm-qwen3:latest",
            "r1":     "llm-r1:latest",
            "gemini": "google_genai.gemini-2.5-flash",
        }

        self.slash_map = {
            "/coder":  "coder",
            "/exaone": "exaone",
            "/qwen3":  "qwen3",
            "/r1":     "r1",
            "/gemini": "gemini",
        }

        self.category_label = {
            "coder":  "💻 코딩 모델 (Qwen2.5-Coder)",
            "exaone": "🇰🇷 한국어 모델 (EXAONE Deep)",
            "qwen3":  "🧠 추론 모델 (Qwen3)",
            "r1":     "🔬 R1 추론 모델 (DeepSeek-R1)",
            "gemini": "✨ Gemini 2.5 Flash (Google)",
        }

        self.keyword_rules = [
            ("exaone", [
                "이력서", "포트폴리오", "자기소개서", "커버레터",
                "문서 작성", "문서화", "보고서 작성", "기획서",
                "번역해", "번역 해", "한국어로 작성", "한글로 작성",
                "작성해줘", "작성해 줘", "써줘", "써 줘",
                "정리해줘", "정리해 줘", "요약해줘", "요약해 줘",
                "소개글", "자소서", "프로필",
            ]),
            ("qwen3", [
                "왜 ", "왜냐", "이유가", "원인이", "차이가",
                "비교해", "분석해", "설명해줘", "설계해",
                "아키텍처", "트레이드오프", "장단점",
                "수학", "증명", "공식", "알고리즘 설계",
                "단계별로", "논리적으로", "구조적으로",
                "어떻게 동작", "어떻게 작동", "원리가",
            ]),
            ("coder", [
                "코드", "함수", "메서드", "클래스", "버그",
                "에러", "오류", "디버그", "구현해", "짜줘",
                "def ", "class ", "import ", "return ",
                "git", "api", "sql", "database", "db",
                "python", "javascript", "typescript", "java",
                "react", "vue", "django", "fastapi", "docker",
                "리팩토링", "테스트 코드", "단위 테스트",
                "스크립트", "자동화", "배포",
            ]),
        ]

    def _keyword_classify(self, message: str) -> str:
        """키워드 기반 즉시 분류 — LLM 호출 없음"""
        msg_lower = message.lower()
        for category, keywords in self.keyword_rules:
            for kw in keywords:
                if kw.lower() in msg_lower:
                    return category
        return "coder"

    def _check_slash(self, message: str):
        stripped = message.strip()
        for slash, key in self.slash_map.items():
            if stripped.lower().startswith(slash):
                clean = stripped[len(slash):].strip()
                return key, clean if clean else stripped
        return None, message

    def _summarize_context(self, messages: list, n: int) -> list:
        if len(messages) <= n * 2:
            return messages
        recent = messages[-(n * 2):]
        summary = {
            "role": "system",
            "content": f"[이전 대화 요약: 총 {len(messages)//2}턴 중 최근 {n}턴만 포함됩니다]"
        }
        return [summary] + recent

    def _has_web_search_context(self, messages: list) -> bool:
        """웹 검색 결과가 포함된 메시지 감지"""
        web_markers = [
            "<source", "search_web", "[WEB]", "snippet",
            "web-search", "retrieval", "<context>",
        ]
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                content_lower = content.lower()
                if any(marker.lower() in content_lower for marker in web_markers):
                    return True
        return False

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        messages = body.get("messages", [])
        if not messages:
            return body

        # 웹 검색 컨텍스트 감지 — messages 재구성 없이 그대로 통과
        if self._has_web_search_context(messages):
            self.routing_info = {
                "method": "웹 검색",
                "key": "coder",
                "category": "WEB",
                "label": "🌐 웹 검색 결과 포함",
            }
            return body

        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    user_msg = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            user_msg += item.get("text", "")
                break

        if not user_msg:
            return body

        # /gemini 처리
        if user_msg.strip().lower().startswith("/gemini"):
            clean = user_msg.strip()[7:].strip()
            body["model"] = "google_genai.gemini-2.5-flash"
            body["messages"][-1]["content"] = clean if clean else user_msg
            self.routing_info = {
                "method": "수동 지정",
                "key": "gemini",
                "category": "EXTERNAL",
                "label": "✨ Gemini 2.5 Flash (Google)",
            }
            return body

        # /claude 처리
        if user_msg.strip().lower().startswith("/claude"):
            body["messages"][-1]["content"] = user_msg.replace("/claude", "", 1).strip()
            self.routing_info = {
                "method": "수동 지정",
                "key": "claude",
                "category": "EXTERNAL",
                "label": "☁️ Claude API (미연결)",
            }
            return body

        # 슬래시 명령 처리
        forced_key, clean_message = self._check_slash(user_msg)
        if forced_key:
            history = messages[:-1]
            context = self._summarize_context(history, self.valves.CONTEXT_TURNS)
            body["model"] = self.model_map[forced_key]
            body["messages"] = context + [{"role": "user", "content": clean_message}]
            self.routing_info = {
                "method": "수동 지정",
                "key": forced_key,
                "category": forced_key.upper(),
                "label": self.category_label[forced_key],
            }
            return body

        # 현재 메시지 파일 첨부 감지
        current_msg = None
        for m in reversed(messages):
            if m.get("role") == "user":
                current_msg = m
                break

        if current_msg:
            content = current_msg.get("content", "")
            has_file = False
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") in ["file", "image_url", "document"]:
                        has_file = True
                        break
            if not has_file and (body.get("files") or body.get("file_ids")):
                has_file = True

            if has_file:
                self.routing_info = {
                    "method": "파일 첨부",
                    "key": "coder",
                    "category": "RAG",
                    "label": "📎 파일 첨부 — 현재 모델 유지",
                }
                return body

        # 키워드 기반 즉시 분류
        target_key = self._keyword_classify(user_msg)
        history = messages[:-1]
        context = self._summarize_context(history, self.valves.CONTEXT_TURNS)
        body["model"] = self.model_map[target_key]
        body["messages"] = context + [{"role": "user", "content": user_msg}]
        self.routing_info = {
            "method": "키워드 분류",
            "key": target_key,
            "category": target_key.upper(),
            "label": self.category_label[target_key],
        }
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.SHOW_ROUTING_INFO:
            return body

        info = self.routing_info
        if not info:
            return body

        method = info.get("method", "")
        label = info.get("label", "")
        category = info.get("category", "")

        header = f"> **[{method}]** {label} | 카테고리: `{category}`\n\n---\n\n"

        messages = body.get("messages", [])
        for m in reversed(messages):
            if m.get("role") == "assistant":
                m["content"] = header + m.get("content", "")
                break

        return body
