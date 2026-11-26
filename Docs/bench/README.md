# Ollama 성능 측정 결과 (Windows 10 / 11, GPU 오버클럭)

측정일: 2026-11-24
목적: Windows 10 → 11 업그레이드와 GPU 오버클럭이 로컬 LLM 속도에 주는 영향 확인

## 환경
- CPU: Ryzen 5 5600X (6코어)
- RAM: 32GB
- GPU: RX 6600 XT 8GB (드라이버 32.0.21045.29003, 전 구간 동일)
- Ollama: 0.40.4 (llama.cpp 백엔드, 전 구간 동일)
- 환경변수: `OLLAMA_HOST=0.0.0.0`, `OLLAMA_KEEP_ALIVE=-1`, `HSA_OVERRIDE_GFX_VERSION=10.3.0`
- 측정 조건: 서비스(open-webui, bifrost, 에이전트) 기동 상태, `bge-m3` 상주, CPU 사용률 약 5% 이하로 안정된 뒤 측정

## 측정 방법
- 스크립트: `bench_ollama.ps1` (Ollama REST API 사용)
- 모델마다 순서대로 실행
  - 콜드 로드: 모델 언로드 후 첫 호출의 `load_duration`
  - 생성 속도: 짧은 프롬프트, 256토큰 생성, `eval_count / eval_duration`
  - 프롬프트 처리 속도: 약 1,500토큰 프롬프트, `prompt_eval_count / prompt_eval_duration`
- `temperature=0`, `seed=1` 고정, 컨텍스트는 Modelfile 기본값 사용
- 모델당 1회 측정 (±1% 이내 차이는 오차 범위)

## 결과 파일
| 파일 | 내용 |
|---|---|
| `win10_baseline_20261124.csv` | Windows 10, 오버클럭 없음 |
| `win11_20261124.csv` | Windows 11, 오버클럭 없음 |
| `win11_oc_20261124.csv` | Windows 11, GPU 코어 자동 오버클럭 |
| `win11_vramoc_20261124.csv` | Windows 11, GPU 코어 + VRAM 오버클럭 (재시도 전체 결과) |
| `win11_vramoc_crashed_partial_20261124.csv` | VRAM 오버클럭 1차 시도 (크래시 전 모델 2개) |
| `win11_oc_settings_20261124.md` | 오버클럭 설정과 크래시 기록 |

## 1. Windows 10 vs 11 (생성 속도, tok/s)
| 모델 | Win10 | Win11 | 변화 |
|---|---|---|---|
| qwen2.5-coder:7b | 28.95 | 28.90 | -0.2% |
| qwen2.5-coder-16k | 29.68 | 29.62 | -0.2% |
| qwen3.5:9b | 23.24 | 24.65 | +6.1% (변동폭 내) |
| qwen3.5-16k | 25.03 | 24.96 | -0.3% |
| gemma4:e4b | 50.89 | 50.76 | -0.3% |
| gemma4-e4b-64k | 50.83 | 50.74 | -0.2% |
| gemma4-e4b-128k | 50.90 | 50.67 | -0.5% |
| deepseek-r1:14b | 10.30 | 10.14 | -1.6% |

- OS 차이에 의한 속도 변화 없음
- GPU 적재 비율도 동일 (deepseek-r1:14b 66%, 나머지 100%)
- 이 PC는 NPU와 하이브리드 코어가 없어 Windows 11의 스케줄러 이점이 없음
- `qwen3.5:9b`는 측정마다 23.2 ~ 24.7 사이로 변동 (Win10 23.24, Win11 24.65, GPU OC 23.25). 같은 가중치의 `qwen3.5-16k`는 25.0으로 일정

## 2. GPU 오버클럭 (생성 속도, tok/s)
| 모델 | Win11 기본 | 코어 OC | 코어 + VRAM OC | 기본 대비 |
|---|---|---|---|---|
| qwen2.5-coder:7b | 28.90 | 29.02 | 31.18 | +7.9% |
| qwen2.5-coder-16k | 29.62 | 29.70 | 32.05 | +8.2% |
| qwen3.5:9b | 24.65 | 23.25 | 25.01 | +1.5% (변동폭 내) |
| qwen3.5-16k | 24.96 | 25.10 | 27.27 | +9.3% |
| gemma4:e4b | 50.76 | 50.94 | 56.24 | +10.8% |
| gemma4-e4b-64k | 50.74 | 50.85 | 56.25 | +10.9% |
| gemma4-e4b-128k | 50.67 | 51.01 | 56.28 | +11.1% |
| deepseek-r1:14b | 10.14 | 10.14 | 10.47 | +3.3% |

- 코어 OC만: 변화 +0.0 ~ +0.7%로 오차 범위
- VRAM OC 추가: GPU 전량 적재 모델 +8 ~ 11%
- 프롬프트 처리 속도는 OC 전 구간에서 거의 동일 (+0.2 ~ +1.9%)
- `deepseek-r1:14b`는 34%가 CPU/RAM에서 처리되어 이득이 +3.3%에 그침

### 설정
- GPU: AMD Software 자동 "GPU 오버클럭됨" 프리셋 (표시값 +2646 MHz) 후 VRAM +2380 MHz
- CPU: 자동 오버클럭 켜짐 (Overclock Offset +0.2 GHz)
- SmartAccess Memory: 비활성화
- VRAM 값은 AMD Software 표시 기준이며 기본값 대비 상승폭은 미확인

## 해석
- 토큰 생성 속도는 연산 성능보다 VRAM 메모리 대역폭이 결정
- 코어 클럭만 올리면 생성 속도 변화 없음, VRAM 클럭을 올려야 속도가 오름
- 8GB VRAM을 넘는 모델(deepseek-r1:14b)은 CPU 오프로딩이 병목이라 GPU 오버클럭 효과가 작음

## 안정성 이슈
- VRAM OC 1차 시도: 모델 2개 완료 후 비정상 종료
  - `Kernel-Power 41`, `WHEA 18` (치명적 하드웨어 오류), 덤프 파일 없음
  - 재시도에서는 재부팅 없이 전 모델 완료, 새 WHEA 이벤트 없음
- 같은 설정에서 1회 크래시, 1회 통과 → 안정 확인 불가
- CPU OC가 동시에 켜져 있어 크래시 원인(CPU / VRAM) 분리 안 됨
- 후속 확인 항목
  - CPU 자동 OC 해제 후 연속 측정
  - VRAM 값을 한 단계 낮춰 연속 측정
  - 스크립트를 3 ~ 4회 연속 실행해 재부팅 여부 확인

## 알려진 한계
- 모델당 1회 측정이라 1% 안팎 차이는 해석 불가
- `deepseek-r1:14b`의 VRAM OC 측정에서 두 번째 호출 대기 시간이 17.5초로 길게 나옴 (이전 0.14초). 모델 재적재 가능성이 있으나 원인 미확인
- 임베딩(`bge-m3`) 측정은 32문장 단일 배치 1회

## 재실행 방법
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Docs\bench\bench_ollama.ps1 -OutCsv <결과.csv>
```
- 측정 중 Ollama가 모델을 올렸다 내리므로 서비스 응답이 잠시 느려질 수 있음
- 서비스 기동 직후에는 CPU 부하가 높으므로 안정된 뒤 실행
