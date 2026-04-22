# =============================================================================
# setup.ps1 — Local LLM Stack 초기 설치 스크립트
# =============================================================================
# 새 PC에서 이 레포를 클론한 후 실행합니다.
#
# 사전 필수 설치:
#   - Ollama       : https://ollama.com/download
#   - Docker Desktop : https://www.docker.com/products/docker-desktop
#   - Git          : https://git-scm.com
#
# 실행 방법:
#   PowerShell을 관리자 권한으로 열고 아래 명령 실행
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup.ps1
# =============================================================================

param(
    # Open WebUI 데이터, .env, docker-compose.yml 등 런타임 파일이 저장될 경로
    [string]$ConfigDir = "C:\your\path\to\local-llm-config",   # ← 수정 필요

    # 이 스크립트 파일 기준 레포 루트 (수정 불필요)
    [string]$RepoDir = (Split-Path $PSScriptRoot -Parent)
)

function Write-Step($msg) {
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}
function Write-OK($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red }

Write-Host @"

=============================================
  Local LLM Stack 초기 설치 스크립트
=============================================
  설정 디렉토리 : $ConfigDir
  레포 디렉토리 : $RepoDir
=============================================
"@ -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# 0. 사전 요구사항 확인
# -----------------------------------------------------------------------------
Write-Step "사전 요구사항 확인 중..."

$allOk = $true
foreach ($cmd in @("ollama --version", "docker --version", "git --version")) {
    $name = $cmd.Split(" ")[0]
    try {
        Invoke-Expression $cmd 2>&1 | Out-Null
        Write-OK "$name 설치 확인"
    } catch {
        Write-Fail "$name 미설치 — 설치 후 다시 실행하세요"
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-Host "`n필수 프로그램을 먼저 설치하세요." -ForegroundColor Red
    exit 1
}

# -----------------------------------------------------------------------------
# 1. 설정 디렉토리 생성
# -----------------------------------------------------------------------------
Write-Step "설정 디렉토리 생성 중..."

foreach ($dir in @("$ConfigDir\docker", "$ConfigDir\ollama")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Write-OK "생성: $dir"
    } else {
        Write-OK "이미 존재: $dir"
    }
}

# -----------------------------------------------------------------------------
# 2. Modelfile 복사
# -----------------------------------------------------------------------------
Write-Step "Modelfile 복사 중..."

foreach ($mf in @("Modelfile.coder", "Modelfile.exaone", "Modelfile.qwen3", "Modelfile.r1")) {
    $src = "$RepoDir\modelfiles\$mf"
    $dst = "$ConfigDir\ollama\$mf"
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-OK "복사: $mf"
    } else {
        Write-Warn "파일 없음: $src"
    }
}

# -----------------------------------------------------------------------------
# 3. Ollama 환경변수 설정
# -----------------------------------------------------------------------------
Write-Step "Ollama 환경변수 설정 중..."

$envVars = @{
    "OLLAMA_HOST"              = "0.0.0.0"
    "OLLAMA_NUM_PARALLEL"      = "1"
    "OLLAMA_MAX_LOADED_MODELS" = "1"
    "OLLAMA_KEEP_ALIVE"        = "30m"
    "OLLAMA_KV_CACHE_TYPE"     = "q8_0"
    "OLLAMA_VULKAN"            = "1"     # AMD GPU 사용 시. NVIDIA는 제거 가능
}

foreach ($key in $envVars.Keys) {
    [System.Environment]::SetEnvironmentVariable($key, $envVars[$key], "User")
    Write-OK "$key = $($envVars[$key])"
}

# -----------------------------------------------------------------------------
# 4. Ollama 모델 다운로드 + 커스텀 모델 등록
# -----------------------------------------------------------------------------
Write-Step "Ollama 기반 모델 다운로드 중... (수 GB, 시간이 오래 걸릴 수 있습니다)"

$baseModels = @(
    "qwen2.5-coder:7b-instruct-q4_K_M",
    "exaone-deep:7.8b",
    "qwen3:8b",
    "deepseek-r1:7b",
    "nomic-embed-text:latest"
)

foreach ($model in $baseModels) {
    Write-Host "  다운로드 중: $model" -ForegroundColor Gray
    ollama pull $model
    if ($LASTEXITCODE -eq 0) {
        Write-OK "$model 완료"
    } else {
        Write-Warn "$model 실패 — 수동 실행: ollama pull $model"
    }
}

Write-Step "커스텀 모델 등록 중..."

$customModels = @(
    @{ Name = "llm-coder";  File = "$ConfigDir\ollama\Modelfile.coder" },
    @{ Name = "llm-exaone"; File = "$ConfigDir\ollama\Modelfile.exaone" },
    @{ Name = "llm-qwen3";  File = "$ConfigDir\ollama\Modelfile.qwen3" },
    @{ Name = "llm-r1";     File = "$ConfigDir\ollama\Modelfile.r1" }
)

foreach ($cm in $customModels) {
    if (Test-Path $cm.File) {
        ollama create $cm.Name -f $cm.File
        if ($LASTEXITCODE -eq 0) { Write-OK "$($cm.Name) 등록 완료" }
        else                     { Write-Warn "$($cm.Name) 등록 실패" }
    } else {
        Write-Warn "Modelfile 없음: $($cm.File)"
    }
}

# -----------------------------------------------------------------------------
# 5. .env 파일 생성
# -----------------------------------------------------------------------------
Write-Step ".env 파일 생성 중..."

$envFile = "$ConfigDir\docker\.env"
if (Test-Path $envFile) {
    Write-Warn ".env 파일이 이미 존재합니다 — 덮어쓰지 않습니다"
} else {
    $secretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object {[char]$_})
    $googleKey = Read-Host "Google Gemini API 키를 입력하세요 (없으면 Enter 스킵)"

    $envContent = "WEBUI_SECRET_KEY=$secretKey`n"
    if ($googleKey) { $envContent += "GOOGLE_API_KEY=$googleKey`n" }

    [System.IO.File]::WriteAllText($envFile, $envContent, [System.Text.Encoding]::UTF8)
    Write-OK ".env 생성 완료 (SECRET_KEY 자동 생성됨)"
}

# -----------------------------------------------------------------------------
# 6. docker-compose.yml 확인
# -----------------------------------------------------------------------------
Write-Step "docker-compose.yml 확인 중..."

if (-not (Test-Path "$ConfigDir\docker\docker-compose.yml")) {
    Write-Warn "docker-compose.yml 없음 — README.md를 참고해 수동으로 생성하세요"
} else {
    Write-OK "docker-compose.yml 존재 확인"
}

# -----------------------------------------------------------------------------
# 7. Open WebUI 실행
# -----------------------------------------------------------------------------
Write-Step "Open WebUI 시작"

$answer = Read-Host "Open WebUI를 지금 시작할까요? (y/n)"
if ($answer -eq "y") {
    Set-Location "$ConfigDir\docker"
    docker compose up -d
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Open WebUI 시작됨"
        Start-Sleep -Seconds 5
        Start-Process "http://localhost:3000"
    } else {
        Write-Warn "시작 실패 — 수동 실행: cd $ConfigDir\docker && docker compose up -d"
    }
}

# -----------------------------------------------------------------------------
# 완료
# -----------------------------------------------------------------------------
Write-Host @"

=============================================
  설치 완료
=============================================
  다음 단계:
  1. http://localhost:3000 접속 후 관리자 계정 생성
  2. Admin Panel > Functions 에서 아래 파일 코드 붙여넣기:
     - functions/llm_router.py
     - functions/google_genai_manifold.py
  3. Admin Panel > Settings > Documents 설정:
     - Embedding Engine : Ollama
     - Embedding Model  : nomic-embed-text:latest
  4. scripts/start.ps1 의 WEBUI_DIR 경로를 수정 후
     부팅 시 자동 실행으로 등록하세요.
=============================================
"@ -ForegroundColor Cyan
