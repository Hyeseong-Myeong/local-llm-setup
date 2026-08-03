# 🚀 로컬 LLM 시스템 최대화 가이드 (2026-07 기준)

> 대상 하드웨어: AMD Ryzen 5 5600X / 32GB RAM / Radeon RX 6600 XT (8GB VRAM, ROCm gfx1032 → `HSA_OVERRIDE_GFX_VERSION=10.3.0`)
> 기존 구축 상태: Ollama + Open WebUI, ChromaDB(8000), `wiki_agent.py`(Watchdog 기반 Obsidian 자동 정리), `discord_bot.py`, Langfuse 관측
> 목적: 취업 준비(백엔드/인프라), 코딩·인프라 실무 보조, 위키 자동화 고도화, 멀티모델 운영 안정성, 반복 작업 자동화, AI 네이티브 개발 파이프라인 구축을 이 하드웨어 한계 안에서 최대치로 끌어올리는 방안 정리

---

## 0. 전제 및 확인 필요 사항

이 문서는 `model_compair.md`에 기록된 기존 설치 모델(`qwen3.5:9b`, `deepseek-r1:14b`, `exaone3.5:7.8b`, `phi4`)이 실제로 설치되어 있다는 가정 하에 작성되었습니다. 정확도를 위해 아래 명령어로 실제 설치 목록을 먼저 확인하시길 권장합니다.

```bash
ollama list
ollama ps   # 현재 VRAM에 올라와 있는 모델 확인
```

또한 아래 1장은 **2026년 7월 기준 웹 검색으로 재검증한 내용**이며, 기존 `model_compair.md`의 일부 서술과 다릅니다. 특히 GPT-OSS-20B 항목은 기존 문서의 낙관적 평가를 정정합니다.

---

## 1. 모델 구성 최신화 (2026-07 검증)

### 1-1. 기존 문서 대비 정정 사항

| 항목 | `model_compair.md` 기존 서술 | 2026-07 검증 결과 |
|---|---|---|
| **GPT-OSS-20B** | "8GB VRAM+32GB RAM 환경에서 극도의 쾌적함" | 정정 필요. 실제 권장 VRAM은 16~24GB([IntuitionLabs](https://intuitionlabs.ai/articles/hardware-requirements-gpt-oss-20b), [willitrunai](https://willitrunai.com/blog/gpt-oss-20b-vram-requirements)). 8GB VRAM에서는 CPU 오프로딩이 강제되며 GPU 대비 **5~20배 느려짐**([HF 논의](https://huggingface.co/openai/gpt-oss-20b/discussions/26)). 이 하드웨어에는 비추천 |
| **Gemma 4** | 작성 당시 미확정 정보 | 2026-04-02 실제 출시 확인. E2B/E4B/26B-A4B(MoE)/31B(Dense) 라인업, Apache 2.0, 에이전트·툴콜링 특화([Google Blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)) |
| **Ministral 3** | "Ministral 3 (8B/14B)" | 2025-12-02 출시 확인. 3B/8B/14B 각각 base/instruct/**reasoning** 변형 제공, 이미지 이해 포함([Mistral AI](https://mistral.ai/news/mistral-3/)) |
| **Qwen 3.5** | 사용 중이라고만 명시 | 2026-02-16(플래그십 397B-A17B) → 02-24(중형) → 03-02(경량, 현재 사용 중인 9B 포함) 단계 출시 확인. thinking/non-thinking 겸용, 네이티브 툴콜링 지원([Ollama X 공지](https://x.com/ollama/status/2028510184788926567)) |
| **EXAONE** | 3.0/3.5 기준 서술 | LG AI Research는 2025-07 **EXAONE 4.0**(32B/1.2B, 하이브리드 추론)에 이어 2026-04 **EXAONE 4.5**(33B, Vision-Language)까지 출시([LG AI Research](https://www.lgresearch.ai/blog/view?seq=576), [PRNewswire](https://www.prnewswire.com/news-releases/lg-reveals-next-gen-multimodal-ai-exaone-4-5-302736993.html)) |
| **DeepSeek-R1-Distill-Qwen-14B** | 심층 추론 최선책으로 서술 | 유효함. DeepSeek는 2026년 R2를 아직 출시하지 않았고(루머만 존재), 주력을 V4/V3.2 계열(초대형, 로컬 불가)에 투입 중이라 이 체급의 로컬 추론 배포판으로는 R1-Distill-14B가 여전히 실질적 최선([펠로AI](https://felloai.com/deepseek-r2/), [InfoQ](https://www.infoq.com/news/2026/01/deepseek-v32/)) |
| **코딩 특화 모델** | 언급 없음 | **Qwen3-Coder** 계열이 2026년 로컬 코딩 1순위로 부상. 이 하드웨어에는 `Qwen3-Coder-30B-A3B`(MoE, 3.3B 활성)가 적합 — 아래 1-2 참고 |

### 1-2. 역할별 최종 모델 배치 제안

| 역할 | 모델 | 양자화/용량 | 하드웨어 적합성 | 비고 |
|---|---|---|---|---|
| 심층 리팩토링·아키텍처 설계 | `deepseek-r1:14b` (기존 유지) | Q4, 초당 15~20토큰 | 32GB RAM에 여유롭게 안착 | 복잡한 버그 추적, 설계 리뷰 전담 |
| **코딩 실무 보조 (신규 1순위)** | `qwen3-coder:30b-a3b-q4_K_M` | **약 19GB**, 30.5B 총 파라미터 중 3.3B 활성 | GPU(8GB)+RAM(32GB) 분할 구동 가능 — 이 하드웨어의 코딩 성능 상한선 | Spring Boot/FastAPI/Terraform 리뷰, IDE 연동용 |
| 빠른 로직 디버깅·핑퐁 | `phi4:latest` (기존 유지) | 14B, 초당 15~20토큰 | 기존 안착 확인됨 | 엄격한 로직/수학 검증 |
| **위키 태깅·분류 (경량, 신규)** | `exaone4.0:1.2b` | 1.2B, 매우 가벼움 | VRAM 여유 큼, 상시 구동 가능 | `wiki_agent.py`의 classify 단계 전담 — 큰 모델과 VRAM 경합 없음 |
| 한국어 심층 문서·이력서 첨삭 | `exaone3.5:7.8b` (기존 유지) | 8GB VRAM 100% 안착 | 그대로 유지 | 3-1 참고 |
| **에이전트/툴콜링 (신규, 검증 필요)** | `gemma4:e4b` 또는 `gemma4:26b-a4b` | 정확한 양자화 용량 **미확인** — `ollama pull` 전 `ollama show` 또는 Ollama 라이브러리 페이지로 실제 GB 확인 필요 | 에이전트 워크플로우/함수 호출에 특화 | MCP 도구 호출 안정성이 중요한 3장/5장 워크플로우에 우선 시도 |
| 장문 컨텍스트·멀티파일 리팩토링 | `ministral3:14b` (reasoning 변형) | 14B, 32GB RAM 혼합 구동 | 신규 후보 | 프로젝트 통째 리팩토링 시 시도 |
| ❌ 비추천 | GPT-OSS-20B | 16~24GB VRAM 권장 | **이 하드웨어엔 부적합** (5~20배 저하) | 기존 문서 정정 |
| ❌ 구동 불가 | Kimi K2 계열 | 1조 파라미터급 | 로드 자체 불가 | 기존 문서 판단 유지 |

> **왜 MoE(A3B/A4B) 모델을 미는가:** 8GB VRAM 환경에서는 "총 파라미터 크기"보다 "추론 시 활성화되는 파라미터 수"가 체감 속도를 결정합니다. Qwen3-Coder-30B-A3B는 총 30B을 디스크/RAM에 두고도 실제 연산에는 3.3B만 쓰므로, 14B Dense 모델(Phi-4 등)보다 오히려 빠르게 응답하면서 지식은 더 넓을 수 있습니다. 다만 최초 로드 시 19GB를 메모리에 올려야 하므로 **다른 대형 모델과 동시 로드는 피해야** 합니다 (2장 참고).

### 1-3. 모델 교체 명령어 예시

```bash
# 신규 추천 모델 설치
ollama pull qwen3-coder:30b-a3b-q4_K_M
ollama pull exaone4.0:1.2b
ollama pull ministral3:14b     # 정확한 태그명은 ollama.com/library에서 확인
ollama pull gemma4:e4b         # 설치 전 ollama show gemma4:e4b 로 용량 확인 권장

# 미사용/저효율 모델 정리
ollama rm qwen-master   # 기존 테스트용 모델
```

---

## 2. Ollama 멀티모델 운영 파라미터 (VRAM 스래싱 방지)

`troubleshooting.md`에 이미 기록된 "다른 작업 중 백그라운드 위키 작업 난입 시 모델 스위칭 스톨" 우려는 실제로 발생 가능한 문제이며, 아래 환경변수로 구조적으로 줄일 수 있습니다. ([Ollama 공식 FAQ](https://docs.ollama.com/faq))

| 환경변수 | 권장값 | 이유 |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | `1` (기본값은 GPU 수×3) | 8GB VRAM에서 여러 모델을 동시에 올리면 예측 불가능한 축출(eviction)이 발생. 안전하게 1개로 제한. 단, `exaone4.0:1.2b`처럼 초경량 모델을 상시 대기시키는 조합이라면 `2`도 검토 가능 |
| `OLLAMA_NUM_PARALLEL` | `1` | 병렬 요청 수만큼 RAM이 `num_ctx × 병렬수`로 배수 증가. 단일 사용자 환경이므로 1 고정 |
| `OLLAMA_KEEP_ALIVE` | 대화형 세션 `5m`(기본), `wiki_agent` 전담 모델은 기존 시간대 락(업무시간 대기 + `/api/ps` 폴링) 로직 유지 | 이미 잘 구현된 부분이므로 신규 자동화 스크립트(4장)도 동일 패턴을 재사용할 것 |
| `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` | 실험적 적용 권장 | KV 캐시 메모리를 약 절반으로 줄여 긴 컨텍스트 처리 시 VRAM 여유 확보. **단, AMD/ROCm(gfx1032)의 아키텍처별 지원 여부가 모델마다 다를 수 있어([Ollama GitHub Issue #13337](https://github.com/ollama/ollama/issues/13337)) 적용 후 반드시 실행 로그로 정상 동작 확인 필요** |

### 2-1. 신규 자동화와의 VRAM 경합 방지 원칙

3장/4장에서 제안하는 모의면접 봇, 커밋 훅 리뷰어 등 신규 자동화는 모두 **`wiki_agent.py`가 이미 쓰고 있는 단일 워커 큐 + `/api/ps` 폴링 락 패턴**을 공유해야 합니다. 별도 프로세스가 각자 Ollama를 호출하게 두면 여러 모델이 번갈아 로드되며 각 5~15초의 스왑 지연이 누적됩니다. 가능하면 모든 로컬 LLM 요청을 하나의 큐 매니저(기존 `wiki_agent.py`의 워커 스레드를 확장하거나, 별도의 경량 요청 브로커 프로세스)를 거치도록 통합하는 것을 권장합니다.

---

## 3. 취업 준비 특화 워크플로우 (백엔드/인프라 취준생 맞춤)

### 3-1. Open WebUI 커스텀 페르소나 추가 제안

기존 `llm_webui_config.md`에 이미 리팩토링 마스터/로직 디버거/한국어 테크라이터/이력서 리뷰어 4종이 정의되어 있습니다. 아래 2종을 추가하는 것을 제안합니다.

**🎤 모의 면접관 (DeepSeek-R1-14B 또는 Gemma4-e4b 기반)**
- System Prompt: "당신은 스타트업/대기업 백엔드 및 클라우드 인프라 채용 면접관입니다. 지원자의 이력서 내용(Java/Spring Boot/FastAPI/AWS/Terraform/MySQL/Redis 경험)을 바탕으로 심화 질문을 하나씩 던지고, 답변을 받으면 실제 면접관처럼 꼬리 질문을 이어가세요. 답변이 부정확하면 그 자리에서 정정하지 말고, 면접이 끝난 뒤 종합 피드백에서 지적하세요."
- Advanced Params: Temperature `0.4`

**📝 CS 기본기 퀴즈 출제자 (경량 모델, Phi-4 또는 Qwen3.5:9b)**
- System Prompt: "너는 백엔드 개발자 채용 대비 CS 퀴즈 출제자다. 매 요청마다 자료구조/알고리즘/네트워크/DB/운영체제/Spring 내부 동작 중 하나를 무작위로 골라 실무형 질문 1개를 낸다. 정답과 채점 기준도 함께 제시하되, 질문 먼저 보여주고 정답은 별도로 접어서 제공해라."
- Advanced Params: Temperature `0.7` (매번 다른 주제가 나오도록)

### 3-2. 위키 기반 자동 복습 시스템 (신규 자동화)

`wiki_agent.py`가 이미 `#tech`, `#career` 태그로 문서를 분류하고 있으므로, 이를 활용해 스스로 축적한 지식을 복습하는 파이프라인을 추가할 수 있습니다.

1. Obsidian Vault에서 `#career` 또는 `#tech` 태그가 붙은 문서 중 최근 N일 이내 것을 ChromaDB 메타데이터(`source`, `tags`)로 조회
2. 경량 모델(Phi-4/Qwen3.5:9b)에게 "이 문서 내용을 바탕으로 면접 예상 질문 3개를 만들어라" 요청
3. Discord Webhook으로 아침 브리핑 채널에 전송 (5-1의 스케줄러 활용)

이 흐름은 새 코드베이스를 만드는 대신 **기존 `wiki_agent.py`의 ChromaDB 조회 로직과 `send_discord_notification()` 함수를 재사용**하는 것이 유지보수 부담을 최소화합니다.

### 3-3. 이력서 STAR 초안 자동화

Discord에 프로젝트 회고나 커밋 로그를 던지면, 기존 `discord_bot.py`의 채널 모니터링 로직을 재사용해 별도 채널(`#resume-draft` 등)을 추가하고, 다음 프롬프트로 EXAONE 3.5에 STAR(Situation-Task-Action-Result) 형식 이력서 항목 초안을 생성하게 할 수 있습니다.

> "다음은 프로젝트 진행 중 남긴 메모/커밋 로그다. 이를 채용 이력서에 쓸 수 있는 STAR 기법 불릿 1~2개로 재구성해라. 정량적 성과(처리량, 응답시간, 비용 절감 등)가 텍스트에 없다면 지어내지 말고 '[수치 확인 필요]'라고 표시해라."

---

## 4. 코딩·인프라 실무 보조 / AI 네이티브 개발 파이프라인

### 4-1. IDE 연동 (Continue.dev + Aider)

2026년 기준 로컬 모델을 IDE에 직접 연동하는 두 축은 **Continue.dev**(VS Code/JetBrains 확장, 채팅+자동완성)와 **Aider**(터미널 기반 Git-aware 페어 프로그래머)입니다. 둘 다 Ollama를 그대로 백엔드로 사용할 수 있습니다. ([localaimaster](https://localaimaster.com/blog/continue-dev-ollama-setup), [localaimaster](https://localaimaster.com/blog/aider-ollama-setup))

`~/.continue/config.yaml` 예시:

```yaml
models:
  - name: Qwen3-Coder (채팅/에이전트)
    provider: ollama
    model: qwen3-coder:30b-a3b-q4_K_M
    roles: [chat, edit]
  - name: 빠른 자동완성
    provider: ollama
    model: qwen2.5-coder:1.5b   # 초경량, 저지연 우선
    roles: [autocomplete]
```

- **채팅/편집용**은 정확도가 중요하므로 `Qwen3-Coder-30B-A3B`,
- **자동완성용**은 타이핑마다 호출되어 지연이 체감되므로 별도의 초경량 모델(1.5B급)을 분리 배치하는 것이 핵심입니다. 이 두 모델을 동시에 유지하려면 `OLLAMA_MAX_LOADED_MODELS=2`가 필요하며, VRAM이 부족하면 자동완성 모델을 CPU 전용으로 강제 배치하는 것도 방법입니다.
- Aider는 `aider --model ollama/deepseek-r1:14b` 형태로 실행해 Git diff 단위 리팩토링에 활용하세요.

> AMD/ROCm은 CUDA 대비 생태계 성숙도가 낮아 설정 마찰이 더 있을 수 있습니다([codersera](https://codersera.com/blog/self-hosted-ai-coding-agent-2026/)). 이미 `HSA_OVERRIDE_GFX_VERSION`으로 우회 중이므로 큰 문제는 없을 것으로 예상되나, Continue.dev 최초 연동 시 응답 지연이 비정상적으로 길다면 ROCm 드라이버 버전을 먼저 의심하세요.

### 4-2. Git 커밋 훅 자동 문서화

`post-commit` 훅에서 `git diff HEAD~1`을 경량 모델에 전달해 변경 요약을 생성하고, 이를 `wiki_agent.py`의 `RAW_DIR`에 마크다운으로 떨어뜨리면 기존 파이프라인이 그대로 위키화합니다. 새 인프라를 만들 필요 없이 **입력 소스만 하나 추가**하는 방식입니다.

### 4-3. Terraform Plan 리뷰어

`terraform plan -no-color` 출력을 Phi-4 또는 DeepSeek-R1에 전달해 "삭제/교체(destroy/replace) 대상이 있는지, 프로덕션 변수와 다른 값이 하드코딩되어 있는지" 검토하게 하는 로컬 스크립트를 추가할 수 있습니다. 이는 AWS 실비용이 드는 `terraform apply` 전에 로컬에서 무료로 1차 검증하는 효과가 있습니다.

---

## 5. 위키 자동화 고도화: MCP로 전환

`mcp.md`에서 이미 "방안 B(Tool/MCP 직접 구현)"를 최적안으로 결론 내렸습니다. 이 판단은 2026년 기준으로도 유효하며, 오히려 **Open WebUI가 v0.6.31부터 MCP(Streamable HTTP)를 네이티브 지원**하게 되어 더 깔끔하게 구현할 수 있습니다. ([Open WebUI 공식 문서](https://docs.openwebui.com/features/extensibility/mcp/), [GitHub Discussion #12104](https://github.com/open-webui/open-webui/discussions/12104))

기존 계획(Tools/Valves 탭에 파이썬 스크립트 붙여넣기) 대신, 표준 MCP 서버로 만들어두면 Open WebUI 외의 다른 MCP 호환 클라이언트(Claude Desktop 등)에서도 동일한 위키 검색 기능을 재사용할 수 있습니다.

`fastmcp`(Python) 기반 스켈레톤 예시:

```python
from fastmcp import FastMCP
import chromadb

mcp = FastMCP("obsidian-wiki")
client = chromadb.HttpClient(host="100.116.28.108", port=8000)
collection = client.get_collection("wiki")

@mcp.tool()
def search_wiki(query: str, n_results: int = 5) -> str:
    """Obsidian 위키(ChromaDB)에서 쿼리와 유사한 문서 조각을 검색한다."""
    results = collection.query(query_texts=[query], n_results=n_results)
    return "\n\n---\n\n".join(results["documents"][0])

@mcp.tool()
def read_note(filename: str) -> str:
    """지정한 파일명의 옵시디언 노트 전문을 읽어온다."""
    path = f"D:/LLM/Obsidian/{filename}.md"
    with open(path, encoding="utf-8") as f:
        return f.read()

@mcp.tool()
def search_by_tag(tag: str) -> str:
    """YAML 태그로 문서를 필터링한다. 예: #tech, #career"""
    results = collection.get(where={"tags": {"$contains": tag}})
    return "\n".join(results["ids"])

if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=9100)
```

Open WebUI 설정: **관리자 설정 → 외부 도구(External Tools) → + 추가 → Type: MCP (Streamable HTTP) → URL: `http://127.0.0.1:9100`**

이 방식은 기존 방안 A(내장 RAG)의 강제 출처 표기 프롬프트 주입 문제(`mcp.md`, `troubleshooting.md` 7장에서 이미 지적)를 원천적으로 피하면서, `wiki_agent.py`가 관리 중인 ChromaDB를 그대로 재사용해 리소스 중복도 없습니다.

---

## 6. 반복 작업 자동화 (스케줄러)

`wiki_agent.py`의 상시 루프 방식은 실시간 감시에는 적합하지만, "매일 아침 8시 브리핑"처럼 정해진 시각에만 실행하면 되는 작업까지 상시 프로세스로 돌릴 필요는 없습니다. Windows **작업 스케줄러(Task Scheduler)**로 분리하는 것을 권장합니다.

```powershell
# 매일 08:00에 daily_briefing.py 실행 (pythonw.exe로 콘솔 창 없이)
schtasks /create /tn "AI_Daily_Briefing" /tr "C:\local_LLM\venv\Scripts\pythonw.exe C:\local_LLM\daily_briefing.py" /sc daily /st 08:00
```

제안 스케줄:

| 작업 | 주기 | 내용 |
|---|---|---|
| 아침 브리핑 | 매일 08:00 | 전날 위키에 쌓인 신규 문서 요약 + 3-2의 복습 질문 3개를 Discord로 전송 |
| 주간 취업준비 리뷰 | 매주 일요일 20:00 | 그 주 `#career` 태그 문서를 모아 회고 정리, 부족한 영역(예: 특정 CS 주제 미학습) 표시 |
| Vault 정합성 점검 | 매주 1회 | 깨진 역링크, 중복 태그, 빈 문서 등을 스캔해 리포트 |

이 작업들도 2-1의 원칙대로, 실행 시점에 `http://localhost:11434/api/ps`로 다른 모델이 VRAM에 있는지 확인 후 없을 때만 로드하는 락을 공유해야 코딩 작업 중 스케줄 작업이 끼어들어 모델 스왑을 유발하는 일을 막을 수 있습니다.

---

## 7. 실행 로드맵 (우선순위 제안)

1. **모델 정리**: `ollama list`로 실제 설치 상태 확인 → `qwen3-coder:30b-a3b-q4_K_M`, `exaone4.0:1.2b` 우선 설치, GPT-OSS-20B는 설치하지 않음
2. **환경변수 튜닝**: 2장의 `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL` 적용 후 기존 워크플로우가 여전히 정상 동작하는지 확인
3. **IDE 연동**: Continue.dev 설정으로 Spring Boot/FastAPI 개발 중 즉시 체감되는 효과 확보 (가장 ROI가 빠름)
4. **취업 준비 페르소나 2종 추가**: Open WebUI에 모의 면접관/CS 퀴즈 출제자 등록
5. **MCP 전환**: `mcp.md` 방안 B를 FastMCP로 구현, Open WebUI 네이티브 MCP 연결
6. **스케줄러 자동화**: 아침 브리핑부터 시작해 점진적으로 확장

---

## 8. 참고 출처

- [GPT-OSS-20B 하드웨어 요구사항 — IntuitionLabs](https://intuitionlabs.ai/articles/hardware-requirements-gpt-oss-20b)
- [GPT-OSS-20B VRAM 요구사항 — willitrunai](https://willitrunai.com/blog/gpt-oss-20b-vram-requirements)
- [GPT-OSS-20B CPU 오프로딩 관련 논의 — Hugging Face](https://huggingface.co/openai/gpt-oss-20b/discussions/26)
- [Gemma 4 공식 발표 — Google Blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- [Ministral 3 공식 발표 — Mistral AI](https://mistral.ai/news/mistral-3/)
- [Qwen 3.5 소형 모델 Ollama 공지 — X(ollama)](https://x.com/ollama/status/2028510184788926567)
- [EXAONE 4.0 공식 발표 — LG AI Research](https://www.lgresearch.ai/blog/view?seq=576)
- [EXAONE 4.5 공식 발표 — PRNewswire](https://www.prnewswire.com/news-releases/lg-reveals-next-gen-multimodal-ai-exaone-4-5-302736993.html)
- [DeepSeek R2 현황 — felloai](https://felloai.com/deepseek-r2/)
- [DeepSeek V3.2 현황 — InfoQ](https://www.infoq.com/news/2026/01/deepseek-v32/)
- [Qwen3-Coder-30B-A3B VRAM/용량 — willitrunai](https://willitrunai.com/models/qwen-3-coder-30b-a3b)
- [Qwen3-Coder 로컬 실행 가이드 — Unsloth](https://unsloth.ai/docs/models/tutorials/qwen3-coder-how-to-run-locally)
- [Ollama 환경변수 공식 FAQ](https://docs.ollama.com/faq)
- [Ollama Flash Attention/KV Cache 아키텍처 지원 이슈 — GitHub #13337](https://github.com/ollama/ollama/issues/13337)
- [Open WebUI MCP(Streamable HTTP) 네이티브 지원 문서](https://docs.openwebui.com/features/extensibility/mcp/)
- [Open WebUI 네이티브 MCP 통합 논의 — GitHub Discussion #12104](https://github.com/open-webui/open-webui/discussions/12104)
- [Continue.dev + Ollama 설정 가이드 — Local AI Master](https://localaimaster.com/blog/continue-dev-ollama-setup)
- [Aider + Ollama 설정 가이드 — Local AI Master](https://localaimaster.com/blog/aider-ollama-setup)
