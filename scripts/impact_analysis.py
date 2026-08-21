"""PR diff를 Bifrost 경유 LLM에 보내 영향도를 분석하고 Job Summary에 남긴다."""
import os
import subprocess
import sys

import requests

MAX_DIFF_CHARS = 12000


def get_diff(base_ref: str) -> str:
    subprocess.run(["git", "fetch", "origin", base_ref], check=True)
    result = subprocess.run(
        ["git", "diff", f"origin/{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (truncated)"
    return diff


def analyze(diff: str) -> str:
    # BIFROST_BASE_URL은 소비하는 쪽마다 기대하는 형식이 다르다. LangChain의
    # ChatOpenAI(src/agent/wiki_agent.py)는 "/v1"까지 포함한 값을 받고, 이 스크립트는
    # 아래에서 "/v1/chat/completions"를 직접 붙인다. 그래서 같은 이름의 값이 .env와
    # GitHub Secrets에서 서로 다른 형식이 되어 두 번이나 405를 냈다
    # (".../v1" + "/v1/chat/completions" = ".../v1/v1/chat/completions").
    # 어느 형식이 들어와도 동작하도록 끝의 "/v1"을 떼어 정규화한다.
    bifrost_url = os.environ["BIFROST_BASE_URL"].rstrip("/").removesuffix("/v1")
    bifrost_key = os.environ["BIFROST_API_KEY"]
    # Bifrost 모델명은 provider를 명시해야 자동 라우팅이 모호해지지 않는다
    # (bare "llama3-70b-8192"는 "could not auto resolve a provider" 오류 발생).
    # groq/llama3-70b-8192는 Groq 측에서 단종되어 groq/openai/gpt-oss-120b로 교체.
    model = os.environ.get("IMPACT_ANALYSIS_MODEL", "groq/openai/gpt-oss-120b")

    prompt = (
        "다음은 하나의 Pull Request의 전체 diff입니다. "
        "이 변경이 시스템에 미치는 영향 범위를 한국어로 간결하게 분석해주세요:\n"
        "1) 변경된 핵심 컴포넌트\n"
        "2) 잠재적 영향/리스크 (하위 호환성, 사이드 이펙트 등)\n"
        "3) 리뷰어가 특히 주의 깊게 봐야 할 부분\n\n"
        f"```diff\n{diff}\n```"
    )

    resp = requests.post(
        f"{bifrost_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {bifrost_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def write_summary(body: str) -> None:
    pr_number = os.environ.get("PR_NUMBER", "?")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    heading = f"## \U0001f50d AI 영향도 분석 (PR #{pr_number})\n\n{body}\n"
    if not summary_path:
        print(heading)
        return
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(heading)


def main() -> None:
    base_ref = os.environ.get("BASE_REF", "main")
    diff = get_diff(base_ref)
    if not diff.strip():
        print("No diff detected, skipping analysis.")
        return
    analysis = analyze(diff)
    write_summary(analysis)
    print("Impact analysis written to job summary.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Impact analysis failed: {e}", file=sys.stderr)
        sys.exit(1)
