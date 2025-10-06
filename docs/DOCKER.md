# Используйте Наш Docker-образ для Настройки Telegram Claim Bot

Использование Docker упрощает настройку Telegram Claim Bot за счёт контейнеризации приложения и его зависимостей. Это обеспечивает единообразную среду на разных архитектурах (x86/ARM64) и операционных системах (на базе Linux/Windows), устраняя проблемы, связанные с управлением зависимостями и конфликтами версий. Docker также предоставляет простой способ развертывания, масштабирования и управления приложением, что делает его идеальным выбором для эффективного запуска Telegram Claim Bot.

Для начала работы с Docker необходимо установить Docker на ваше устройство.

## Установка Docker

### Для Windows или Mac (Docker Desktop)

Скачайте и установите **Docker Desktop** с официального сайта Docker [здесь](https://www.docker.com/products/docker-desktop).

**ПРИМЕЧАНИЕ:** Docker Desktop включает Docker Engine и должен быть запущен, когда вы хотите использовать Claim Bot, однако отдельные окна командной строки можно закрывать после запуска сессий в виде процессов PM2.

- **Windows**:
  - Запустите Docker Engine, открыв Docker Desktop и оставив его открытым.
  - Откройте Командную строку (нажмите `Win + R`, введите `cmd` и нажмите Enter).
  - Перейдите к разделу [Общие команды](#common-commands) ниже.

- **Mac**:
  - Запустите Docker Engine, открыв Docker Desktop и оставив его открытым.
  - Откройте Терминал (Finder > Applications > Utilities > Terminal).
  - Перейдите к разделу [Общие команды](#common-commands) ниже.

### Для Виртуальных Частных Серверов (доступ через CLI)

#### Amazon Linux

```bash
sudo yum update -y
sudo yum install docker -y
sudo service docker start
sudo usermod -aG docker $USER
exit
```

#### Ubuntu

```bash
sudo apt-get update -y
sudo apt-get install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
exit
```

После выполнения этих команд повторно войдите в систему на вашем VPS и перейдите к разделу [Общие команды](#common-commands) ниже.

## Общие команды

### Шаг 1: Создайте Контейнер на Основе Нашего Основного Образа (только при первом запуске)

Для создания и запуска Docker-контейнера:

```bash
docker run -d --name telegram-claim-bot --restart unless-stopped hwoarang91/hot-wallet-claimer:latest
```

Docker-контейнер наследует сетевые свойства от хост-компьютера. Если у вас возникают проблемы с DNS при использовании стандартных сетевых настроек Docker (например, GitHub не разрешается и игры не загружаются), вы можете вручную переопределить DNS с помощью команд ниже:

**Использование DNS Cloudflare (если стандартная команда выше не работает)**

```bash
docker stop telegram-claim-bot
docker rm telegram-claim-bot
docker run -d --name telegram-claim-bot --dns="1.1.1.1" --restart unless-stopped hwoarang91/hot-wallet-claimer:latest
```

**Использование DNS Google (если стандартная команда выше не работает)**

```bash
docker stop telegram-claim-bot
docker rm telegram-claim-bot
docker run -d --name telegram-claim-bot --dns="8.8.8.8" --restart unless-stopped hwoarang91/hot-wallet-claimer:latest
```

### Шаг 2: Работа Внутри Контейнера

Для взаимодействия со скриптом, включая добавление аккаунтов или мониторинг:

```bash
docker exec -it telegram-claim-bot /bin/bash
```

### Шаг 3: Добавление Игр

Оказавшись внутри контейнера, вы можете добавлять игры.

- Чтобы выбрать из списка доступных скриптов:

  ```bash
  ./launch.sh
  ```

- Или указать скрипт по имени:

  ```bash
  ./launch.sh hot
  ```

Все остальные инструкции соответствуют основному `README.md`.

## Дополнительные команды и подсказки Docker (используются внутри контейнера)

- Для ручного обновления до последнего кода или добавления новых игр (скрипт обновления делает это автоматически каждые 12 часов):

```bash
./pull-games.sh
```

- Чтобы выйти из контейнера и вернуться к командной строке:

```bash
exit
```

## Дополнительные команды и подсказки Docker (используются в командной строке вне контейнера)

- Чтобы запустить контейнер после перезагрузки или остановки:

```bash
docker start telegram-claim-bot
docker exec -it telegram-claim-bot /bin/bash
```

- Чтобы остановить и удалить контейнер:

```bash
docker stop telegram-claim-bot
docker rm telegram-claim-bot
```

---

Все остальные инструкции соответствуют основному `README.md`.