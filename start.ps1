# code-healer — launch backend + frontend
# Run from the repo root: .\start.ps1
#
# IMPORTANT: --reload is intentionally OFF by default.
# uvicorn's file-watcher triggers a server reload when it detects any .py
# change inside the watched dirs. On Python 3.9/Windows that can include
# __pycache__ churn from the pytest precheck, which kills the background
# task mid-run and leaves the run stuck as "running".
#
# Use -Dev only while actively editing backend code (not during demo runs):
#   .\start.ps1 -Dev

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Dev
)

# $PSScriptRoot is the directory containing this script (= repo root)
$root = $PSScriptRoot

if (-not $FrontendOnly) {
    Write-Host "Starting backend…" -ForegroundColor Cyan
    if ($Dev) {
        Start-Process powershell -ArgumentList "-NoExit", "-Command",
            "cd '$root'; uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --port 8000"
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command",
            "cd '$root'; uvicorn backend.main:app --port 8000"
    }
}

if (-not $BackendOnly) {
    Write-Host "Starting frontend…" -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$root\frontend'; npm run dev"
}

Write-Host "Dashboard: http://localhost:5173" -ForegroundColor Green
if ($Dev) {
    Write-Host "(Dev mode: backend will reload on .py changes in backend/ and agent/)" -ForegroundColor DarkYellow
}
