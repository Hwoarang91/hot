# 🚀 Быстрый старт - Docker на Windows 11

## Для нетерпеливых - 3 команды

### 1️⃣ Откройте WSL терминал и клонируйте репозиторий
```bash
cd ~
git clone https://github.com/Hwoarang91/hot.git
cd hot
```

### 2️⃣ Соберите Docker образ
```bash
./build.sh
```

### 3️⃣ Запустите контейнер
```bash
docker-compose up -d
```

**Готово!** 🎉

---

## 📋 Управление контейнером

### Просмотр логов
```bash
docker logs -f hot-wallet-claimer
```

### Остановка
```bash
docker-compose down
```

### Перезапуск
```bash
docker-compose restart
```

### Обновление кода и пересборка
```bash
git pull
./build.sh
docker-compose up -d --force-recreate
```

---

## 🪟 Альтернатива для Windows PowerShell

Если вы предпочитаете PowerShell вместо WSL:

### 1. Откройте PowerShell в папке проекта
```powershell
cd C:\Users\ВашеИмя\hot
```

### 2. Соберите образ
```powershell
.\build.ps1
```

### 3. Запустите
```powershell
docker-compose up -d
```

---

## 🎯 Использование Docker Desktop GUI

1. Откройте **Docker Desktop**
2. Перейдите в раздел **Images**
3. Найдите `hwoarang91/hot-wallet-claimer:latest`
4. Нажмите **Run** ▶️
5. Настройте volumes и нажмите **Run**

---

## 📚 Подробная документация

Для детальных инструкций смотрите:
- [DOCKER_BUILD_GUIDE_RU.md](docs/DOCKER_BUILD_GUIDE_RU.md) - Полное руководство
- [DOCKER.md](docs/DOCKER.md) - Документация по Docker

---

## 🐛 Проблемы?

### Docker не найден в WSL
```bash
# Убедитесь что Docker Desktop запущен
# В Docker Desktop включите WSL Integration для вашего дистрибутива
```

### Контейнер сразу останавливается
```bash
docker logs hot-wallet-claimer
```

### Нужна помощь?
Создайте Issue в репозитории: https://github.com/Hwoarang91/hot/issues
