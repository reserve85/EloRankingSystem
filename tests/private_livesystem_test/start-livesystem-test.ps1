# ============================================================================
# Start Elo Ranking System - Live System Backup (Docker Desktop)
# ============================================================================
#
# This script builds the current local source code and starts the Elo
# Ranking System against the live system backup data.
#
# Usage:
#   .\start-livesystem-test.ps1            # Build & start (default)
#   .\start-livesystem-test.ps1 build      # Rebuild the image and start
#   .\start-livesystem-test.ps1 stop       # Stop the container
#   .\start-livesystem-test.ps1 stop-clean # Stop and remove volumes (DB data stays in ./data)
#   .\start-livesystem-test.ps1 logs       # Show container logs
#   .\start-livesystem-test.ps1 status     # Show container status
#
# ============================================================================

param(
    [ValidateSet("up", "build", "stop", "stop-clean", "logs", "status")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"

# Navigate to script directory (in case run from elsewhere)
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Elo Ranking System - Live System Backup" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not running"
    }
    Write-Host "[OK] Docker is running (version: $dockerVersion)" -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "        Please start Docker Desktop first." -ForegroundColor Yellow
    exit 1
}

# Check for database file
if (-not (Test-Path ".\data\database.db")) {
    Write-Host "[ERROR] Database file not found at .\data\database.db" -ForegroundColor Red
    Write-Host "        Expected backup data in:" -ForegroundColor Yellow
    Write-Host "        $PSScriptRoot\data\database.db" -ForegroundColor Yellow
    exit 1
}
else {
    $dbSize = (Get-Item ".\data\database.db").Length / 1KB
    Write-Host "[OK] Database found: .\data\database.db ($([math]::Round($dbSize, 1)) KB)" -ForegroundColor Green
}

# Check for upload files
if (Test-Path ".\uploads\*") {
    $uploadCount = (Get-ChildItem ".\uploads\*").Count
    Write-Host "[OK] Uploads found: $uploadCount file(s)" -ForegroundColor Green
}

Write-Host ""

switch ($Action) {
    { $_ -in "up", "build" } {
        Write-Host "Building image from local source code..." -ForegroundColor Yellow
        Write-Host "(Repository root: $((Get-Item "$PSScriptRoot\..\..\").FullName))" -ForegroundColor Gray
        Write-Host ""

        # Always do a clean rebuild (no cache) so the latest code is picked up
        docker compose build --no-cache

        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "[ERROR] Docker build failed!" -ForegroundColor Red
            exit 1
        }

        Write-Host ""
        Write-Host "Starting container..." -ForegroundColor Yellow
        docker compose up -d

        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "=============================================" -ForegroundColor Green
            Write-Host " Container is starting!" -ForegroundColor Green
            Write-Host "=============================================" -ForegroundColor Green
            Write-Host ""
            Write-Host " Application URL:  " -NoNewline
            Write-Host "http://localhost:8877" -ForegroundColor Yellow
            Write-Host ""
            Write-Host " System User:      " -NoNewline
            Write-Host "reserve" -ForegroundColor Yellow
            Write-Host " System Password:  " -NoNewline
            Write-Host "(your live password)" -ForegroundColor Yellow
            Write-Host ""
            Write-Host " Use '\start-livesystem-test.ps1 logs' to follow startup." -ForegroundColor Gray
            Write-Host " The app may take ~10 seconds to start (running migrations)." -ForegroundColor Gray
            Write-Host ""
        }
        else {
            Write-Host ""
            Write-Host "[ERROR] Failed to start container!" -ForegroundColor Red
            Write-Host "        Run: .\start-livesystem-test.ps1 logs" -ForegroundColor Yellow
            exit 1
        }
    }

    "stop" {
        Write-Host "Stopping container (data is preserved)..." -ForegroundColor Yellow
        docker compose down
        Write-Host ""
        Write-Host "[OK] Container stopped. Backup data is untouched." -ForegroundColor Green
        Write-Host ""
    }

    "stop-clean" {
        Write-Host "Stopping container and removing volumes..." -ForegroundColor Yellow
        docker compose down -v
        Write-Host ""
        Write-Host "[OK] Container stopped and volumes removed." -ForegroundColor Green
        Write-Host "     Note: Your source files in .\data are still intact." -ForegroundColor Gray
        Write-Host ""
    }

    "logs" {
        docker compose logs -f --tail=50
    }

    "status" {
        Write-Host "Container status:" -ForegroundColor Yellow
        Write-Host ""
        docker compose ps
        Write-Host ""

        # Check if app is responding
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8877/health" -TimeoutSec 5 -ErrorAction Stop
            Write-Host "[OK] Application is responding (HTTP $($response.StatusCode))" -ForegroundColor Green
        }
        catch {
            Write-Host "[WAIT] Application not yet responding (still starting?)" -ForegroundColor Yellow
            Write-Host "       Run: .\start-livesystem-test.ps1 logs" -ForegroundColor Gray
        }
        Write-Host ""
    }
}