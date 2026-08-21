# 🛠️ 로컬 LLM 환경 문제 해결 가이드 (Troubleshooting)

이 문서는 Open WebUI 및 로컬 모델(Ollama) 사용 중 발생하는 흔한 에러들과 해결 방법을 모아둔 트러블슈팅 가이드입니다.

---

## 1. 웹 스크래핑(Jina Reader) 사용 시 401 Unauthorized 에러

### 🔴 증상
채팅창에서 웹 검색 후 스크래핑 툴(Enhanced Web Scrape 등)이 호출될 때 아래와 같은 에러 메시지가 출력되며 답변이 중단됩니다.
> `Error scraping web page: 401 Client Error: Unauthorized for url: https://r.jina.ai/...`

### 🤔 원인
해당 에러는 대상 사이트(네이버 등)에서 차단한 것이 아니라, 중간에서 마크다운 변환을 수행하는 **Jina Reader API(`r.jina.ai`) 측에서 인증 오류를 낸 것**입니다. Jina AI 측의 무료 트래픽 제한에 걸렸거나 최근 인증 정책이 강화되어 API Key 없이 익명으로 과도한 요청을 보낼 경우 접속을 차단(401 Unauthorized)하기 때문에 발생합니다.

### 🟢 해결 방법 (Jina API Key 적용)
툴 설정(Valves)에 본인만의 Jina API Key를 발급받아 넣어주면 즉각적으로 해결됩니다.

1. **Jina Reader API Key 발급 (무료)**
   * [Jina Reader 공식 사이트(https://jina.ai/reader/)](https://jina.ai/reader/)에 접속합니다.
   * 화면 상단의 **[API]** 메뉴를 누르고 구글 계정 등으로 로그인합니다.
   * 대시보드에서 `Generate API Key`를 클릭하여 고유한 키(보통 `jina_...` 로 시작함)를 복사합니다. (무료 플랜으로도 매달 100만 토큰 이상이 제공되어 개인용으로 충분합니다.)

2. **Open WebUI 툴 설정(Valves)에 키 등록**
   * Open WebUI 하단의 **작업공간(Workspace) > 도구(Tools)** 메뉴로 이동합니다.
   * 설치해 둔 `Enhanced Web Scrape` 툴 우측의 **톱니바퀴 아이콘(설정)** 또는 **Valves** 탭을 클릭합니다.
   * 설정 창을 보면 `Global Jina Api Key` 혹은 `Jina Api Key`를 입력하는 텍스트 칸이 있습니다.
   * 방금 복사한 API Key를 해당 칸에 붙여넣고 하단의 **[저장(Save)]**을 누릅니다.

3. **테스트 및 확인**
   * 다시 채팅창으로 돌아가서 동일하게 *"2026년 7월 8일 kbo 야구 경기 결과를 알려주고 특이사항을 요약해주세요"* 라고 질문해 보세요.
   * 이번에는 401 에러 없이 정상적으로 네이버 스포츠 페이지를 읽어와 야구 경기 결과와 특이사항을 완벽하게 요약해 줄 것입니다!

---

## 2. 웹 검색 후 답변이 중국어로 나오거나 도중에 멈추는 현상 (응답 없음)

### 🔴 증상
웹 스크래핑(Tool)이 성공적으로 완료("Successfully Scraped...")된 직후, 모델이 생각(Thought)을 시작하더니 갑자기 **중국어("用户询问的是...")로 말문을 열고는 문장이 끊기며 더 이상 응답하지 않습니다.**

### 🤔 원인
이 현상은 크게 **두 가지 원인**이 결합되어 발생한 전형적인 로컬 LLM의 한계 증상입니다.
1. **모델의 태생적 언어 편향 (중국어 문제):** 현재 사용 중이신 `qwen3.5:9b` 모델은 알리바바(중국)에서 만든 모델입니다. 평소에는 한국어를 잘하지만, 외부 툴(Tool)을 사용하거나 엄청난 양의 컨텍스트(웹페이지 본문)가 갑자기 주입되면 모델이 당황하여 본능적으로 기본 언어인 중국어로 사고(Think) 과정을 출력해 버리는 고질적인 버그가 있습니다.
2. **컨텍스트 길이 초과 및 메모리 부족 (응답 끊김 문제):** 네이버 스포츠와 KBO 홈페이지의 본문 텍스트는 길이가 어마어마하게 깁니다. 3개의 사이트를 동시에 긁어와서 `qwen3.5:9b`의 머릿속(Context Window)에 한 번에 욱여넣다 보니, 모델이 기억력 한계를 초과하여 뻗어버렸거나(OOM), 대답을 출력할 빈 공간(Tokens)이 부족해져 중간에 답변을 멈춰버린 것입니다.

### 🟢 해결 방법

**방법 A. 한국어에 특화된 모델로 교체 (가장 추천)**
정보 검색 및 요약(특히 한국어 웹사이트) 작업에는 태생이 중국어인 Qwen보다는, 이전에 다운로드하신 **한국어 특화 모델 `EXAONE 3.0 7.8B`**를 사용하시는 것이 압도적으로 좋습니다. (WebUI 모델 선택창에서 엑사원으로 바꾸고 다시 검색해 보세요.)

**방법 B. 스크래핑 텍스트 양 줄이기 (과부하 방지)**
어떤 모델을 쓰든 웹페이지를 한 번에 너무 많이 읽으면 뻗어버립니다.
1. Open WebUI 설정(Settings) > **웹 검색(Web Search)** 메뉴에서 **동시 요청 수(Concurrent Requests)**를 기본값(아마 3~5)에서 **`1` 또는 `2`**로 줄이세요.
2. `Enhanced Web Scrape` 툴 설정(Valves)에서 `CLEAN_CONTENT` 옵션을 반드시 켜서 불필요한 링크나 이미지가 텍스트 용량을 차지하지 않게 만드세요.

**방법 C. 문맥 길이(Context Length) 늘려주기**
Qwen 모델을 계속 써야 한다면, 모델이 뻗지 않도록 뇌 용량을 늘려주어야 합니다.
* 채팅방 우측 상단의 제어판(🎛️) 아이콘 > **고급 파라미터(Advanced Parameters)** > **문맥 길이 (Context Length / num_ctx)** 값을 기존(아마 2048~4096)에서 **`16384`** 정도로 크게 넉넉하게 잡아주세요. (단, VRAM을 많이 먹습니다.)

---

## 3. 생각(Thinking Process)이 너무 길어지다가 답변 없이 멈추는 현상

### 🔴 증상
모델이 "Thinking Process"를 시작하더니 영어로 끝없이 자기 혼자 묻고 답하며 고민(Loop)하다가, 정작 최종 답변은 내놓지 않고 출력이 뚝 끊겨버립니다.

### 🤔 원인
이 현상은 **"최대 생성 토큰(Max Tokens) 초과"** 현상과 **"로직 무한 루프(Overthinking)"**가 결합된 결과입니다.
1. **무한 루프:** "타구를 주자가 맞으면"이라는 한국어 야구 규칙(실제로는 주자 아웃, 데드볼 선언)을 모델이 영어로 번역해서 해석하려다 보니, 주자(Runner)와 수비수(Fielder)의 개념을 혼동하며 혼자서 미궁에 빠진 것입니다.
2. **토큰 초과로 인한 강제 종료:** Open WebUI와 Ollama는 모델이 한 번에 말할 수 있는 최대 단어 수(보통 2048토큰)가 정해져 있습니다. 모델이 혼자 영어로 2분 동안 장문의 생각을 써 내려가다 보니 **허용된 말하기 할당량(Max Tokens)을 다 써버렸고**, 결국 실제 답변을 출력하기도 전에 시스템이 강제로 마이크를 꺼버린(응답 중단) 것입니다.

### 🟢 해결 방법
1. **시스템 프롬프트 제어 (가장 즉각적인 방법):**
   * 방금 문서 6장에서 세팅하신 **전역 시스템 프롬프트(Global System Prompt)**에 다음 문장을 추가하세요.
   * *"사고 과정(Thinking Process)을 텍스트로 출력하지 마라. 즉시 최종 정답만 한국어로 간결하게 말해라."* 
   * 이렇게 하면 모델이 할당량을 생각하는 데 낭비하지 않고 바로 정답을 출력합니다.
2. **최대 생성 토큰(num_predict) 늘리기:**
   * 채팅창 우측 상단 🎛️ 제어판 > **고급 파라미터**에서 **`Max Tokens (num_predict)`** 값을 `4096` 또는 `-1`(무제한)로 늘려주면 도중에 말이 끊기는 현상을 막을 수 있습니다.
3. **한국어 로직에 강한 모델 사용:**
   * Qwen3.5는 이런 미묘한 한국어 스포츠 룰에서 섀도우 복싱(Shadow Boxing)을 하는 경향이 있습니다. 앞서 추천해 드린 **EXAONE 3.0**이나, 아예 이런 깊은 고민에 특화된 **DeepSeek-R1**을 사용하시면 이런 헛발질 없이 빠르고 정확하게 정답을 도출합니다.
4. **Qwen 공식 권장 파라미터 적용 (해외 커뮤니티 검증 해결책):**
   * Qwen3.5가 불필요하게 길게 고민하는 'Overthink' 버그는 작업 목적에 맞게 파라미터를 조정하여 강제로 해결할 수 있습니다.
   * 상세한 모드별 파라미터 세팅값(일반, 코딩, 추론 등)은 `[model_tuning.md](file:///c:/local_LLM/Docs/model_tuning.md)` 문서의 **Qwen 3.5 튜닝 가이드**를 참조하여 Open WebUI 제어판에 적용해 주세요.

---

## 5. 추론(Reasoning) 모델의 언어 오역 및 규칙 환각(Hallucination) 문제

### 🔴 증상 (대화 로그 분석)
Qwen 3.5 모델을 '사고(Thinking) 모드'로 세팅하여 야구 규칙("타구를 주자가 맞으면 어떻게 되는지")에 대해 대화할 때, 다음과 같은 3가지 치명적 문제점이 발견되었습니다.
1. **오역 및 섀도우 복싱:** 모델이 속으로 생각(Thought)할 때 영어로 사고하면서, 한국어의 "공을 맞다(Be hit by)"를 "공을 치다(Hit the ball)"로 오역하여 스스로 논리적 모순에 빠졌습니다.
2. **환각 (거짓말):** 사용자가 상황을 정확히 정정해 주었음에도 불구하고, "야구 규칙상 그런 조항은 없다"며 **완전히 틀린 정보(실제로는 수비방해 아웃, 데드볼 처리됨)를 당당하게 거짓말**했습니다.
3. **검색 스크래핑 에러 (422 Error):** 웹 검색 툴이 작동했으나 `422 Client Error`로 인해 정보를 가져오지 못했습니다. 그럼에도 모델은 모른다고 하지 않고 뇌피셜로 결론을 내렸습니다.

### 🟢 해결 방법 및 설정 가이드

**문제점 1 해결: 사고 과정(Thought) 한국어 강제 설정**
* Qwen 3.5가 속으로 고민할 때 영어로 번역을 거치며 한국어의 미묘한 뉘앙스를 잃어버리는 것을 막아야 합니다.
* **설정 방법:** Open WebUI **설정 > 일반 > 시스템 프롬프트**에 다음 문구를 반드시 최상단에 추가하세요.
  > *"You are a helpful AI assistant. You MUST process your internal thoughts and logic entirely in KOREAN. 사고 과정(Thinking Process)을 영어로 번역하지 말고, 처음부터 끝까지 한국어로만 생각하고 답변해라."*

**문제점 2 해결: 용도에 맞는 '모델 분리' 원칙 준수**
* Qwen 계열 모델은 일반적인 코딩이나 텍스트 처리에는 강하지만, 한국의 로컬 스포츠 규칙이나 뉘앙스에서는 지식 부족으로 환각(거짓말)을 종종 일으킵니다.
* **설정 방법:** 정보 검색, 상식, 한국어 뉘앙스가 중요한 대화는 반드시 사전에 설정한 **`EXAONE 3.0` (한국어 특화 모델)**으로 스위칭하여 질문하셔야 합니다. 코딩할 때만 추론 모델을 사용하세요.

**문제점 3 해결: 검색 툴 차단(422) 대처 및 프롬프트 방어**
* `422 Unprocessable Entity` 에러는 검색 툴이 방문한 대상 사이트(baseball-korea.org)에서 봇(크롤러)의 접근을 차단했거나 존재하지 않는 페이지일 때 발생합니다.
* **설정 방법:** 시스템 프롬프트에 **"환각 방지(Anti-Hallucination) 룰"**을 추가해야 합니다.
  > *"웹 검색 도구(Tool)에서 에러가 발생하거나 관련 정보를 찾지 못했다면, 절대로 추측해서 지어내지 마라. '검색에 실패하여 정확한 규칙을 확인할 수 없습니다'라고 사실대로 말해라."*

---

## 6. 웹 검색(RAG) 기능 연동 시 발생하는 부작용 및 해결 (로그 분석 2차)

### 🔴 증상 (웹 검색 툴 항상 켜짐 모드)
웹 검색 기능을 항상 켜둔 상태로 대화를 진행하면, 다음과 같은 3가지 부작용이 발생합니다.
1. **무조건 검색 (리소스 낭비):** 질문의 성격과 무관하게 무조건 웹 검색을 시도하여 답변 속도가 매우 느려집니다.
2. **가짜 출처(Fake Citation) 생성:** 모델이 검색된 텍스트에서 명확한 답을 찾지 못했음에도, 툴(Tool) 양식을 흉내 내기 위해 `[id="1"][footnote]...[/footnote]` 같은 가짜 각주를 마구 지어냅니다. (기존의 '의료진 투입' 뇌피셜이 각주 형태를 빌려 계속 튀어나옵니다.)
3. **맥락 오염 (Context Contamination):** 이전 질문(야구 결과)에서 검색해 온 방대한 텍스트 데이터가 채팅방 메모리에 남아, 다음 질문(이력서 검토)과 완전히 섞여버렸습니다. 그 결과 "이력서 안에 야구 결과가 없다"는 황당한 대답을 내놓습니다.

### 🟢 해결 방법 및 설정 가이드

**해결 1: 필요한 경우에만 수동으로 웹 검색 트리거하기 (# 명령어)**
* **설정 방법:** Open WebUI **설정(Settings) > 웹 검색(Web Search)** 메뉴에서 웹 검색을 항상 켜두는(글로벌 활성화) 옵션을 끕니다. 
* **사용법:** 평소에는 꺼두고 채팅을 치다가, 진짜 최신 정보 검색이 필요할 때만 채팅창 입력란에서 **`#`** 키를 누르거나 채팅창 하단의 **[웹 검색] 버튼(+)**을 수동으로 켜서 해당 질문에만 검색이 작동하게 하세요.

**해결 2: 가짜 출처(환각) 방지용 RAG 전용 프롬프트 주입**
* **설정 방법:** 앞서 작성해 드린 전역 시스템 프롬프트의 환각 방지 섹션에 다음 문구를 추가하여 거짓 각주 생성을 막아야 합니다.
  > *"검색 결과(Context)에 명확한 답이 없다면 절대 지어내지 말고, 가짜 출처 태그(예: [id="1"])나 footnote를 임의로 생성하지 마라."*

**해결 3: 주제가 바뀔 때는 반드시 '새 채팅(New Chat)' 열기**
* 웹 검색 툴이 가져온 방대한 텍스트는 채팅방 메모리(컨텍스트)에 찌꺼기처럼 계속 쌓입니다. 야구 얘기를 하다가 이력서 첨삭으로 넘어가면 모델의 뇌가 섞여버립니다. **대화의 주제가 완전히 다를 때는 무조건 좌측 상단의 [새 채팅]을 눌러 과거의 맥락을 백지화한 후 질문하셔야 합니다.**

---

## 7. 프롬프트 주의사항 및 숨겨진 RAG 템플릿 충돌 (핑크 코끼리 & 포맷 붕괴)

### 🔴 증상 (대화 로그 3차/4차 분석)
전역 프롬프트에서 `[id="1"]` 금지어를 완전히 지웠음에도 불구하고, 모델이 계속해서 기괴한 각주나 `[id="1"]`, `[- 없음, id 태그 미존재]` 같은 내부 코드를 출력하며 환각을 일으킵니다. 심지어 사용자가 "이 [id] 태그가 무슨 뜻이냐?"라고 묻자, 모델 스스로도 "왜 들어갔는지 모르겠다"며 황당한 답변을 합니다.

### 🤔 원인 (Open WebUI의 숨겨진 RAG 템플릿)
이것은 이제 전역 시스템 프롬프트의 문제가 아닙니다. Open WebUI는 '웹 검색'이나 '문서 업로드(RAG)' 기능이 활성화되어 있을 때, 사용자가 모르게 모델의 뒷단에 **숨겨진 RAG 프롬프트(명령어)**를 강제로 주입합니다.
보통 그 숨겨진 시스템 프롬프트에는 *"답변을 할 때는 반드시 제공된 문서의 출처를 [id="1"] 형태로 표기해라"*라는 강력한 영어 지시가 들어있습니다. 
EXAONE 같은 8B 체급 소형 모델은 이 '숨겨진 강제 출처 표기 지시'와 '이력서를 첨삭하라'는 사용자의 지시 사이에서 충돌을 일으켰습니다. 그래서 이력서 피드백을 하면서도 강박적으로 가짜 출처 태그(`[id="x"]`)를 문장마다 억지로 끼워 맞추려다 포맷 붕괴(정신 분열)를 일으킨 것입니다.

### 🟢 해결 방법 (웹 검색 끄기 및 템플릿 수정)

**해결 1: 이력서 등 순수 텍스트 작업 시 웹 검색 완전히 끄기 (가장 추천)**
* 이력서 첨삭, 코드 리뷰, 번역 등 순수한 텍스트 분석을 할 때는 채팅창 하단의 **[웹 검색] 아이콘(+)이 꺼져 있는지 반드시 확인하세요.** 검색이 켜져 있는 순간, 숨겨진 출처 표기 프롬프트가 주입되어 모델의 포맷이 망가집니다.

**해결 2: Open WebUI의 RAG 템플릿 자체를 수정 (고급)**
* Open WebUI 좌측 하단 프로필 > **관리자 설정(Admin Settings) > 문서(Documents)** (또는 RAG 설정) 메뉴로 이동합니다.
* **RAG 템플릿(RAG Template)** 항목을 찾습니다. 템플릿 내용 중에 출처를 표기하라는 부분(예: `cite the sources using [id="x"] format` 혹은 그와 유사한 인용 지시문)을 찾아 **완전히 삭제**하고 저장하세요. 이렇게 하면 검색을 켜두더라도 기괴한 태그를 생성하지 않습니다.

---

## 8. 스크래핑 툴 사용 시 `example.com`을 허공에서 긁어오는 현상 (툴 환각)

### 🔴 증상 (대화 로그 5차 분석)
사용자가 "최신 정보를 찾아줘"라고 질문했을 때, 출처 목록(소스)에 뜬금없이 `https://www.example.com/...` 이라는 가짜 주소가 포함되어 있고, 해당 소스를 열어보면 404 에러나 "Example Domain"이라는 내용이 들어있습니다.

### 🤔 원인 (검색 툴과 스크래핑 툴의 혼동)
이것은 LLM이 **'검색(Search)' 명령을 받았지만, 정작 수중에는 '스크래핑(Scrape)' 툴밖에 없을 때 발생하는 전형적인 툴 환각(Tool Hallucination)**입니다.
1. 사용자가 "최신 트렌드를 찾아줘"라고 지시합니다.
2. 모델은 렌치 아이콘(🔧)에 켜져 있는 `Enhanced Web Scrape` 툴을 써야겠다고 판단합니다.
3. 하지만 이 툴은 검색 엔진이 아니라 "정확한 URL"을 입력해야만 작동하는 단순 텍스트 추출기입니다.
4. 모델은 스스로 실제 웹 URL을 찾을 능력이 없기 때문에, 임의로 가짜 예시 주소(`https://www.example.com/hr-developer-hiring-trends`)를 지어내어 툴에 집어넣어 버립니다.
5. 툴은 바보같이 그 가짜 주소에 접속했다가 에러(404 Not Found)를 반환하고, 이 뻘짓 기록이 소스 1번에 남게 된 것입니다.

### 🟢 해결 방법 (목적에 맞는 도구 사용)

* **방법 A. 검색이 목적일 때 (키워드 탐색):** 
  렌치 아이콘(🔧)에서 `Enhanced Web Scrape` 툴의 스위치를 **끄고**, 대신 채팅창의 **[웹 검색(🌐) 버튼] (Tavily 등)**을 켜셔야 합니다. 그래야 모델이 가짜 주소를 지어내지 않고 실제 검색 엔진을 통해 진짜 기사 링크를 가져옵니다.
* **방법 B. 스크래핑이 목적일 때 (특정 페이지 읽기):**
  `Enhanced Web Scrape` 툴을 켜둔 상태라면, 사용자 질문에 **반드시 정확한 실제 URL(예: `https://brunch.co.kr/...`)을 텍스트로 같이 넘겨주어야** 모델이 엉뚱한 `example.com`을 지어내지 않고 해당 주소만 예쁘게 긁어옵니다.

---

## [Wiki Agent & Bot] 최적화 및 에러 해결 로그

### 🔴 증상 1: 봇이 특정 채널의 메시지/링크에 응답하지 않음
* **원인:** 코드 단에서 `message_content` 인텐트를 켰으나, **Discord 개발자 포털**의 봇 설정 탭에서 `Message Content Intent` 토글 스위치가 비활성화되어 있어 Discord 서버에서 봇에게 메시지 텍스트를 전송해주지 않음.
* **해결:** 개발자 포털에서 Intent 토글을 켜고, 봇 코드가 텍스트를 제대로 읽어오는지 확인하기 위해 수신 로그를 출력하도록 디버깅 코드를 추가.

### 🔴 증상 2: AI 위키 작성 중 문서가 중간에 끊기고 잘리는 현상
* **원인:** 모델의 기본 `num_ctx`(입력 컨텍스트 제한)를 넘었거나, LangChain의 `max_tokens`(출력 제한) 기본값이 너무 짧아서 발생.
* **해결:** `wiki_agent.py` 실행 시 문서 길이를 계산하여 **글자수의 약 4배(최소 4096~최대 32768)로 동적 컨텍스트(max_tokens, num_ctx)를 할당**하도록 수정하여 텍스트 짤림 방지.

### 🔴 증상 3: 여러 개의 파일을 동시에 넣을 경우 AI 모델 서버 과부하 우려
* **원인:** 실시간 폴더 감시(Watchdog) 데몬이 파일이 생성될 때마다 즉시 AI 처리 함수를 호출하여, 요청이 한꺼번에 몰릴(DDoS 형태) 위험이 존재함.
* **해결:** `queue.Queue`와 백그라운드 단일 Worker 스레드를 도입. 파일이 들어오면 대기열(Queue)에 쌓아두고 **오직 한 번에 한 개의 파일만 순차적으로 처리**(Producer-Consumer 패턴)하도록 안정성 확보.

### 🟡 우려 사항: 다른 작업(DeepSeek) 중 백그라운드 위키 작업(Qwen) 난입 시 모델 스위칭 스톨(Thrashing) 발생 우려
* **원인 (예상):** Ollama는 제한된 VRAM 용량 때문에 서로 다른 모델에 대한 요청이 번갈아 오면 기존 모델을 메모리에서 내리고 새 모델을 올리는 **적재/해제 작업(약 5~15초 소요)을 매번 반복**하게 됨. 노트북으로 DeepSeek을 쓰는 도중 위키 작업이 끼어들면 작업 효율이 크게 저하될 우려가 있음.
* **해결 방안 및 구현:**
  1. **시간대 제한 적용:** 주 업무 시간(오전 8시 ~ 밤 10시) 동안에는 백그라운드 워커가 큐(Queue) 처리 작업을 멈추고 대기하도록 구현.
  2. **Ollama API 폴링 락(Lock) 추가:** 업무 시간 외(밤 10시 이후)라도, 워커 스레드가 처리 전 `http://localhost:11434/api/ps`를 확인하여 VRAM에 타 모델(DeepSeek 등)이 올라가 있다면 30분간 더 대기하도록 이중 잠금장치 구현.
  *(참고: VRAM 증설을 통한 하드웨어적 해결은 경제적 부담이 커서 제외됨)*

### 🔴 증상 4: Discord 봇 무한 루프 현상 (알림 웹훅 재수집)
* **원인:** Wiki Agent가 문서를 처리한 후 완료 알림을 디스코드 '알림' 채널에 Webhook으로 전송했는데, `discord_bot.py`가 봇 자신(`client.user`)이 보낸 메시지만 무시하도록 설정되어 있어, **웹훅(Webhook)이 보낸 알림 메시지를 일반 유저 메시지로 착각하여 다시 스크래핑**하고 저장하는 무한 루프가 발생함.
* **해결:** `discord_bot.py`의 `on_message` 핸들러에서 `if message.author.bot:` 조건을 통해 **자신뿐만 아니라 웹훅을 포함한 모든 봇의 메시지를 무시하도록 수정**하여 해결.

### 🔴 증상 5: 파이썬 데몬(pythonw.exe) 중복 실행에 따른 중복 처리
* **원인:** 콘솔 창이 없는 `pythonw.exe` 형태로 백그라운드 실행을 하다 보니, 스크립트 수정 후 코드를 재시작할 때 기존 프로세스가 죽지 않고 계속 살아있어 동일한 파일이 2~3번 중복 처리되는 문제가 발생.
* **해결:** 프로젝트 루트 디렉토리에 **`shutdown.bat`** 파일을 생성. WMI(`wmic process call terminate`) 명령어를 사용하여 구동 중인 `discord_bot.py` 및 `wiki_agent.py` 프로세스만 콕 집어서 일괄 강제 종료하도록 조치함. 수정 사항 적용 전에는 항상 이 배치 파일을 실행하여 프로세스를 깔끔히 정리.

---

## 🚀 [Wiki Agent] 기능 개선 노트

* **[개선 1] LLM을 활용한 스마트 파일명 지정:** 
  기존에는 `AI_Discord_20260709_...md` 같은 타임스탬프 파일명으로 저장되었으나, 프롬프트를 수정하여 LLM이 문서 최상단(YAML 바로 밑)에 `# [주요 키워드] 요약된 핵심 내용` 형식의 제목을 생성하게 만들었음. 파이썬 코드에서 이를 정규식으로 파싱하여 실제 옵시디언 파일명으로 저장하도록 개선됨.
* **[개선 2] 문서 최상단 원문 역링크 자동화:** 
  생성된 위키 문서 본문 최상단에 `▶ 원본 링크: [[원본 파일명]]` 형태의 역링크가 고정적으로 박히도록 프롬프트 템플릿과 파라미터 매핑(`original_file_name`) 기능을 추가.
* **[개선 3] RAG 역링크 과거 데이터 하위 호환(Backward Compatibility):**
  파일명 변경 로직이 도입됨에 따라, ChromaDB에 저장된 메타데이터의 `source` 속성이 변경됨. 기존 데이터(`Discord_...md`)와 신규 데이터(`[키워드] 제목`)를 조회할 때 옵시디언 역링크 양식(`[[AI_...]]` vs `[[...]]`)이 꼬이지 않도록 `retrieve_memory` 로직에 분기 처리를 구현하여 매끄러운 지식 연결망 유지.

### 🔴 증상 6: 긴 원문 처리 시 LLM OOM(Out of Memory) 발생
* **원인:** 로컬 모델의 컨텍스트 한계를 초과하는 긴 텍스트(4000자 이상)가 프롬프트에 통째로 주입됨.
* **해결:** `wiki_agent.py`의 `clean_data` 노드에 하이브리드(Map-Reduce) 텍스트 분할 방식 적용. 길이가 너무 긴 경우 `RecursiveCharacterTextSplitter`를 사용해 1800자 단위 청크로 나누어 개별 정제 후 병합 처리.

### 🔴 증상 7: 컴파일(작성) 중 모델의 출력 잘림 (Truncation)
* **원인:** 메모리 누수나 부하를 줄이기 위해 설정한 `max_tokens=2048` 한도에 도달하여 모델 생성이 강제로 멈춤(`finish_reason: length`).
* **해결:** 폴백(Fallback) 구조 도입. 일차적으로 2048 제한으로 시도하되 잘림이 감지되면 한도를 8192로 늘려 재시도하여 느려지더라도 끝까지 작성하도록 수정.

### 🔴 증상 8: 옵시디언에서 공백이 포함된 태그 인식 불가
* **원인:** 마크다운 문법상 프론트매터의 태그 내에 띄어쓰기(Space)가 포함되면 옵시디언이 정상 태그로 인식하지 못함.
* **해결:** 시스템 프롬프트(`prompts.py`)의 절대 규칙에 "태그 생성 시 공백 사용 금지, 필요시 언더스코어(_)나 하이픈(-)으로 대체할 것" 이라는 규정을 추가.

### 🔴 증상 9: ChromaDB upsert 시 "Non-empty lists are required..." 에러 발생
* **증상:** "원인: Non-empty lists are required for ['ids', 'metadatas', 'documents'] in upsert." 에러가 나면서 에이전트가 중단됨.
* **원인:** 문서의 길이가 분할 기준(4000자) 근처인데 내부에 코드가 많아 실제 토큰 수가 높은 경우, 모델(특히 추론형 모델)이 정제 작업(`clean_data`) 중 생각(`<think>`)을 길게 하다가 `max_tokens` 한도에 걸려 빈 문자열을 반환함. 이로 인해 최종 생성물이 텅 비게 되고, 청크(Chunk)로 쪼갤 데이터가 없어 DB 저장이 실패함.
* **해결:** `wiki_agent.py`의 단일 처리 기준을 4000자에서 **2500자**로 대폭 낮추고, `clean_data`의 `max_tokens` 제한을 상향(1536 -> 2500)하여 넉넉한 추론 공간을 확보함. 또한 DB 저장 전 `docs` 리스트가 비어있는지 체크하는 안전망(if문) 추가.

---

## 🔎 [2026-07-10] 코드 리뷰 기반 버그 수정 및 안정성 개선

전체 코드 리뷰를 2회 수행하여 발견한 문제점들을 일괄 수정. 논리 오류, 성능, 보안, 구조 문제를 포함하며 총 **5개 파일, 21건**의 수정을 적용함.

### 🔴 증상 10: 디스코드 봇의 이벤트 루프 차단 (URL 스크래핑 시 봇 멈춤)
* **원인:** `discord_bot.py`에서 URL 스크래핑에 동기(blocking) HTTP 라이브러리 `requests.get()`을 사용하고 있었음. `discord.py`는 `asyncio` 기반인데, `on_message` 핸들러 안에서 동기 호출을 하면 **이벤트 루프 전체가 최대 15초(timeout)간 멈춤**. URL이 여러 개인 메시지에서는 차단 시간이 누적됨.
* **해결:** `requests` 라이브러리를 `aiohttp`로 교체하고 `async with session.get()`으로 비동기 처리. 동일한 이유로 파일 I/O도 `aiofiles`로 전환하여 네트워크 드라이브 환경에서의 이벤트 루프 차단을 방지함.

### 🔴 증상 11: Wiki Agent 성공 알림에 카테고리가 항상 빈 문자열로 표시
* **원인:** `process_file()` 함수에서 `app.invoke(initial_state, ...)`의 **반환값을 변수에 저장하지 않았음**. LangGraph의 `invoke()`는 변경된 state를 반환하지만, 원본 `initial_state` 딕셔너리를 참조하여 알림을 보내고 있어서 카테고리가 초기값인 빈 문자열(`""`)로 전송됨.
* **해결:** `final_state = app.invoke(...)` 형태로 반환값을 수집하고, `final_state.get('category')` 사용.

### 🔴 증상 12: Archive/Error 폴더에 동일 파일명 존재 시 `shutil.move()` 에러 → 무한 재처리
* **원인:** `shutil.move()`는 Windows에서 대상 경로에 동일 파일이 이미 존재하면 `shutil.Error` 예외를 발생시킴. 특히 **에러 핸들러 안에서 error 폴더로 이동 시 또 예외가 발생하면**, 파일이 RAW에 그대로 남아 Watchdog이 다시 감지 → 무한 재처리 루프에 빠질 수 있었음.
* **해결:** `safe_move()` 유틸 함수를 만들어 대상 파일 존재 시 타임스탬프 접미사를 자동 부여. archive/error 이동 모두 이 함수를 사용하도록 통합.

### 🔴 증상 13: ChromaDB에 구버전 문서 청크가 잔존하여 검색 시 오래된 내용 반환
* **원인:** 동일 제목의 문서를 재처리할 때, 이전 버전의 청크 수(예: 5개)가 새 버전(예: 3개)보다 많으면 `chunk_0~2`만 upsert로 덮어쓰고 **이전의 `chunk_3`, `chunk_4`는 ChromaDB에 잔존**함. RAG 검색 시 오래된 내용이 컨텍스트에 포함될 수 있었음.
* **해결:** `save_wiki()` 에서 upsert 직전에 `collection.get(where={"source": base_name})` 으로 기존 청크를 조회 후 `collection.delete()`로 정리한 뒤 새로 upsert.

### 🟡 증상 14: 파일명 충돌 시 ChromaDB의 source 메타데이터 불일치
* **원인:** 파일명 충돌로 타임스탬프 접미사가 붙은 경우(`문서명_20260710.md`), `save_path`는 변경되었지만 ChromaDB에 저장되는 `base_name`은 접미사 적용 전 값을 사용하고 있었음.
* **해결:** `save_path` 확정 이후에 `base_name = os.path.basename(save_path).replace(".md", "")` 으로 재계산.

### 🟡 증상 15: `schema.md` 파일 미존재 시 모든 문서가 compile 단계에서 반복 실패
* **원인:** `compile_wiki()` 노드에서 `open(settings.SCHEMA_PATH)` 호출 시 `FileNotFoundError` 발생. 에러 핸들링이 되어 파일은 error 폴더로 이동하지만, **모든 문서가 동일한 이유로 실패**하여 error 폴더에 파일만 계속 쌓임. 근본 원인(파일 부재)은 알기 어려웠음.
* **해결:** `__main__` 블록에서 프로그램 시작 시 `schema.md` 존재 여부를 검증. 없으면 Discord 웹훅 알림을 보내고 `SystemExit(1)` 발생.

### 🟡 증상 16: URL 정규식 ReDoS(정규표현식 서비스 거부) 취약점
* **원인:** `discord_bot.py`의 URL 감지 정규식이 중첩 반복 구조(`(?:...|...)+`)를 포함하고 있어, 악의적으로 조작된 문자열에서 Python `re` 모듈의 백트래킹이 폭주할 수 있었음.
* **해결:** 정규식을 `r'https?://[^\s<>"{}|\\^` + "`" + `\[\]]+'` 로 단순화하여 백트래킹 위험을 제거.

### 🟡 증상 17: 스크래핑 결과에 악의적 HTML 태그가 포함될 수 있는 보안 문제
* **원인:** Jina Reader의 스크래핑 결과에 `<script>`, `<iframe>` 등 위험한 HTML 태그가 포함될 수 있으며, 이것이 그대로 Obsidian Vault에 저장되면 특정 Obsidian 플러그인이 이를 실행할 가능성이 있었음.
* **해결:** `sanitize_content()` 함수를 추가하여 저장 직전에 위험한 HTML 태그(`<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<style>`), `javascript:` URI, `on*` 이벤트 핸들러 속성을 정규식으로 제거.

### 🔴 증상 18: 작업은 완료되었으나 생성된 문서가 비어 있고 제목이 원본과 동일한 현상
* **원인:** 긴 문서를 처리하다가 `compile_wiki` 단계에서 토큰 제한(length)에 걸려 폴백(Fallback) 모드가 가동됨. 이 때 끊기지 않고 끝까지 작성하게 하려고 `max_tokens=8192`를 지정했으나, LLM(Ollama 등)의 Context Window 한계를 초과하는 요청이 들어가면 모델이 조용히 실패하며 **빈 문자열을 반환**함. 빈 문자열이 저장되므로 정규식으로 새 제목(태그)을 추출하지 못해 원본 파일명이 그대로 사용되고 깡통 파일이 생성됨.
* **해결:** 폴백 시 `max_tokens`를 8192에서 **4096**으로 하향 조정하여 Context Window 초과를 방지하고, 모델이 빈 문자열을 반환할 경우 `raise ValueError`를 발생시켜 조용히 넘어가지 않고 Error 폴더로 이동되도록 안전망 추가.

---

## 🚀 [2026-07-10] 코드 리뷰 기반 기능/구조 개선

### [개선 4] 분류기(classify) 정확도 향상
* `classify_document()` 노드에서 단순 문자열 전달 → `SystemMessage` + `HumanMessage` 형태로 변경. ChatML 기반 모델에서 역할 분리를 통해 분류 정확도를 높임.

### [개선 5] 분할 기준 상수 통합 (`SPLIT_THRESHOLD`)
* `discord_bot.py`에서는 4000자, `wiki_agent.py`에서는 2500자로 분할 기준이 불일치하여 사용자에게 보이는 안내 메시지와 실제 동작이 달랐음.
* `config.py`에 `SPLIT_THRESHOLD = 2500` 공통 상수를 추가하고 양쪽에서 참조하도록 통합.

### [개선 6] 웹훅 함수 코드 중복 제거
* ChromaDB 초기화 실패 알림용 `_send_startup_webhook()`과 기존 `send_discord_notification()`이 거의 동일한 로직이었음. `send_discord_notification()`을 파일 최상단으로 이동하여 하나로 통합.

### [개선 7] 워커 큐 잔여량 가시성 확보
* 작업 완료 후 `file_queue.qsize()` 값을 로그에 출력하여 대기열에 남은 파일 수를 확인할 수 있도록 추가 (`📋 대기열: N개 남음`).

### [개선 8] 로그 파일 무한 증가 방지 (로테이션)
* `logger_setup.py`에 로그 로테이션 추가. 시작 시 로그 파일이 10MB를 초과하면 이전 `.bak` 삭제 후 현재 로그를 `.bak`으로 이름 변경하여 새로 시작.
* `atexit.register(log_file.close)` 추가로 프로그램 종료 시 로그 파일 핸들을 명시적으로 닫아 마지막 로그 유실 방지.

### [개선 9] `shutdown.bat` 프로세스 종료 정확도 향상
* 기존: `%errorlevel%`로 프로세스 종료 여부를 판별했으나, PowerShell의 `Where-Object` 결과가 비어도 에러코드가 0이어서 `[WARN]` 메시지가 절대 출력되지 않았음.
* 개선: PowerShell 내부에서 프로세스 존재 여부를 직접 판별하도록 스크립트 수정. 실행 중이면 `[OK] Terminated PID: ...`, 미실행이면 `[SKIP] not running.` 으로 정확히 표시.

---

## 9. 🌐 [2026-07-15] Bifrost 게이트웨이 연동 및 통신 에러 해결 로그

### 🔴 증상 1: Ollama 서버 추가 시 `failed to execute HTTP request to provider API` 에러
* **증상:** Bifrost Web UI에서 Ollama Provider를 추가하고 `http://host.docker.internal:11434`를 입력했으나 지속적으로 연결 실패 에러가 발생하며 모델 동기화가 이루어지지 않음.
* **원인 (SSRF 방어 메커니즘):** Bifrost는 보안(SSRF 차단)을 위해 기본적으로 `192.168.x.x`, `10.x.x.x` 및 `host.docker.internal`과 같은 사설망(Private IP)으로의 아웃바운드 HTTP 요청을 강제 차단함. Docker 컨테이너 내에서 호스트의 Ollama에 접근하려면 사설망 통신이 필수인데 이를 자체적으로 막은 것임.
* **해결:** Bifrost UI의 **Ollama Provider 설정 > Network 탭**에서 **`Allow Private Network`** 옵션 스위치를 **ON**으로 활성화하여 사설망 접근 차단을 해제함.

### 🔴 증상 2: Go 언어 DNS Resolver의 `host.docker.internal` 해석 실패 버그
* **원인:** Bifrost 컨테이너 내부의 `wget` 등 리눅스 기본 C 라이브러리 통신망은 `host.docker.internal`을 정상적으로 호스트 IP(`192.168.65.254`)로 해석하여 통신에 성공하나, Bifrost 자체 구동 엔진인 **Go 언어의 내장 DNS Resolver**가 윈도우 Docker Desktop 환경에서 해당 영문 도메인을 해석하지 못하고 NXDOMAIN을 뱉는 고질적인 버그가 발견됨.
* **해결:** URL 입력란에 영문 도메인 대신 Docker가 윈도우 호스트에 부여한 실제 내부 Gateway IP 주소(`http://192.168.65.254:11434`)를 **명시적(Raw IP)으로 직접 입력**하여 Go 엔진의 DNS 번역 과정을 완벽하게 우회함.

---

## 10. 🌐 [2026-07-15] Open WebUI 도구(Tool) 및 ChromaDB 연결 에러 해결 로그

### 🔴 증상 1: ChromaDB FastEmbed 호환성 에러 (bge-m3 모델 로드 실패)
* **증상:** `ValueError: Model BAAI/bge-m3 is not supported in TextEmbedding`
* **원인:** 초기에는 빠르고 가벼운 `FastEmbed` 라이브러리를 사용하여 `bge-m3`를 로컬 임베딩하려 했으나, 해당 패키지(fastembed)가 `bge-m3` 모델을 네이티브로 지원하지 않아 로드 자체가 불가능했음.
* **해결:** FastEmbed를 과감히 버리고, 이미 PC에 설치되어 켜져있는 Ollama의 `bge-m3` 모델을 직접 호출하는 `OllamaEmbeddingFunction`으로 전면 교체하여 해결함.

### 🔴 증상 2: Open WebUI MCP Streamable HTTP 404/405 연결 에러
* **증상:** Open WebUI의 '도구 서버 관리'에 `http://...:9000/sse`를 넣었더니, 콘솔에 `POST /sse 405 Method Not Allowed` 및 `GET /sse/openapi.json 404 Not Found` 에러가 무한 발생함.
* **원인:** Open WebUI의 '도구 서버 관리(External Tools)' 메뉴는 실험적인 MCP(Model Context Protocol)가 아니라, **표준 OpenAPI(FastAPI) 규격**을 기대하는 메뉴였음. 해당 메뉴에서 SSE 기반의 FastMCP를 연결하려 하니 프로토콜 불일치로 에러가 발생함.
* **해결:** 불안정한 실험적 MCP 방식 대신, Open WebUI와 100% 네이티브로 완벽하게 호환되는 **표준 FastAPI 기반 도구 서버(`fastapi_wiki_server.py`)로 아키텍처를 전면 교체**함. (이후 URL에서 `/sse`를 빼고 베이스 URL만 입력하여 즉시 해결됨)

### 🔴 증상 3: Python 서버 실행 시 [Errno 10048] 포트 충돌
* **증상:** `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)`
* **원인:** 윈도우 환경에서 다른 파이썬 서버나 백그라운드 프로세스(또는 Docker 앱)가 이미 `8000`번 포트를 사용 중이어서, 새로 띄우려는 위키 툴 서버가 포트를 점유하지 못함.
* **해결:** 툴 서버 코드를 수정하여 포트를 충돌 확률이 적은 `9000`번으로 변경(`port=9000`)하여 즉각 우회함.

### 🔴 증상 4: FastAPI 서버 비동기 블로킹(Event Loop Blocking)으로 인한 타임아웃
* **증상:** Open WebUI에서 위키 검색 시, 간헐적으로 검색이 오래 걸리고 서버 전체가 응답하지 않거나 다른 작업이 타임아웃 됨.
* **원인:** `fastapi_wiki_server.py`의 엔드포인트가 `async def`로 선언되어 있었으나, 내부의 ChromaDB 쿼리와 Ollama 연결 모듈(`OllamaEmbeddingFunction`)은 **동기(Synchronous)**로 작동하는 코드였음. 이로 인해 검색을 수행하는 수 초 동안 FastAPI의 메인 이벤트 루프 전체가 멈춰버림.
* **해결:** 해당 엔드포인트를 `async def`에서 `def`로 변경. FastAPI는 일반 `def` 라우터를 내부 스레드 풀(Thread Pool)에서 별도로 실행하므로 메인 루프 블로킹이 완벽히 해결됨.

---

## 11. 📊 [2026-07-23] Langfuse 모니터링 연동 및 타임아웃/프리징 에러 해결 로그

### 🔴 증상 1: Langfuse 대시보드에 로그(Trace)가 표시되지 않음
* **증상:** Langfuse 환경변수를 세팅하고 `CallbackHandler`를 연동했음에도, 랭퓨즈 UI에 아무런 기록이 남지 않음.
* **원인 1 (매개변수 오류):** `CallbackHandler(session_id=...)` 형태로 사용하려 했으나, 최신 LangChain/Langfuse에서는 `session_id` 대신 `app.invoke(..., config={"run_name": ...})` 방식을 사용해야 했음.
* **원인 2 (강제 종료로 인한 Flush 실패):** 파이썬 백그라운드 워커가 돌다가 `shutdown.bat`의 `wmic process call terminate` 명령어에 의해 강제로 즉사(Kill) 당하면서, Langfuse 내부의 백그라운드 스레드가 서버로 로그를 쏘아올릴 시간(Flush)을 얻지 못하고 증발함.
* **해결:** `config={"callbacks": [lf_handler], "run_name": file_name}` 형태로 세팅을 변경하여 파일명 기준으로 트레이스를 묶고, 에이전트 재시작 시 안전한 종료 시간을 고려하도록 함.

### 🔴 증상 2: 504 Gateway Timeout 에러 (위키 컴파일 중 중단)
* **증상:** `Error code: 504 ... request timed out (default is 300 seconds)` 에러 발생. 에이전트가 5분 동안 멈춰있다가 디스코드에 실패 알림을 전송.
* **원인:** 처리하려는 네이버 블로그 글이 매우 길었는데, `compile_wiki` 단계에서 쪼개진 요약본들을 하나로 모두 합쳐 **"한 번의 거대한 프롬프트"**로 LLM(`qwen3.5:9b`)에게 밀어넣음. 긴 컨텍스트를 한 번에 처리하고 장문의 마크다운을 한 번에 생성하려다 보니 연산 시간이 300초(Bifrost 게이트웨이 타임아웃)를 초과해버림.
* **해결 (목차별 순차 생성 도입):** `compile_wiki` 아키텍처를 전면 개편. 텍스트를 한 번에 생성하지 않고, **[Part 1: 개요], [Part 2: 본문], [Part 3: 결론]의 3단계로 나누어 LLM을 연속 3번 호출**하도록 수정. 각 호출 당 생성 시간이 300초 이내로 단축되어 타임아웃을 근본적으로 방어함.

### 🔴 증상 3: 시작하자마자 CPU 및 RAM 점유율 100% 도달하며 컴퓨터 5분간 마비(Freeze)
* **증상:** 자동 재개(Auto-Resume) 기능으로 파일 분석을 시작하자마자 윈도우 OS 전체가 마비(프리징)되며 마우스조차 버벅임.
* **원인 (VRAM 충돌 및 RAM 스와핑 폭발):**
  1. 먼저 지식 검색을 위해 `bge-m3`(임베딩 모델, 약 2.2GB)가 로드됨. Ollama는 기본 5분 동안 모델을 메모리에 살려둠(`keep_alive=5m`).
  2. 1초 뒤 곧바로 요약을 위해 `qwen3.5:9b`(LLM, 약 5.5GB)를 호출함.
  3. 8GB짜리 GPU 공간에 2.2GB + 5.5GB + Context Cache가 비집고 들어가려다 보니 **VRAM 용량 초과 발생**.
  4. Ollama가 억지로 모델을 시스템 RAM으로 밀어내고(Offloading), RAM마저 꽉 차면서 윈도우 스와핑(하드디스크 사용)이 발생하여 극심한 100% 병목 및 프리징 발생.
* **해결 (VRAM 강제 퇴거 - Eviction):** 
  * `wiki_agent.py` 내부에 `unload_ollama_model(model_name)` 함수를 신설.
  * Ollama API의 숨겨진 기능인 `keep_alive=0`을 활용. 임베딩 검색이 끝나면 즉각적으로 `bge-m3`를 메모리에서 쫓아내고, 텍스트 생성이 끝나면 즉각 `qwen`을 쫓아내어 **절대로 8GB VRAM 안에서 두 모델이 겹치지 않도록 물리적(소프트웨어적)으로 교통정리를 완벽하게 구현**함.

### 🔴 증상 4: `GGML_ASSERT(buffer) failed / failed to allocate Vulkan0 buffer` OOM 크래시
* **증상:** 에이전트가 `classify_document` 단계(첫 LLM 호출)에서 500 에러와 함께 즉사. 에러 메시지에 `TerminateProcess: Access is denied.`가 포함됨.
* **원인 (좀비 `llama-server` 프로세스의 VRAM 점거):**
  * 이전 에러(504 타임아웃, 500 프로세스 종료 등)로 비정상 종료된 `llama-server.exe` 프로세스가 **좀비 상태로 살아남아 GPU VRAM을 물고 놓지 않았음**.
  * `Get-Process llama-server`로 조회한 결과, 좀비 프로세스 3개(그 중 하나는 9일 전 생성)가 발견됨. `ollama ps`에는 보이지 않는 유령 프로세스.
  * 새 요청 시 Ollama가 `qwen3.5:9b`(약 1GB 버퍼)를 할당하려 했으나, 좀비가 점거한 VRAM 때문에 공간 부족으로 `GGML_ASSERT(buffer) failed` 발생.
  * Ollama가 실패한 프로세스를 정리하려 했으나 윈도우가 권한을 거부(`TerminateProcess: Access is denied`)하여 좀비가 좀비를 낳는 연쇄 실패 발생.
* **해결 (3중 안전장치 구축):**
  1. **좀비 프로세스 사냥꾼 (`kill_zombie_llama_servers`):** `keep_alive=0` 퇴거 명령 실패 시, `taskkill /f /im llama-server.exe`로 좀비 프로세스를 강제 사살하는 폴백 로직 추가.
  2. **VRAM 비우기 확인 대기 (`wait_for_vram_clear`):** 퇴거 후 `ollama ps` API를 최대 10초간 1초 간격 폴링하여, GPU 드라이버의 물리적 메모리 해제가 완료된 것을 확인한 후에만 다음 단계로 진행하도록 수정.
  3. **자가 치유 (`process_file` Auto-Healing):** 500 에러(OOM/좀비) 감지 시 좀비 사살 → VRAM 해제 대기 → **1회 자동 재시도**. 재시도도 실패하면 Error 폴더로 이동. 디스코드에 자가 치유 가동/성공/실패 알림 전송.

---

## 12. 🔒 [2026-08-06] Self-hosted runner PowerShell 실행 정책(AllSigned) 차단 해결 로그

### 🔴 증상: `deploy`와 `impact-analysis` job이 "not digitally signed" 에러로 실패
* **증상:** self-hosted runner에서 `deploy_update.ps1`을 실행하는 `deploy` job이 실패. 에러 메시지는 다음과 같음.
  > `File C:\actions-runner\_work\_temp\<guid>.ps1 cannot be loaded. The file ... is not digitally signed. You cannot run this script on the current system.`
* **추가 증상:** 같은 러너에서 `actions/setup-python`을 쓰는 `impact-analysis`, `performance` job도 동일한 에러로 실패. 심지어 GitHub이 `-ExecutionPolicy Unrestricted`를 명시해서 실행한 압축 해제 스텝은 통과했는데, 그 직후 `setup-python`이 내부적으로 `./setup.ps1`을 dot-source 방식으로 실행하는 스텝에서 같은 에러가 재발함.

### 🤔 원인
* `Get-ExecutionPolicy -List`로 확인한 결과, 이 PC의 **`LocalMachine` 범위 정책이 `AllSigned`**로 설정되어 있었음 (Windows 기본값인 `Restricted`보다도 엄격 — 로컬에서 만든 스크립트조차 신뢰할 수 있는 게시자 서명이 없으면 전부 차단).
* GitHub Actions는 `run:` 스텝을 실행할 때마다 그 내용을 담은 **임시 `.ps1` 파일을 새로 생성**해서 `powershell -command ". '{0}'"` (dot-sourcing) 방식으로 실행함. 이 임시 파일은 실행 직전에 생성되고 끝나면 삭제되는 구조라, **미리 서명해둘 수 있는 대상이 아님**.
* `actions/setup-python`이 내부적으로 실행하는 `setup.ps1` 역시 같은 방식(dot-source)으로 호출되어 동일하게 차단됨. 즉 우리 스크립트만의 문제가 아니라 **이 러너에서 도는 모든 PowerShell 기반 CI 스텝이 구조적으로 막혀 있었음**.

### 🟢 해결 (머신 전체 정책은 건드리지 않는 방향으로 선택)
`Set-ExecutionPolicy -Scope LocalMachine`으로 머신 전체 정책을 완화하는 방법도 검토했으나(가장 간단하지만 이 PC의 다른 모든 계정·서비스에도 영향), **우리 워크플로 범위로만 한정되는 방법을 최종 채택**함.

1. **좁은 범위 우회 (`shell:` 커스텀 지정):** `pipeline.yml`의 self-hosted job들(`deploy`, `impact-analysis`, `performance`)에서 `run:` 스텝의 `shell`을 다음과 같이 지정.
   ```yaml
   shell: powershell -ExecutionPolicy Bypass -File "{0}"
   ```
   `-File`로 실행하며 `-ExecutionPolicy Bypass`를 그 프로세스 호출 하나에만 적용 — 레지스트리(`LocalMachine` 정책)는 전혀 건드리지 않음.
2. **`actions/setup-python` 제거:** 이 서드파티 액션 내부의 `setup.ps1`은 우리 워크플로의 `shell:` 설정이 미치지 않는 범위라 위 방법으로 고칠 수 없음. 대신 이 러너 PC에 이미 있는 `C:\local_LLM\venv\Scripts\python.exe`(필요 패키지 `requests` 기설치됨)를 절대경로로 직접 호출하도록 변경해서, 애초에 `setup-python`을 쓰지 않도록 우회.
3. **`performance` job은 `actions/checkout`도 제거:** 벤치마크가 측정하는 건 PR의 코드가 아니라 지금 떠 있는 Bifrost 게이트웨이의 실제 응답 속도라 PR diff와 무관함. `C:\local_LLM`에 있는(항상 최신 main인) 스크립트를 checkout 없이 바로 실행하도록 단순화.

**참고:** 코드 서명(Authenticode)으로 해결하는 방법도 검토했으나, 차단되는 대상이 우리가 만든 스크립트가 아니라 GitHub이 그때그때 즉석 생성하는 임시 래퍼 파일이라 애초에 서명이 불가능한 구조임을 확인하고 제외함.

---

## 13. 🌐 [2026-08-06] `impact_analysis.py` — 인코딩 에러 및 Bifrost 모델 라우팅 에러 해결 로그

실행 정책 문제(12번)를 해결한 뒤에도 `impact-analysis` job이 3번 더 다른 이유로 실패해서, 하나씩 원인을 좁혀나간 기록.

### 🔴 증상 1: `UnicodeDecodeError` → `Impact analysis failed: object of type 'NoneType' has no len()`
* **원인:** `subprocess.run(["git", "diff", ...], capture_output=True, text=True)`에서 `encoding`을 지정하지 않으면 Windows에서는 OS 로케일(이 러너는 한국어 Windows라 `cp949`)로 출력을 디코딩함. 코드베이스 곳곳의 한글 주석/문자열이 포함된 diff는 UTF-8인데 `cp949`로는 디코딩이 안 되어 `subprocess`의 백그라운드 리더 스레드 안에서 `UnicodeDecodeError`가 발생. 이 예외가 메인 스레드까지 정상 전파되지 않고 `result.stdout`이 `None`으로 남아, 그다음 `len(diff)` 호출에서 엉뚱한 `NoneType` 에러로 나타남 (진짜 원인은 로그에 묻혀 있었음).
* **해결:** `subprocess.run(..., encoding="utf-8", errors="replace")`로 인코딩을 명시.

### 🔴 증상 2: `405 Client Error: Method Not Allowed for url: .../v1/chat/completions`
* **원인:** 로컬(`127.0.0.1:8080`)에서 같은 경로로 직접 테스트하니 정상(POST 시 400)이었음 → 코드나 Bifrost 자체 문제가 아니라 **`BIFROST_BASE_URL` 리포지토리 시크릿 값이 실제 게이트웨이 주소가 아닌 다른 값**으로 설정되어 있었던 것으로 확인.
* **해결:** self-hosted runner가 Bifrost와 같은 PC에 있으므로 Tailscale IP 등을 거칠 필요 없이 시크릿 값을 `http://127.0.0.1:8080`으로 수정.

### 🔴 증상 3: `400 Client Error: Bad Request` → `"could not auto resolve a provider for the request"`
* **원인:** Bifrost에 모델명을 bare로(`llama3-70b-8192`) 보내면 여러 provider에 동일 이름이 등록되어 있을 경우 자동 라우팅이 모호해져 거부됨. `groq/llama3-70b-8192`처럼 **provider를 접두사로 명시**해야 함.
* **추가 발견:** provider를 명시해도 `model_decommissioned` 에러 발생 — Groq가 `llama3-70b-8192`를 이미 단종시킴.
* **해결:** `scripts/impact_analysis.py`의 기본 모델을 현재 Groq에서 서빙 중인 `groq/openai/gpt-oss-120b`로 교체. (참고: Ollama 로컬 모델은 provider가 하나뿐이라 `qwen3.5:9b`처럼 bare 이름으로도 정상 라우팅됨 — `benchmark_bifrost.py`는 수정 불필요.)

### 🔴 증상 4: `403 Forbidden` → `"Resource not accessible by integration"` (PR 코멘트 게시)
* **원인:** public 레포에서 `pull_request` 이벤트로 트리거되는 워크플로는 GitHub이 보안상 `GITHUB_TOKEN`을 강제로 제한함. 워크플로 YAML의 `permissions: issues: write`나 리포지토리 차원의 "Workflow permissions: Read and write" 설정을 모두 켜도, self-hosted runner + `pull_request` 조합에서는 상한이 올라가지 않고 계속 거부됨.
* **해결 (기능 자체를 재설계):** `GITHUB_TOKEN` 대신 별도 PAT를 쓰는 우회도 가능하지만, 채택하지 않음. 대신 **PR 코멘트 게시를 포기하고 GitHub Actions의 Job Summary(`$GITHUB_STEP_SUMMARY`)에 결과를 남기는 방식으로 전환** — 추가 권한이나 시크릿이 전혀 필요 없고, Actions 실행 화면에서 바로 확인 가능함. `post_comment()`를 제거하고 `write_summary()`로 교체, 워크플로에서 `permissions:`와 `GITHUB_TOKEN` env를 모두 제거.

### 🔴 증상 5 (사전 발견, 사후 검토로 예방): git "detected dubious ownership in repository"
* **증상:** 아직 실제로 발생하진 않았으나, `deploy` job이 원인 불명으로 조기 종료된 이전 실패 사례를 재검토하던 중 발견.
* **원인:** `deploy_update.ps1`은 `C:\local_LLM`(대화형 사용자 소유)에서 직접 git 명령을 실행하는데, 러너 서비스 계정(`NETWORK SERVICE`)에는 `.gitconfig` 자체가 없어(확인 완료: `C:\Windows\ServiceProfiles\NetworkService\.gitconfig` 없음) 이 디렉토리에 대한 `safe.directory` 신뢰 등록이 전혀 안 되어 있었음. Git은 소유자가 다른 저장소에서 명령을 실행하면 기본적으로 "dubious ownership" 에러로 거부함.
* **해결:** `deploy_update.ps1` 최상단에서 매 실행마다 `git config --global --add safe.directory $RepoPath`를 멱등하게 실행하도록 추가. 같은 검토 과정에서 `git fetch` 실패 시 `$LASTEXITCODE`를 확인하지 않고 그대로 진행하던 부분도 함께 발견해, `git merge --ff-only`와 동일한 패턴의 실패 처리(디스코드 알림 + 중단)를 추가함.

### 🔴 증상 6: `deploy` job이 PowerShell 파싱 에러로 실패 (`main` 최초 실전 배포 시도)
* **증상:** `The string is missing the terminator: "."`, `Missing closing '}' in statement block` — `deploy_update.ps1`의 한글 문자열이 깨진 채로 파서 에러 발생 (`??諛고룷 ?ㅽ뙣 -> 濡ㅻ갚 ?꾨즺...` 처럼 로그에 완전히 깨진 텍스트로 출력됨).
* **원인:** `deploy_update.ps1` 파일에 **UTF-8 BOM이 없었음**. self-hosted 러너가 `run:` 스텝을 실행하는 `powershell.exe`는 **Windows PowerShell 5.1**(pwsh 7이 아님)인데, 이 버전은 BOM 없는 `.ps1` 파일을 UTF-8이 아니라 시스템 코드페이지(한국어 Windows라 cp949)로 읽는다. 그 결과 파일 안의 한글(주석, 디스코드 알림 문자열)이 깨지면서 문자열 안에 포함된 백틱/따옴표까지 오염되어, 파서가 문자열/블록의 끝을 못 찾고 실패함.
* **해결:** 파일 맨 앞에 UTF-8 BOM(`EF BB BF`)을 추가. `[System.Management.Automation.Language.Parser]::ParseFile()`로 실행 없이 문법만 파싱해 로컬에서 먼저 검증한 뒤 push. 저장소 내 다른 `.ps1` 파일이 있는지도 함께 확인(없음 — 현재는 `deploy_update.ps1`이 유일).

### 🔴 증상 7: BOM 수정 후에도 `deploy`가 여전히 "unsafe repository"로 실패
* **증상:** `fatal: unsafe repository ('C:/local_LLM' is owned by someone else)`가 `git status`/`git rev-parse`/`git tag`/`git fetch`마다 반복 출력됨. 증상 5에서 추가했던 `git config --global --add safe.directory $RepoPath`가 실행은 됐지만 **효과가 없었음**.
* **원인:** 러너 서비스 계정(`NETWORK SERVICE`)에 정상적인 `HOME`이 없어서, `git config --global`이 전역 설정 파일을 어디에 써야 할지 못 찾고 조용히 무효화된 것으로 추정됨(에러 없이 그냥 반영이 안 됨). `git config --system`으로 바꾸는 것도 검토했으나, `icacls`로 확인한 결과 `C:\Program Files\Git\etc`가 `BUILTIN\Users`에 읽기 전용이라 애초에 쓰기 권한이 없음을 확인.
* **해결:** 스크립트 시작 시 `$env:HOME`을 이 서비스 계정도 항상 쓰기 가능한 `$env:TEMP`로 명시적으로 재지정한 뒤 `git config --global --add safe.directory "*"` 실행. `actions/checkout`이 매 실행마다 `HOME`을 임시 override하는 것과 동일한 패턴. 격리된 테스트(임시 HOME 디렉토리로 실제 실행)로 `.gitconfig`에 정상 반영되는 것까지 확인 후 push.

### 🔴 증상 8: Discord 실패 알림이 깨진 텍스트로 도착
* **증상:** `?? ?? ??: origin/main fetch? ?????? (???? ??? ? ??).` 처럼 완전히 깨진 메시지가 Discord에 옴.
* **원인:** BOM 수정은 `.ps1` **파일을 읽는** 문제만 해결했을 뿐, `Invoke-RestMethod -Body $koreanString`가 HTTP 요청 본문을 **보낼 때** 인코딩하는 것은 별개 문제. Windows PowerShell 5.1은 문자열 `-Body`를 시스템 코드페이지(cp949)로 인코딩해서 전송해 한글이 깨짐.
* **해결:** `[System.Text.Encoding]::UTF8.GetBytes($body)`로 명시적으로 UTF-8 바이트로 변환한 뒤 그 바이트 배열을 `-Body`로 전달.

### 🟢 교훈
* GitHub Secrets는 값을 조회할 수 없으므로, 연동 실패 시 **같은 요청을 로컬에서 직접 재현**(`curl -X POST http://127.0.0.1:8080/...`)해서 코드/설정 중 어느 쪽 문제인지 빠르게 좁히는 것이 효율적이었음.
* 외부 API 모델명은 공급사가 예고 없이 단종시킬 수 있으므로, 코드에 하드코딩된 기본값도 정기적으로 점검이 필요함.
* self-hosted runner + `pull_request` 조합에서 `GITHUB_TOKEN` 쓰기 권한은 리포지토리 설정으로 못 푸는 플랫폼 차원의 제약일 수 있음 — 안 되면 권한을 더 파는 대신 **애초에 그 권한이 필요 없는 방식(Job Summary 등)으로 설계를 바꾸는 것**이 더 빠른 해결책이었음.
* 매번 실행 후 에러를 하나씩 고치는 대신, **관련 파일 전체를 처음부터 끝까지 정독하며 잠재적 문제를 한 번에 찾아 고치는 방식**으로 전환한 뒤 증상 5(safe.directory)를 실제 실패가 나기 전에 미리 발견함.
* 한글이 포함된 `.ps1` 파일은 **반드시 UTF-8 BOM으로 저장**해야 Windows PowerShell 5.1에서 안전하게 파싱됨 — 텍스트 에디터/도구가 기본적으로 BOM 없는 UTF-8을 쓰는 경우가 많아 놓치기 쉬운 함정.
* 서비스 계정(NETWORK SERVICE 등)에서 도는 자동화 스크립트는 **`HOME`이 정상적으로 설정되어 있다고 가정하면 안 됨** — `git config --global`처럼 HOME에 의존하는 명령은 실행 성공(exit code 0)해도 실제로는 조용히 무효화될 수 있으므로, 실제로 반영됐는지 격리 테스트로 검증하는 습관이 필요함.
* "파일을 올바르게 읽는 것"과 "출력을 올바르게 내보내는 것"은 인코딩 관점에서 별개의 문제 — 하나를 고쳤다고 관련된 다른 인코딩 문제까지 자동으로 해결되는 것은 아님.

### 🔴 증상 9: 증상 6~7 수정 후에도 매번 "Working tree is dirty"로 실패 (변경사항 없음에도 반복)
* **증상:** 이전 수정들을 반영한 뒤 재시도해도, 실제로 커밋되지 않은 변경사항이 전혀 없는데도 매번 dirty로 판정되어 배포가 중단됨.
* **원인:** 증상 7에서 추가한 `$env:HOME = $env:TEMP` 자체가 새로운 부작용을 냄. 대화형 사용자 계정(`%USERPROFILE%`)의 실제 전역 git 설정에는 `.claude/`를 안 보이게 하는 개인용 `core.excludesFile` 규칙이 있는데, 이건 **프로젝트의 `.gitignore`가 아니라 그 사용자 계정에만 있는 개인 설정**이었음. `HOME`을 `$env:TEMP`로 바꾸면 이 개인 설정을 전혀 못 읽어오므로, 프로젝트 자체에는 안 걸러지는 `.claude/`가 `git status --porcelain`에서 매번 `?? .claude/`로 잡혀 dirty 판정이 영구적으로 발생함. 격리 테스트(`HOME`을 리다이렉트한 상태에서 직접 `git status --porcelain` 실행)로 재현·확정함.

### 🟢 [2026-08-10] 결정: `deploy` job 완전 제거
증상 5~9를 거치며 `deploy`에서만 반복적으로 문제가 발생했음(safe.directory, HOME, 인코딩, 그리고 증상 9의 오탐까지). 근본적으로 재검토한 결과, 이 프로젝트는 **개발 디렉토리와 서비스가 실행되는 디렉토리가 애초에 동일(`C:\local_LLM`)**해서 "배포 대상"이라는 개념 자체가 실제로는 존재하지 않고, GitHub push는 버전 관리/아카이브 목적이 큼. `deploy` job과 `scripts/deploy_update.ps1`을 제거하고, `main`이 바뀌면 수동으로 `git pull` + `restart.bat`을 실행하는 방식으로 되돌림. `secret-scan`/`lint`/`codeql`/`impact-analysis`는 이 문제와 무관하게 안정적으로 동작했음.

---

## 14. 🌐 [2026-08-21] Bifrost 로컬/원격 동시 접속 불가 — Windows 예약 포트(Hyper-V) 문제

### 🔴 증상: 컨테이너는 `healthy`인데 로컬(`127.0.0.1:8080`)·원격(Tailscale) 양쪽 모두 연결 실패
* **관찰:** `docker ps`는 `Up (healthy)`, 컨테이너 로그도 `successfully started bifrost, serving UI on http://0.0.0.0:8080`으로 완전히 정상. 그런데 양쪽 주소 모두 연결 거부.
* **결정적 단서 — 요청한 바인딩과 실제 바인딩의 불일치:**
  * `HostConfig.PortBindings` = `127.0.0.1:8080` + `<Tailscale IP>:8080` (설정은 정상)
  * `NetworkSettings.Ports` = `{"8080/tcp":[]}` ← **실제로는 하나도 붙지 않음**
  * `docker port bifrost`는 출력 없음, `netstat`에도 8080 없음.
  * `docker ps`의 PORTS에 찍힌 `127.0.0.1:32768->8080/tcp`는 실제와 무관한 잔여 표시값이었음.
* **오진했던 가설:** 직전 커밋(루프백+Tailscale IP 이중 바인딩)을 의심해, 부팅 시 Tailscale 인터페이스가 늦게 올라와 특정 IP 바인딩이 실패하는 경쟁 조건으로 추정했음. 같은 시각 재시작된 open-webui가 정상인 것도 "인터페이스를 지정하지 않아서"로 해석했으나 **둘 다 틀렸음**.
* **실제 원인:** 컨테이너를 재생성하자 비로소 에러 원문이 드러남 — `bind: An attempt was made to access a socket in a way forbidden by its access permissions`(WSAEACCES). **`127.0.0.1:8080`조차 실패**했으므로 Tailscale과 무관.
  * `netsh interface ipv4 show excludedportrange protocol=tcp` → **`8037-8136` 구간이 예약되어 8080이 그 안에 포함**. Hyper-V/WinNAT가 선점한 것으로, 예약된 포트는 어떤 프로세스도 바인딩할 수 없음(점유 프로세스는 없고 예약만 걸린 상태).
  * `netsh int ipv4 show dynamicport tcp` → **동적 포트 범위가 `1024~15000`** (Windows 기본값은 49152~). 이 비정상 설정 탓에 Hyper-V가 부팅할 때마다 해당 범위 안에서 임의 블록을 예약해 가고, 8080이 그 사정권에 들어 있었음.
  * open-webui가 멀쩡했던 이유는 인터페이스 지정 여부가 아니라 **3000번이 예약 범위 밖**이었기 때문.
* **해결:** 호스트 포트를 **18080**으로 이전(컨테이너 내부 포트는 Bifrost가 서빙하는 8080 그대로 유지). 18080은 동적 포트 범위와 예약 블록 밖이라 재부팅해도 선점되지 않음. `.env`의 `BIFROST_BASE_URL`, GitHub Secrets의 동명 시크릿, README 아키텍처 다이어그램도 함께 갱신.
* **대안(미채택):** `netsh int ipv4 set dynamicport tcp start=49152 num=16384`로 동적 포트 범위를 기본값으로 되돌리고 8080을 영구 예약(`add excludedportrange ... store=persistent`)하는 방법. 관리자 권한과 재부팅이 필요해 이번에는 포트 이전을 택했으나, **비정상 동적 포트 범위 자체는 8080 외 다른 서비스 포트도 언제든 삼킬 수 있어 근본 원인으로 남아 있음.**

### 🟢 [2026-08-21] 결정: `0.0.0.0` 바인딩 + 방화벽 제한 안으로 바꾸지 않음
* **검토 배경:** 특정 IP 바인딩이 인터페이스 상태에 의존한다고 판단해, `0.0.0.0:18080`으로 단순화하고 접근 제한은 Windows 방화벽에 맡기는 안을 검토했음.
* **폐기 사유 1:** 애초에 인터페이스 타이밍은 원인이 아니었으므로(위 참조) 이 안의 이점이 사라짐.
* **폐기 사유 2:** 방화벽 규칙을 조회해보니 `Docker Desktop Backend` 규칙이 Private/Public 프로필에서 **TCP/UDP 전 포트(`LocalPort: Any`) 인바운드를 허용**하고 있었음. 즉 `0.0.0.0` 바인딩은 Wi-Fi 대역에 그대로 노출되며, Windows 기본 차단에 기댈 수 없음.
* **폐기 사유 3:** Windows 방화벽은 **Block 규칙이 Allow보다 우선**하고 "~를 제외하고 차단"이라는 문법이 없음. "Tailscale만 허용"을 표현하려면 RFC1918 사설 대역을 일일이 Block으로 나열해야 해서 규칙이 늘고 깨지기 쉬움.
* **결론:** 현행 이중 바인딩(`127.0.0.1` + `${BIFROST_BIND_IP}`) 유지. 특정 IP 바인딩은 **Wi-Fi 인터페이스에 소켓 자체를 열지 않으므로** 방화벽 설정과 무관하게 안전함. 기존 `Tailscale-In` 규칙(`LocalIP: <Tailscale IP>/32`, `Protocol: Any`)이 포트 무관 허용이라 18080도 추가 방화벽 작업 없이 커버됨(원격 200 OK로 확인).

### 🟢 교훈
* **Docker 헬스체크는 컨테이너 내부에서 실행되므로 호스트 포트 퍼블리싱 실패를 원리적으로 감지하지 못함.** `healthy`인데 접속 불가가 실제로 성립함. 감시는 ①컨테이너 실행 여부 ②`NetworkSettings.Ports`가 비어있지 않은지 ③호스트에서의 HTTP 응답, **3계층으로 나눠야** 하며 ②를 따로 보면 이 장애 유형을 즉시 특정할 수 있음.
* `docker ps`의 PORTS 컬럼을 신뢰하지 말 것. 실제 적용 여부는 `docker inspect`의 `NetworkSettings.Ports`와 `netstat`로 교차 확인해야 함.
* **`restart: unless-stopped`로 자동 재시작된 컨테이너는 바인딩 실패 에러를 삼킨다.** 컨테이너를 재생성(`docker rm -f` → `up -d`)해야 에러 원문이 드러남 — 이번 진단의 전환점이었음. 상태만 보고 원인을 추정하기 전에 **재현부터** 시킬 것.
* Windows에서 "포트를 쓰는 프로세스가 없는데 바인딩이 거부된다"면 점유(`netstat`)가 아니라 **예약 범위(`excludedportrange`)**를 먼저 확인할 것.
* 예약 블록 위치는 재부팅마다 달라지므로 **"어제는 되던 게 오늘 안 되는" 간헐적 장애**로 나타남. 서비스 포트는 동적 포트 범위 밖(이 기기 기준 15000 초과)에 두는 것이 안전함.


