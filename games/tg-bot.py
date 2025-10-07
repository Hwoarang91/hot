import os
import sys
import json
import asyncio
import logging
import subprocess
import requests
import re

from status import list_pm2_processes, list_all_pm2_processes, get_inactive_directories, get_logs_by_process_name, get_status_logs_by_process_name, fetch_and_process_logs, should_exclude_process

def download_file(url, dest):
    """Скачать файл с URL по указанному пути назначения."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Убедиться, что нет ошибок в ответе
        with open(dest, 'wb') as f:
            f.write(response.content)
        print(f"Загружено {url} в {dest}")
    except Exception as e:
        print(f"Не удалось загрузить {url}: {e}")
        sys.exit(1)

def modify_pull_games_script(script_path):
    """Изменить скрипт pull-games.sh под наши нужды."""
    script_content = """#!/bin/bash

# Определяем целевые и исходные директории
TARGET_DIR="/app"
GAMES_DIR="$TARGET_DIR/games"
DEST_DIR="/usr/src/app/games"

# Проверяем, существует ли директория и является ли она git-репозиторием
if [ -d "$TARGET_DIR" ] && [ -d "$TARGET_DIR/.git" ]; then
    echo "В $TARGET_DIR выполняется обновление до последней версии."
    cd $TARGET_DIR
    git pull
elif [ -d "$TARGET_DIR" ] ; then
    echo "$TARGET_DIR существует, но не является git-репозиторием. Удаляем и клонируем заново."
    rm -rf $TARGET_DIR
    git clone https://github.com/Hwoarang91/hot.git $TARGET_DIR
else
    echo "$TARGET_DIR не существует. Клонируем репозиторий."
    git clone https://github.com/Hwoarang91/hot.git $TARGET_DIR
fi

# Устанавливаем рабочую директорию в клонированный репозиторий
cd $GAMES_DIR

# Создаем директорию назначения
mkdir -p $DEST_DIR

# Рекурсивно копируем содержимое директории games
cp -r $GAMES_DIR/* $DEST_DIR

echo "Все файлы и поддиректории скопированы в $DEST_DIR"
"""
    try:
        with open(script_path, 'w') as f:
            f.write(script_content)
        print(f"Скрипт {script_path} успешно изменён.")
    except Exception as e:
        print(f"Не удалось изменить {script_path}: {e}")
        sys.exit(1)

def check_and_update_games_utils():
    """Проверить наличие games/utils, и если нет, обновить с помощью pull-games.sh."""
    if not os.path.exists("/usr/src/app/games/utils"):
        pull_games_dest = "/usr/src/app/pull-games.sh"

        # Проверяем, существует ли pull-games.sh
        if os.path.exists(pull_games_dest):
            # Изменяем скрипт pull-games.sh
            modify_pull_games_script(pull_games_dest)

            # Делаем скрипт исполняемым
            os.chmod(pull_games_dest, 0o755)

            # Запускаем скрипт pull-games.sh
            result = subprocess.run([pull_games_dest], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Не удалось выполнить {pull_games_dest}: {result.stderr}")
                sys.exit(1)
            else:
                print(f"Успешно выполнен {pull_games_dest}: {result.stdout}")
        else:
            print("pull-games.sh не найден, обновление пропущено.")

# Убедиться, что games/utils присутствует перед импортом
check_and_update_games_utils()

try:
    from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, Update,
                          InlineKeyboardButton, InlineKeyboardMarkup)
    from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                              ContextTypes, ConversationHandler, MessageHandler, filters)
except ImportError:
    print("Модуль 'python-telegram-bot' не установлен. Устанавливаю сейчас...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot"])
    from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, Update,
                          InlineKeyboardButton, InlineKeyboardMarkup)
    from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                              ContextTypes, ConversationHandler, MessageHandler, filters)

try:
    from utils.pm2 import start_pm2_app, save_pm2
except ImportError:
    print("Не удалось импортировать утилиты PM2 даже после попытки скопировать необходимые файлы и директории.")
    sys.exit(1)

from status import list_pm2_processes, list_all_pm2_processes, get_inactive_directories, get_logs_by_process_name, get_status_logs_by_process_name, fetch_and_process_logs

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Определяем состояния
COMMAND_DECISION, SELECT_PROCESS, PROCESS_DECISION, PROCESS_COMMAND_DECISION = range(4)

stopped_processes = []
running_processes = []
inactive_directories = []

selected_process = None

def load_telegram_token(file_path: str) -> str:
    """Загрузить токен телеграм бота из указанного файла."""
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не существует.")
        sys.exit(1)

    with open(file_path, 'r') as file:
        config = json.load(file)
    
    token = config.get("telegramBotToken")

    if token:
        logger.info(f"Токен получен: {token}")
        return token
    else:
        logger.error("telegramBotToken не найден в файле.")
        sys.exit(1)

def run() -> None:
    """Запустить бота."""
    token = load_telegram_token('variables.txt')
    if not token:
        sys.exit(1)

    application = Application.builder().token(token).build()

    # Добавляем новые команды как точки входа
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('list', list_games),
            CommandHandler('list_pattern', list_games_with_pattern),
            CommandHandler('start_game', start_game),
            CommandHandler('restart', restart_game),
            CommandHandler('stop', stop_game),
            CommandHandler('logs', fetch_logs),  # Добавлено для получения логов
            CommandHandler('status', fetch_status)  # Добавлено для получения статуса
        ],
        states={
            COMMAND_DECISION: [CallbackQueryHandler(command_decision)],
            SELECT_PROCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_process)],
            PROCESS_DECISION: [CallbackQueryHandler(process_decision)],
            PROCESS_COMMAND_DECISION: [CallbackQueryHandler(process_command_decision)]
        },
        fallbacks=[CommandHandler('exit', exit),
           CommandHandler('list', list_games),
           CommandHandler('list_pattern', list_games_with_pattern),
           CommandHandler('start_game', start_game),
           CommandHandler('restart', restart_game),
           CommandHandler('stop', stop_game),
           CommandHandler('logs', fetch_logs),  # Добавлено для fallback
           CommandHandler('status', fetch_status)  # Добавлено для fallback
        ]
    )

    application.add_handler(conv_handler)

    # Другие глобальные команды
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("exit", exit))
    application.add_handler(CommandHandler('list', list_games))

    application.run_polling()

async def fetch_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить логи для указанного процесса."""
    if not context.args:
        await send_message(update, context, "Использование: /logs <имя_процесса> [количество_строк]")
        return

    process_name = context.args[0]
    
    # Количество строк по умолчанию 30, если указано - берем из аргументов
    lines = 30
    if len(context.args) > 1:
        try:
            lines = int(context.args[1])
        except ValueError:
            await send_message(update, context, "Пожалуйста, укажите корректное число для количества строк.")
            return

    logs = get_logs_by_process_name(process_name, lines)

    if not logs:
        await send_message(update, context, f"Логи для процесса {process_name} не найдены.")
    else:
        # Если логи слишком длинные, разбиваем на части и отправляем по частям
        await send_long_message(update, context, f"Логи для {process_name}:\n{logs}")

async def fetch_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить статус для указанного процесса или всех процессов, если процесс не указан."""
    # Если имя процесса не указано, показываем статус всех процессов
    if not context.args:
        await status_all(update, context)
        return

    # Иначе получаем статус указанного процесса
    process_name = context.args[0]
    status = get_status_logs_by_process_name(process_name)

    if not status:
        await send_message(update, context, f"Статус для процесса {process_name} не найден.")
    else:
        # Если статус слишком длинный, разбиваем на части и отправляем по частям
        await send_long_message(update, context, f"Статус логов для {process_name}:\n{status}")

async def send_long_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, chunk_size: int = 4000):
    """Отправить длинное сообщение, разбив его на части."""
    for chunk in [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]:
        await send_message(update, context, chunk)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запускает разговор и спрашивает пользователя о предпочтительной команде."""
    await update.message.reply_text(
        '<b>Телеграм Клейм Бот!\n'
        'Чем могу помочь?</b>',
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove(),
    )

    # Определяем inline-кнопки для выбора
    keyboard = [
        [InlineKeyboardButton('ВСЕ СТАТУСЫ', callback_data='status')],
        [InlineKeyboardButton('ВЫБРАТЬ ПРОЦЕСС', callback_data='process')],
        [InlineKeyboardButton('Помощь', callback_data='help')],
        [InlineKeyboardButton('Выход', callback_data='exit')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('<b>Пожалуйста, выберите:</b>', parse_mode='HTML', reply_markup=reply_markup)

    return COMMAND_DECISION

async def command_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Спрашивает пользователя о выборе команды."""
    query = update.callback_query
    await query.answer()
    decision = query.data

    if decision == 'process':
        return await select_process(update, context)
    elif decision == 'status':
        return await status_all(update, context)
    elif decision == 'help':
        return await help(update, context)
    elif decision == 'exit':
        return await exit(update, context)
    else:
        await query.edit_message_text(f"Неверная команда: {decision}")
        return ConversationHandler.END

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_message(update, context, """
Доступные команды:
    
/start - Запустить оригинального бота

/logs <имя сессии> <опционально количество строк> - Показать логи процесса
    Пример: /logs HOT:Wallet1
    Пример: /logs HOT:Wallet2 100

/status - Показать сводку статусов всех игровых сессий в PM2
/status <имя сессии> - Получить последние 30 балансов и статус для конкретной сессии
    Пример: /status HOT:Wallet1

/list - Показать все активные и неактивные игры из PM2.
/list <шаблон> - Показать только игры, соответствующие шаблону
    Пример: /list hot

/start <шаблон> - Запустить все процессы PM2, соответствующие шаблону
    Пример: /start HOT:Wallet1

/restart <шаблон> - Перезапустить все процессы PM2, соответствующие шаблону
    Пример: /restart :Wallet1

/stop <шаблон> - Остановить процессы, соответствующие шаблону
    Пример: /stop Vertus:

/update - Обновить игровые файлы (попытка через pull-games.sh, затем git pull).

/help - Показать это сообщение помощи.

/exit - Выйти из бота.
""")

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выйти из бота."""
    return await send_message(update, context, "До свидания!")

async def list_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все игры, исключая нежелательные и пустые, с указанием статуса (запущен/остановлен)."""
    if context.args:
        # Если есть аргументы (шаблон), переключаемся в режим поиска по шаблону
        await list_games_with_pattern(update, context)
    else:
        # Иначе показываем все игры
        games = list_all_pm2_processes()
        running_processes = list_pm2_processes("online")  # Получаем запущенные процессы

        for game in games:
            # Исключаем процессы, соответствующие ключевым словам исключения
            if should_exclude_process(game.strip()):
                continue  # Пропускаем этот процесс

            # Получаем и обрабатываем логи для каждой игры
            name, balance, _, _, status = fetch_and_process_logs(game.strip())

            # Отфильтровываем пустые или неполные записи
            if not name or balance == "None" or status == "Log file missing":
                continue  # Пропускаем неполные записи

            # Определяем, запущен процесс или остановлен
            process_state = "Запущен" if game.strip() in running_processes else "Остановлен"

            # Отправляем детали каждой игры отдельным сообщением
            response = f"Имя сессии: {name}\nБаланс: {balance}\nСтатус: {status}\nСостояние: {process_state}\n"
            await send_message(update, context, response)

async def list_games_with_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать игры, соответствующие шаблону, исключая определённые процессы и показывая статус."""
    if not context.args:
        await send_message(update, context, "Пожалуйста, укажите шаблон для поиска.")
        return

    pattern = context.args[0]
    games = list_all_pm2_processes()  # Получаем все процессы PM2
    running_processes = list_pm2_processes("online")  # Получаем запущенные процессы
    response = ""

    for game in games:
        # Исключаем процессы, соответствующие ключевым словам исключения
        if should_exclude_process(game.strip()):
            continue

        # Проверяем, соответствует ли шаблон имени сессии (без учёта регистра)
        if re.search(pattern, game.strip(), re.IGNORECASE):
            name, balance, _, _, status = fetch_and_process_logs(game.strip())

            # Отфильтровываем пустые или неполные записи
            if not name or balance == "None" or status == "Log file missing":
                continue  # Пропускаем неполные записи

            # Определяем, запущен процесс или остановлен
            process_state = "Запущен" if game.strip() in running_processes else "Остановлен"

            # Формируем ответ
            response += f"Имя сессии: {name}\nБаланс: {balance}\nСтатус: {status}\nСостояние: {process_state}\n\n"

    if not response:
        response = f"Игры, соответствующие шаблону '{pattern}', не найдены."

    await send_message(update, context, response)

async def manage_process(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Управлять процессами (запуск/перезапуск/остановка) через PM2 с обратной связью."""
    if not context.args:
        await send_message(update, context, f"Использование: /{action} <шаблон>")
        return
    
    pattern = context.args[0]  # Получаем шаблон от пользователя
    games = list_all_pm2_processes()  # Получаем все процессы из PM2

    # Находим процессы, соответствующие шаблону
    matched_games = [game for game in games if re.search(pattern, game)]

    if not matched_games:
        await send_message(update, context, f"Процессы, соответствующие шаблону '{pattern}', не найдены.")
        return

    # Для каждого найденного процесса выполняем нужное действие PM2 и сообщаем результат
    for game in matched_games:
        command = f"pm2 {action} {game.strip()}"
        result = await run_command(command)  # Запускаем команду PM2 и получаем результат

        # Отправляем обратную связь пользователю в Телеграм
        if "Process not found" in result:
            await send_message(update, context, f"Процесс не найден: {game.strip()}")
        else:
            # Корректируем сообщение в зависимости от действия
            if action == "start":
                await send_message(update, context, f"Успешно запущен: {game.strip()}")
            elif action == "restart":
                await send_message(update, context, f"Успешно перезапущен: {game.strip()}")
            elif action == "stop":
                await send_message(update, context, f"Успешно остановлен: {game.strip()}")

async def update_game_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновить игровые файлы, сначала пытаясь через pull-games.sh, затем git pull при неудаче."""
    pull_games_script = "./pull-games.sh"
    
    # Проверяем, существует ли pull-games.sh
    if os.path.exists(pull_games_script):
        # Пытаемся выполнить pull-games.sh
        result = await run_command(pull_games_script)
        if "not found" in result.lower() or "failed" in result.lower():
            await send_message(update, context, "Не удалось выполнить pull-games.sh. Пытаюсь выполнить git pull...")
            # Пытаемся выполнить git pull, если pull-games.sh не удался
            git_result = await run_git_pull(update, context)
            return
        else:
            await send_message(update, context, f"pull-games.sh выполнен успешно:\n{result}")
    else:
        await send_message(update, context, "pull-games.sh не найден. Пытаюсь выполнить git pull...")
        # Пытаемся выполнить git pull, если pull-games.sh отсутствует
        git_result = await run_git_pull(update, context)

async def run_git_pull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить git pull и обработать вывод с ограничением в 4к символов."""
    git_result = await run_command("git pull")
    
    if "error" in git_result.lower() or "aborting" in git_result.lower():
        # Если есть ошибки, отправляем результат ошибки
        await send_limited_message(update, context, git_result)
    else:
        # Если успешно, отправляем результат обновления
        await send_limited_message(update, context, git_result)

async def run_command(command: str) -> str:
    """Выполнить shell-команду и вернуть её вывод, включая stdout и stderr."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    # Объединяем stdout и stderr в один ответ, чтобы захватить весь вывод
    return stdout.decode() + "\nОшибка: " + stderr.decode()

async def send_limited_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, limit: int = 4096):
    """Отправлять сообщения частями, ограниченными 4к символами."""
    # Разбиваем текст на части по 4096 символов и отправляем каждую отдельно
    for i in range(0, len(text), limit):
        await send_message(update, context, text[i:i + limit])

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    """Отправить сообщение с помощью бота."""
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        await update.callback_query.answer()
    elif update.message:
        await update.message.reply_text(text)

# Обработчики для /start, /restart, /stop
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запустить бота или обработать запуск процесса по шаблону, если есть аргументы."""
    # Проверяем, есть ли аргументы (например, /start <шаблон>)
    if context.args:
        # Если есть аргументы, считаем, что нужно запустить конкретный процесс
        await manage_process(update, context, "start")
        return ConversationHandler.END
    else:
        # Если аргументов нет, запускаем обычный диалог бота
        await update.message.reply_text(
            '<b>Телеграм Клейм Бот!\n'
            'Чем могу помочь?</b>',
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove(),
        )

        # Определяем inline-кнопки для опций бота
        keyboard = [
            [InlineKeyboardButton('ВСЕ СТАТУСЫ', callback_data='status')],
            [InlineKeyboardButton('ВЫБРАТЬ ПРОЦЕСС', callback_data='process')],
            [InlineKeyboardButton('Помощь', callback_data='help')],
            [InlineKeyboardButton('Выход', callback_data='exit')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('<b>Пожалуйста, выберите:</b>', parse_mode='HTML', reply_markup=reply_markup)

        return COMMAND_DECISION

async def restart_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manage_process(update, context, "restart")

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manage_process(update, context, "stop")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запустить процесс по шаблону с помощью функции manage_process."""
    await manage_process(update, context, "start")

#region Уникальный процесс

async def select_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global stopped_processes, running_processes, inactive_directories

    await get_processes()

    """Выбрать процесс для запуска."""
    query = update.callback_query

    keyboard = []

    print("Остановленные процессы: " + ', '.join(stopped_processes))
    print("Запущенные процессы: " + ', '.join(running_processes))
    print("Неактивные директории: " + ', '.join(inactive_directories))

    for process in stopped_processes:
        keyboard.append([InlineKeyboardButton(process + u" 🔴", callback_data=process)])

    for process in running_processes:
        keyboard.append([InlineKeyboardButton(process + u" 🟢", callback_data=process)])

    for directory in inactive_directories:
        keyboard.append([InlineKeyboardButton(directory + u" ⚫", callback_data=directory)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text('<b>Выберите опцию:</b>', parse_mode='HTML', reply_markup=reply_markup)

    return PROCESS_DECISION

async def process_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global selected_process

    """Спрашивает пользователя о выборе команды."""
    query = update.callback_query
    await query.answer()
    selected_process = query.data

    # Определяем inline-кнопки для выбора действия
    keyboard = [
        [InlineKeyboardButton('СТАТУС', callback_data='status')],
        [InlineKeyboardButton('ЛОГИ', callback_data='logs')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text('<b>Пожалуйста, выберите:</b>', parse_mode='HTML', reply_markup=reply_markup)

    return PROCESS_COMMAND_DECISION

async def process_command_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор команды для процесса."""
    query = update.callback_query
    await query.answer()
    decision = query.data

    if decision == 'status':
        return await status_process(update, context)
    elif decision == 'logs':
        return await logs_process(update, context)
    else:
        await query.edit_message_text(f"Неверная команда: {decision}")
        return ConversationHandler.END

async def status_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправить сообщение со статусом процесса."""

    logs = get_status_logs_by_process_name(selected_process)
    await send_message(update, context, (f"{logs}." if logs != "" else f"Процесс {selected_process} не найден."))
    return ConversationHandler.END

async def logs_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправить сообщение с логами процесса."""

    logs = get_logs_by_process_name(selected_process)
    await send_message(update, context, (f"{logs}." if logs != "" else f"Процесс {selected_process} не найден."))
    return ConversationHandler.END

def find_index(lst, value):
    for i, v in enumerate(lst):
        if v == value:
            return i
    return -1

#endregion

#region Все процессы

async def status_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global stopped_processes, running_processes, inactive_directories

    await get_processes()

    for process in stopped_processes:
        if not should_exclude_process(process):
            await send_message(update, context, show_logs(process.strip()))

    for process in running_processes:
        if not should_exclude_process(process):
            await send_message(update, context, show_logs(process.strip()))

    for directory in inactive_directories:
        if not should_exclude_process(directory):
            await send_message(update, context, show_logs(directory.strip()))

    return ConversationHandler.END

def should_exclude_process(process_name):
    excluded_keywords = ["solver-tg-bot", "Telegram", "http-proxy", "Activating", "Initialising"]
    return any(keyword in process_name for keyword in excluded_keywords)

def show_logs(process) -> str:
    """Отправить сообщение со статусом процесса."""

    try:
        name, balance, profit_hour, next_claim_at, log_status = fetch_and_process_logs(process.strip())
        return f"{name}\n\tБАЛАНС: {balance}\n\tПРИБЫЛЬ/ЧАС: {profit_hour}\n\tСЛЕДУЮЩИЙ КЛЕЙМ В: {next_claim_at}\n\tСТАТУС ЛОГА:\n\t{log_status}"
    except Exception as e:
        print(f"Ошибка: {e}")
        return f"{process}: ОШИБКА при получении информации."

#endregion

#region Утилиты

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    """Отправить сообщение с помощью бота."""

    # Определяем правильный способ отправки ответа в зависимости от типа обновления
    if update.callback_query:
        # Если вызвано из callback query, используем сообщение callback_query
        chat_id = update.callback_query.message.chat_id
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        # Опционально можно подтвердить callback query
        await update.callback_query.answer()
    elif update.message:
        # Если вызвано из прямого сообщения
        await update.message.reply_text(text)
    else:
        # Обработка других случаев или логирование предупреждения
        logger.warning('skip_mileage был вызван без контекста message или callback_query.')

async def get_processes():
    global stopped_processes, running_processes, inactive_directories

    stopped_processes = list_pm2_processes("stopped")
    running_processes = list_pm2_processes("online")
    inactive_directories = get_inactive_directories()

#endregion

def main() -> None:
    token = load_telegram_token('variables.txt')
    if not token:
        sys.exit(1)

    if not os.path.exists("/usr/src/app/games/utils"):
        pull_games_dest = "/usr/src/app/pull-games.sh"

        # Проверяем, существует ли pull-games.sh
        if os.path.exists(pull_games_dest):
            # Изменяем скрипт pull-games.sh
            modify_pull_games_script(pull_games_dest)

            # Делаем скрипт исполняемым
            os.chmod(pull_games_dest, 0o755)

            # Запускаем скрипт pull-games.sh
            result = subprocess.run([pull_games_dest], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Не удалось выполнить {pull_games_dest}: {result.stderr}")
                sys.exit(1)
            else:
                print(f"Успешно выполнен {pull_games_dest}: {result.stdout}")
        else:
            print("pull-games.sh не найден, обновление пропущено.")

    list_pm2_processes = set(list_all_pm2_processes())

    if "Telegram-Bot" not in list_pm2_processes:
        script = "games/tg-bot.py"

        pm2_session = "Telegram-Bot"
        print(f"Вы можете добавить новую/обновленную сессию в PM с помощью: pm2 start {script} --interpreter venv/bin/python3 --name {pm2_session} -- {pm2_session}", 1)
        user_choice = input("Введите 'e' для выхода, 'a' или <Enter> для автоматического добавления в PM2: ").lower()

        if user_choice == "e":
            print("Выход из скрипта. Вы можете возобновить процесс позже.", 1)
            sys.exit()
        elif user_choice == "a" or not user_choice:
            start_pm2_app(script, pm2_session, pm2_session)
            user_choice = input("Сохранить процессы PM2? (Y/n): ").lower()
            if user_choice == "y" or not user_choice:
                save_pm2()
            print(f"Теперь вы можете смотреть логи сессии в PM2 с помощью: pm2 logs {pm2_session}", 2)
            sys.exit()

    run()

if __name__ == '__main__':
    main()