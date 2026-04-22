# =============================================================================
# start.ps1 — Local LLM Stack 자동 시작 스크립트
# =============================================================================
# 사용 전 아래 설정 섹션을 본인 환경에 맞게 수정하세요.
# =============================================================================

# ===== 설정 (본인 환경에 맞게 수정) =========================================
$OLLAMA_PATH    = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$DOCKER_PATH    = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$TAILSCALE_PATH = "C:\Program Files\Tailscale\tailscale.exe"
$WEBUI_DIR    = "$env:USERPROFILE\local-llm-config\docker"  # ← 폴더명이 다르면 수정
$WEBUI_URL      = "http://localhost:3000"
$PRELOAD_MODEL  = "llm-coder:latest"
# =============================================================================

function Write-Step($msg) {
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}
function Write-OK($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ⚠ $msg" -ForegroundColor Yellow }

# -----------------------------------------------------------------------------
# 1. Ollama 시작
# -----------------------------------------------------------------------------
Write-Step "Ollama 시작 중..."

$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProc) {
    Write-OK "Ollama 이미 실행 중"
} else {
    if (Test-Path $OLLAMA_PATH) {
        Start-Process $OLLAMA_PATH -WindowStyle Hidden
        Start-Sleep -Seconds 3
        Write-OK "Ollama 시작됨"
    } else {
        Write-Warn "Ollama 실행 파일을 찾을 수 없습니다: $OLLAMA_PATH"
    }
}

$ollamaReady = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
        $ollamaReady = $true
        Write-OK "Ollama API 응답 확인 (모델 $($resp.models.Count)개 로드됨)"
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ollamaReady) { Write-Warn "Ollama API 응답 없음 — 계속 진행합니다" }

# -----------------------------------------------------------------------------
# 2. Docker Desktop + Open WebUI
# -----------------------------------------------------------------------------
Write-Step "Docker Desktop 시작 중..."

$dockerProc = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if ($dockerProc) {
    Write-OK "Docker Desktop 이미 실행 중"
} else {
    if (Test-Path $DOCKER_PATH) {
        Start-Process $DOCKER_PATH
        Write-Host "  Docker Desktop 시작 대기 중 (최대 60초)..." -ForegroundColor Gray
        $dockerReady = $false
        for ($i = 0; $i -lt 12; $i++) {
            Start-Sleep -Seconds 5
            docker ps 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $dockerReady = $true
                Write-OK "Docker 엔진 준비 완료"
                break
            }
        }
        if (-not $dockerReady) { Write-Warn "Docker 엔진 응답 없음 — 계속 진행합니다" }
    } else {
        Write-Warn "Docker Desktop을 찾을 수 없습니다: $DOCKER_PATH"
    }
}

Write-Step "Open WebUI 컨테이너 확인 중..."
$containerStatus = docker inspect --format "{{.State.Status}}" open-webui 2>&1
if ($containerStatus -eq "running") {
    Write-OK "Open WebUI 이미 실행 중"
} else {
    Write-Host "  Open WebUI 시작 중..." -ForegroundColor Gray
    Set-Location $WEBUI_DIR
    docker compose up -d 2>&1 | Out-Null

    $webuiReady = $false
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 5
        try {
            $resp = Invoke-WebRequest -Uri $WEBUI_URL -TimeoutSec 3 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                $webuiReady = $true
                Write-OK "Open WebUI 시작 완료"
                break
            }
        } catch {}
    }
    if (-not $webuiReady) { Write-Warn "Open WebUI 응답 없음 — 브라우저에서 확인하세요" }
}

# -----------------------------------------------------------------------------
# 3. Tailscale 상태 확인
# -----------------------------------------------------------------------------
Write-Step "Tailscale 상태 확인 중..."

if (Test-Path $TAILSCALE_PATH) {
    $tsStatus = & $TAILSCALE_PATH status 2>&1
    if ($tsStatus -match "100\.\d+\.\d+\.\d+") {
        $ip = ($tsStatus | Select-String "100\.\d+\.\d+\.\d+").Matches[0].Value
        Write-OK "Tailscale 연결됨 — IP: $ip"
        Write-Host "  외부 접속 URL: http://${ip}:3000" -ForegroundColor Gray
    } else {
        Write-Warn "Tailscale 미연결 — 외부 접속 불가"
    }
} else {
    Write-Warn "Tailscale을 찾을 수 없습니다: $TAILSCALE_PATH"
}

# -----------------------------------------------------------------------------
# 4. 상주 모델 프리로드 (백그라운드)
# -----------------------------------------------------------------------------
Write-Step "상주 모델 프리로드 중 ($PRELOAD_MODEL)..."
Start-Job -ScriptBlock {
    param($model)
    try {
        Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
            -Method POST `
            -ContentType "application/json" `
            -Body "{`"model`": `"$model`", `"prompt`": `"`", `"stream`": false}" `
            -TimeoutSec 60 | Out-Null
    } catch {}
} -ArgumentList $PRELOAD_MODEL | Out-Null
Write-OK "프리로드 백그라운드 실행 중"

# -----------------------------------------------------------------------------
# 5. 브라우저 열기
# -----------------------------------------------------------------------------
Write-Step "브라우저에서 Open WebUI 열기..."
Start-Process $WEBUI_URL
Write-OK "완료"

Write-Host "`n=============================" -ForegroundColor Cyan
Write-Host " Local LLM Stack 시작 완료" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host " Open WebUI : $WEBUI_URL"
Write-Host " Ollama API : http://localhost:11434"
Write-Host "=============================" -ForegroundColor Cyan
