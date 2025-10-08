#!/bin/bash

# Скрипт для сборки Docker образа HotWalletClaimer
# Автоматически определяет архитектуру процессора

set -e

echo "======================================================================"
echo "🐳 Сборка Docker образа HotWalletClaimer"
echo "======================================================================"
echo ""

# Определение архитектуры
ARCH=$(uname -m)
echo "🔍 Обнаружена архитектура: $ARCH"
echo ""

# Выбор Dockerfile
if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
    DOCKERFILE="docker/Dockerfile.amd64"
    echo "✅ Использую Dockerfile для AMD64/Intel"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    DOCKERFILE="docker/Dockerfile.arm64"
    echo "✅ Использую Dockerfile для ARM64"
else
    echo "❌ Неподдерживаемая архитектура: $ARCH"
    echo "Поддерживаются: x86_64 (amd64), aarch64 (arm64)"
    exit 1
fi

echo ""
echo "======================================================================"
echo "🔨 Начинаю сборку образа..."
echo "======================================================================"
echo ""

# Сборка образа
docker build -f "$DOCKERFILE" -t hwoarang91/hot-wallet-claimer:latest .

echo ""
echo "======================================================================"
echo "✅ Сборка завершена успешно!"
echo "======================================================================"
echo ""

# Показать информацию об образе
docker images | grep hwoarang91/hot-wallet-claimer

echo ""
echo "======================================================================"
echo "📋 Следующие шаги:"
echo "======================================================================"
echo ""
echo "1. Запустить контейнер:"
echo "   docker-compose up -d"
echo ""
echo "2. Или запустить вручную:"
echo "   docker run -d --name hot-wallet-claimer hwoarang91/hot-wallet-claimer:latest"
echo ""
echo "3. Просмотреть логи:"
echo "   docker logs -f hot-wallet-claimer"
echo ""
echo "4. Опубликовать в Docker Hub:"
echo "   docker login"
echo "   docker push hwoarang91/hot-wallet-claimer:latest"
echo ""
echo "======================================================================"
