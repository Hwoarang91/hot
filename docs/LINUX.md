## Отдельная установка Linux (Ubuntu 20.04 до 24.04):

Убедитесь, что ваша операционная система обновлена, выполнив следующие команды:
```bash
   sudo apt-get update
   sudo apt-get upgrade -y
   sudo reboot
```

Выполните блок команд QuickStart, чтобы клонировать этот репозиторий GitHub, настроить виртуальное окружение и установить все зависимости:
```bash
   sudo apt install -y git
   git clone https://github.com/thebrumby/HotWalletBot.git
   cd HotWalletBot
   sudo chmod +x install.sh launch.sh
   ./install.sh
```

**Только для пользователей Ubuntu:** Включите PM2 для сохранения состояния после перезагрузок с помощью следующей команды (пользователям Windows следовать Руководству для Windows).
```bash
   pm2 startup systemd
```

Если у вас нет прав суперпользователя, обратите внимание на вывод PM2 с подсказкой выполнить команду от имени суперпользователя. Пример может выглядеть так:

```sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u ubuntu --hp /home/ubuntu```

Следуя этим шагам, вы получите полностью рабочее окружение для запуска Telegram Claim Bot на вашей системе Ubuntu. Обязательно ознакомьтесь с файлом [DOCKER.md](docs/DOCKER.md) для подробных инструкций по использованию Docker, если это предпочтительно.