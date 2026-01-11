# Start backend server in background
$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting Akcion Backend in background..." -ForegroundColor Cyan

# Kill any existing python processes on port 8000
$processId = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($processId) {
    Write-Host "⏹️  Stopping existing backend on port 8000..." -ForegroundColor Yellow
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Start backend in background
$backendPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $backendPath

$process = Start-Process -FilePath "python" `
    -ArgumentList "run_server.py" `
    -WorkingDirectory $backendPath `
    -PassThru `
    -WindowStyle Hidden

Write-Host "✅ Backend started in background (PID: $($process.Id))" -ForegroundColor Green
Write-Host "📍 API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "📍 Docs: http://localhost:8000/api/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop: Stop-Process -Id $($process.Id)" -ForegroundColor Yellow

Pop-Location
