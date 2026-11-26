param(
  [string]$OutCsv = "$PSScriptRoot\bench_results.csv",
  [string]$Base = "http://127.0.0.1:11434"
)
$ErrorActionPreference = 'Stop'

$models = @(
  'qwen2.5-coder:7b','qwen2.5-coder-16k:latest',
  'qwen3.5:9b','qwen3.5-16k:latest',
  'gemma4:e4b','gemma4-e4b-64k:latest','gemma4-e4b-128k:latest',
  'deepseek-r1:14b'
)

$shortPrompt = 'Explain in detail how a hash map works, including collision handling and resizing. Use plain text.'
$para = 'The quick brown fox jumps over the lazy dog while the engineers monitor GPU memory, token throughput, and latency across several quantized language models running locally on a desktop machine. '
$longPrompt = ($para * 45) + "`n`nSummarize the text above in three sentences."

function Invoke-Gen($model, $prompt, $numPredict, $keepAlive) {
  $body = @{ model=$model; prompt=$prompt; stream=$false; keep_alive=$keepAlive
             options=@{ temperature=0; seed=1; num_predict=$numPredict } } | ConvertTo-Json -Depth 5
  $bytes = [Text.Encoding]::UTF8.GetBytes($body)
  Invoke-RestMethod -Uri "$Base/api/generate" -Method Post -Body $bytes -ContentType 'application/json' -TimeoutSec 900
}
function Get-Split($model) {
  $ps = (Invoke-RestMethod -Uri "$Base/api/ps").models | Where-Object { $_.name -eq $model -or $_.model -eq $model }
  if(-not $ps){ return @{gpu=$null; size=$null; ctx=$null} }
  $p = $ps | Select-Object -First 1
  @{ gpu=[math]::Round(100.0*$p.size_vram/$p.size,0); size=[math]::Round($p.size/1GB,2); ctx=$p.context_length }
}
function Get-Vram {
  try { [math]::Round(((Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples | Measure-Object CookedValue -Maximum).Maximum/1GB,2) } catch { $null }
}
function Tps($n,$ns){ if($ns -gt 0){ [math]::Round($n/($ns/1e9),2) } else { $null } }

$rows = @()
foreach($m in $models){
  Write-Host "=== $m ==="
  try {
    # 0) make sure it's unloaded -> cold start measurement
    try { Invoke-Gen $m '' 1 0 | Out-Null } catch {}
    Start-Sleep -Seconds 3

    # 1) cold: load time + short decode
    $r1 = Invoke-Gen $m $shortPrompt 256 '5m'
    # 2) warm: decode speed
    $r2 = Invoke-Gen $m $shortPrompt 256 '5m'
    # 3) warm, long prompt: prefill speed
    $r3 = Invoke-Gen $m $longPrompt 64 '5m'
    $split = Get-Split $m
    $vram = Get-Vram

    $rows += [pscustomobject]@{
      model=$m
      ctx=$split.ctx
      loaded_gb=$split.size
      gpu_pct=$split.gpu
      vram_used_gb=$vram
      cold_load_s=[math]::Round($r1.load_duration/1e9,2)
      decode_tps_cold=Tps $r1.eval_count $r1.eval_duration
      decode_tps_warm=Tps $r2.eval_count $r2.eval_duration
      decode_tokens=$r2.eval_count
      prefill_tps=Tps $r3.prompt_eval_count $r3.prompt_eval_duration
      prefill_tokens=$r3.prompt_eval_count
      ttft_warm_s=[math]::Round(($r2.total_duration-$r2.eval_duration)/1e9,2)
      error=''
    }
  } catch {
    Write-Host "  ERROR: $($_.Exception.Message)"
    $rows += [pscustomobject]@{ model=$m; error=$_.Exception.Message }
  } finally {
    try { Invoke-Gen $m '' 1 0 | Out-Null } catch {}
    Start-Sleep -Seconds 3
  }
  $rows | Export-Csv -Path $OutCsv -NoTypeInformation -Encoding utf8
}

# embedding model (already resident)
try {
  $texts = 1..32 | ForEach-Object { "Sentence number $_ about local language model benchmarking on a desktop GPU." }
  $body = @{ model='bge-m3'; input=$texts } | ConvertTo-Json
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $e = Invoke-RestMethod -Uri "$Base/api/embed" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json'
  $sw.Stop()
  Write-Host ("bge-m3 embed 32 sentences: {0:N2}s" -f $sw.Elapsed.TotalSeconds)
  $rows += [pscustomobject]@{ model='bge-m3 (32 sentences/batch)'; decode_tps_warm=$null; ttft_warm_s=[math]::Round($sw.Elapsed.TotalSeconds,2); error='' }
  $rows | Export-Csv -Path $OutCsv -NoTypeInformation -Encoding utf8
} catch { Write-Host "embed error: $($_.Exception.Message)" }

Write-Host 'DONE'
