# PowerShell скрипт для сборки Docker образа на Windows
# Запускайте из PowerShell или Windows Terminal

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🐳 Сборка Docker образа HotWalletClaimer" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker
Write-Host "🔍 Проверка Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "✅ Docker установлен: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker не найден! Убедитесь что Docker Desktop запущен." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Определение архитектуры (для Windows обычно amd64)
$arch = $env:PROCESSOR_ARCHITECTURE
Write-Host "🔍 Архитектура процессора: $arch" -ForegroundColor Yellow

$dockerfile = "docker/Dockerfile.amd64"
Write-Host "✅ Использую Dockerfile для AMD64/Intel" -ForegroundColor Green

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🔨 Начинаю сборку образа..." -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Сборка образа
docker build -f $dockerfile -t hwoarang91/hot-wallet-claimer:latest .

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "✅ Сборка завершена успешно!" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host ""
    
    # Показать информацию об образе
    docker images | Select-String "hwoarang91/hot-wallet-claimer"
    
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "📋 Следующие шаги:" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Запустить контейнер через Docker Compose:" -ForegroundColor White
    Write-Host "   docker-compose up -d" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "2. Или запустить вручную:" -ForegroundColor White
    Write-Host "   docker run -d --name hot-wallet-claimer hwoarang91/hot-wallet-claimer:latest" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "3. Просмотреть логи:" -ForegroundColor White
    Write-Host "   docker logs -f hot-wallet-claimer" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "4. Опубликовать в Docker Hub:" -ForegroundColor White
    Write-Host "   docker login" -ForegroundColor Yellow
    Write-Host "   docker push hwoarang91/hot-wallet-claimer:latest" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "❌ Ошибка при сборке образа!" -ForegroundColor Red
    Write-Host "Проверьте логи выше для получения подробностей." -ForegroundColor Red
    exit 1
}
