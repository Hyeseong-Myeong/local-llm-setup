# main 브랜치 push를 받아 실행 중인 로컬 스택을 최신 코드로 갱신하고,
# 헬스체크 실패 시 이전 커밋으로 롤백한다. 배포 대상 디렉토리가 개발
# 작업 디렉토리와 동일하므로, 커밋되지 않은 변경사항이 있으면 중단한다.

$RepoPath = if ($env:DEPLOY_REPO_PATH) { $env:DEPLOY_REPO_PATH } else { "C:\local_LLM" }
$WebhookUrl = $env:DISCORD_WEBHOOK_URL

function Send-DiscordNotice {
    param([string]$Message)
    if (-not $WebhookUrl) { return }
    try {
        $body = @{ content = $Message } | ConvertTo-Json -Compress
        # Windows PowerShell 5.1의 Invoke-RestMethod는 문자열 -Body를 시스템 코드페이지로
        # 인코딩해서 보내므로, 한글이 깨지지 않도록 UTF-8 바이트로 직접 인코딩해서 넘긴다.
        $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
        Invoke-RestMethod -Uri $WebhookUrl -Method Post -ContentType "application/json; charset=utf-8" -Body $bodyBytes | Out-Null
    } catch {
        Write-Warning "Discord 알림 전송 실패: $_"
    }
}

function Test-StackHealthy {
    try {
        $bifrost = Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -TimeoutSec 5 -UseBasicParsing
        $wiki = Invoke-WebRequest -Uri "http://127.0.0.1:9000/docs" -TimeoutSec 5 -UseBasicParsing
        return ($bifrost.StatusCode -eq 200) -and ($wiki.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Set-Location $RepoPath

# 러너 서비스 계정(NETWORK SERVICE)은 대화형 사용자가 소유한 이 디렉토리를
# 신뢰(safe.directory)하지 않은 상태라 모든 git 명령이 "unsafe repository"
# 에러로 실패할 수 있다. --global은 이 서비스 계정에 정상적인 HOME이 없어서
# 조용히 반영되지 않았음(실측 확인됨). --system은 Git 설치 폴더(Program Files)
# 쓰기 권한이 필요한데 NETWORK SERVICE에는 그 권한이 없음(icacls로 확인:
# BUILTIN\Users는 읽기 전용)도 확인함. 대신 HOME을 이 서비스 계정도 항상
# 쓸 수 있는 %TEMP%로 명시적으로 지정한 뒤 --global로 등록한다
# (actions/checkout이 매 실행마다 HOME을 임시 override하는 것과 같은 패턴).
$env:HOME = $env:TEMP
git config --global --add safe.directory "*"

$dirty = git status --porcelain
if ($dirty) {
    Send-DiscordNotice "⚠️ 배포 중단: $RepoPath 에 커밋되지 않은 변경사항이 있어 자동 배포를 건너뜁니다."
    Write-Warning "Working tree is dirty, aborting deploy."
    exit 1
}

$previousCommit = git rev-parse HEAD
$rollbackTag = "pre-deploy-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
git tag $rollbackTag $previousCommit

Write-Host "Fetching latest main..."
git fetch origin main
if ($LASTEXITCODE -ne 0) {
    Send-DiscordNotice "⚠️ 배포 중단: origin/main fetch에 실패했습니다 (네트워크 문제일 수 있음)."
    git tag -d $rollbackTag | Out-Null
    exit 1
}

git merge --ff-only origin/main
if ($LASTEXITCODE -ne 0) {
    Send-DiscordNotice "⚠️ 배포 중단: main 브랜치를 fast-forward할 수 없습니다 (로컬 이력이 origin/main과 분기됨)."
    git tag -d $rollbackTag | Out-Null
    exit 1
}

$newCommit = git rev-parse --short HEAD
$commitMsg = git log -1 --pretty=%s

Write-Host "Restarting stack..."
& "$RepoPath\restart.bat"

Write-Host "Waiting for services to come up..."
Start-Sleep -Seconds 15

$healthy = $false
for ($i = 0; $i -lt 6; $i++) {
    if (Test-StackHealthy) { $healthy = $true; break }
    Start-Sleep -Seconds 10
}

if ($healthy) {
    Send-DiscordNotice "✅ 배포 성공: ``$newCommit`` $commitMsg"
    Write-Host "Deploy succeeded at $newCommit"
} else {
    Write-Warning "Health check failed. Rolling back to $rollbackTag"
    git reset --hard $rollbackTag
    & "$RepoPath\restart.bat"
    Send-DiscordNotice "❌ 배포 실패 -> 롤백 완료: ``$newCommit`` 헬스체크 실패, $($previousCommit.Substring(0,7))(으)로 복구됨"
    exit 1
}
