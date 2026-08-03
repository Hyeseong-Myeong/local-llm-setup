import sys
import os
import datetime
import atexit

def setup_logger(log_filename):
    """
    pythonw.exe 환경에서 실행 시 콘솔이 없어 print() 출력이 유실되는 것을 방지하기 위해
    stdout(표준 출력) 및 stderr(표준 에러)를 파일로 리다이렉트합니다.
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_filename)
    
    # 로그 로테이션: 10MB 초과 시 이전 로그 삭제 후 현재 로그를 백업
    max_log_size = 10 * 1024 * 1024  # 10MB
    if os.path.exists(log_path) and os.path.getsize(log_path) > max_log_size:
        bak_path = log_path + '.bak'
        if os.path.exists(bak_path):
            os.remove(bak_path)
        os.rename(log_path, bak_path)
    
    # 파일을 append 모드로 열고 라인 버퍼링(buffering=1) 적용
    log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    atexit.register(log_file.close)  # 프로그램 종료 시 로그 파일 핸들 명시적 닫기
    
    class TeeLogger:
        def __init__(self, file, terminal):
            self.file = file
            self.terminal = terminal
            
        def write(self, data):
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
