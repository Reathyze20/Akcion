# Akcion - Start Full Stack
# ==========================
# Spustí backend + frontend najednou

Write-Host "🚀 Starting Akcion Trading Intelligence..." -ForegroundColor Green

# Backend
Write-Host "`n📡 Starting Backend (FastAPI)..." -ForegroundColor Cyan
$backendPath = Join-Path $PSScriptRoot "backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; python run_server.py" -WindowStyle Normal

# Wait for backend to start
Write-Host "⏳ Waiting for backend to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Frontend
Write-Host "`n🎨 Starting Frontend (Vite)..." -ForegroundColor Cyan
$frontendPath = Join-Path $PSScriptRoot "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; npm run dev" -WindowStyle Normal

Write-Host "`n✅ Full stack started!" -ForegroundColor Green
Write-Host "`n📝 URLs:" -ForegroundColor White
Write-Host "   Backend API: http://localhost:8002" -ForegroundColor Gray
Write-Host "   Swagger Docs: http://localhost:8002/api/docs" -ForegroundColor Gray
Write-Host "   Frontend: http://localhost:5173" -ForegroundColor Gray
Write-Host "`n💡 Tip: Close terminal windows to stop servers" -ForegroundColor Yellow
