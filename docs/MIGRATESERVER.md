## Миграция сервера

### На сервере, который будет выведен из эксплуатации

1. Перейдите в директорию `HotWalletBot`:
   ```bash
   cd HotWalletBot
   ```

2. Сохраните список процессов PM2 и создайте `pm2-backup.json` из дампа:
   ```bash
   pm2 save
   cp ~/.pm2/dump.pm2 pm2-backup.json
   ```

3. Создайте сжатый tar-архив с необходимыми файлами:
   ```bash
   tar -czvf compressed_files.tar.gz selenium backups screenshots pm2-backup.json
   ```

### На новом сервере

4. Следуйте общим инструкциям по установке в [LINUX.md](docs/LINUX.md).

5. С помощью SSH, ShellNGN или другого инструмента для подключения к серверу скопируйте `compressed_files.tar.gz` со старого сервера на новый.

6. Скопируйте `compressed_files.tar.gz` в директорию `HotWalletBot` и распакуйте его:
   ```bash
   cp /path/to/compressed_files.tar.gz /path/to/HotWalletBot
   bash
   cd HotWalletBot
   tar -xzvf compressed_files.tar.gz
   ```

7. Создайте скрипт восстановления:
   ```bash
   nano recover_pm2.sh
   ```

   Вставьте следующее в `recover_pm2.sh`:
   ```
   #!/bin/bash

   # Путь к вашему PM2 dump файлу
   DUMP_FILE="pm2-backup.json"

   # Замена базовой директории
   OLD_BASE_DIR="/root/HotWalletBot"
   NEW_BASE_DIR="/home/ubuntu/HotWalletBot"

   # Перебор каждого процесса в dump файле и запуск с задержкой
   jq -c '.[]' $DUMP_FILE | while read -r process; do
     NAME=$(echo $process | jq -r '.name')
     SCRIPT_PATH=$(echo $process | jq -r '.pm_exec_path' | sed "s|$OLD_BASE_DIR|$NEW_BASE_DIR|g")
     CWD=$(echo $process | jq -r '.pm_cwd' | sed "s|$OLD_BASE_DIR|$NEW_BASE_DIR|g")
     SESSION_NAME=$(echo $process | jq -r '.args[0] // empty')
     RELATIVE_SCRIPT_PATH=$(realpath --relative-to="$CWD" "$SCRIPT_PATH")
     ENV=$(echo $process | jq -c '.env')
     
     # Использовать имя процесса как session_name, если явно не задано
     SESSION_NAME=${SESSION_NAME:-$NAME}
     
     # Проверка, запущен ли процесс уже
     if pm2 describe "$NAME" >/dev/null 2>&1; then
       echo "Процесс $NAME уже запущен. Пропускаем..."
     else
       echo "Запуск процесса: $NAME со скриптом: $RELATIVE_SCRIPT_PATH в рабочей директории: $CWD и сессией: $SESSION_NAME"
       # Перейти в правильную рабочую директорию перед запуском процесса
       cd "$CWD" || exit
       NODE_NO_WARNINGS=1 pm2 start "$RELATIVE_SCRIPT_PATH" --name "$NAME" --interpreter "venv/bin/python3" --watch "$RELATIVE_SCRIPT_PATH" -- "$SESSION_NAME"
       
       echo "Ожидание 2 минуты перед запуском следующего процесса..."
       sleep 120 # 120 секунд = 2 минуты
     fi
   done

   echo "Все процессы обработаны."
   ```

8. Сделайте скрипт исполняемым:
   ```bash
   chmod +x recover_pm2.sh
   ```

9. Запустите скрипт:
   ```bash
   ./recover_pm2.sh
   ```

Этот процесс мигрирует ваши процессы PM2, гарантируя корректный запуск скриптов на новом сервере с обновлёнными путями и настройками.