"""PR diff를 Bifrost 경유 LLM에 보내 영향도를 분석하고 PR 코멘트로 게시한다."""
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
    bifrost_url = os.environ["BIFROST_BASE_URL"].rstrip("/")
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


def post_comment(body: str) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    token = os.environ["GITHUB_TOKEN"]

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": f"## \U0001f50d AI 영향도 분석\n\n{body}"},
        timeout=30,
    )
    resp.raise_for_status()


def main() -> None:
    base_ref = os.environ.get("BASE_REF", "main")
    diff = get_diff(base_ref)
    if not diff.strip():
        print("No diff detected, skipping analysis.")
        return
    analysis = analyze(diff)
    post_comment(analysis)
    print("Impact analysis posted.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Impact analysis failed: {e}", file=sys.stderr)
        sys.exit(1)
