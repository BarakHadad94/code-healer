# code-healer Demo Script — Scenario A: Self-Heal
# Run from any directory; the script locates the repo root automatically.
#
# Usage:
#   .\demo\run_demo.ps1            # Scenario A (self-heal, default)
#   .\demo\run_demo.ps1 -Scenario B # Scenario B (deep review)
#   .\demo\run_demo.ps1 -Scenario C # Scenario C (skip / green path)

param(
    [ValidateSet("A", "B", "C")]
    [string]$Scenario = "A"
)

$root = Split-Path $PSScriptRoot -Parent

function Ok($msg)   { Write-Host "  OK   $msg" -ForegroundColor Green }
function Err($msg)  { Write-Host "  FAIL $msg" -ForegroundColor Red }
function Info($msg) { Write-Host "  -->  $msg" -ForegroundColor Yellow }
function Banner($msg) {
    Write-Host ""
    Write-Host $msg -ForegroundColor Cyan
    Write-Host ("─" * $msg.Length) -ForegroundColor DarkGray
}

Banner "code-healer demo — Scenario $Scenario"

# ── 1. .env ──────────────────────────────────────────────────────────────────
if (-not (Test-Path "$root\.env")) {
    Err ".env not found at repo root."
    Info "Create it: copy .env.example .env  then add your ANTHROPIC_API_KEY"
    exit 1
}
$envText = Get-Content "$root\.env" -Raw
if ($envText -notmatch "ANTHROPIC_API_KEY\s*=\s*sk-") {
    Err "ANTHROPIC_API_KEY looks missing or invalid in .env"
    exit 1
}
Ok ".env found with API key"

# ── 2. Docker ─────────────────────────────────────────────────────────────────
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Err "Docker Desktop is not running."
    Info "Start Docker Desktop, wait for it to finish loading, then re-run this script."
    exit 1
}
Ok "Docker Desktop is running"

# ── 3. Sandbox image ──────────────────────────────────────────────────────────
$images = docker images --format "{{.Repository}}" 2>&1
if ($images -notcontains "code-healer-sandbox") {
    Err "Sandbox image 'code-healer-sandbox' not found."
    Info "Build it once: docker build -t code-healer-sandbox .\sandbox-image"
    exit 1
}
Ok "Sandbox image exists"

# ── 4. Backend ────────────────────────────────────────────────────────────────
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/runs" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Ok "Backend is up (port 8000)"
} catch {
    Err "Backend is not responding on port 8000."
    Info "Start it:  uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --port 8000"
    exit 1
}

# ── 5. Frontend ───────────────────────────────────────────────────────────────
try {
    $r = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Ok "Frontend is up (port 5173)"
} catch {
    Err "Frontend is not responding on port 5173."
    Info "Start it:  cd frontend; npm run dev"
    exit 1
}

# ── 6. Reset workspace ────────────────────────────────────────────────────────
if ($Scenario -eq "A") {
    Write-Host ""
    Write-Host "  Resetting demo/broken_code to broken state..." -ForegroundColor DarkGray
    git -C "$root\demo\broken_code" checkout HEAD -- calculator.py 2>&1 | Out-Null
    Ok "calculator.py reset (add bug re-injected)"
}

# ── 7. Open browser ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Opening http://localhost:5173 ..." -ForegroundColor DarkGray
Start-Process "http://localhost:5173"

# ── 8. Demo guide ─────────────────────────────────────────────────────────────
Banner "READY — follow these steps"

switch ($Scenario) {
    "A" {
        Write-Host "  Scenario A — Self-Heal (broken calculator)" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Click the  [⚡ Self-heal]  preset button" -ForegroundColor White
        Write-Host "  2. Click  [Start Healing]" -ForegroundColor White
        Write-Host "  3. Watch Agent Reasoning:" -ForegroundColor White
        Write-Host "       • pytest runs and fails on the broken add() function" -ForegroundColor DarkGray
        Write-Host "       • Agent activates, reads the file, rewrites the fix" -ForegroundColor DarkGray
        Write-Host "       • Tests re-run inside Docker — pass" -ForegroundColor DarkGray
        Write-Host "       • Fix committed to a new git branch" -ForegroundColor DarkGray
        Write-Host "  4. Code Diff panel shows the before/after change" -ForegroundColor White
    }
    "B" {
        Write-Host "  Scenario B — Deep Review (sensitive auth path)" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Click the  [🔍 Deep review]  preset button" -ForegroundColor White
        Write-Host "  2. Click  [Start Healing]" -ForegroundColor White
        Write-Host "  3. Watch Agent Reasoning:" -ForegroundColor White
        Write-Host "       • pytest runs and passes (code is clean)" -ForegroundColor DarkGray
        Write-Host "       • auth/session.py triggers deep-review activation" -ForegroundColor DarkGray
        Write-Host "       • Agent reviews the file semantically, reports findings" -ForegroundColor DarkGray
    }
    "C" {
        Write-Host "  Scenario C — Skip (green build, no sensitive paths)" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Click the  [✓ Skip]  preset button" -ForegroundColor White
        Write-Host "  2. Click  [Start Healing]" -ForegroundColor White
        Write-Host "  3. Watch Agent Reasoning:" -ForegroundColor White
        Write-Host "       • pytest runs and passes" -ForegroundColor DarkGray
        Write-Host "       • No sensitive paths touched — agent skipped entirely" -ForegroundColor DarkGray
        Write-Host "       • Zero API tokens used" -ForegroundColor DarkGray
    }
}

Write-Host ""
