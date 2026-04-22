"""
title: Google GenAI Manifold
author: Hyeseong-Myeong
version: 2.0.0
license: MIT
description: |
    google-genai SDK를 사용한 Gemini 모델 연동.
    Open WebUI Functions manifold 타입으로 동작.
    GOOGLE_API_KEY 환경변수 또는 Valves에서 키 설정.
    기본 모델: gemini-2.5-flash

requirements:
    - google-genai (Dockerfile에 RUN pip install google-genai 추가 필요)
"""
import os
from pydantic import BaseModel, Field
from typing import List, Union, Iterator
from google import genai
from google.genai import types


class Pipe:
    class Valves(BaseModel):
        GOOGLE_API_KEY: str = Field(default="")

    def __init__(self):
        self.id = "google_genai"
        self.type = "manifold"
        self.name = "Google: "
        self.valves = self.Valves(
            **{"GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "")}
        )

    def _get_client(self):
        return genai.Client(api_key=self.valves.GOOGLE_API_KEY)

    def get_google_models(self):
        if not self.valves.GOOGLE_API_KEY:
            return [{"id": "error", "name": "GOOGLE_API_KEY를 설정해주세요"}]
        try:
            client = self._get_client()
            models = client.models.list()
            result = []
            for m in models:
                if hasattr(m, "supported_actions"):
                    if "generateContent" not in (m.supported_actions or []):
                        continue
                name = m.name
                if name.startswith("models/"):
                    name = name[7:]
                display = getattr(m, "display_name", name)
                result.append({"id": name, "name": display})
            return result if result else [{"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"}]
        except Exception as e:
            return [{"id": "error", "name": f"오류: {str(e)}"}]

    def pipes(self) -> List[dict]:
        return self.get_google_models()

    def pipe(self, body: dict) -> Union[str, Iterator[str]]:
        if not self.valves.GOOGLE_API_KEY:
            return "오류: GOOGLE_API_KEY가 설정되지 않았습니다"
        try:
            client = self._get_client()
            model_id = body["model"]
            if model_id.startswith("google_genai."):
                model_id = model_id[len("google_genai."):]
            if model_id.startswith("models/"):
                model_id = model_id[7:]

            messages = body.get("messages", [])
            contents = []
            system_instruction = None

            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    contents.append(types.Content(
                        role="user", parts=[types.Part(text=content)]
                    ))
                elif role == "assistant":
                    contents.append(types.Content(
                        role="model", parts=[types.Part(text=content)]
                    ))

            config = types.GenerateContentConfig(
                temperature=body.get("temperature", 0.7),
                max_output_tokens=body.get("max_tokens", 8192),
                system_instruction=system_instruction,
            )

            stream = body.get("stream", False)

            if stream:
                def stream_generator():
                    response = client.models.generate_content_stream(
                        model=model_id, contents=contents, config=config,
                    )
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text
                return stream_generator()
            else:
                response = client.models.generate_content(
                    model=model_id, contents=contents, config=config,
                )
                return response.text

        except Exception as e:
            return f"오류: {str(e)}"
