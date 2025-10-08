# 🐳 Инструкция по сборке Docker образа на Windows 11

## Предварительные требования

### ✅ Что должно быть установлено:
1. **Windows 11**
2. **Docker Desktop** (с включенным WSL 2 backend)
3. **WSL 2** (Ubuntu или другой дистрибутив Linux)
4. **Git** (в WSL)

---

## 📋 Шаг 1: Подготовка WSL

### 1.1 Откройте WSL терминал
Нажмите `Win + X` и выберите "Terminal" или "Windows Terminal", затем выберите вкладку с вашим WSL дистрибутивом (обычно Ubuntu).

### 1.2 Проверьте установку Docker
```bash
docker --version
docker ps
```

Если команды работают - отлично! Если нет, убедитесь что:
- Docker Desktop запущен
- В настройках Docker Desktop включен "Use the WSL 2 based engine"
- Ваш WSL дистрибутив включен в разделе "Resources > WSL Integration"

---

## 📦 Шаг 2: Клонирование репозитория

### 2.1 Перейдите в домашнюю директорию
```bash
cd ~
```

### 2.2 Клонируйте ваш репозиторий
```bash
git clone https://github.com/Hwoarang91/hot.git
cd hot
```

---

## 🔨 Шаг 3: Сборка Docker образа

### 3.1 Определите архитектуру вашего процессора

**Для Intel/AMD процессоров (большинство ПК):**
```bash
docker build -f docker/Dockerfile.amd64 -t hwoarang91/hot-wallet-claimer:latest .
```

**Для ARM процессоров (редко на Windows):**
```bash
docker build -f docker/Dockerfile.arm64 -t hwoarang91/hot-wallet-claimer:latest .
```

### 3.2 Дождитесь завершения сборки
Процесс может занять 5-15 минут в зависимости от скорости интернета и мощности компьютера.

Вы увидите примерно такой вывод:
```
[+] Building 234.5s (15/15) FINISHED
 => [internal] load build definition
 => => transferring dockerfile
 => [internal] load .dockerignore
 => [1/10] FROM ubuntu:24.04
 => [2/10] RUN apt-get update && apt-get install...
 ...
 => => naming to hwoarang91/hot-wallet-claimer:latest
```

### 3.3 Проверьте созданный образ
```bash
docker images | grep hwoarang91
```

Вы должны увидеть:
```
hwoarang91/hot-wallet-claimer   latest   abc123def456   2 minutes ago   1.5GB
```

---

## 🚀 Шаг 4: Запуск контейнера

### 4.1 Базовый запуск (для тестирования)
```bash
docker run -it --rm hwoarang91/hot-wallet-claimer:latest
```

**Параметры:**
- `-it` - интерактивный режим с терминалом
- `--rm` - автоматически удалить контейнер после остановки

### 4.2 Запуск с сохранением данных
```bash
docker run -d \
  --name hot-wallet-claimer \
  -v ~/hot-data:/usr/src/app/data \
  -v ~/hot-sessions:/usr/src/app/sessions \
  hwoarang91/hot-wallet-claimer:latest
```

**Параметры:**
- `-d` - запуск в фоновом режиме (detached)
- `--name` - имя контейнера
- `-v` - монтирование папок для сохранения данных между перезапусками

### 4.3 Просмотр логов
```bash
docker logs -f hot-wallet-claimer
```

Нажмите `Ctrl+C` чтобы выйти из просмотра логов (контейнер продолжит работать).

### 4.4 Остановка контейнера
```bash
docker stop hot-wallet-claimer
```

### 4.5 Запуск остановленного контейнера
```bash
docker start hot-wallet-claimer
```

### 4.6 Удаление контейнера
```bash
docker rm hot-wallet-claimer
```

---

## 🎯 Шаг 5: Запуск через Docker Desktop GUI

### 5.1 Откройте Docker Desktop
Найдите иконку Docker Desktop в трее Windows и кликните по ней.

### 5.2 Перейдите в раздел "Images"
Вы увидите ваш образ `hwoarang91/hot-wallet-claimer:latest`

### 5.3 Запустите контейнер
1. Нажмите кнопку "Run" (▶️) рядом с образом
2. В открывшемся окне настройте:
   - **Container name:** `hot-wallet-claimer`
   - **Ports:** (если нужно) `8080:8080`
   - **Volumes:** 
     - Host path: `C:\Users\ВашеИмя\hot-data` → Container path: `/usr/src/app/data`
     - Host path: `C:\Users\ВашеИмя\hot-sessions` → Container path: `/usr/src/app/sessions`
3. Нажмите "Run"

### 5.4 Управление контейнером
В разделе "Containers" вы можете:
- ▶️ Запустить
- ⏸️ Остановить
- 🔄 Перезапустить
- 📋 Просмотреть логи
- 🗑️ Удалить

---

## 📤 Шаг 6: Публикация образа в Docker Hub (опционально)

### 6.1 Создайте аккаунт на Docker Hub
Перейдите на https://hub.docker.com/ и зарегистрируйтесь.

### 6.2 Войдите в Docker Hub из терминала
```bash
docker login
```

Введите ваш username и password.

### 6.3 Опубликуйте образ
```bash
docker push hwoarang91/hot-wallet-claimer:latest
```

### 6.4 Теперь образ доступен публично
Любой пользователь может скачать его командой:
```bash
docker pull hwoarang91/hot-wallet-claimer:latest
```

---

## 🔧 Дополнительные команды

### Просмотр запущенных контейнеров
```bash
docker ps
```

### Просмотр всех контейнеров (включая остановленные)
```bash
docker ps -a
```

### Зайти внутрь запущенного контейнера
```bash
docker exec -it hot-wallet-claimer bash
```

### Очистка неиспользуемых образов и контейнеров
```bash
docker system prune -a
```

⚠️ **Внимание:** Эта команда удалит все неиспользуемые образы и контейнеры!

### Пересборка образа (после изменений в коде)
```bash
cd ~/hot
git pull
docker build -f docker/Dockerfile.amd64 -t hwoarang91/hot-wallet-claimer:latest .
```

---

## 🐛 Решение проблем

### Проблема: "Cannot connect to the Docker daemon"
**Решение:** 
1. Убедитесь что Docker Desktop запущен
2. В настройках Docker Desktop включите WSL Integration для вашего дистрибутива

### Проблема: "permission denied while trying to connect to the Docker daemon socket"
**Решение:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Проблема: Сборка образа очень медленная
**Решение:**
1. Проверьте скорость интернета
2. В Docker Desktop увеличьте выделенную память и CPU (Settings > Resources)

### Проблема: Контейнер сразу останавливается
**Решение:**
```bash
docker logs hot-wallet-claimer
```
Проверьте логи на наличие ошибок.

---

## 📚 Полезные ссылки

- **Документация Docker:** https://docs.docker.com/
- **Docker Desktop для Windows:** https://docs.docker.com/desktop/install/windows-install/
- **WSL 2 установка:** https://docs.microsoft.com/en-us/windows/wsl/install
- **Ваш репозиторий:** https://github.com/Hwoarang91/hot

---

## ✅ Готово!

Теперь вы можете собирать и запускать собственный Docker образ на Windows 11 с WSL! 🎉

Если у вас возникнут вопросы, проверьте документацию проекта или создайте Issue в репозитории.
