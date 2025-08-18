param(
  [string]$Dir = "scratch_demo",
  [int]$DelayMs = 600
)

Write-Host "Gnosis Flow demo: creating/modifying/deleting in '$Dir'" -ForegroundColor Cyan

function Sleep-Step([int]$ms) {
  Start-Sleep -Milliseconds $ms
}

try {
  # 1) Create demo directory
  if (-not (Test-Path $Dir)) {
    New-Item -ItemType Directory -Path $Dir | Out-Null
  }
  # Give the watcher ample time to detect directory creation
  Sleep-Step $DelayMs

  # 2) Create a file and write lines
  $file = Join-Path $Dir "demo.txt"
  New-Item -ItemType File -Path $file -Force | Out-Null
  Sleep-Step $DelayMs

  Add-Content -Path $file -Value "hello"
  Sleep-Step $DelayMs

  Add-Content -Path $file -Value "world"
  Sleep-Step $DelayMs

  # 3) Create a subdirectory
  $sub = Join-Path $Dir "subdir"
  if (-not (Test-Path $sub)) {
    New-Item -ItemType Directory -Path $sub | Out-Null
  }
  Sleep-Step $DelayMs

  # 4) Modify again
  Add-Content -Path $file -Value "another line"
  Sleep-Step $DelayMs

  # 5) Delete file
  if (Test-Path $file) {
    Remove-Item -Path $file -Force
  }
  Sleep-Step $DelayMs

  # 6) Delete subdir
  if (Test-Path $sub) {
    Remove-Item -Path $sub -Force
  }
  Sleep-Step $DelayMs

  # 7) Delete demo directory
  if (Test-Path $Dir) {
    Remove-Item -Path $Dir -Force
  }
  # Allow watcher to detect dir deletion before exiting
  Sleep-Step $DelayMs

  Write-Host "Demo finished. Check your Gnosis Flow console for events." -ForegroundColor Green
}
catch {
  Write-Warning "Demo encountered an error: $($_.Exception.Message)"
}
