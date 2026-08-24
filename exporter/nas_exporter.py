#!/usr/bin/env python3
"""NAS 호스트 exporter — Docs/plg_monitoring_design.md 5-2, 12-2.

DSM 작업 스케줄러(root, 부팅 시 트리거)로 상주 실행한다. 컨테이너로 만들지 않는다 —
컨테이너에 Docker 소켓을 마운트하면 컨테이너 탈출이 곧 호스트 장악이 된다(12-2).

읽기 전용 명령만 쓴다 — `docker inspect` · `docker ps` · `/proc` · 파일 크기 조회.
`docker run` · `exec` · `rm` 은 쓰지 않는다(5-3 원칙 2).

표준 라이브러리만 사용한다 — NAS 에 pip 패키지가 설치돼 있다는 보장이 없다.
"""
import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen

BIND_HOST = "127.0.0.1"  # 루프백 전용 — K10. 같은 호스트의 Prometheus 만 긁는다.
BIND_PORT = 13091

# 감시 대상 — 5-2. 하나 늘리려면 여기에만 추가한다.
CONTAINERS = [
    "chromadb",
    "couchdb-obsidian-sync",
    "hyeseongkit-hub",
    "hyeseongkit-jenkins",
]

DOCKER_BIN = shutil.which("docker") or "/usr/local/bin/docker"
CHROMA_DATA_PATH = "/volume1/docker/chromadb/data"
CHROMA_HEARTBEAT_URL = "http://127.0.0.1:8000/api/v2/heartbeat"

_HEALTH_STATUS_MAP = {"starting": 0, "healthy": 1, "unhealthy": 2}


def _docker_inspect(name):
    """docker inspect 결과(dict) 또는 None(대상이 없거나 명령 실패)."""
    try:
        out = subprocess.run(
            [DOCKER_BIN, "inspect", name],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    return data[0] if data else None


def _docker_ps_all_names():
    """docker ps -a 의 컨테이너 이름 목록. 실패 시 빈 리스트."""
    try:
        out = subprocess.run(
            [DOCKER_BIN, "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [line for line in out.stdout.splitlines() if line]


class Metrics:
    """Prometheus 텍스트 포맷 라인을 모은다."""

    def __init__(self):
        self.lines = []

    def gauge(self, name, value, **labels):
        self._line(name, value, labels)

    def counter(self, name, value, **labels):
        self._line(name, value, labels)

    def _line(self, name, value, labels):
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            self.lines.append(f"{name}{{{label_str}}} {value}")
        else:
            self.lines.append(f"{name} {value}")

    def render(self):
        return "\n".join(self.lines) + "\n"


def collect_container_metrics(m: Metrics, name: str):
    """공통 컨테이너 지표 (5-2 표) — 대상 하나당."""
    info = _docker_inspect(name)
    if info is None:
        m.gauge("container_scrape_error", 1, target=name)
        return
    m.gauge("container_scrape_error", 0, target=name)

    state = info.get("State", {})
    m.gauge("container_running", 1 if state.get("Running") else 0, container=name)
    m.gauge("container_restart_count", info.get("RestartCount", 0), container=name)
    m.gauge("container_last_exit_code", state.get("ExitCode", 0), container=name)
    m.gauge(
        "container_state_error_present",
        1 if state.get("Error") else 0,
        container=name,
    )

    ports = (info.get("NetworkSettings") or {}).get("Ports") or {}
    bound_all = 0
    published = 0
    for bindings in ports.values():
        if not bindings:
            continue
        for b in bindings:
            published += 1
            if b.get("HostIp") in ("0.0.0.0", "::", ""):
                bound_all = 1
    m.gauge("container_bound_all_interfaces", bound_all, container=name)
    m.gauge("container_published_ports", published, container=name)

    health = state.get("Health")
    if health and health.get("Status") in _HEALTH_STATUS_MAP:
        m.gauge(
            "container_health_status",
            _HEALTH_STATUS_MAP[health["Status"]],
            container=name,
        )


def collect_chroma_metrics(m: Metrics):
    """chromadb 전용 지표 (5-2)."""
    try:
        with urlopen(CHROMA_HEARTBEAT_URL, timeout=5) as resp:
            up = 1 if resp.status == 200 else 0
    except (URLError, OSError, ValueError):
        up = 0
    m.gauge("chroma_http_up", up)

    # "HTTP 200 은 누가 응답하는지 알려주지 않는다" — 실제로 8000 을 물고 있는 컨테이너가
    # chromadb 라는 이름인지 확인한다. docker rename 으로 물러난 _old 컨테이너가 죽지 않고
    # 되살아나 포트를 선점한 사고(troubleshooting.md)가 있었다.
    responder = None
    try:
        out = subprocess.run(
            [DOCKER_BIN, "ps", "--format", "{{.Names}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                if ":8000->" in line or "0.0.0.0:8000" in line:
                    responder = line.split("\t", 1)[0]
                    break
    except (OSError, subprocess.TimeoutExpired):
        pass
    m.gauge("chroma_responding_container", 1 if responder == "chromadb" else 0)

    # os.walk 는 최상위 경로가 없어도 예외를 던지지 않고 그냥 빈 결과를 낸다 —
    # isdir 로 먼저 확인하지 않으면 "경로가 없음"과 "데이터가 0바이트"를 구분하지 못한다.
    if not os.path.isdir(CHROMA_DATA_PATH):
        m.gauge("chroma_data_scrape_error", 1)
    else:
        total = 0
        for dirpath, _dirnames, filenames in os.walk(CHROMA_DATA_PATH):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        m.gauge("chroma_data_bytes", total)
        m.gauge("chroma_data_scrape_error", 0)

    m.gauge(
        "chroma_old_container_exists",
        1 if "chromadb_old" in _docker_ps_all_names() else 0,
    )


def _read_proc_meminfo():
    values = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                rest = rest.strip()
                if rest.endswith("kB"):
                    values[key] = int(rest[:-2].strip()) * 1024
    except OSError:
        pass
    return values


def collect_host_metrics(m: Metrics):
    """NAS 호스트 자원 (5-2) — host="nas" 라벨."""
    # CPU — /proc/loadavg 의 1분 평균을 코어 수로 정규화한 근사치.
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
        cpu_count = os.cpu_count() or 1
        m.gauge("host_cpu_percent", round(min(load1 / cpu_count, 1.0) * 100, 1), host="nas")
        m.gauge("host_scrape_error", 0, target="cpu")
    except (OSError, ValueError, IndexError):
        m.gauge("host_scrape_error", 1, target="cpu")

    mem = _read_proc_meminfo()
    if mem.get("MemTotal") and "MemAvailable" in mem:
        total = mem["MemTotal"]
        avail = mem["MemAvailable"]
        used = total - avail
        m.gauge("host_memory_total_bytes", total, host="nas")
        m.gauge("host_memory_used_bytes", used, host="nas")
        m.gauge("host_memory_percent", round(used / total * 100, 1), host="nas")
        m.gauge("host_scrape_error", 0, target="memory")
    else:
        m.gauge("host_scrape_error", 1, target="memory")

    for mount in ("/volume1",):
        try:
            usage = shutil.disk_usage(mount)
            m.gauge("host_disk_total_bytes", usage.total, mount=mount)
            m.gauge("host_disk_free_bytes", usage.free, mount=mount)
            m.gauge("host_scrape_error", 0, target=f"disk:{mount}")
        except OSError:
            m.gauge("host_scrape_error", 1, target=f"disk:{mount}")


def build_metrics_text():
    m = Metrics()
    for name in CONTAINERS:
        collect_container_metrics(m, name)
    collect_chroma_metrics(m)
    collect_host_metrics(m)
    return m.render()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = build_metrics_text().encode("utf-8")
        except Exception as exc:  # 절대 프로세스를 죽이지 않는다 — 5-3 원칙 3.
            body = f"# exporter internal error: {exc}\n".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 요청마다 stdout 을 채우지 않는다
        pass


def main():
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), MetricsHandler)
    print(f"nas_exporter listening on {BIND_HOST}:{BIND_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
