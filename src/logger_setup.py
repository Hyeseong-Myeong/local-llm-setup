import atexit
import datetime
import os
import re
import sys

# 1차 방어(Docs/plg_monitoring_design.md 12-3) — 로그 파일에 쓰기 전에 치환한다.
# Alloy 쪽 2차 방어(monitoring/*/config.alloy 의 loki.process "redact")와 같은
# 패턴을 쓴다 — 한 곳에서 관리하고 양쪽에 반영한다.
_REDACT_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key\s*[=:]\s*)\S+'), r'\1<REDACTED>'),
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}'), r'\1<REDACTED>'),
    (re.compile(r'(?i)(authorization\s*[=:]\s*)\S+'), r'\1<REDACTED>'),
    (re.compile(r'(?i)(token\s*[=:]\s*)\S+'), r'\1<REDACTED>'),
    (re.compile(r'(?i)(webhook[s]?/)[A-Za-z0-9._\-/]+'), r'\1<REDACTED>'),
    (re.compile(r'sk-[A-Za-z0-9]{16,}'), '<REDACTED>'),
]


def _redact(text):
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def setup_logger(log_filename):
    """
    pythonw.exe 환경에서 실행 시 콘솔이 없어 print() 출력이 유실되는 것을 방지하기 위해
    stdout(표준 출력) 및 stderr(표준 에러)를 파일로 리다이렉트합니다.
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 날짜 기반 파일명(4-1) — 같은 이름으로 재생성하면 Alloy 의 Windows 로테이션
    # 결함(grafana/alloy#2292)에 걸려 수집이 통째로 멈춘다. 날이 바뀌면 새 경로가
    # 생기므로 이 문제가 없다. 크기 기반 회전(.bak)은 더 이상 필요 없어 제거했다.
    base, ext = os.path.splitext(log_filename)
    dated_filename = f"{base}-{datetime.datetime.now().strftime('%Y%m%d')}{ext}"
    log_path = os.path.join(log_dir, dated_filename)

    # 파일을 append 모드로 열고 라인 버퍼링(buffering=1) 적용
    log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    atexit.register(log_file.close)  # 프로그램 종료 시 로그 파일 핸들 명시적 닫기

    class TeeLogger:
        def __init__(self, file, terminal):
            self.file = file
            self.terminal = terminal

        def write(self, data):
            data = _redact(data)
            self.file.write(data)
            # terminal 객체가 None이 아니고 쓰기 가능하면 출력 (pythonw에서는 오류 방지)
            if self.terminal:
                try:
                    self.terminal.write(data)
                except Exception:
                    pass
            self.file.flush()

        def flush(self):
            self.file.flush()
            if self.terminal:
                try:
                    self.terminal.flush()
                except Exception:
                    pass

        def isatty(self):
            if self.terminal and hasattr(self.terminal, 'isatty'):
                return self.terminal.isatty()
            return False

        def fileno(self):
            if self.terminal and hasattr(self.terminal, 'fileno'):
                return self.terminal.fileno()
            raise OSError()

    # pythonw의 경우 sys.stdout이 None일 수 있음
    sys.stdout = TeeLogger(log_file, getattr(sys, 'stdout', None))
    sys.stderr = TeeLogger(log_file, getattr(sys, 'stderr', None))

    # 프로그램 시작을 알리는 구분선 추가
    start_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*50}\n🚀 [START] Process initialized at {start_time}\n{'='*50}")
