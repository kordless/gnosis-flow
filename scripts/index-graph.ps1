# Pre-warm the gnosis-flow code relationship graph on Windows
# Usage:
#   PowerShell -ExecutionPolicy Bypass -File .\scripts\index-graph.ps1
# Optional params:
#   -Types "import_dep,shared_tokens,term_ref" -Limit 1 -Include "*.py" -Dir "."

param(
  [string] $Types = "import_dep,shared_tokens,term_ref",
  [int] $Limit = 1,
  [string] $Include = "*.py",
  [string] $Dir = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
  if (-not (Get-Command gnosis-flow -ErrorAction SilentlyContinue)) {
    Write-Error "'gnosis-flow' not found in PATH. Run 'pip install -e .' in gnosis-flow/ first."
    exit 1
  }

  Push-Location $Dir
  Write-Host "Indexing graph..." -ForegroundColor Cyan
  Write-Host "  Types: $Types" -ForegroundColor DarkCyan
  Write-Host "  Limit: $Limit" -ForegroundColor DarkCyan
  Write-Host "  Include: $Include (recursive)" -ForegroundColor DarkCyan

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $files = Get-ChildItem -Recurse -File -Include $Include
  $total = ($files | Measure-Object).Count
  if ($total -eq 0) {
    Write-Host "No files matched '$Include' under '$Dir'." -ForegroundColor Yellow
    return
  }
  $count = 0
  foreach ($f in $files) {
    gnosis-flow graph neighbors "$($f.FullName)" --types "$Types" --limit $Limit | Out-Null
    $count += 1
    $elapsed = [math]::Max($sw.Elapsed.TotalSeconds, 0.001)
    $rate = $count / $elapsed
    $remaining = [math]::Max($total - $count, 0)
    $eta = if ($rate -gt 0) { $remaining / $rate } else { 0 }
    $pct = [int](($count / $total) * 100)
    $name = (Split-Path $f.FullName -Leaf)
    Write-Progress -Activity "Indexing graph" -Status ("{0}/{1} · {2} · {3:N1} f/s · ETA {4:N1}s" -f $count, $total, $name, $rate, $eta) -PercentComplete $pct
  }
  $sw.Stop()
  Write-Progress -Activity "Indexing graph" -Completed
  Write-Host ("Done. Indexed {0} files in {1:n1}s ({2:n1} f/s)" -f $count, $sw.Elapsed.TotalSeconds, ($count / [math]::Max($sw.Elapsed.TotalSeconds, 0.001))) -ForegroundColor Green
}
catch {
  Write-Error $_
  exit 1
}
finally {
  Pop-Location
}
