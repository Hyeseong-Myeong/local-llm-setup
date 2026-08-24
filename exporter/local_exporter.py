#!/usr/bin/env python3
"""개발 PC 상태 exporter — Docs/plg_monitoring_design.md 5-1, 12장 구축 순서 4번.

시작 스크립트(ai-server-start.bat)와 같은 방식(pythonw)으로 상주 실행한다.
Prometheus 는 이 exporter 를 직접 긁지 않는다 — 같은 머신의 Alloy 만 127.0.0.1
에서 긁어 NAS 로 remote-write 한다(6-1). 그래서 인바운드 포트를 열지 않는다.

읽기 전용 조회만 쓴다 — Ollama/Bifrost API, config.db(mode=ro), psutil, 로그
파일 크기. 상태를 바꾸는 호출은 하지 않는다(5-3 원칙 2).

수집은 백그라운드 스레드가 30초 주기로 수행하고 결과를 캐시한다. 스크랩 요청은
캐시를 그대로 낸다(부하 관리) — wiki_embedding_up 은 실제 GPU 호출이라 5분
주기로 따로 돈다.
"""
import glob
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen

import psutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(REPO_ROOT, "src"))

from chroma_client import get_chroma_client  # noqa: E402
from config import settings  # noqa: E402
from embedding_function import get_embedding_function  # noqa: E402

BIND_HOST = "127.0.0.1"  # 루프백 전용 — 6-1. 같은 머신의 Alloy 만 긁는다.
BIND_PORT = 13092

COLLECTION_INTERVAL_SECONDS = 30
EMBEDDING_CHECK_EVERY_N_TICKS = 10  # 30s * 10 = 5분 — GPU 를 건드리는 호출이라 따로 뗀다.

WIKI_COLLECTION_NAME = "my_wiki_db"
TOOL_SERVER_URL = "http://127.0.0.1:9000/docs"

BIFROST_DB_PATH = os.path.join(REPO_ROOT, "bifrost", "data", "config.db")

# start 스크립트가 pythonw 로 띄우는 세 에이전트. 정상값은 프로세스당 2
# (venv 런처 + 실제 인터프리터 — Windows venv 는 exec 치환 없이 자식 프로세스를 띄운다).
AGENT_SCRIPTS = {
    "wiki_agent": "wiki_agent.py",
    "discord_bot": "discord_bot.py",
    "fastapi_wiki_server": "fastapi_wiki_server.py",
}

LOG_FILES = {
    "wiki_agent": "wiki_agent.log",
    "discord_bot": "discord_bot.log",
    "fastapi_wiki_server": "fastapi_wiki_server.log",
}

# (disk_usage 에 넘길 경로, 라벨). 라벨에서 트레일링 백슬래시를 빼 이스케이프 문제를 피한다.
HOST_DISK_MOUNTS = [("C:\\", "C:")]


class Metrics:
    """Prometheus 텍스트 포맷 라인을 모은다."""

    def __init__(self):
        self.lines = []

    def gauge(self, metric_name, value, **labels):
        # 인자명이 'name' 이면 라벨로 name= 을 넘기는 호출과 충돌한다(agent_process_count{name=...}).
        self._line(metric_name, value, labels)

    def _line(self, name, value, labels):
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            self.lines.append(f"{name}{{{label_str}}} {value}")
        else:
            self.lines.append(f"{name} {value}")

    def render(self):
        return "\n".join(self.lines) + "\n"


def collect_ollama_metrics(m: Metrics):
    """Ollama 상태 (5-1). `ollama_model_gpu_ratio` 가 이 exporter 의 핵심 지표."""
    base = settings.OLLAMA_BASE_URL.rstrip("/")
    try:
        with urlopen(f"{base}/api/tags", timeout=5) as resp:
            up = 1 if resp.status == 200 else 0
    except (URLError, OSError, ValueError):
        up = 0
    m.gauge("ollama_up", up)
    if not up:
        m.gauge("ollama_scrape_error", 1, target="ollama")
        return

    try:
        with urlopen(f"{base}/api/ps", timeout=5) as resp:
            data = json.loads(resp.read())
    except (URLError, OSError, ValueError):
        m.gauge("ollama_scrape_error", 1, target="ollama")
        return
    m.gauge("ollama_scrape_error", 0, target="ollama")

    models = data.get("models", [])
    m.gauge("ollama_loaded_models_count", len(models))
    for model in models:
        name = model.get("name", "unknown")
        size = model.get("size", 0)
        size_vram = model.get("size_vram", 0)
        ratio = round(size_vram / size, 4) if size else 0
        m.gauge("ollama_model_loaded", 1, model=name)
        m.gauge("ollama_model_size_bytes", size, model=name)
        m.gauge("ollama_model_vram_bytes", size_vram, model=name)
        m.gauge("ollama_model_gpu_ratio", ratio, model=name)
        m.gauge("ollama_model_context_length", model.get("context_length", 0), model=name)

    runner_count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == "llama-server.exe":
                runner_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # 정상치는 "지금 적재된 모델 수" — 모델 하나당 러너 프로세스 하나다.
    m.gauge("ollama_orphan_runners", runner_count - len(models))


def collect_bifrost_metrics(m: Metrics):
    """Bifrost 게이트웨이 상태 (5-1). `/metrics` 스크랩(6-3)과는 별개 — 이건 config.db 기반."""
    base = settings.BIFROST_BASE_URL.rstrip("/").removesuffix("/v1")
    try:
        with urlopen(f"{base}/api/version", timeout=5) as resp:
            up = 1 if resp.status == 200 else 0
    except (URLError, OSError, ValueError):
        up = 0
    m.gauge("bifrost_up", up)

    try:
        conn = sqlite3.connect(f"file:{BIFROST_DB_PATH}?mode=ro", uri=True, timeout=5)
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, network_config_json FROM config_providers")
            providers = cur.fetchall()

            for _pid, name, net_json in providers:
                if not net_json:
                    continue
                try:
                    cfg = json.loads(net_json)
                except json.JSONDecodeError:
                    continue
                timeout_s = cfg.get("default_request_timeout_in_seconds")
                if timeout_s is not None:
                    m.gauge("bifrost_request_timeout_seconds", timeout_s, provider=name)

            cur.execute("SELECT provider_id, models_json FROM config_keys WHERE enabled = 1")
            models_count_by_provider_id = {}
            for provider_id, models_json in cur.fetchall():
                n = len(json.loads(models_json)) if models_json else 0
                models_count_by_provider_id[provider_id] = (
                    models_count_by_provider_id.get(provider_id, 0) + n
                )

            for pid, name, _net_json in providers:
                count = models_count_by_provider_id.get(pid, 0)
                m.gauge("bifrost_allowed_models", count, provider=name)
                m.gauge("bifrost_provider_configured", 1 if count > 0 else 0, provider=name)
            m.gauge("bifrost_scrape_error", 0, target="config_db")
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        m.gauge("bifrost_scrape_error", 1, target="config_db")


def _call_with_timeout(fn, timeout):
    """fn() 을 별도 스레드에서 돌리고 timeout 초 안에 안 끝나면 (None, True) 를 반환한다.

    chromadb HttpClient·OpenAIEmbeddingFunction 은 자체 타임아웃이 없다. 실측 사고:
    수집 도중 chromadb 컨테이너가 재시작되자 count() 호출이 응답 없이 영원히
    걸렸고, 백그라운드 수집이 단일 스레드라 그 뒤로 모든 지표가 24시간+ 정지된
    채로 나갔다(캐시가 남아 있어 "정상처럼 보이는 죽은 데이터"였다 — 최악의 형태).
    스레드는 강제 종료가 안 되므로 타임아웃 나면 그 스레드는 새고, 다음 틱이
    새 스레드로 다시 시도한다 — 매 수집 주기(30초)마다 하나씩이라 감당 가능한
    수준이고, 최소한 다른 지표들은 계속 갱신된다.
    """
    result = {}

    def target():
        try:
            result["value"] = fn()
        except Exception as exc:
            result["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, True
    if "error" in result:
        raise result["error"]
    return result.get("value"), False


def collect_wiki_metrics(m: Metrics):
    """위키 파이프라인 상태 (5-1) — wiki_embedding_up 은 별도 5분 주기(collect_wiki_embedding_metrics)."""
    try:
        client = get_chroma_client()
        collection = client.get_collection(name=WIKI_COLLECTION_NAME)
        count, timed_out = _call_with_timeout(collection.count, 10)
        if timed_out:
            m.gauge("wiki_scrape_error", 1, target="chroma")
        else:
            m.gauge("wiki_collection_documents", count)
            m.gauge("wiki_scrape_error", 0, target="chroma")
    except Exception:
        # chromadb 예외 계층이 httpx/grpc 등으로 다양해 구체 타입으로 좁히기 어렵다.
        m.gauge("wiki_scrape_error", 1, target="chroma")

    try:
        with urlopen(TOOL_SERVER_URL, timeout=5) as resp:
            up = 1 if resp.status == 200 else 0
    except (URLError, OSError, ValueError):
        up = 0
    m.gauge("wiki_tool_server_up", up)


def collect_wiki_embedding_metrics(m: Metrics):
    """실제 임베딩 1회 호출 — GPU 를 건드리므로 5분 주기로만 돈다(부하 관리)."""
    try:
        ef = get_embedding_function()
        vectors, timed_out = _call_with_timeout(lambda: ef(["ping"]), 15)
        up = 1 if (not timed_out and vectors) else 0
    except Exception:
        # OpenAIEmbeddingFunction 호출 경로도 네트워크/HTTP 예외가 다양하다.
        up = 0
    m.gauge("wiki_embedding_up", up)


def collect_process_metrics(m: Metrics):
    """에이전트 프로세스 수 + 앱 로그 크기 (5-1)."""
    counts = {name: 0 for name in AGENT_SCRIPTS}
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for name, script in AGENT_SCRIPTS.items():
            if script in cmdline:
                counts[name] += 1
    for name, count in counts.items():
        m.gauge("agent_process_count", count, name=name)

    for name, filename in LOG_FILES.items():
        # logger_setup.py 가 날짜 기반 파일명을 쓴다(4-1) — 그런데 그 날짜는
        # 프로세스 시작 시점에 한 번 정해진다. 자정을 넘겨도 재시작 전까지는
        # 어제 파일에 계속 쓴다 — "오늘 파일"을 가정하면 그동안 계속
        # log_scrape_error 가 뜬다. ollama 와 같은 방식(최신 파일)으로 찾는다.
        pattern = os.path.join(REPO_ROOT, "logs", f"{filename[:-4]}-*.log")
        candidates = glob.glob(pattern)
        if not candidates:
            m.gauge("log_scrape_error", 1, target=name)
            continue
        try:
            latest = max(candidates, key=os.path.getmtime)
            m.gauge("log_file_bytes", os.path.getsize(latest), name=name)
            m.gauge("log_scrape_error", 0, target=name)
        except OSError:
            m.gauge("log_scrape_error", 1, target=name)

    # Ollama 로그 (6-4) — 날짜가 아니라 재기동 시각으로 파일명이 갈리므로
    # "오늘 것"이 아니라 "가장 최근에 수정된 것"을 찾는다. 로테이션이 없어
    # 조용히 커질 수 있어 크기를 감시한다(대응 2) — 정리는 cleanup_logs.ps1 이 한다.
    # 🔴 실측: 실제 볼륨은 거의 다 stderr 로 간다(stdout 은 수십 바이트, stderr 는
    # 수 KB) — stdout 만 보면 감시 대상을 놓친다. 둘 다 따로 잰다.
    stdout_logs = [p for p in glob.glob(os.path.join(REPO_ROOT, "logs", "ollama-*.log")) if not p.endswith(".err.log")]
    stderr_logs = glob.glob(os.path.join(REPO_ROOT, "logs", "ollama-*.err.log"))
    for label, candidates in (("ollama-stdout", stdout_logs), ("ollama-stderr", stderr_logs)):
        if not candidates:
            m.gauge("log_scrape_error", 1, target=label)
            continue
        try:
            latest = max(candidates, key=os.path.getmtime)
            m.gauge("log_file_bytes", os.path.getsize(latest), name=label)
            m.gauge("log_scrape_error", 0, target=label)
        except OSError:
            m.gauge("log_scrape_error", 1, target=label)


def collect_host_metrics(m: Metrics):
    """PC 자원 (5-1). GPU 는 별도 대리 지표(ollama_model_gpu_ratio)를 쓴다 — 여긴 CPU/메모리/디스크뿐."""
    try:
        m.gauge("host_cpu_percent", psutil.cpu_percent(interval=None))
        m.gauge("host_scrape_error", 0, target="cpu")
    except OSError:
        m.gauge("host_scrape_error", 1, target="cpu")

    try:
        vm = psutil.virtual_memory()
        m.gauge("host_memory_used_bytes", vm.used)
        m.gauge("host_memory_total_bytes", vm.total)
        m.gauge("host_scrape_error", 0, target="memory")
    except OSError:
        m.gauge("host_scrape_error", 1, target="memory")

    for path, label in HOST_DISK_MOUNTS:
        try:
            usage = shutil.disk_usage(path)
            m.gauge("host_disk_used_bytes", usage.used, mount=label)
            m.gauge("host_disk_free_bytes", usage.free, mount=label)
            m.gauge("host_scrape_error", 0, target=f"disk:{label}")
        except OSError:
            m.gauge("host_scrape_error", 1, target=f"disk:{label}")

    try:
        m.gauge("host_uptime_seconds", round(time.time() - psutil.boot_time(), 1))
        m.gauge("host_scrape_error", 0, target="uptime")
    except OSError:
        m.gauge("host_scrape_error", 1, target="uptime")


_cache_lock = threading.Lock()
_cached_text = "# local_exporter: 아직 첫 수집 전\n"
_cached_embedding_lines = []


def _collect_once(tick: int) -> str:
    m = Metrics()
    for collector in (
        collect_ollama_metrics,
        collect_bifrost_metrics,
        collect_wiki_metrics,
        collect_process_metrics,
        collect_host_metrics,
    ):
        try:
            collector(m)
        except Exception as exc:  # 절대 프로세스를 죽이지 않는다 — 5-3 원칙 3.
            m.lines.append(f"# {collector.__name__} 내부 오류: {exc}")

    global _cached_embedding_lines
    if tick % EMBEDDING_CHECK_EVERY_N_TICKS == 0:
        em = Metrics()
        try:
            collect_wiki_embedding_metrics(em)
        except Exception as exc:
            em.lines.append(f"# collect_wiki_embedding_metrics 내부 오류: {exc}")
        _cached_embedding_lines = em.lines
    m.lines.extend(_cached_embedding_lines)

    return m.render()


def _refresh_cache(tick: int):
    text = _collect_once(tick)
    global _cached_text
    with _cache_lock:
        _cached_text = text


def _background_loop():
    tick = 1
    while True:
        time.sleep(COLLECTION_INTERVAL_SECONDS)
        _refresh_cache(tick)
        tick += 1


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        with _cache_lock:
            body = _cached_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 요청마다 stdout 을 채우지 않는다
        pass


def main():
    psutil.cpu_percent(interval=None)  # 첫 호출은 기준점만 세팅되므로 미리 버린다.
    _refresh_cache(tick=0)  # 서버가 열리기 전에 첫 수집을 동기로 끝낸다.

    threading.Thread(target=_background_loop, daemon=True).start()

    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), MetricsHandler)
    print(f"local_exporter listening on {BIND_HOST}:{BIND_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
