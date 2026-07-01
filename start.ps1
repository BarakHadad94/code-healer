# code-healer — start backend + frontend dev servers
# Run from the repo root: .\start.ps1
#
# --reload-dir backend --reload-dir agent  ← REQUIRED: limits uvicorn's file
# watcher to source-code only.  Without these flags uvicorn will also watch
# demo/broken_code/ and restart itself the moment the agent writes the fix,
# killing the run at the write_file step (iteration 3).

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$root = Split-Path $PSScriptRoot -Parent
if ((Split-Path $PSScriptRoot -Leaf) -ne "code-healer") {
    $root = $PSScriptRoot
}

if (-not $FrontendOnly) {
    Write-Host "Starting backend…" -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$root'; uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --port 8000"
}

if (-not $BackendOnly) {
    Write-Host "Starting frontend…" -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$root\frontend'; npm run dev"
}

Write-Host "Dashboard: http://localhost:5173" -ForegroundColor Green
