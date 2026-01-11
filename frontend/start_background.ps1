# Start frontend dev server in background
$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting Akcion Frontend in background..." -ForegroundColor Cyan

# Kill any existing node processes on port 5173
$processId = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($processId) {
    Write-Host "⏹️  Stopping existing frontend on port 5173..." -ForegroundColor Yellow
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Start frontend in background
$frontendPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $frontendPath

$process = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c npm run dev" `
    -WorkingDirectory $frontendPath `
    -PassThru `
    -WindowStyle Hidden

Write-Host "Frontend started in background (PID: $($process.Id))" -ForegroundColor Green
Write-Host "URL: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop: Stop-Process -Id $($process.Id)" -ForegroundColor Yellow

Pop-Location
